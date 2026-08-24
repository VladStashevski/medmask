from __future__ import annotations

from pathlib import Path

import pytest

from medmask import batch


def test_output_directory_is_safe_and_unique(tmp_path: Path) -> None:
    source = tmp_path / "Иванов Иван"
    source.mkdir()

    first = batch._new_output_dir(source)
    assert first == tmp_path / "Обезличенные"

    first.mkdir()
    second = batch._new_output_dir(source)
    assert second.parent == tmp_path
    assert second.name.startswith("Обезличенные_")
    assert "Иванов" not in second.name


def test_discovery_is_recursive_and_does_not_include_hidden_files(tmp_path: Path) -> None:
    nested = tmp_path / "вложенная"
    nested.mkdir()
    (nested / "карта.PDF").write_bytes(b"%PDF")
    (nested / "заметка.txt").write_text("текст", encoding="utf-8")
    (nested / "снимок.jpg").write_bytes(b"jpg")
    (tmp_path / ".скрытый.pdf").write_bytes(b"%PDF")

    files, skipped = batch.discover_files(tmp_path)

    assert [path.name for path in files] == ["заметка.txt", "карта.PDF"]
    assert skipped == {".jpg": 1}


def test_safe_report_contains_no_source_name_or_text_snippet(tmp_path: Path) -> None:
    secret_name = "Иванов Иван Иванович.pdf"
    secret_snippet = "Иванов Иван Иванович, телефон 89991234567"
    source = tmp_path / secret_name
    result = batch.FileResult(
        number=1,
        source_path=source,
        output_path=tmp_path / "document_0001.pdf",
        findings=[("ФИО", secret_snippet)],
    )

    report_path = batch.write_safe_report(tmp_path, [result], {".jpg": 2})
    report = report_path.read_text(encoding="utf-8-sig")

    assert secret_name not in report
    assert secret_snippet not in report
    assert "document_0001" in report
    assert ".jpg: 2" in report


def test_inn_is_masked() -> None:
    cleaned = batch.engine.depersonalize("ИНН: 123456789012")
    assert "123456789012" not in cleaned
    assert "[INN]" in cleaned


@pytest.mark.parametrize(
    "source",
    [
        "Номер медицинской карты: 123456789",
        "История болезни № A-123456",
        "Номер ИБ: 2026/12345",
        "№ карты\n123456789",
    ],
)
def test_medical_record_number_is_masked(source: str) -> None:
    cleaned = batch.engine.depersonalize(source)
    assert "123456" not in cleaned
    assert "[MEDICAL_RECORD]" in cleaned


def test_medical_record_label_is_preserved() -> None:
    cleaned = batch.engine.depersonalize("Номер медицинской карты: 123456789")
    assert cleaned == "Номер медицинской карты: [MEDICAL_RECORD]"


@pytest.mark.parametrize(
    "source",
    [
        "Врач: Петров Пётр Сергеевич",
        "Лечащий врач: Петров П.П.",
        "Врач:\nПетров",
    ],
)
def test_staff_name_is_masked_in_strict_mode(source: str) -> None:
    cleaned = batch.engine.depersonalize(source)
    assert "Петров" not in cleaned
    assert "[FIO]" in cleaned


@pytest.mark.parametrize(
    ("source", "tag"),
    [
        ("Телефон: +7 (999) 123-45-67", "[PHONE]"),
        ("СНИЛС 123-456-789 01", "[SNILS]"),
        ("Email: patient@example.org", "[EMAIL]"),
        ("Пациент: Иванов Иван Иванович", "[FIO]"),
        ("Адрес проживания: г. Москва, ул. Ленина, д. 1", "[ADDRESS]"),
    ],
)
def test_core_masks_common_identifiers(source: str, tag: str) -> None:
    assert tag in batch.engine.depersonalize(source)


def test_process_folder_creates_anonymized_pdf_and_keeps_source(tmp_path: Path) -> None:
    source_dir = tmp_path / "Исходные истории"
    source_dir.mkdir()
    source_file = source_dir / "Иванов Иван Иванович.txt"
    original = "\n".join(
        [
            "Пациент: Иванов Иван Иванович",
            "Дата рождения: 01.01.1980",
            "Телефон: +7 (999) 123-45-67",
            "ИНН: 123456789012",
            "Email: patient@example.org",
            "Адрес проживания: г. Москва, ул. Ленина, д. 1",
            "Диагноз: тестовая запись",
        ]
    )
    source_file.write_text(original, encoding="utf-8")

    result = batch.process_folder(source_dir)

    assert source_file.read_text(encoding="utf-8") == original
    assert result.output_dir == tmp_path / "Обезличенные"
    assert result.successful == 1
    assert [path.name for path in result.output_dir.glob("*.pdf")] == ["document_0001.pdf"]

    with batch.engine.fitz.open(result.output_dir / "document_0001.pdf") as document:
        output_text = "\n".join(page.get_text() for page in document).replace("\u00a0", " ")

    for secret in (
        "Иванов",
        "01.01.1980",
        "999",
        "123456789012",
        "patient@example.org",
        "Москва",
        "Ленина",
    ):
        assert secret not in output_text
    assert "Диагноз: тестовая запись" in output_text


def test_progress_moves_during_a_single_document(tmp_path: Path) -> None:
    source_dir = tmp_path / "Истории"
    source_dir.mkdir()
    (source_dir / "карта.txt").write_text(
        "Пациент: Иванов Иван Иванович\nДиагноз: тест",
        encoding="utf-8",
    )
    updates: list[batch.Progress] = []

    batch.process_folder(source_dir, on_progress=updates.append)

    assert updates
    assert updates[0].percent > 0
    assert any(update.stage == "Обезличивание текста" for update in updates)
    assert any(update.stage == "Создание нового PDF" for update in updates)
    assert any(update.stage == "Проверка результата" for update in updates)
    assert [update.percent for update in updates] == sorted(update.percent for update in updates)


def test_pdf_progress_reports_pages(tmp_path: Path) -> None:
    source_dir = tmp_path / "PDF"
    source_dir.mkdir()
    source_path = source_dir / "карта.pdf"
    with batch.engine.fitz.open() as document:
        for number in range(1, 4):
            page = document.new_page()
            page.insert_text((72, 72), f"Patient record page {number}")
        document.save(source_path)

    updates: list[batch.Progress] = []
    batch.process_folder(source_dir, on_progress=updates.append)

    page_updates = [
        update for update in updates if update.stage == "Извлечение и обезличивание"
    ]
    assert [update.detail for update in page_updates] == [
        "Страница 1 из 3",
        "Страница 2 из 3",
        "Страница 3 из 3",
    ]
