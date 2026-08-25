"""Регрессии по утечкам ПДн и по порче клинического текста.

Каждый тест воспроизводит дефект, найденный на реальных историях болезни.
"""

from __future__ import annotations

from datetime import date

import pytest

from medmask import depersonalizer as engine


def clean(text: str) -> str:
    """Полный проход: построчная чистка плюс финальное затирание повторов."""
    memory = engine.PIIMemory()
    return memory.sweep_fio(engine.depersonalize(text, memory))


# ---------- фамилии с буквой ё ----------

@pytest.mark.parametrize(
    "line",
    [
        "Заключение подписал Ковалёв А.С.",
        "Осмотрен врачом Соловьёв П.П.",
    ],
)
def test_surname_with_yo_is_recognized(line: str) -> None:
    assert "[FIO]" in clean(line)


def test_yo_surname_is_a_strong_name_token() -> None:
    assert engine._is_strong_name_token("Ковалёв")
    assert engine._is_strong_name_token("Королёва")


# ---------- название отделения не равно специальности врача ----------

def test_department_name_is_not_doctor_context() -> None:
    assert not engine.is_doctor_line("Неврология   Иванов Иван Иванович")
    assert not engine.is_doctor_line("Хирургическое   Смирнов Олег Петрович")
    assert not engine.is_doctor_line("Реанимация   Ковалёв Артём Сергеевич")


def test_specialty_of_a_person_is_still_doctor_context() -> None:
    assert engine.is_doctor_line("Невролог Петров П.П.")
    assert engine.is_doctor_line("Осмотр невролога Петрова П.П.")
    assert engine.is_doctor_line("Лечащий врач: Петров П.П.")


# ---------- подпись врача целиком ----------

@pytest.mark.parametrize(
    "line",
    [
        "Лечащий врач: Петров П.П.",
        "Врач: Петров П. П.",
        "Заведующий отделением: Петров П.П.",
    ],
)
def test_staff_initials_are_masked_without_tail(line: str) -> None:
    result = clean(line)
    assert "[FIO]" in result
    assert "П." not in result


def test_staff_role_word_survives_masking() -> None:
    result = clean("Врач-невролог Сидорова М.И.")
    assert result.startswith("Врач-невролог")
    assert "Сидорова" not in result
    assert "И." not in result


# ---------- дата рождения в табличной строке ----------

def test_birth_date_next_to_name_becomes_age() -> None:
    result = clean("Неврология   Ковалёв Артём Сергеевич   14.03.1968")
    assert "14.03.1968" not in result
    assert "лет" in result or "год" in result


def test_recent_examination_date_is_not_treated_as_birth_date() -> None:
    this_year = date.today().year
    result = clean(f"Осмотр провел Петров П.П.   12.05.{this_year}")
    assert f"12.05.{this_year}" in result


# ---------- клинический текст не портится ----------

CLINICAL_LINES = [
    "Повторный ишемический инсульт в бассейне левой СМА.",
    "Температура тела 36.6, состояние средней тяжести.",
    "Окончание курса антибактериальной терапии.",
    "Уважаемый коллега, направляем выписку.",
]


@pytest.mark.parametrize("line", CLINICAL_LINES)
def test_common_words_are_not_swept_as_names(line: str) -> None:
    memory = engine.PIIMemory()
    for word in ("Повторный", "Температура", "Окончание", "Уважаемый", "Кисель", "Истории"):
        memory.add_fio(word)
        memory.add_fio_strict(word)
    assert memory.sweep_fio(line) == line


def test_word_after_a_name_does_not_become_a_global_name() -> None:
    memory = engine.PIIMemory()
    memory.sweep_fio("Пациент [FIO] Температура 36.6")
    assert memory.sweep_fio("Температура тела нормальная.") == "Температура тела нормальная."


def test_known_surname_is_still_swept_everywhere() -> None:
    memory = engine.PIIMemory()
    first = memory.sweep_fio(engine.depersonalize("Пациент: Ковалёв Артём Сергеевич", memory))
    assert "[FIO]" in first
    assert "Ковалёв" not in memory.sweep_fio("Согласовано с Ковалёвым.")


# ---------- находки на реальной истории болезни ----------

def test_label_glued_to_an_uppercase_name_is_masked() -> None:
    """В выгрузке МИС метка и значение слипаются: «Ф.И.О. пациентаСОКОЛОВА»."""
    result = clean("Ф.И.О. пациентаСОКОЛОВА АННА ПЕТРОВНА")
    assert "СОКОЛОВА" not in result
    assert "АЛЕКСАНДРА" not in result


@pytest.mark.parametrize(
    "line",
    [
        "Ф.И.О возраст: Соколова А. И. (ж) (05.09.1947 / 79 лет)",
        "Пациент: Иванов Иван Иванович (м) (05.09.1947, 79 лет)",
        "№ Истории: 1010/2026 DS. Кома. Ф.И.О возраст: [FIO] (ж) (05.09.1947 / 79 лет)",
    ],
)
def test_birth_date_next_to_explicit_age_disappears(line: str) -> None:
    assert "05.09.1947" not in clean(line)


def test_age_survives_when_the_line_is_not_swallowed_by_a_label() -> None:
    result = clean("Пациент: Иванов Иван Иванович (м) (05.09.1947, 79 лет)")
    assert "79 лет" in result


def test_date_that_does_not_match_the_age_is_left_alone() -> None:
    """Дата осмотра рядом с числом лет не превращается в возраст."""
    line = "Пациент [FIO]: перелом получен 12.05.2020, стаж курения 30 лет."
    assert "12.05.2020" in clean(line)


def test_bare_birth_year_left_by_a_form_is_masked() -> None:
    memory = engine.PIIMemory()
    text = "Дата рождения: 05.09.1947\nМесто получения травмы: другое (указать) 1947"
    result = memory.sweep_fio(engine.depersonalize(text, memory))
    assert "1947" not in result


def test_year_unrelated_to_the_birth_date_survives() -> None:
    memory = engine.PIIMemory()
    text = "Дата рождения: 05.09.1947\nОперация выполнена в 2019 году."
    result = memory.sweep_fio(engine.depersonalize(text, memory))
    assert "2019 году" in result


@pytest.mark.parametrize(
    "line, surname",
    [
        ("Совместный осмотр зам. гл. врача Дубровиной А.Н., зав.РАО1 Ветровой Е.Е.", "Ветровой"),
        ("В составе заведующего отделением для больных с ОНМК Ольховской Е.В., врача", "Ольховской"),
        ("Панько С.В. - заведующий пульмонологическим отделением", "Панько"),
        ("Гнатюк М.А– врач анестезиолог-реаниматолог", "Гнатюк"),
        ("Подпись медсестры Юнусова У.Я Арутюнян З.Л.", "Юнусова"),
        ("[FIO], клинического фармаколога [FIO], диетолога Соловьёвой Т.Ю.", "Соловьёвой"),
        ("ОНМК [FIO], деж. реаниматолога Хабировой И.С.", "Хабировой"),
        ("медицинского психолога Гайнуллиной К.Г., логопеда [FIO]", "Гайнуллиной"),
        ("Подпись врача [FIO] С.Е Белогорцев", "Белогорцев"),
        ("Подпись медсестры Юнусова УАрутюнян З.Л.", "Арутюнян"),
    ],
)
def test_staff_surname_in_an_oblique_case_is_masked(line: str, surname: str) -> None:
    """ФИО медработника — тоже ПДн, а падежные формы в SURNAME_SUFFIX не входят."""
    assert surname not in clean(line)


@pytest.mark.parametrize(
    "line",
    [
        "Осмотр в динамике: состояние больной тяжелое, левой рукой движения сохранены.",
        "Врач осмотрел: тонус мышц в левой руке снижен, реакция живая.",
    ],
)
def test_clinical_words_shaped_like_oblique_surnames_survive(line: str) -> None:
    assert clean(line) == line


def test_surname_before_masked_initials_is_removed() -> None:
    memory = engine.PIIMemory()
    line = "Подпись заведующего отделением ВЕТРОВА [FIO]"
    assert "ВЕТРОВА" not in memory.sweep_fio(line)


@pytest.mark.parametrize(
    "line",
    [
        "Подпись медсестры [FIO]",
        "Лечащий врач [FIO]",
        "Диагноз [FIO]",
    ],
)
def test_role_word_before_a_mask_is_kept(line: str) -> None:
    assert engine.PIIMemory().sweep_fio(line) == line


# ---------- сводный документ ----------

DOCUMENT = """БУ «Областная клиническая больница»
Неврологическое отделение

Медицинская карта № 1234-2026
Неврология   Ковалёв Артём Сергеевич   14.03.1968
Пациент Ковалёв А.С., 58 лет
Адрес: г. Сургут, ул. Ленина, д. 12, кв. 5
Телефон: +7 912 345-67-89
СНИЛС 123-456-789 01

Осмотр невролога   Ковалёв Артём Сергеевич
Лечащий врач: Петров П.П.
Врач-невролог Сидорова М.И.

Диагноз: повторный ишемический инсульт в бассейне левой СМА.
Температура тела 36.6. Состояние средней тяжести.
Согласовано с Ковалёвым.
"""

LEAKING_VALUES = [
    "Ковалёв", "Ковалёвым", "Артём", "Сергеевич", "Петров", "Сидорова",
    "14.03.1968", "Ленина", "912", "123-456-789",
]


@pytest.mark.parametrize("value", LEAKING_VALUES)
def test_document_keeps_no_personal_data(value: str) -> None:
    assert value not in clean(DOCUMENT)


@pytest.mark.parametrize(
    "phrase",
    [
        "повторный ишемический инсульт",
        "Температура тела",
        "Неврологическое отделение",
        "Врач-невролог",
    ],
)
def test_document_keeps_clinical_text(phrase: str) -> None:
    assert phrase in clean(DOCUMENT)
