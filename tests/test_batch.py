from __future__ import annotations

import threading
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

    assert [path.name for path in files] == ["заметка.txt", "карта.PDF", "снимок.jpg"]
    assert skipped == {}


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
        "МЕДИЦИНСКАЯ КАРТА пациента № 11128/2026",
        "МЕДИЦИНСКАЯ КАРТА ПАЦИЕНТА,\n№ 1112/2026",
    ],
)
def test_medical_record_in_header_is_masked(source: str) -> None:
    cleaned = batch.engine.depersonalize(source)
    assert "1112" not in cleaned
    assert "[MEDICAL_RECORD]" in cleaned


def test_known_dob_and_record_are_swept_from_repeated_table_values() -> None:
    source = "\n".join(
        [
            "Дата рождения: 01.02.1980",
            "Повтор значения 01.02.1980",
            "Номер медицинской карты: 11128/2026",
            "Повтор № 11128/2026",
        ]
    )
    cleaned = batch.engine.depersonalize(source)

    assert "01.02.1980" not in cleaned
    assert "11128/2026" not in cleaned
    assert "[MEDICAL_RECORD]" in cleaned


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
    "source",
    [
        "Исполнитель: Петров Пётр Сергеевич",
        "Владелец:\nПетров Пётр Сергеевич",
        "Комментарий подтвердил: Петров П.П.",
    ],
)
def test_extended_staff_labels_are_masked(source: str) -> None:
    cleaned = batch.engine.depersonalize(source)
    assert "Петров" not in cleaned
    assert "[FIO]" in cleaned


def test_electronic_signature_certificate_is_masked() -> None:
    source = "Сертификат: 26 0A30 3987 1FB3 39A1 70B0 394B 4BF6 8BE5"
    cleaned = batch.engine.depersonalize(source)

    assert "0A30" not in cleaned
    assert "[CERTIFICATE]" in cleaned


def test_patient_name_is_masked_inside_laboratory_block() -> None:
    source = "\n".join(
        [
            "Наименование Результат Ед. изм. Комментарий подтвердил",
            "Фамилия, имя, отчество пациента: Иванов Иван Иванович",
        ]
    )
    cleaned = batch.engine.depersonalize(source)

    assert "Иванов" not in cleaned
    assert "[FIO]" in cleaned


def test_ocr_name_without_colon_or_capitalization_is_masked() -> None:
    source = "2026-04-12 05:44 Имя иванова Возраст: 67 Пол: женский"
    cleaned = batch.engine.depersonalize(source)

    assert "иванова" not in cleaned.lower()
    assert "[FIO]" in cleaned


@pytest.mark.parametrize(
    "source",
    [
        "ИВАНОВА\nМАРИЯ ПЕТРОВНА",
        "Иванова Мария\nПетровна",
    ],
)
def test_name_split_by_line_break_is_masked(source: str) -> None:
    cleaned = batch.engine.depersonalize(source)

    assert "Иванов" not in cleaned
    assert "Петровн" not in cleaned
    assert "[FIO]" in cleaned


def test_ocr_header_name_and_short_birth_date_are_masked() -> None:
    source = "САВВА НИКОЛАЙ ВАСИЛЬЕВИ 03.10.41 / 64 ГОДА"
    cleaned = batch.engine.depersonalize(source)

    assert "САВВА" not in cleaned
    assert "НИКОЛАЙ" not in cleaned
    assert "03.10.41" not in cleaned
    assert "64 ГОДА" in cleaned
    assert "[FIO]" in cleaned


def test_short_birth_date_after_fio_period_is_masked() -> None:
    memory = batch.engine.PIIMemory()
    cleaned = memory.sweep_fio("[FIO]. 03.10.41 год")

    assert "03.10.41" not in cleaned
    assert "[AGE]" in cleaned


def test_patient_name_from_parent_folder_masks_ocr_truncated_name() -> None:
    memory = batch.engine.PIIMemory()
    memory.seed_from_source_path("/tmp/11128-2026_ИВАНОВА_АИ/скан.pdf")

    cleaned = batch.engine.depersonalize(
        "ИВАНОВА АЛЬМИРА РИФОВ-",
        mem=memory,
    )

    assert "ИВАНОВА" not in cleaned
    assert "АЛЬМИРА" not in cleaned
    assert "РИФОВ" not in cleaned
    assert "[FIO]" in cleaned


def test_lab_table_row_is_not_mistaken_for_medical_record_number() -> None:
    source = "\n".join(
        [
            "Иммунологические исследования",
            "№ Наименование Результат Ед. изм Норма",
            "1 Антитела к HIV 1 и 2 и HIV1 p24, обнаружение в сыворотке крови Отрицательно лот 8322 от 19.06.2026",
        ]
    )

    cleaned = batch.engine.depersonalize(source)

    assert "Антитела к HIV" in cleaned
    assert "Отрицательно" in cleaned
    assert "№ [MEDICAL_RECORD]" not in cleaned


def test_lab_comment_is_not_mistaken_for_name_or_address() -> None:
    source = "\n".join(
        [
            "Наименование Результат Ед. изм. Норма",
            "Антитела к HIV 1 и 2 Отрицательно",
            "Комментарий: КОМБИ БЕСТ ВИЧ ИФА с.2025г. до 16.12.2026г.",
        ]
    )

    cleaned = batch.engine.depersonalize(source)

    assert "КОМБИ БЕСТ ВИЧ" in cleaned
    assert "[FIO]" not in cleaned
    assert "[ADDRESS]" not in cleaned


def test_lab_acronym_is_not_reported_as_residual_fio(tmp_path: Path) -> None:
    output = tmp_path / "lab.pdf"
    text = "Комментарий: КОМБИ БЕСТ ВИЧ ИФА"
    document = batch.engine.render_text_pdf(
        [text],
        [batch.engine.fitz.Rect(0, 0, *batch.engine.A4_RECT_WH)],
    )
    assert document is not None
    document.save(output)
    document.close()

    findings = batch.engine.audit_pdf(str(output))

    assert not any(kind.startswith("ФИО") for kind, _ in findings)


def test_composite_sex_age_birth_date_keeps_age_only() -> None:
    cleaned = batch.engine.depersonalize(
        "Пол/возраст: Женский/68/05.08.1957"
    )

    assert "05.08.1957" not in cleaned
    assert "68 лет" in cleaned


def test_generic_identifier_is_masked() -> None:
    cleaned = batch.engine.depersonalize("Идентификатор: 260500151276")

    assert "260500151276" not in cleaned
    assert "[IDENTIFIER]" in cleaned


def test_ocr_spaced_phone_is_masked() -> None:
    cleaned = batch.engine.depersonalize("A +9 998 300 1500")

    assert "998 300 1500" not in cleaned
    assert "[PHONE]" in cleaned


def test_year_followed_by_new_sentence_is_not_birth_year() -> None:
    source = "Дата поступления 06.02.2026г. Расчет нутритивной потребности"

    cleaned = batch.engine.depersonalize(source)

    assert "2026г. Расчет" in cleaned
    assert "лет" not in cleaned


@pytest.mark.parametrize(
    "source",
    [
        "пациент способен выполнить свои обычные обязанности",
        "Ф.И.О. полностью",
    ],
)
def test_fio_audit_does_not_mask_form_labels_or_clinical_sentence(source: str) -> None:
    cleaned = batch.engine.depersonalize(source)

    assert "[FIO]" not in cleaned
    assert cleaned == source


def test_empty_fio_form_label_is_not_reported_as_name() -> None:
    cleaned = batch.engine.depersonalize("ФИО больного")

    assert not batch.engine.ocr_fio_label_re.search(cleaned)


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


def test_cancellation_removes_partial_output_and_keeps_source(tmp_path: Path) -> None:
    source_dir = tmp_path / "Истории"
    source_dir.mkdir()
    source_file = source_dir / "карта.txt"
    original = "Пациент: Иванов Иван Иванович\nДиагноз: тест"
    source_file.write_text(original, encoding="utf-8")
    cancelled = threading.Event()

    def update(progress: batch.Progress) -> None:
        if progress.stage == "Обезличивание текста":
            cancelled.set()

    with pytest.raises(batch.BatchCancelled):
        batch.process_folder(
            source_dir,
            on_progress=update,
            is_cancelled=cancelled.is_set,
        )

    assert source_file.read_text(encoding="utf-8") == original
    assert not (tmp_path / batch.OUTPUT_FOLDER_NAME).exists()


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


def test_scanned_pdf_uses_ocr_and_reports_page(monkeypatch, tmp_path: Path) -> None:
    source_dir = tmp_path / "Сканы"
    source_dir.mkdir()
    source_path = source_dir / "скан.pdf"
    # Формируем PDF-скан, но само распознавание подменяем стабильным результатом.
    with batch.engine.fitz.open() as document:
        page = document.new_page()
        pixmap = batch.engine.fitz.Pixmap(
            batch.engine.fitz.csRGB,
            batch.engine.fitz.IRect(0, 0, 20, 20),
            False,
        )
        pixmap.clear_with(255)
        page.insert_image(page.rect, pixmap=pixmap)
        document.save(source_path)

    recognized = batch.engine.local_ocr.OCRResult(
        text="Пациент: Иванов Иван Иванович\nДиагноз: тест",
        confidence=0.92,
        line_count=2,
    )
    monkeypatch.setattr(batch.engine, "_ocr_page", lambda page: recognized)

    result = batch.process_folder(source_dir)

    assert result.successful == 1
    assert result.files[0].ocr_pages == [1]
    assert result.files[0].scan_pages == []
    with batch.engine.fitz.open(result.files[0].output_path) as document:
        output_text = "\n".join(page.get_text() for page in document)
    assert "Иванов" not in output_text
    assert "[FIO]" in output_text


def test_ocr_assets_are_present_and_valid() -> None:
    batch.engine.local_ocr.verify_assets()
