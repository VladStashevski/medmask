"""Обезличивание медицинских карт: PDF -> PDF (текст внутри деперсонализируется).

Конвейер для PDF:
  1) извлекаем текст постранично в порядке чтения (page.get_text(sort=True));
  2) склеиваем искусственные переносы вёрстки МИС-выгрузки (reflow);
  3) прогоняем через движок деперсонализации (регексы ФИО/адрес/ДР/СНИЛС/паспорт/
     телефон/полис/ИНН/почта + контекст врача) и доп. сети безопасности;
  4) рендерим СВЕЖИЙ PDF из чистого текста.

Полная пересборка из текста — самая надёжная защита: в выходной PDF не попадают
исходные метаданные, аннотации, формы, скрытый/белый текст, картинки (которые могут
содержать ФИО/печати/подписи). Страницы без извлекаемого текста (сканы) помечаются
заглушкой и попадают в отчёт _ОТЧЁТ_audit.txt для ручной проверки.

Не-PDF форматы (docx/rtf/odt/odg/xlsx/txt) читаются и тоже сохраняются как обезличенный PDF.
"""
import os
import re
import sys
import glob
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, date
import hashlib
import unicodedata

import chardet
import docx2txt
from striprtf.striprtf import rtf_to_text
from tqdm import tqdm

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None

try:
    import openpyxl  # чтение xlsx/xlsm
except ImportError:
    openpyxl = None


INPUT_DIR = "Карты"
OUTPUT_DIR = "Карты_clean"


# ==================== ЧТЕНИЕ ФАЙЛОВ ====================

def read_txt(path: str) -> str:
    with open(path, "rb") as f:
        data = f.read()
    enc = chardet.detect(data).get("encoding") or "utf-8"
    return data.decode(enc, errors="ignore")


def read_docx(path: str) -> str:
    return docx2txt.process(path) or ""


def read_rtf(path: str) -> str:
    with open(path, "rb") as f:
        data = f.read()
    enc = chardet.detect(data).get("encoding") or "utf-8"
    return rtf_to_text(data.decode(enc, errors="ignore"))


def read_odt(path: str) -> str:
    with zipfile.ZipFile(path, "r") as z:
        data = z.read("content.xml")
    root = ET.fromstring(data)
    ns = {"text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0"}
    paragraphs = ["".join(p.itertext()) for p in root.findall(".//text:p", ns)]
    return "\n".join(paragraphs)


# ---------- ODG (LibreOffice Draw) ----------
_ODG_NS = {
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
}
_SVG_X_ATTR = "{urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0}x"
_SVG_Y_ATTR = "{urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0}y"
_SVG_UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4 / 72, "pc": 25.4 / 6, "px": 25.4 / 96}
_svg_len_re = re.compile(r"^\s*(-?[\d.]+)\s*([a-z%]*)\s*$", re.IGNORECASE)


def _svg_len_to_mm(value: str | None) -> float:
    if not value:
        return 0.0
    m = _svg_len_re.match(value)
    if not m:
        return 0.0
    return float(m.group(1)) * _SVG_UNIT_TO_MM.get(m.group(2).lower(), 1.0)


def read_odg(path: str) -> str:
    with zipfile.ZipFile(path, "r") as z:
        data = z.read("content.xml")
    root = ET.fromstring(data)

    pages = root.findall(".//draw:page", _ODG_NS)
    if not pages:
        paragraphs = ["".join(p.itertext()) for p in root.findall(".//text:p", _ODG_NS)]
        return "\n".join(paragraphs)

    pages_text = []
    for page in pages:
        shapes = [el for el in page if _SVG_X_ATTR in el.attrib or _SVG_Y_ATTR in el.attrib]
        if not shapes:
            shapes = list(page)
        shapes.sort(key=lambda el: (
            _svg_len_to_mm(el.get(_SVG_Y_ATTR)),
            _svg_len_to_mm(el.get(_SVG_X_ATTR)),
        ))
        paragraphs = [
            "".join(p.itertext())
            for shape in shapes
            for p in shape.findall(".//text:p", _ODG_NS)
        ]
        pages_text.append("\n".join(paragraphs))
    return "\n\n".join(pages_text)


def _xlsx_cell_to_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    return str(value)


_XLSX_CELL_SEP = "    "


def read_xlsx(path: str) -> str:
    if openpyxl is None:
        raise RuntimeError("Для xlsx нужен openpyxl. Установите: pip install openpyxl")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        lines = []
        multi = len(wb.worksheets) > 1
        for ws in wb.worksheets:
            if multi:
                lines.append(f"=== Лист: {ws.title} ===")
            for row in ws.iter_rows(values_only=True):
                cells = [_xlsx_cell_to_str(c) for c in row]
                while cells and cells[-1] == "":
                    cells.pop()
                lines.append(_XLSX_CELL_SEP.join(cells))
        return "\n".join(lines)
    finally:
        wb.close()


READERS = {
    ".txt": read_txt,
    ".docx": read_docx,
    ".rtf": read_rtf,
    ".odt": read_odt,
    ".odg": read_odg,
    ".xlsx": read_xlsx,
    ".xlsm": read_xlsx,
}


# ==================== НОРМАЛИЗАЦИЯ / ХЕЛПЕРЫ ====================

def norm(s: str) -> str:
    return (
        s.replace("\u00A0", " ")
         .replace("\u202F", " ")
         .replace("\u2007", " ")
         .replace("\u2009", " ")
         .replace("\u200A", " ")
         .replace("\u00AD", "-")
         .replace("\u200B", "")
         .replace("\u200C", "")
         .replace("\u200D", "")
         .replace("\uFEFF", "")
         .replace("\u2010", "-")
         .replace("\u2011", "-")
         .replace("\u2012", "-")
         .replace("\u2212", "-")
    )


def _line_ending(s: str) -> str:
    if s.endswith("\r\n"):
        return "\r\n"
    if s.endswith("\n"):
        return "\n"
    return ""


def sanitize_for_windows(text: str) -> str:
    text = text.replace("\u0085", "\n").replace("\u2028", "\n").replace("\u2029", "\n")
    trans = {c: None for c in range(0x00, 0x20) if c not in (0x09, 0x0A, 0x0D)}
    text = text.translate(trans)
    return unicodedata.normalize("NFC", text)


def age_phrase(age) -> str:
    """«41 год», «42 года», «45 лет» — вместо неизменного «лет»."""
    if age == "[AGE]" or not str(age).isdigit():
        return "[AGE]"
    n = int(age)
    r100, r10 = n % 100, n % 10
    if 11 <= r100 <= 14 or r10 == 0 or r10 >= 5:
        unit = "лет"
    elif r10 == 1:
        unit = "год"
    else:
        unit = "года"
    return f"{n} {unit}"


def calc_age_from_str(dob_str: str, ref_date: date = None) -> str:
    if ref_date is None:
        ref_date = date.today()
    try:
        dob = datetime.strptime(dob_str, "%d.%m.%Y").date()
    except ValueError:
        return "[AGE]"
    age = ref_date.year - dob.year - ((ref_date.month, ref_date.day) < (dob.month, dob.day))
    if age < 0 or age > 150:
        return "[AGE]"
    return str(age)


def _normline(s: str) -> str:
    return re.sub(r"\s+", " ", norm(s)).strip().lower()


def letters_only(s: str) -> str:
    return re.sub(r"[^a-zа-яё]+", "", s.lower())


def digits_count(s: str) -> int:
    return len(re.sub(r"\D", "", s))


# ==================== РЕГЕКСЫ ====================

email_re = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
phone_re = re.compile(r"(?<!\w)(?:\+7|7|8)?[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2}(?!\w)")
intl_phone_re = re.compile(r"(?<![\w])\+\d(?:[\s\-().]*\d){8,14}(?!\w)")
snils_re = re.compile(r"(?<!\d)\d{3}[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{2}(?!\d)")

# СТРОГАЯ форма телефона. Применяется ВНЕ явного телефонного контекста.
# phone_re ловит ЛЮБЫЕ 10 цифр подряд и поэтому превращал в [PHONE] номера
# рецептурных бланков и назначений («Б/Р №2000230409»). Строгая форма требует
# либо междугородний префикс 8/7/+7 и 10 цифр после него, либо мобильный 9xx.
strict_phone_re = re.compile(
    r"(?<!\w)(?:"
    r"(?:\+7|8|7)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2}"
    r"|9\d{2}[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2}"
    r")(?!\w)"
)

inn_labeled_re = re.compile(r"(\bинн\b\s*[:\-]?\s*)\d{10,12}", re.IGNORECASE)
policy_labeled_re = re.compile(r"(\b(?:полис|полиса)\b[^\d]{0,60})\d{8,25}", re.IGNORECASE)
policy_number_re = re.compile(r"(№\s*медицинского\s+страхового\s+полиса\s+)\d+", re.IGNORECASE)
policy_issue_date_re = re.compile(r"(?i)(дата\s+выдачи\s+полиса[^:\n]*:\s*)[^\n]+")

# ---------- Лист нетрудоспособности ----------
sick_leave_labeled_re = re.compile(
    r"(?i)(лист(?:ок|ка|а)?\s+нетрудоспособности\b[^\d]{0,60}(?:№|номер)\s*[:\-]?\s*)(\d{4,})"
)

# Контекст «дата выдачи полиса» — используется для поимки СЛЕДУЮЩЕЙ (сирой) даты,
# которая при извлечении из Word/ODT ячейки таблицы падает на отдельную строку.
policy_issue_date_ctx_re = re.compile(r"(?i)дата\s+выдачи\s+полис")

# «Голая» дата на отдельной строке (цифрами или с текстовым месяцем) — нужна для
# затирания сирота-даты, которая осталась после метки «дата выдачи полиса…».
_MONTH_WORD_ALT = (
    r"январ[ья]|феврал[ья]|март[а]?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|"
    r"август[а]?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья]"
)
_orphan_bare_date_line_re = re.compile(
    rf"(?i)^\s*(?:\d{{1,2}}[.\-/]\d{{1,2}}[.\-/]\d{{2,4}}"
    rf"|\d{{1,2}}\s+(?:{_MONTH_WORD_ALT})\s+\d{{4}}"
    rf"(?:\s*(?:г\.?|год[а]?))?)\s*$"
)

# То же самое, но дата стоит в НАЧАЛЕ строки, а дальше сразу (без переноса) идёт
# текст следующего поля — reflow склеивает сирота-дату со строкой «данные о
# страховой мед. организации…», из-за чего _orphan_bare_date_line_re не срабатывает.
_orphan_leading_date_re = re.compile(
    rf"(?i)^(\s*)(\d{{1,2}}[.\-/]\d{{1,2}}[.\-/]\d{{2,4}}"
    rf"|\d{{1,2}}\s+(?:{_MONTH_WORD_ALT})\s+\d{{4}}"
    rf"(?:\s*(?:г\.?|год[а]?))?)(\s+\S.*)?$"
)

# ---------- Паспорт ----------
passport_num_re = re.compile(r"(?<!\d)\d{2}\s?\d{2}\s?\d{6}(?!\d)")
passport_series_inline_re = re.compile(r"(?i)(\bсерия\b\s*[:\-]?\s*)(\d{2}\s*\d{2})")
passport_series_only_re = re.compile(r"(?i)^\s*серия\s*[:\-]?\s*$")
passport_number_only_re = re.compile(r"(?i)^\s*(?:№|no\.?|номер)\s*[:\-]?\s*$")
passport_context_line_re = re.compile(
    r"(?i)\b(паспорт|документ\W*удостоверяющий\W*личность|серия)\b"
)
passport_number_inline_in_context_re = re.compile(
    r"(?i)(\b(?:паспорт|документ\W*удостоверяющий\W*личность|серия)\b[^\n]*?(?:№|\bno\.?|\bномер\b)\s*[:\-]?\s*)(\d{4,10})"
)

# ---------- Карта ----------
card_no_label_only_re = re.compile(r"(?i)^\s*(?:№|номер)\s*карты\b\s*[:\-]?\s*$")
card_label_inline_re = re.compile(
    r"(?i)(?:\bмедицинск\w*\s+карт\w*[^\n]*?(?:№|номер)|(?:№|номер)[^\n]*?\bмедицинск\w*\s+карт\w*)"
)
medical_record_inline_re = re.compile(
    r"(?i)("
    r"(?:№|номер)?\s*"
    r"(?:медицинск\w*\s+)?карт\w*"
    r"|(?:№|номер)?\s*истори[ия]\s+болезни"
    r"|номер\s+иб|\bиб"
    r")"
    r"(\s*[:№\-]?\s*)"
    r"(?=[A-ZА-ЯЁ0-9/._\-]*\d)"
    r"[A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9/._\-]{2,}"
)

# Слова, после которых «Номер X» — НЕ номер карты пациента.
_NOT_CARD_NUMBER_LABELS_RE = re.compile(
    r"(?i)^\s*номер\s+(?:телефона|телефонов|"
    r"образца|образцов|направления|направлений|протокола|протоколов|"
    r"пробы|проб|анализа|анализов|заказа|заказов|"
    r"полиса|снилс|паспорта|документа|"
    r"истории|страхового|страхования)\b"
)

# ---------- Простые однострочные теги ----------
snils_tag_re = re.compile(r"^\s*(?:\d+\s*[.)]\s*)?снилс\b\s*[:\-]?\s*$", re.IGNORECASE)

# ---------- АДРЕСНЫЕ МЕТКИ ----------
ADDRESS_LABEL_BODY = (
    r"(?:"
        r"адрес(?!\s+(?:электронн\w+|эл\.))(?:\s+[а-яё]+){0,5}"
        r"|по\s+адресу"
        r"|место\s+(?:жительств\w*|регистрации|прожив\w*|пребывани\w*)"
        r"|регистрация\s+по\s+месту\s+(?:жительств\w*|пребывани\w*)"
        r"|прописка(?:\s+[а-яё]+){0,3}"
        r"|домашн\w+\s+адрес"
        r"|фактическ\w+\s+адрес(?:\s+[а-яё]+){0,3}"
    r")"
)
ADDRESS_LABEL_RE = re.compile(
    rf"(?i)^\s*(?:\d+\s*[.)]\s*)?{ADDRESS_LABEL_BODY}\s*[:\-]?\s*$"
)
ADDRESS_LABEL_INLINE_RE = re.compile(
    rf"(?i)^(\s*(?:\d+\s*[.)]\s*)?{ADDRESS_LABEL_BODY}\s*[:\-]\s*)(\S.+)$"
)
MIDLINE_ADDR_RE = re.compile(
    rf"(?i)({ADDRESS_LABEL_BODY}\s*[:\-]\s*)\S[^\n]*"
)
ADDRESS_LABEL_NOPUNCT_INLINE_RE = re.compile(
    rf"(?i)^(\s*\d+\s*[.)]\s*{ADDRESS_LABEL_BODY})[ \t]+"
    rf"(?!(?:{ADDRESS_LABEL_BODY})\b)"
    r"(\S.*?)"
    r"(?=[ \t]+(?:тел\.?|телефон\w*|моб\.?|сот\.?|№)\b|[ \t]+\d+\s*[.)]|\s*$)"
)

lives_in_inline_re = re.compile(r"(?i)\bпрожива\w+\b\s+(?:в|во|по\s+адресу)\b[^\r\n]*")

# ---------- МЕСТО РАБОТЫ / ДОЛЖНОСТЬ ----------
workplace_label_only_re = re.compile(
    r"(?i)^\s*(?:\d+\s*[.)]\s*)?место\s+работы\b(?:\s*[,/]?\s*должность\b)?\s*[:\-]?\s*$"
)
position_label_only_re = re.compile(r"(?i)^\s*(?:\d+\s*[.)]\s*)?должность\b\s*[:\-]?\s*$")
workplace_inline_re = re.compile(
    r"(?i)^(\s*(?:\d+\s*[.)]\s*)?место\s+работы\b(?:\s*[,/]?\s*должность\b)?\s*[:\-]?\s*)(\S.+?)\s*$"
)
position_inline_re = re.compile(r"(?i)^(\s*(?:\d+\s*[.)]\s*)?должность\s*[:\-]?\s*)(\S.+?)\s*$")

# ---------- ДР/возраст ----------
dob_tag_re = re.compile(r"^\s*(?:\d+\s*[.)]\s*)?дата\s*рождения\b\s*[:\-]?\s*$", re.IGNORECASE)
dob_age_tag_re = re.compile(r"^\s*(?:\d+\s*[.)]\s*)?дата\s*рождения\s*,\s*возраст\b\s*[:\-]?\s*$", re.IGNORECASE)
age_tag_re = re.compile(r"^\s*(?:\d+\s*[.)]\s*)?(?:возраст|лет)\b\s*[:\-]?\s*$", re.IGNORECASE)
age_label_inline_re = re.compile(r"(?i)^(\s*(?:\d+\s*[.)]\s*)?возраст\s*[:\-]\s*)(.+)$")

flex_date_re = re.compile(r"(?<!\d)(\d{1,2})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{4})(?!\d)")
month_word_date_re = re.compile(
    r"(?i)\b(\d{1,2})\s+("
    r"январ[ья]|феврал[ья]|март|марта|апрел[ья]|май|мая|июн[ья]|июл[ья]|август|августа|"
    r"сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья]"
    r")\s+(\d{4})(?:\s*(?:г\.?|год[а]?))?\b"
)
MONTH_MAP = {
    "января": 1, "январь": 1, "февраля": 2, "февраль": 2, "марта": 3, "март": 3,
    "апреля": 4, "апрель": 4, "мая": 5, "май": 5, "июня": 6, "июнь": 6,
    "июля": 7, "июль": 7, "августа": 8, "август": 8, "сентября": 9, "сентябрь": 9,
    "октября": 10, "октябрь": 10, "ноября": 11, "ноябрь": 11, "декабря": 12, "декабрь": 12,
}
# Бланки печатают день в кавычках: «Дата рождения: « 26 » декабря 1950 г.».
# Ни один датовый регекс такую форму не ловил — приводим к обычному виду.
_QUOTED_DAY_RE = re.compile(
    rf"[«\"'‹„”]\s*(\d{{1,2}})\s*[»\"'›“”]\s*(?=(?:{_MONTH_WORD_ALT})\b)",
    re.IGNORECASE,
)


def normalize_quoted_dates(text: str) -> str:
    return _QUOTED_DAY_RE.sub(r"\1 ", text)


dob_label_inline_re = re.compile(r"(?i)(\bдата\s*рождения\b\s*[:\-]?\s*)(.*)$")
dob_age_inline_row_re = re.compile(
    r"(?i)(\bдата\s*рождения\s*,\s*возраст\b.*?)(\d{1,2}\s*[.\-/]\s*\d{1,2}\s*[.\-/]\s*\d{4})\s*[,;]?\s*(\d{1,3}\s*(?:год|года|лет|г\.|л\.))"
)
dob_age_value_re = re.compile(r"(?i)\b(\d{1,3})\s*(год|года|лет|г\.|л\.)\b")
age_only_number_re = re.compile(r"(?i)^\s*(\d{1,3})\s*$")

dob_date_inline_re = re.compile(
    r"(?i)(\bдата\s*рождения\s*[:\-]\s*)"
    r"(\d{1,2}\s*[.\-/]\s*\d{1,2}\s*[.\-/]\s*\d{4}"
    r"|\d{1,2}\s+(?:январ[ья]|феврал[ья]|март[а]?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|"
    r"август[а]?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья])\s+\d{4}(?:\s*(?:г\.?|год[а]?))?"
    r")"
)
bare_date_line_re = re.compile(r"^\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{4})\s*$")
TABLE_DOB_NEIGHBOR_KEYWORDS = ("фио", "лет", "пол", "дата рождения", "возраст", "год рождения")

dob_split_inline_re = re.compile(
    r"(?i)(\bдата\s*рождения\s*[:\-]?\s*)число\s*(\d{1,2})\s*месяц\s*([а-яё]+)\s*год\s*(\d{4})"
)


def _dob_split_inline_to_age(m: re.Match) -> str:
    label, d, mon_word, y = m.group(1), int(m.group(2)), m.group(3).lower(), int(m.group(4))
    mon = MONTH_MAP.get(mon_word)
    if not mon:
        return m.group(0)
    age = calc_age_from_str(f"{d:02d}.{mon:02d}.{y:04d}")
    return label + (age_phrase(age))

# ---------- КОНТЕКСТ ВРАЧА (НЕ маскируем) ----------
DOCTOR_CONTEXT_RE = re.compile(
    r"(?i)\b("
        r"врач\w*"
        r"|доктор\w*"
        r"|лечащ\w+\s+врач\w*"
        r"|фио\s+врач\w*"
        r"|зав(?:едующ\w+)?\.?\s*отделени\w+"
        r"|медсестр\w*"
        r"|фельдшер\w*"
        r"|акушер\w*"
        r"|анестезиолог\w*"
        r"|хирург\w*"
        r"|терапевт\w*"
        r"|кардиолог\w*"
        r"|невролог\w*"
        r"|гинеколог\w*"
        r"|уролог\w*"
        r"|онколог\w*"
        r"|ординатор\w*"
        r"|интерн\w*"
        r"|подпис\w+\s+врач\w*"
        r"|медицинск\w+\s+работник\w*"
        r"|медработник\w*"
        r"|фио\s+медицинск\w+\s+работник\w*"
        r"|рентгенолог\w*"
        r"|рентгенлаборант\w*"
        r"|радиолог\w*"
        r"|лаборант\w*"
        r"|эндокринолог\w*"
        r"|офтальмолог\w*"
        r"|окулист\w*"
        r"|оторинолар\w*"
        r"|отоларинголог\w*"
        r"|лор\b"
        r"|психиатр\w*"
        r"|психотерапевт\w*"
        r"|нарколог\w*"
        r"|дерматолог\w*"
        r"|дерматовенеролог\w*"
        r"|венеролог\w*"
        r"|инфекционист\w*"
        r"|ревматолог\w*"
        r"|пульмонолог\w*"
        r"|гастроэнтеролог\w*"
        r"|нефролог\w*"
        r"|проктолог\w*"
        r"|колопроктолог\w*"
        r"|травматолог\w*"
        r"|ортопед\w*"
        r"|стоматолог\w*"
        r"|патологоанатом\w*"
        r"|фтизиатр\w*"
        r"|аллерголог\w*"
        r"|иммунолог\w*"
        r"|неонатолог\w*"
        r"|реаниматолог\w*"
        r"|реанимац\w*"
        r"|эпидемиолог\w*"
        r"|диетолог\w*"
        r"|физиотерапевт\w*"
        r"|рефлексотерапевт\w*"
        r"|генетик\w*"
        r"|гематолог\w*"
        r"|маммолог\w*"
        r"|нейрохирург\w*"
        r"|диагност\w*"
        r"|заведующ\w*"
        r"|начальник\w*"
        r"|специалист\w*"
    r")\b"
)

doctor_label_only_re = re.compile(
    r"(?i)^\s*(?:фио\s+)?(?:лечащ\w+\s+)?(?:врач\w*|доктор\w*)\s*[:\-]?\s*$"
)
doctor_label_with_colon_re = re.compile(
    r"(?i)^\s*(?:фио\s+)?(?:лечащ\w+\s+)?(?:врач\w*|доктор\w*)\s*[:\-]\s*$"
)

# ---------- ФИО — метки ПАЦИЕНТА ----------
FIO_LABEL_FULL = (
    r"(?:"
        r"ф\.?\s*и\.?\s*о\.?"
        r"|фамилия\s*[,.]?\s*и(?:мя)?\.?\s*[,.]?\s*о(?:тчество)?\.?"
        r"(?:\s*\(при\s+наличии\))?"
    r")"
)
FIO_PATIENT_LABEL = (
    rf"(?:{FIO_LABEL_FULL}"
    r"(?!\s+(?:врач\w*|доктор\w*|медсестр\w*|зав\w*|фельдшер\w*))"
    r"(?:\s+(?:пациент\w*|ребенк\w*|больн\w*))?)"
)

fio_tag_only_re = re.compile(
    rf"^\s*(?:\d+\s*[.)]\s*)?(?:{FIO_PATIENT_LABEL}|пациент\w*)\s*[:\-\.]?\s*$",
    re.IGNORECASE,
)

fio_patient_inline_re = re.compile(
    rf"(?i)^(\s*(?:\d+\s*[.)]\s*)?{FIO_LABEL_FULL}"
    r"(?!\s+(?:врач\w*|доктор\w*|медсестр\w*|зав\w*|фельдшер\w*))"
    r"(?:\s+(?:пациент\w*|ребенк\w*|больн\w*))?"
    r"\s*[:\-]\s*)(\S.+?)\s*$"
)
fio_patient_no_colon_inline_re = re.compile(
    rf"(?i)^(\s*(?:\d+\s*[.)]\s*)?{FIO_LABEL_FULL}"
    r"(?!\s+(?:врач\w*|доктор\w*|медсестр\w*|зав\w*|фельдшер\w*))"
    r"(?:\s+(?:пациент\w*|ребенк\w*|больн\w*))?"
    r"\s+)([А-ЯЁA-Z][\S].*?)\s*$"
)

surname_label_inline_re = re.compile(
    r"(?i)^(\s*(?:\d+\s*[.)]\s*)?фамилия\s*[:\-]\s*)(\S.+?)\s*$"
)
firstname_label_inline_re = re.compile(
    r"(?i)^(\s*(?:\d+\s*[.)]\s*)?имя\s*[:\-]\s*)(\S.+?)\s*$"
)
patronymic_label_inline_re = re.compile(
    r"(?i)^(\s*(?:\d+\s*[.)]\s*)?отчество(?:\s*\(при\s+наличии\))?\s*[:\-]\s*)(\S.+?)\s*$"
)
surname_label_only_re = re.compile(r"(?i)^\s*(?:\d+\s*[.)]\s*)?фамилия\s*[:\-]?\s*$")
firstname_label_only_re = re.compile(r"(?i)^\s*(?:\d+\s*[.)]\s*)?имя\s*[:\-]?\s*$")
patronymic_label_only_re = re.compile(r"(?i)^\s*(?:\d+\s*[.)]\s*)?отчество(?:\s*\(при\s+наличии\))?\s*[:\-]?\s*$")

_TBL_GAP = r"(?:[ \t]{2,}|\t+)"
surname_table_re = re.compile(rf"(?i)^(\s*(?:\d+\s*[.)]\s*)?фамилия{_TBL_GAP})(\S.*?)\s*$")
firstname_table_re = re.compile(rf"(?i)^(\s*(?:\d+\s*[.)]\s*)?имя{_TBL_GAP})(\S.*?)\s*$")
patronymic_table_re = re.compile(
    rf"(?i)^(\s*(?:\d+\s*[.)]\s*)?отчество(?:\s*\(при\s+наличии\))?{_TBL_GAP})(\S.*?)\s*$"
)
dob_table_re = re.compile(rf"(?i)^(\s*(?:\d+\s*[.)]\s*)?дата\s+рождени\w*{_TBL_GAP})(\S.*?)\s*$")

dob_line_re = re.compile(r"(?i)^(\s*(?:\d+\s*[.)]\s*)?дата\s+рождени\w*)\b(.*)$")
any_raw_date_re = re.compile(r"\d{1,2}\s*[.\-/]\s*\d{1,2}\s*[.\-/]\s*\d{2,4}")

# ---------- ФИО — значения ----------
RUS_WORD = r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?"
PATRONYMIC = r"[А-ЯЁ][а-яё]+(?:ович|евич|иевич|ич|овна|евна|иевна|ьевна|ична|инична|оглы|кызы)\b"
SURNAME_SUFFIX = r"(?:ов|ова|ев|ева|ин|ина|ын|ына|ский|ская|цкий|цкая|ко|енко|ук|юк|чук|щук|дзе|швили|ян)"
SURNAME = rf"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?{SURNAME_SUFFIX}"

KEEP_COLUMN_LABEL = (
    r"(?:№|номер\b|отделени\w*|дата\b|направивш\w*|результат\w*|кабинет\w*|"
    r"палат\w*|кем\b|пол\b|возраст\w*|диагноз\w*|наименовани\w*)"
)
stray_surname_table_re = re.compile(
    rf"(?i)^(\s*){SURNAME}(?=\s{{2,}}{KEEP_COLUMN_LABEL})"
)

_PNAME_TOKEN = r"(?:[А-ЯЁ][а-яё]+|[А-ЯЁ]\.)"
patient_fio_inline_re = re.compile(
    r"\b([Пп]ациент\w*|[Бб]ольн\w*|[Пп]острадавш\w*)\s+"
    rf"({_PNAME_TOKEN}(?:\s*{_PNAME_TOKEN}){{0,2}})"
)

# Метки, прямо указывающие на ПАЦИЕНТА (а не на врача).
PATIENT_ROLE_LABEL = (
    r"(?:пациент\w*"
    r"|больн(?:ой|ая|ого|ому|ым|ых)"
    r"|пострадавш\w*"
    r"|(?:законн\w+\s+)?представител\w*"
    r"|ф\.?\s*и\.?\s*о\.?\s*пациент\w*)"
)
PATIENT_MARKER_RE = re.compile(rf"(?i)\b{PATIENT_ROLE_LABEL}\s*[:\-]")

# «Пациент: Иванова Мария Петровна Дата рождения: …» — метка с двоеточием.
# Слова-метки соседних колонок в захват ФИО не попадают.
_FIELD_LABEL_WORD = (
    r"(?:Дата|Время|Возраст|Номер|Пол|Телефон|Тел|Адрес|Год|Диагноз|Отделение|"
    r"Место|Полис|СНИЛС|Паспорт|Врач|Пациент|Представитель|Жалобы|Анамнез|"
    r"Рост|Вес|Наименование|Отделения)"
)
_PNAME_TOKEN_SAFE = rf"(?!{_FIELD_LABEL_WORD}\b)(?:[А-ЯЁ][а-яё]+|[А-ЯЁ]\.)"
# Разделитель токенов: пробел ИЛИ его отсутствие после точки — «Петров П.П.».
_PNAME_SEP = r"(?:\s+|(?<=\.))"
patient_label_fio_inline_re = re.compile(
    rf"\b((?i:{PATIENT_ROLE_LABEL})\s*[:\-]\s*)"
    rf"({_PNAME_TOKEN_SAFE}(?:{_PNAME_SEP}{_PNAME_TOKEN_SAFE}){{0,2}})"
)


# ==================== БЛОКИ РЕЗУЛЬТАТОВ ИССЛЕДОВАНИЙ ====================
# В табличных бланках лабораторных результатов есть колонка «Комментарий
# подтвердил» с фамилией специалиста, подтвердившего анализ. При извлечении
# текста фамилия падает в отдельную строку рядом с названием исследования и
# затиралась меткой [FIO], разрушая результаты. Такие блоки защищаем целиком.

LAB_TABLE_HEADER_RE = re.compile(
    r"(?i)комментарий\s+подтвердил"
    r"|наименовани\w*\b.{0,60}результат\w*\b.{0,80}(?:реф\.|референс\w*|ед\.\s*изм)"
)
STUDY_NAME_LINE_RE = re.compile(
    r"(?i)\b(?:исследовани\w*|определени\w*)\s+"
    r"(?:уровня|активности|содержани\w*|концентраци\w*|числа|количества)\b"
)
# Строки, на которых защита снимается: там снова начинаются данные пациента.
STUDY_BLOCK_STOP_RE = re.compile(
    r"(?i)данные\s+о\s+пациенте"
    r"|ф\.?\s*и\.?\s*о\.?\s*(?:пациент\w*)?\s*[:\-]"
    r"|\bфамилия\b|\bимя\b|\bотчество\b"
    r"|дата\s+рождени|\bвозраст\b|год\s+рождени"
    r"|\bадрес\b|место\s+жительств|\bполис\b|\bснилс\b|\bпаспорт"
    r"|телефон|\bпациент\w*\s*[:\-]|представител"
)


def mark_study_regions(lines) -> set:
    """Индексы строк, относящихся к блоку результатов исследований."""
    protected = set()
    active = False
    for idx, raw in enumerate(lines):
        s = norm(raw).strip()
        if not s:
            if active:
                protected.add(idx)
            continue
        if STUDY_BLOCK_STOP_RE.search(s):
            active = False
            continue
        if LAB_TABLE_HEADER_RE.search(s):
            active = True
            protected.add(idx)
            continue
        if active:
            protected.add(idx)

    # Даже без шапки таблицы: строка с названием исследования и её соседи
    # (там же лежит фамилия подтвердившего и инициалы «Н.В.»).
    n = len(lines)
    for idx, raw in enumerate(lines):
        s = norm(raw).strip()
        if not s or not STUDY_NAME_LINE_RE.search(s):
            continue
        protected.add(idx)
        for k in (idx - 1, idx + 1):
            if 0 <= k < n and not STUDY_BLOCK_STOP_RE.search(norm(lines[k])):
                protected.add(k)
    return protected

fio_triplet_inline_re = re.compile(rf"\b{RUS_WORD}\s+{RUS_WORD}\s+{PATRONYMIC}")
fio_with_initials_inline_re = re.compile(rf"\b{SURNAME}\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.")
fio_line_triplet_re = re.compile(rf"^\s*{RUS_WORD}\s+{RUS_WORD}\s+{PATRONYMIC}\s*$")
fio_line_doublet_re = re.compile(rf"^\s*{SURNAME}\s+{RUS_WORD}\s*$")
fio_line_initials_re = re.compile(rf"^\s*{SURNAME}\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.\s*$")

UPPER_RUS_WORD = r"[А-ЯЁ]{2,}(?:-[А-ЯЁ]{2,})?"
UPPER_PATRONYMIC = (
    r"[А-ЯЁ]+(?:ОВИЧ|ЕВИЧ|ИЕВИЧ|ЬЕВИЧ|ИЧ|ОВНА|ЕВНА|ИЕВНА|ЬЕВНА|ИНИЧНА|ИЧНА|ОГЛЫ|КЫЗЫ)"
)
fio_upper_triplet_inline_re = re.compile(
    rf"\b{UPPER_RUS_WORD}\s+{UPPER_RUS_WORD}\s+{UPPER_PATRONYMIC}\b"
)
fio_upper_triplet_line_re = re.compile(
    rf"^\s*{UPPER_RUS_WORD}\s+{UPPER_RUS_WORD}\s+{UPPER_PATRONYMIC}\s*$"
)
fio_upper_with_initials_inline_re = re.compile(
    rf"\b{UPPER_RUS_WORD}\s+[А-ЯЁ]\.\s*[А-ЯЁ]\."
)
fio_upper_with_initials_line_re = re.compile(
    rf"^\s*{UPPER_RUS_WORD}\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.\s*$"
)
fio_initials_upper_inline_re = re.compile(
    rf"\b[А-ЯЁ]\.\s*[А-ЯЁ]\.\s+{UPPER_RUS_WORD}\b"
)

PATRONYMIC_STRONG = (
    r"[А-ЯЁ][а-яёА-ЯЁ]+(?:ович|евич|иевич|ьевич|овна|евна|иевна|ьевна|инична|оглы|кызы)"
)
fio_line_single_patronymic_re = re.compile(rf"^\s*{PATRONYMIC_STRONG}\s*$")

# ---------- Организации / гео / клинический контекст ----------
ORG_GEO_STOPWORDS = (
    "здравоохран", "министерств", "республик", "больниц", "учрежден", "организац",
    "отделен", "департамент", "федерац", "город", "клиническ", "поликлиник",
    "центр", "осети", "алани", "област", "бюджетн", "государствен", "помощ",
    "медицин", "медицинск", "скор", "лаборатор", "кабинет", "отдел", "диспансер",
    "станци", "служб", "управлен", "комитет", "академи", "институт", "университет",
    "факультет", "корпус", "имени", "северн", "южн", "восточн", "западн", "район",
    "поселок", "посёлок", "село", "край", "респ", "обл", "отряд", "подразделен",
    "специалист", "заведующ", "начальник", "территориальн", "стационар",
    "амбулатор", "перинатальн", "родильн", "детск", "взросл", "структурн",
)
ORG_GEO_STOPWORD_RE = re.compile(r"(?i)^(?:" + "|".join(ORG_GEO_STOPWORDS) + r")")

CLINICAL_STOPWORDS = (
    "цитолог", "гистолог", "биопс", "биоптат", "морфолог", "иммуногист",
    "соскоб", "пунктат", "анализ", "исследован", "заключен", "протокол",
    "рентген", "томограф", "сцинтиграф", "денситометр", "маммограф",
    "флюорограф", "спирометр", "допплер", "дуплекс", "триплекс",
    "щитовидн", "молочн", "предстательн", "брюшн", "грудн", "забрюшинн",
    "лимфоуз", "желчн", "поджелуд", "сосудист", "новообразован",
    "ультразвук", "эндоскоп", "колоноскоп", "гастроскоп", "ирригоскоп",
)
CLINICAL_STOPWORD_RE = re.compile(r"(?i)^(?:" + "|".join(CLINICAL_STOPWORDS) + r")")
CLINICAL_WHOLE_WORDS = frozenset({
    "узи", "кт", "мрт", "мскт", "экг", "ээг", "эхо", "ктг", "фгдс", "эгдс",
    "фвд", "ро", "рг", "оак", "оам", "бак", "ифа", "пцр", "соэ", "нсг",
    "эхокг", "рэг", "мскткг",
    "из", "по", "на", "от", "для", "при", "над", "под", "без", "во", "со",
    "об", "до", "и", "с", "в", "к",
})

CLINICAL_CONTENT_LINE_RE = re.compile(
    r"(?i)^\s*(?:\d+\s*[.)]\s*)?(?:"
    r"план\s+обследовани\w*"
    r"|план\s+лечени\w*"
    r"|план\s+ведени\w*"
    r"|обследовани\w*"
    r"|назначени\w*"
    r"|рекомендац\w*"
    r"|жалоб\w*"
    r"|анамнез\w*"
    r"|диагноз\w*"
    r"|протокол\w*"
    r")\b"
)


def _has_org_geo_word(span: str) -> bool:
    for w in re.split(r"[\s\-]+", span):
        w = w.strip(".,;:\"'«»()[]")
        if w and ORG_GEO_STOPWORD_RE.match(w):
            return True
    return False


def _has_clinical_word(span: str) -> bool:
    for w in re.split(r"[\s\-/.,]+", span):
        wl = w.strip(".,;:\"'«»()[]/").lower()
        if not wl:
            continue
        if wl in CLINICAL_WHOLE_WORDS or CLINICAL_STOPWORD_RE.match(wl):
            return True
    return False


# Инициалы убираем перед проверкой: в «Ивановой М.И.» токен «И» совпадал с
# предлогом «и» из CLINICAL_WHOLE_WORDS, и ФИО ошибочно признавалось клиническим
# текстом — строка «Пациентке Ивановой М.И. выполнена операция» не затиралась.
_INITIALS_TOKEN_RE = re.compile(r"(?<![А-Яа-яЁё])[А-ЯЁ]\.")


def _is_not_fio(span: str) -> bool:
    probe = _INITIALS_TOKEN_RE.sub(" ", span)
    return _has_org_geo_word(probe) or _has_clinical_word(probe)


# ==================== ПАМЯТЬ ОБ ОБЕЗЛИЧЕННЫХ ФИО ====================
_NAME_SWEEP_STOPWORDS = frozenset({
    "января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
    "сентября", "октября", "ноября", "декабря", "январь", "февраль", "март",
    "апрель", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
    "результат", "наименование", "комментарий", "значение", "заключение",
    "понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье",
    "отделение", "направление", "диагноз", "возраст", "пациент", "пациента",
    "дата", "имя", "фамилия", "отчество", "пол", "подпись", "номер", "паспорт",
    "снилс", "полис", "телефон", "адрес", "время", "протокол", "образец", "образца",
    "место", "работа", "должность", "документ", "профессия", "гражданство",
    "национальность", "регистрация", "организация", "учреждение", "страховая",
})


def _is_namelike(tok: str) -> bool:
    if len(tok) < 3:
        return False
    if not re.match(r"^[А-ЯЁ][А-Яа-яёЁ]+$", tok):
        return False
    if tok.lower() in _NAME_SWEEP_STOPWORDS:
        return False
    return not _is_not_fio(tok)


_PATRONYMIC_SUFFIX_RE = re.compile(
    r"(?:ович|евич|иевич|ьевич|ич|овна|евна|иевна|ьевна|ична|инична|оглы|кызы)$",
    re.IGNORECASE,
)
_SURNAME_SUFFIX_END_RE = re.compile(SURNAME_SUFFIX + r"$", re.IGNORECASE)


def _is_strong_name_token(tok: str) -> bool:
    if not _is_namelike(tok):
        return False
    low = tok.lower()
    if low in _FIRST_NAMES_LOWER:
        return True
    if _SURNAME_SUFFIX_END_RE.search(low):
        return True
    if _PATRONYMIC_SUFFIX_RE.search(low):
        return True
    return False


class PIIMemory:
    """Накопитель токенов ФИО пациента + финальное «подметание» по всему тексту."""

    def __init__(self):
        self.fio_tokens = set()

    def add_fio(self, value: str):
        if not value:
            return
        namelike_toks = []
        for raw in re.split(r"[\s\-]+", value):
            tok = raw.strip(".,;:\"'«»()[]<>")
            if _is_namelike(tok):
                namelike_toks.append(tok)

        has_strong = any(_is_strong_name_token(t) for t in namelike_toks)
        for tok in namelike_toks:
            if has_strong or _is_strong_name_token(tok):
                self.fio_tokens.add(tok.lower())

    def add_fio_strict(self, value: str):
        if not value:
            return
        for raw in re.split(r"[\s\-]+", value):
            tok = raw.strip(".,;:\"'«»()[]<>")
            if _is_namelike(tok):
                self.fio_tokens.add(tok.lower())

    def sweep_fio(self, text: str) -> str:
        """Затирает оставшиеся вхождения запомненных токенов ФИО.

        ВАЖНО: строки с явной ролью врача/медработника («Врач: Иванов И.И.»,
        «Лечащий врач — Петров», «Подпись врача - рентгенолога») НЕ затираются.
        Блоки результатов исследований тоже не затираются — там фамилия
        относится к специалисту, подтвердившему анализ.
        """
        long_toks = sorted((t for t in self.fio_tokens if len(t) >= 6), key=len, reverse=True)
        short_toks = sorted((t for t in self.fio_tokens if 4 <= len(t) < 6), key=len, reverse=True)

        def _mask_line(line: str) -> str:
            for tok in long_toks:
                esc = re.escape(tok.capitalize())
                line = re.sub(rf"(?i)\b{esc}[а-яёА-ЯЁ]{{0,3}}\b", "[FIO]", line)
            for tok in short_toks:
                esc = re.escape(tok.capitalize())
                line = re.sub(rf"(?i)\b{esc}\b", "[FIO]", line)
            return line

        src_lines = text.split("\n")
        study_idx = mark_study_regions(src_lines)
        result_lines = []
        for idx, line in enumerate(src_lines):
            if idx in study_idx or is_doctor_line(line):
                result_lines.append(line)
            else:
                result_lines.append(_mask_line(line))
        text = "\n".join(result_lines)

        src_lines = text.split("\n")
        study_idx = mark_study_regions(src_lines)

        def _initials_sub_line(idx: int, line: str) -> str:
            if idx in study_idx or is_doctor_line(line):
                return line
            return re.sub(r"\[FIO\]\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.", "[FIO]", line)
        text = "\n".join(_initials_sub_line(i, l) for i, l in enumerate(src_lines))

        text = re.sub(r"\b[А-ЯЁ][а-яё]{1,3}-\[FIO\]", "[FIO]", text)
        text = "\n".join(
            _mask_dob_next_to_fio(
                _mask_bare_dob_after_fio_in_line(line),
                force=bool(PATIENT_MARKER_RE.search(line)),
            )
            for line in text.split("\n")
        )
        return text


_MEM = None


def _remember_fio(value: str):
    if _MEM is not None and value:
        _MEM.add_fio(value)


def _remember_fio_strict(value: str):
    if _MEM is not None and value:
        _MEM.add_fio_strict(value)


def _mask_fio_unless_org(rx: re.Pattern, s: str) -> str:
    def repl(m: re.Match) -> str:
        if _is_not_fio(m.group(0)):
            return m.group(0)
        _remember_fio(m.group(0))
        return "[FIO]"
    return rx.sub(repl, s)


# ---------- Адрес — эвристика ----------
street_line_re = re.compile(r"^\s*(?:ул\.|улица)\b.*$", re.IGNORECASE)
# ВАЖНО про \b: раньше все сокращения были в общей группе, закрытой `\b`. После
# точки перед пробелом границы слова НЕТ, поэтому «ул. Водная», «обл.,», «д. 7»
# не находились вообще. Теперь сокращения — отдельная ветка без хвостового \b.
# Приметы разделены на «сильные» (улица/проспект — почти всегда адрес) и
# «слабые» (г., обл., д., кв. — бывают и в датах, и в нумерации пунктов).
_ADDR_STRONG_RE = re.compile(
    r"(?i)(?:\b(?:улиц\w*|проспект\w*|переул\w*|шоссе|бульвар\w*|набережн\w*|"
    r"площад\w*|проезд\w*|микрорайон\w*|станиц\w*|хутор\w*|садовое\s+товарищ\w*)\b"
    r"|(?<![а-яё])(?:ул|пр-?т|пр-?д|пер|б-р|наб|пл|мкр|снт|тер)\.)"
)
_ADDR_WEAK_RE = re.compile(
    r"(?i)(?:\b(?:город|област\w*|край|республик\w*|дом|квартир\w*|корпус\w*|"
    r"строени\w*|литер\w*|офис\w*|помещени\w*|посёлок|поселок|село|деревн\w*)\b"
    r"|(?<![а-яё])(?:г|обл|респ|д|кв(?!\.\s?м\b)|корп|кор|стр|лит|оф|пос|дер|п)\.)"
)
_POSTAL_INDEX_RE = re.compile(r"^\s*\d{6}\s*,")

# Строка называет медорганизацию («ГУЗ "Клиническая больница №12" 400040, …»).
# Целиком затирать нельзя — потеряется название; затираем только адресный хвост.
MED_ORG_LINE_RE = re.compile(
    r"(?i)(?<![а-яё])(?:г?б?уз|фгбу\w*|фгаоу|мбуз|огбуз|обуз|кгбуз|гбу|гау|"
    r"ооо|оао|зао|пао|ао|ип)(?![а-яё])"
    r"|больниц\w*|поликлиник\w*|диспансер\w*|госпитал\w*|медсанчаст\w*|амбулатори\w*|"
    r"учреждени\w+\s+здравоохранени\w*|(?:медицинск\w+|перинатальн\w+)\s+центр\w*"
)
_ADDRESS_TAIL_INDEX_RE = re.compile(r"(?<![\d-])\d{6}(?=\s*,?\s*\D)")


def mask_address_tail(s: str) -> str:
    """Затирает адресный хвост, оставляя название организации в начале строки."""
    m = _ADDRESS_TAIL_INDEX_RE.search(s)
    if m is None:
        m = _ADDR_STRONG_RE.search(s)
    if m is None or m.start() == 0:
        left_ws = re.match(r"^\s*", s).group(0)
        return left_ws + "[ADDRESS]"
    return s[:m.start()].rstrip() + " [ADDRESS]"

# ---------- Контексты для телефонов ----------
card_context_inline_re = re.compile(
    r"(?i)(?:№|\bномер)\s*(?:карты|истори[ияй](?:\s+болезни)?|иб\b|и\.\s*б\.)"
)
phone_label_re = re.compile(r"(?i)\b(?:номер\s+телефона|контактн\w+\s+телефон|телефон|тел\.?|моб\.?|сот\.?)\b")

# ИНН физического лица должен маскироваться. В исходной версии строка с ИНН
# ошибочно целиком считалась реквизитами организации и пропускала общую маску.
org_id_re = re.compile(r"(?i)\b(?:кпп|огрн(?:ип)?|окпо|октмо|оквэд|бик)\b")
docnum_context_re = re.compile(
    r"(?i)№\s*(?:образц\w*|направлен\w*|протокол\w*|анализ\w*|заказ\w*|пробы|биоматериал\w*)"
    r"|номер\s+(?:образц\w*|направлен\w*|протокол\w*|пробы)"
    # рецептурный бланк в листе назначений: «Б/Р №2000230409», «Рецепт № …»
    r"|(?<![а-яёa-z])б\s*[/\\]\s*р\b"
    r"|\bрецепт\w*"
    r"|\bбланк\w*\s+рецепт\w*"
    r"|\bльготн\w+\s+рецепт\w*"
)


# ==================== КОНТЕКСТНЫЕ ПРОВЕРКИ ====================

DOCTOR_ROLE_RE = re.compile(
    r"(?i)\bврач\w*|\bдоктор\w*|медсестр\w*|медбрат\w*|фельдшер\w*|акушер\w*|"
    r"подпис\w*|заведующ\w*|\bзав\.?\s*отделени|ординатор\w*|\bинтерн\w*|"
    r"медицинск\w+\s+работник\w*|медработник\w*|\bлаборант\w*"
)
DEPARTMENT_CTX_RE = re.compile(r"(?i)отделени\w*|кабинет\w*")

# Токен-идентификатор: любое «слово» с цифрой внутри — номер ИБ, номер карты,
# дата, код МКБ. В таких токенах встречаются названия специальностей
# («Номер ИБ: 2026/Неврология./1»), из-за чего строка ошибочно считалась
# «строкой врача» и ФИО пациента в ней не затиралось.
_IDENTIFIER_TOKEN_RE = re.compile(r"\S*\d\S*")


def _doctor_probe(line: str) -> str:
    return _IDENTIFIER_TOKEN_RE.sub(" ", line)


def is_doctor_line(line: str) -> bool:
    probe = _doctor_probe(line)
    if not DOCTOR_CONTEXT_RE.search(probe):
        return False
    if DOCTOR_ROLE_RE.search(probe):
        return True
    # Явная метка пациента перевешивает «слабый» намёк вроде названия
    # специальности внутри наименования отделения/номера.
    if PATIENT_MARKER_RE.search(line):
        return False
    return not DEPARTMENT_CTX_RE.search(probe)


_date_only_line_re = re.compile(r"^\s*\d{1,2}\s*[.\-/]\s*\d{1,2}\s*[.\-/]\s*\d{4}\s*[гл]?\.?\s*$")
_signature_label_only_re = re.compile(r"(?i)^\s*подпис\w*\s*[:\-]?\s*$")


def has_doctor_context_above(lines, idx, window: int = 6) -> bool:
    found_nonempty = 0
    for k in range(idx - 1, max(-1, idx - 1 - window), -1):
        s = norm(lines[k]).strip()
        if not s:
            continue
        if _date_only_line_re.match(s) or _signature_label_only_re.match(s):
            continue
        found_nonempty += 1

        if doctor_label_only_re.match(s):
            return True

        if re.search(r"(?i)(врач\w*|доктор\w*|медсестр\w*|фельдшер\w*|медицинск\w+\s+работник\w*|медработник\w*|зав(?:едующ\w+)?\.?\s*отделени\w*)\s*[:\-]?\s*$", s):
            return True

        if is_doctor_line(s) and not (
            fio_triplet_inline_re.search(s)
            or fio_with_initials_inline_re.search(s)
            or fio_upper_triplet_inline_re.search(s)
            or fio_upper_with_initials_inline_re.search(s)
        ):
            return True

        if found_nonempty >= 1:
            return False
    return False


def has_doctor_context_below(lines, idx, window: int = 5) -> bool:
    for k in range(idx + 1, min(len(lines), idx + 1 + window)):
        s = norm(lines[k]).strip()
        if not s or _date_only_line_re.match(s):
            continue
        if re.search(r"(?i)подпис", s) and DOCTOR_CONTEXT_RE.search(s):
            return True
        if is_doctor_line(s) and not (
            fio_line_triplet_re.match(s)
            or fio_line_doublet_re.match(s)
            or fio_line_initials_re.match(s)
            or fio_upper_triplet_line_re.match(s)
            or fio_upper_with_initials_line_re.match(s)
        ):
            return True
        if _signature_label_only_re.match(s):
            continue
        if (
            fio_line_triplet_re.match(s)
            or fio_line_doublet_re.match(s)
            or fio_line_initials_re.match(s)
            or fio_line_single_patronymic_re.match(s)
            or fio_upper_triplet_line_re.match(s)
            or fio_upper_with_initials_line_re.match(s)
        ):
            continue
        return False
    return False


def is_header_block_above(lines, idx, window=10) -> bool:
    start = max(0, idx - window)
    block = letters_only(" ".join(norm(lines[k]) for k in range(start, idx + 1)))
    return (
        "медицинскаякартпациента" in block
        and "стационарныхусловиях" in block
        and "дневногостационара" in block
    )


def has_passport_context(lines, idx, window=1) -> bool:
    for k in range(max(0, idx - window), min(len(lines), idx + window + 1)):
        if passport_context_line_re.search(_normline(lines[k])):
            return True
    return False


def is_card_number_line(line: str) -> bool:
    """Строка выглядит как номер карты; исключаем телефоны и служебные номера."""
    if not re.match(r"(?i)^\s*(?:№|no\.?|номер)\b", line):
        return False
    if _NOT_CARD_NUMBER_LABELS_RE.match(line):
        return False
    return digits_count(line) >= 9


def is_table_dob_context(lines, idx, window=4) -> bool:
    start = max(0, idx - window)
    end = min(len(lines), idx + window + 1)
    for k in range(start, end):
        if k == idx:
            continue
        low = _normline(lines[k])
        if not low:
            continue
        for kw in TABLE_DOB_NEIGHBOR_KEYWORDS:
            if low == kw or low.startswith(kw + " ") or low.endswith(" " + kw):
                return True
    return False


STUDY_SIGNATURE_CTX_RE = re.compile(
    r"(?i)("
    r"дата\s+проведения|дата\s+исследовани|дата\s+подписи|"
    r"исследовани|заключени|протокол|"
    r"подпис\w*|"
    r"врач\w*|доктор\w*|медицинск\w+\s+работник\w*|медработник\w*"
    r")"
)


def has_study_signature_context(lines, idx, window=4) -> bool:
    start = max(0, idx - window)
    end = min(len(lines), idx + window + 1)
    for k in range(start, end):
        if STUDY_SIGNATURE_CTX_RE.search(_normline(lines[k])):
            return True
    return False


def match_label_span(lines, i, label_re, max_join: int = 3) -> int:
    for n in range(1, max_join + 1):
        if i + n > len(lines):
            break
        parts = []
        good = True
        for k in range(n):
            s = norm(lines[i + k]).strip()
            if not s:
                good = False
                break
            if k > 0 and re.match(r"^\s*\d+\s*[.)]", lines[i + k]):
                good = False
                break
            parts.append(s)
        if not good:
            continue
        joined = " ".join(parts)
        if label_re.match(joined):
            return n
    return 0


# ==================== ПОГЛОЩЕНИЕ ТАБЛИЧНОГО БЛОКА ЗНАЧЕНИЙ ====================

VALUE_BLOCK_STOP_RE = re.compile(
    r"(?i)^\s*(?:\d+\s*[.)]\s*)?"
    r"(?:поступил|состояние|кем\s+доставл|признак|повторная|"
    r"аналогичных|санитарно|период|количество|сведения|номер\s+медицинск|"
    r"фамилия|имя|отчество|фио|пациент|"
    r"снилс|серия|паспорт|"
    r"контактн\w+\s+телефон|номер\s+телефона|телефон|тел\.|моб\.|сот\.|"
    r"email|e-?mail|полис|инн|пол\b|"
    r"дата\s+рождения|возраст|год\s+рождения|"
    r"жалобы|анамнез|диагноз|объективно|осмотр|температура|"
    r"место\s+работы|должность|"
    r"код\s+диагноза|обоснование\s+направления|"
    r"место\s+(?:жительств|регистрации|прожив|пребывани)|"
    r"адрес\b|регистрация\s+по\s+месту|прописка|домашн\w+\s+адрес|"
    r"отделение|врач|доктор"
    r")"
)
NUMBERED_ITEM_RE = re.compile(r"^\s*\d+\s*[.)]\s*\S")


def consume_value_block(lines, start_idx: int, max_lines: int = 30) -> int:
    j = start_idx
    while j < len(lines) and (j - start_idx) < max_lines:
        s = norm(lines[j]).strip()
        if not s:
            break
        if s.endswith(":"):
            break
        if NUMBERED_ITEM_RE.match(s):
            break
        if VALUE_BLOCK_STOP_RE.match(s):
            break
        j += 1
    return j


# ==================== ХЕЛПЕРЫ ОЧИСТКИ ====================

def looks_like_address(line: str) -> bool:
    s = norm(line).strip()
    if not s:
        return False
    if "улучш" in s.lower():
        return False
    s_check = year_birth_re2.sub(" ", year_birth_re.sub(" ", s))
    has_digit = re.search(r"\d", s) is not None

    # Считаем РАЗНЫЕ приметы: «с 03 марта 2026 г. … по 16 марта 2026 г.» содержит
    # «г.» дважды, но это одна и та же примета — строка не адрес.
    def _keys(rx):
        return {m.group(0).lower().strip().rstrip(".")[:4] for m in rx.finditer(s_check)}

    strong = _keys(_ADDR_STRONG_RE)
    weak = _keys(_ADDR_WEAK_RE)
    markers = len(strong) + len(weak)

    if strong and has_digit:
        return True
    if _POSTAL_INDEX_RE.match(s_check) and markers:
        return True
    if has_digit and markers >= 2:
        return True
    # Адрес без цифр: «Московская область, город Химки, микрорайон Сходня».
    return markers >= 3


def find_age_from_text(s: str) -> str | None:
    s2 = norm(s)

    m_age = dob_age_value_re.search(s2)
    if m_age:
        unit = m_age.group(2).replace(".", "")
        return f"{m_age.group(1)} {unit}"

    if age_only_number_re.match(s2):
        return age_phrase(s2.strip())

    m_num = flex_date_re.search(s2)
    if m_num:
        d, m, y = map(int, m_num.groups())
        age = calc_age_from_str(f"{d:02d}.{m:02d}.{y:04d}")
        return age_phrase(age)

    m_word = month_word_date_re.search(s2)
    if m_word:
        d = int(m_word.group(1))
        mon_word = m_word.group(2).lower()
        y = int(m_word.group(3))
        mon = MONTH_MAP.get(mon_word)
        if mon:
            age = calc_age_from_str(f"{d:02d}.{mon:02d}.{y:04d}")
            return age_phrase(age)
    return None


def _dob_date_inline_to_age(m: re.Match) -> str:
    label, datestr = m.group(1), m.group(2)
    age = find_age_from_text(datestr) or "[AGE]"
    return label + age


def _mask_bare_dob_after_fio_in_line(s: str) -> str:
    if "[FIO]" not in s or STUDY_SIGNATURE_CTX_RE.search(s.lower()):
        return s
    for date_re, is_word in ((flex_date_re, False), (month_word_date_re, True)):
        m = date_re.search(s)
        if not m:
            continue
        remainder = s.replace("[FIO]", "")
        remainder = date_re.sub("", remainder)
        remainder = re.sub(
            r"(?i)\b(муж|жен|пол|лет|год[ауа]?|г\.?|число|дата|рождени\w*)\b", "", remainder,
        )
        remainder = re.sub(r"[\W\d]+", "", remainder)
        if is_word:
            d = int(m.group(1))
            mo = MONTH_MAP.get(m.group(2).lower())
            y = int(m.group(3))
        else:
            d, mo, y = map(int, m.groups())
        if mo and len(remainder) <= 2 and 1900 <= y <= date.today().year:
            age = calc_age_from_str(f"{d:02d}.{mo:02d}.{y:04d}")
            repl = age_phrase(age)
            return s[:m.start()] + repl + s[m.end():]
    return s


# Дата рождения БЕЗ метки, сразу за ФИО: «Сведения о пациенте: Иванов Иван
# Иванович, 21.04.1985 (41 год)». Штатные регексы ждут метку «дата рождения»,
# а _mask_bare_dob_after_fio_in_line требует, чтобы в строке кроме ФИО и даты
# почти ничего не было, — здесь не срабатывал ни один.
_AGE_UNIT_RE = r"(?:год(?:а|у|ов)?|лет|г\.|л\.)"
_ANY_DOB_ALT = (
    r"\d{1,2}\s*[.\-/]\s*\d{1,2}\s*[.\-/]\s*\d{4}"
    rf"|\d{{1,2}}\s+(?:{_MONTH_WORD_ALT})\s+\d{{4}}(?:\s*(?:г\.?|год[а]?))?"
)
_fio_dob_inline_re = re.compile(
    r"(\[FIO\]\s*[,;:\u2013\u2014-]?\s*)"
    rf"(?:{_ANY_DOB_ALT})"
    rf"(\s*[(,]?\s*\d{{1,3}}\s*{_AGE_UNIT_RE}\s*\)?)?",
    re.IGNORECASE,
)


def _mask_dob_next_to_fio(s: str, force: bool = False) -> str:
    """Убирает ДР, стоящую сразу после [FIO], оставляя возраст.

    force=True — строка помечена как относящаяся к пациенту («Сведения о
    пациенте:», «Пациент:»), тогда возраст считается из даты. Без метки правило
    срабатывает, только если возраст уже указан рядом явно — иначе есть риск
    затереть дату осмотра или подписи.
    """
    if "[FIO]" not in s:
        return s

    def repl(m: re.Match) -> str:
        head, age_part = m.group(1), m.group(2)
        if age_part:
            return head + age_part.strip().strip("(),; ")
        if not force:
            return m.group(0)
        return head + (find_age_from_text(m.group(0)) or "[AGE]")

    return _fio_dob_inline_re.sub(repl, s)


# ==================== ОЧИСТКА ОДНОЙ СТРОКИ ====================

def _patient_label_fio_sub(m: re.Match) -> str:
    name = m.group(2).strip()
    if _is_not_fio(name):
        return m.group(0)
    toks = name.split()
    if len(toks) >= 2 or any(_is_strong_name_token(t) for t in toks):
        _remember_fio(name)
        return m.group(1) + "[FIO]"
    return m.group(0)


def clean_line_single(
    line: str,
    passport_ctx: bool = False,
    doctor_ctx: bool = False,
    study_ctx: bool = False,
) -> str:
    original_ending = _line_ending(line)
    core = line[:-len(original_ending)] if original_ending else line
    s = norm(core)

    if not doctor_ctx:
        doctor_ctx = is_doctor_line(s)

    clinical_ctx = bool(CLINICAL_CONTENT_LINE_RE.match(s))

    # «Пациент: …», «Больной: …», «Представитель: …» — метка прямо называет
    # субъекта ПДн, поэтому ФИО затирается независимо от прочего контекста
    # строки (в ней может стоять номер ИБ с названием отделения и т.п.).
    if not study_ctx:
        s = patient_label_fio_inline_re.sub(_patient_label_fio_sub, s)

    if not doctor_ctx and not clinical_ctx and not study_ctx:
        if fio_line_triplet_re.match(s) or fio_line_doublet_re.match(s) or fio_line_initials_re.match(s):
            _remember_fio(s)
            return "[FIO]" + original_ending

        if fio_line_single_patronymic_re.match(s):
            _remember_fio(s)
            return "[FIO]" + original_ending

        if (fio_upper_triplet_line_re.match(s) or fio_upper_with_initials_line_re.match(s)) \
                and not _is_not_fio(s):
            _remember_fio(s)
            return "[FIO]" + original_ending

        matched = False
        for rx in (
            fio_patient_inline_re,
            fio_patient_no_colon_inline_re,
            surname_label_inline_re,
            firstname_label_inline_re,
            patronymic_label_inline_re,
            surname_table_re,
            firstname_table_re,
            patronymic_table_re,
        ):
            m = rx.match(s)
            if m:
                _remember_fio_strict(m.group(2))
                s = m.group(1) + "[FIO]"
                matched = True
                break

        if not matched:
            s = fio_triplet_inline_re.sub(lambda m: (_remember_fio(m.group(0)), "[FIO]")[1], s)
            s = fio_with_initials_inline_re.sub(lambda m: (_remember_fio(m.group(0)), "[FIO]")[1], s)
            s = _mask_fio_unless_org(fio_upper_triplet_inline_re, s)
            s = _mask_fio_unless_org(fio_upper_with_initials_inline_re, s)
            s = _mask_fio_unless_org(fio_initials_upper_inline_re, s)
            s = _mask_fio_by_dictionary(s)

            def _stray_sub(m: re.Match) -> str:
                _remember_fio(m.group(0).strip())
                return m.group(1) + "[FIO]"
            s = stray_surname_table_re.sub(_stray_sub, s)

            def _patient_fio_sub(m: re.Match) -> str:
                name = m.group(2).strip()
                toks = name.split()
                if _is_not_fio(name):
                    return m.group(0)
                if len(toks) >= 2 or any(_is_strong_name_token(t) for t in toks):
                    _remember_fio(name)
                    return m.group(1) + " [FIO]"
                return m.group(0)
            s = patient_fio_inline_re.sub(_patient_fio_sub, s)

    if passport_ctx:
        s = passport_series_inline_re.sub(r"\1[PASSPORT]", s)
        s = passport_num_re.sub("[PASSPORT]", s)
        s = passport_number_inline_in_context_re.sub(r"\1[PASSPORT]", s)

    def _dob_age_row_sub(m: re.Match) -> str:
        return f"{m.group(1)}{m.group(3)}"
    s = dob_age_inline_row_re.sub(_dob_age_row_sub, s)

    s = dob_date_inline_re.sub(_dob_date_inline_to_age, s)
    s = dob_split_inline_re.sub(_dob_split_inline_to_age, s)

    m_dob_tbl = dob_table_re.match(s)
    if m_dob_tbl:
        label, rest = m_dob_tbl.groups()
        s = label + (find_age_from_text(rest) or "[AGE]")

    m_inl = dob_label_inline_re.match(s)
    if m_inl:
        label, rest = m_inl.groups()
        if not re.search(r"[а-яё]+\s*[:\-]\s*", rest, re.IGNORECASE):
            s = label + (find_age_from_text(rest) or "[AGE]")

    m_dobline = dob_line_re.match(s)
    if m_dobline and any_raw_date_re.search(m_dobline.group(2)):
        label, rest = m_dobline.groups()
        s = label + " " + (find_age_from_text(rest) or "[AGE]")

    m_age_inl = age_label_inline_re.match(s)
    if m_age_inl:
        label, rest = m_age_inl.groups()
        s = label + (find_age_from_text(rest) or "[AGE]")

    s = _mask_bare_dob_after_fio_in_line(s)
    s = _mask_dob_next_to_fio(s, force=bool(PATIENT_MARKER_RE.search(s)))

    m_wk = workplace_inline_re.match(s)
    if m_wk and m_wk.group(2):
        s = m_wk.group(1) + "[WORKPLACE]"
    else:
        m_pos = position_inline_re.match(s)
        if m_pos and m_pos.group(2):
            s = m_pos.group(1) + "[POSITION]"

    m_addr_inl = ADDRESS_LABEL_INLINE_RE.match(s)
    if m_addr_inl:
        s = m_addr_inl.group(1) + "[ADDRESS]"
    elif not clinical_ctx and MIDLINE_ADDR_RE.search(s):
        s = MIDLINE_ADDR_RE.sub(lambda m: m.group(1) + "[ADDRESS]", s)
    elif not clinical_ctx:
        m_addr_nopunct = ADDRESS_LABEL_NOPUNCT_INLINE_RE.match(s)
        if m_addr_nopunct:
            s = m_addr_nopunct.group(1) + " [ADDRESS]" + s[m_addr_nopunct.end(2):]

    if lives_in_inline_re.search(s):
        s = lives_in_inline_re.sub("Проживает [ADDRESS]", s)
        s = re.sub(r"\[ADDRESS\][\s.)]*", "[ADDRESS].", s)

    if not clinical_ctx and (street_line_re.match(s) or looks_like_address(s)):
        if MED_ORG_LINE_RE.search(s):
            s = mask_address_tail(s)
        else:
            left_ws = re.match(r"^\s*", s).group(0)
            s = left_ws + "[ADDRESS]"

    # Телефон: при явной метке («тел.», «контактный телефон») маскируем любую
    # 10/11-значную последовательность — и делаем это ДО СНИЛС, иначе номер
    # телефона получал метку [SNILS]. Без метки — только строгие формы, чтобы
    # не портить номера рецептурных бланков в назначениях.
    if phone_label_re.search(s):
        s = phone_re.sub("[PHONE]", s)
    s = intl_phone_re.sub("[PHONE]", s)
    if not docnum_context_re.search(s):
        s = strict_phone_re.sub("[PHONE]", s)
        s = snils_re.sub("[SNILS]", s)

    return s + original_ending


# ==================== ОСНОВНАЯ ДЕПЕРСОНАЛИЗАЦИЯ ====================

def depersonalize(text: str, mem: "PIIMemory | None" = None, sweep: bool = True) -> str:
    global _MEM
    _MEM = mem if mem is not None else PIIMemory()

    text = normalize_quoted_dates(norm(text))
    lines = text.splitlines(keepends=True)
    study_idx = mark_study_regions(lines)
    out = []
    i = 0
    n = len(lines)

    def _consume_value_line(start_idx: int):
        j = start_idx
        while j < n and _normline(lines[j]) == "":
            out.append(lines[j])
            j += 1
        if j >= n:
            return j, None, "\n"
        end = _line_ending(lines[j])
        core = lines[j][:-len(end)] if end else lines[j]
        return j + 1, norm(core), (end if end else "\n")

    def _emit_tag_and_consume_block(label_span: int, tag: str):
        for k in range(label_span):
            out.append(lines[i + k])
        end = _line_ending(lines[i + label_span - 1]) or "\n"
        if not _line_ending(lines[i + label_span - 1]):
            out[-1] = out[-1] + "\n"
        out.append(tag + end)
        return consume_value_block(lines, i + label_span)

    while i < n:
        line = lines[i]
        stripped = _normline(line)
        study_ctx = i in study_idx
        passport_ctx = has_passport_context(lines, i)
        doctor_ctx_above = has_doctor_context_above(lines, i)
        doctor_ctx_below = has_doctor_context_below(lines, i)
        doctor_ctx = doctor_ctx_above or doctor_ctx_below

        if org_id_re.search(stripped):
            out.append(line)
            i += 1
            continue

        if is_card_number_line(stripped) or (
            is_header_block_above(lines, i)
            and re.match(r"(?i)^\s*(?:№|no\.?|номер)\b", stripped)
        ):
            end = _line_ending(line)
            core = line[:-len(end)] if end else line
            masked = medical_record_inline_re.sub(r"\1\2[MEDICAL_RECORD]", core)
            if masked == core:
                label = re.match(r"(?i)^(\s*(?:№|no\.?|номер)\b\s*[:\-]?\s*)", core)
                masked = (label.group(1) if label else "") + "[MEDICAL_RECORD]"
            out.append(masked + end)
            i += 1
            continue

        if doctor_label_only_re.match(stripped):
            out.append(line)
            i += 1
            continue

        span = match_label_span(lines, i, ADDRESS_LABEL_RE, max_join=3)
        if span:
            nxt = _emit_tag_and_consume_block(span, "[ADDRESS]")
            i = nxt
            continue

        end_i = _line_ending(line)
        m_addr_top = ADDRESS_LABEL_INLINE_RE.match(norm(line[:-len(end_i)] if end_i else line))
        if m_addr_top:
            out.append(m_addr_top.group(1) + "[ADDRESS]" + (end_i or "\n"))
            i = consume_value_block(lines, i + 1)
            continue

        if workplace_label_only_re.match(stripped):
            out.append(line)
            nxt_i, _, end = _consume_value_line(i + 1)
            out.append("[WORKPLACE]" + end)
            i = nxt_i
            continue

        if position_label_only_re.match(stripped):
            out.append(line)
            nxt_i, _, end = _consume_value_line(i + 1)
            out.append("[POSITION]" + end)
            i = nxt_i
            continue

        if dob_age_tag_re.match(stripped):
            out.append(line)
            nxt_i, val, end = _consume_value_line(i + 1)
            out.append((find_age_from_text(val or "") or "[AGE]") + end)
            i = nxt_i
            continue

        if dob_tag_re.match(stripped):
            out.append(line)
            nxt_i, val, end = _consume_value_line(i + 1)
            out.append((find_age_from_text(val or "") or "[AGE]") + end)
            i = nxt_i
            continue

        if age_tag_re.match(stripped):
            out.append(line)
            nxt_i, val, end = _consume_value_line(i + 1)
            out.append((find_age_from_text(val or "") or "[AGE]") + end)
            i = nxt_i
            continue

        if snils_tag_re.match(stripped):
            out.append(line)
            nxt_i, _, end = _consume_value_line(i + 1)
            out.append("[SNILS]" + end)
            i = nxt_i
            continue

        if fio_tag_only_re.match(stripped) and not study_ctx:
            out.append(line)
            nxt_i, val, end = _consume_value_line(i + 1)
            if doctor_ctx_below:
                out.append((val or "") + end)
            else:
                _remember_fio_strict(val)
                out.append("[FIO]" + end)
            i = nxt_i
            continue

        if not study_ctx and (
            surname_label_only_re.match(stripped)
            or firstname_label_only_re.match(stripped)
            or patronymic_label_only_re.match(stripped)
        ):
            out.append(line)
            nxt_i, val, end = _consume_value_line(i + 1)
            if doctor_ctx_below:
                out.append((val or "") + end)
            else:
                _remember_fio_strict(val)
                out.append("[FIO]" + end)
            i = nxt_i
            continue

        if passport_series_only_re.match(stripped):
            out.append(line)
            nxt_i, _, end = _consume_value_line(i + 1)
            out.append("[PASSPORT]" + end)
            i = nxt_i
            continue

        if card_no_label_only_re.match(stripped):
            out.append(line)
            nxt_i, _, end = _consume_value_line(i + 1)
            out.append("[MEDICAL_RECORD]" + end)
            i = nxt_i
            continue

        if passport_number_only_re.match(stripped):
            out.append(line)
            nxt_i, val, end = _consume_value_line(i + 1)
            digits = re.sub(r"\D", "", (val or ""))
            if passport_ctx and 6 <= len(digits) <= 10:
                out.append("[PASSPORT]" + end)
            else:
                out.append((val or "") + end)
            i = nxt_i
            continue

        if card_label_inline_re.search(stripped):
            out.append(medical_record_inline_re.sub(r"\1\2[MEDICAL_RECORD]", line))
            i += 1
            continue

        if (
            bare_date_line_re.match(stripped)
            and is_table_dob_context(lines, i)
            and not has_study_signature_context(lines, i)
        ):
            m = bare_date_line_re.match(norm(line).strip())
            d, mo, y = m.groups()
            end = _line_ending(line)
            age = calc_age_from_str(f"{int(d):02d}.{int(mo):02d}.{int(y):04d}")
            out.append((age_phrase(age)) + end)
            i += 1
            continue

        out.append(clean_line_single(
            line,
            passport_ctx=passport_ctx,
            doctor_ctx=doctor_ctx,
            study_ctx=study_ctx,
        ))
        i += 1

    text2 = "".join(out)

    # ==================== ГЛОБАЛЬНЫЕ МАСКИ (построчно) ====================
    masked_lines = []
    prev_is_card_label = False
    card_label_only_strict_re = re.compile(r"(?i)^\s*(?:№|номер)\s*карты\s*[:\-]?\s*$")

    def _global_masks(line: str) -> str:
        line = intl_phone_re.sub("[PHONE]", line)
        line = email_re.sub("[EMAIL]", line)
        line = inn_labeled_re.sub(lambda m: m.group(1) + "[INN]", line)
        line = policy_labeled_re.sub(lambda m: m.group(1) + "[POLICY]", line)
        line = policy_number_re.sub(r"\1[POLICY]", line)
        line = policy_issue_date_re.sub(lambda m: m.group(1) + "[DATE]", line)
        line = sick_leave_labeled_re.sub(lambda m: m.group(1) + "[SICKLEAVE]", line)
        if not docnum_context_re.search(line):
            line = snils_re.sub("[SNILS]", line)
        return line

    for ln in text2.splitlines(keepends=True):
        low = _normline(ln)
        low_stripped = low.strip()

        if org_id_re.search(low):
            masked_lines.append(ln)
            prev_is_card_label = False
            continue

        is_card_ctx = (
            card_context_inline_re.search(low) is not None
            or card_label_inline_re.search(low) is not None
            or docnum_context_re.search(low) is not None
            or is_card_number_line(low_stripped)
        )
        is_phone_ctx = phone_label_re.search(low) is not None

        if is_phone_ctx:
            ln2 = phone_re.sub("[PHONE]", ln)
            prev_is_card_label = False
        elif is_card_ctx:
            ln2 = ln
        elif prev_is_card_label and low_stripped:
            ln2 = ln
            prev_is_card_label = False
        else:
            # Без телефонной метки — только строгие формы номера, иначе любые
            # 10 цифр (номер рецептурного бланка и т.п.) стали бы [PHONE].
            ln2 = strict_phone_re.sub("[PHONE]", ln)

        masked_lines.append(_global_masks(ln2))

        if low_stripped:
            prev_is_card_label = bool(card_label_only_strict_re.fullmatch(low_stripped))

    text2 = "".join(masked_lines)

    # Затирание СИРОЙ даты, оставшейся после метки «дата выдачи полиса…».
    # Из Word/ODT ячейка таблицы иногда извлекается двумя строками:
    #   строка 1: «дата выдачи полиса…: [DATE]»  (или голая дата, потом маска)
    #   строка 2: «27.05.2021»                    ← сирота-дубликат
    #   строка 3: «данные о страховой мед. организации…»
    # Ловим шаблон: строка с контекстом «дата выдачи полис…» → (пусто/[DATE]) →
    # голая дата → строка с «данные о страховой…» ЛИБО просто голая дата сразу
    # после [DATE]-строки, содержащей контекст даты выдачи.
    text2 = _mask_orphan_policy_issue_date(text2)
    text2 = _mask_orphan_dob_before_label(text2)
    text2 = _mask_dob_after_fio_line(text2)

    text2 = extra_safety_pass(text2)

    if sweep:
        text2 = _MEM.sweep_fio(text2)
    text2 = strict_privacy_pass(text2)
    _MEM = None

    return sanitize_for_windows(text2)


def _mask_orphan_policy_issue_date(text: str) -> str:
    """Затирает голую дату-сироту, оставшуюся после метки «дата выдачи полиса…».

    Word/ODT-таблица извлекается так, что дата выдачи повторяется на отдельной
    строке (перед строкой «данные о страховой мед. организации…»). Обычные
    регексы её не ловят: вокруг ничего кроме цифр.

    Стратегия — построчный автомат:
      1. Запоминаем «есть контекст даты выдачи полиса» на строке с такой меткой.
      2. Пока идут пустые/технические строки и строки, в которых уже есть [DATE],
         контекст удерживается.
      3. Первая же голая дата (цифрами или с текстовым месяцем) на своей строке
         затирается в [DATE], и контекст сбрасывается.
      4. При любой содержательной строке (буквы) контекст также сбрасывается,
         кроме случая, когда следующая строка — «данные о страховой…»: тогда
         последний увиденный кандидат-даты, если он был, тоже затирается.
    """
    lines = text.split("\n")
    n = len(lines)
    ctx_active = False
    result = []
    for idx, line in enumerate(lines):
        stripped = line.strip()

        # Обновляем контекст: метка «дата выдачи полис…» + маркер [DATE] или голая дата.
        if policy_issue_date_ctx_re.search(line):
            ctx_active = True
            result.append(line)
            continue

        if ctx_active:
            # Пустые строки — не ломают контекст.
            if not stripped:
                result.append(line)
                continue
            # Голая дата на своей строке → это и есть сирота, затираем.
            if _orphan_bare_date_line_re.match(stripped):
                # Сохраняем ведущие/хвостовые пробелы.
                m = re.match(r"^(\s*).*?(\s*)$", line)
                lead = m.group(1) if m else ""
                trail = m.group(2) if m else ""
                result.append(f"{lead}[DATE]{trail}")
                ctx_active = False
                continue
            # Строка с «[DATE]» и/или продолжением метки — оставляем, контекст держим.
            if "[DATE]" in line:
                result.append(line)
                continue
            # Сирота-дата склеена reflow'ом с текстом следующего поля — затираем
            # только сам датовый префикс, остальное строки не трогаем.
            m_lead = _orphan_leading_date_re.match(line)
            if m_lead:
                result.append(f"{m_lead.group(1)}[DATE]{m_lead.group(3) or ''}")
                ctx_active = False
                continue
            # Любая другая содержательная строка — контекст сбрасывается.
            ctx_active = False

        result.append(line)
    return "\n".join(result)


# Значение поля «Дата рождения» на строке ПЕРЕД её меткой (см. ниже).
_bare_dob_before_label_re = re.compile(
    r"^(\s*)(\d{1,2})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{4})"
    r"(?:\s*,\s*\d{1,3}\s*(?:лет|года?|л\.)?)?"
    r"(\s*)$"
)
_dob_label_start_re = re.compile(r"(?i)^\s*(?:\d+\s*[.)]\s*)?дата\s+рождени\w*\b")


def _mask_orphan_dob_before_label(text: str) -> str:
    """Затирает дату рождения, выведенную В СТРОКЕ ПЕРЕД меткой «Дата рождения».

    Шаблоны «Лист назначений», «Лист регистрации трансфузии» и т.п. рисуют
    значение и подписи трёх соседних полей («Дата рождения:», «№ медицинской
    карты:», «№ палаты:») в разных ячейках одной таблицы; PyMuPDF извлекает
    их сверху вниз, поэтому строка со значением («21.08.1982, 43») оказывается
    ПЕРЕД строкой с меткой. Обычные регексы ждут порядок «метка -> значение»
    и это пропускают.
    """
    lines = text.split("\n")
    n = len(lines)
    for idx in range(n - 1):
        m = _bare_dob_before_label_re.match(lines[idx])
        if not m:
            continue
        j = idx + 1
        while j < n and lines[j].strip() == "":
            j += 1
        if j >= n or not _dob_label_start_re.match(lines[j]):
            continue
        d, mo, y = int(m.group(2)), int(m.group(3)), int(m.group(4))
        age = calc_age_from_str(f"{d:02d}.{mo:02d}.{y:04d}")
        repl = age_phrase(age)
        lines[idx] = f"{m.group(1)}{repl}{m.group(5)}"
    return "\n".join(lines)


_fio_only_line_re = re.compile(r"^\[FIO\],?$")
_leading_bare_date_re = re.compile(r"^(\s*)(\d{1,2})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{4})\b")


def _mask_dob_after_fio_line(text: str) -> str:
    """Затирает дату рождения на строке СРАЗУ ПОСЛЕ отдельной строки «[FIO]».

    «Выписной эпикриз» выводит ФИО пациента отдельной строкой без метки
    («[FIO],»), а дату рождения — следующей строкой, тоже без метки
    («21.08.1982 (возраст на момент поступления: 43 лет...) Жен»). Штатной
    метки «дата рождения» тут нет вовсе, поэтому обычные регексы её не ловят.
    """
    lines = text.split("\n")
    prev_is_fio_only = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if prev_is_fio_only:
            m = _leading_bare_date_re.match(line)
            if m:
                d, mo, y = int(m.group(2)), int(m.group(3)), int(m.group(4))
                age = calc_age_from_str(f"{d:02d}.{mo:02d}.{y:04d}")
                repl = age_phrase(age)
                lines[idx] = line[:m.start(2)] + repl + line[m.end(4):]
        prev_is_fio_only = bool(_fio_only_line_re.match(stripped))
    return "\n".join(lines)


# ==================== ДОП. СЕТИ БЕЗОПАСНОСТИ ====================

RUSSIAN_FIRST_NAMES = frozenset({
    "Александр", "Алексей", "Анатолий", "Андрей", "Антон", "Аркадий", "Арсений",
    "Артём", "Артем", "Артур", "Богдан", "Борис", "Вадим", "Валентин", "Валерий",
    "Василий", "Виктор", "Виталий", "Владимир", "Владислав", "Вячеслав", "Геннадий",
    "Георгий", "Глеб", "Григорий", "Даниил", "Данил", "Денис", "Дмитрий", "Евгений",
    "Егор", "Иван", "Игорь", "Илья", "Кирилл", "Константин", "Лев", "Леонид",
    "Максим", "Марк", "Матвей", "Михаил", "Никита", "Николай", "Олег", "Павел",
    "Пётр", "Петр", "Роман", "Руслан", "Светослав", "Семён", "Семен", "Сергей",
    "Станислав", "Степан", "Тимофей", "Тимур", "Фёдор", "Федор", "Эдуард", "Юрий",
    "Ян", "Ярослав",
    "Александра", "Алёна", "Алена", "Алина", "Алла", "Анастасия", "Ангелина",
    "Анжела", "Анна", "Антонина", "Валентина", "Валерия", "Варвара", "Вера",
    "Вероника", "Виктория", "Галина", "Дарья", "Диана", "Евгения", "Екатерина",
    "Елена", "Елизавета", "Жанна", "Зинаида", "Зоя", "Инна", "Ирина", "Карина",
    "Кристина", "Ксения", "Лариса", "Лидия", "Любовь", "Людмила", "Маргарита",
    "Марина", "Мария", "Надежда", "Наталья", "Наталия", "Нина", "Оксана", "Ольга",
    "Полина", "Раиса", "Регина", "Светлана", "София", "Софья", "Тамара", "Татьяна",
    "Ульяна", "Юлия", "Яна",
})

_FIRST_NAMES_LOWER = frozenset(n.lower() for n in RUSSIAN_FIRST_NAMES)

_CAP_WORD = r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?"
_NAME_ALT = "|".join(sorted(RUSSIAN_FIRST_NAMES, key=len, reverse=True))
_dict_fio_name_first_re = re.compile(rf"\b(?:{_NAME_ALT})\s+{_CAP_WORD}(?:\s+{_CAP_WORD})?")
_dict_fio_name_second_re = re.compile(rf"\b{_CAP_WORD}\s+(?:{_NAME_ALT})\b")


def _mask_fio_by_dictionary(s: str) -> str:
    def repl(m: re.Match) -> str:
        if _has_org_geo_word(m.group(0)):
            return m.group(0)
        _remember_fio(m.group(0))
        return "[FIO]"
    s = _dict_fio_name_first_re.sub(repl, s)
    s = _dict_fio_name_second_re.sub(repl, s)
    return s


enp_re = re.compile(r"(?<!\d)\d{4}\s?\d{4}\s?\d{4}\s?\d{4}(?!\d)")
year_birth_re = re.compile(r"(?i)\b((?:19|20)\d{2})\s*(?:г\.?\s?р\.?|года?\s+рожд\w*)")
year_birth_re2 = re.compile(r"(?i)(?:\bг\.?\s?р\.?|\bгод\s+рождения)\s*[:\-]?\s*((?:19|20)\d{2})\b")


def _year_to_age(year: int) -> str:
    age = date.today().year - year
    return age_phrase(age) if 0 <= age <= 150 else "[AGE]"


def extra_safety_pass(text: str) -> str:
    if not text:
        return text
    out = []
    for line in text.splitlines(keepends=True):
        low = line.lower()
        if not (card_context_inline_re.search(low) or "карт" in low or "истори" in low):
            line = enp_re.sub("[POLICY]", line)
        out.append(line)
    text = "".join(out)

    def _yb(m: re.Match) -> str:
        y = int(re.search(r"(?:19|20)\d{2}", m.group(0)).group(0))
        return _year_to_age(y)

    text = year_birth_re.sub(_yb, text)
    text = year_birth_re2.sub(_yb, text)
    return text


_STAFF_LABEL_VALUE_RE = re.compile(
    r"(?i)("
    r"\b(?:фио\s+)?(?:лечащ\w+\s+)?"
    r"(?:врач\w*|доктор\w*|медсестр\w*|медбрат\w*|фельдшер\w*|акушер\w*|"
    r"заведующ\w*|ординатор\w*|лаборант\w*|рентгенолог\w*|реаниматолог\w*)"
    r"\b\s*[:\-]\s*"
    r")"
    r"((?:[А-ЯЁ][а-яё]+|[А-ЯЁ]\.)"
    r"(?:\s+(?:[А-ЯЁ][а-яё]+|[А-ЯЁ]\.)){0,2})"
)


def strict_privacy_pass(text: str) -> str:
    """Финальный строгий проход: номера историй и ФИО сотрудников тоже ПДн."""
    output = []
    staff_value_expected = False

    for line in text.splitlines(keepends=True):
        ending = _line_ending(line)
        core = line[:-len(ending)] if ending else line
        stripped = core.strip()

        if staff_value_expected and stripped:
            if (
                _is_namelike(stripped)
                or fio_line_triplet_re.match(stripped)
                or fio_line_initials_re.match(stripped)
                or fio_upper_triplet_line_re.match(stripped)
                or fio_upper_with_initials_line_re.match(stripped)
            ):
                leading = re.match(r"^\s*", core).group(0)
                output.append(leading + "[FIO]" + ending)
                staff_value_expected = False
                continue
            staff_value_expected = False

        core = medical_record_inline_re.sub(r"\1\2[MEDICAL_RECORD]", core)
        core = _STAFF_LABEL_VALUE_RE.sub(r"\1[FIO]", core)
        core = fio_triplet_inline_re.sub("[FIO]", core)
        core = fio_with_initials_inline_re.sub("[FIO]", core)
        core = fio_upper_triplet_inline_re.sub("[FIO]", core)
        core = fio_upper_with_initials_inline_re.sub("[FIO]", core)
        core = fio_initials_upper_inline_re.sub("[FIO]", core)
        core = _mask_fio_by_dictionary(core)

        output.append(core + ending)
        staff_value_expected = bool(doctor_label_only_re.fullmatch(stripped))

    return "".join(output)


# ==================== ФОРМАТТЕР: СБОРКА PDF ИЗ ТЕКСТА ====================

_REFLOW_CONT_PUNCT = frozenset(")]},;»")
_REFLOW_TERMINATORS = (".", "!", "?", "…")


# Точка после сокращения («…2026 г.», «…59 мин.») — не конец предложения.
_ABBREV_TAIL_RE = re.compile(
    r"(?i)(?:^|[\s(«\"])(?:гг?|мин|час|сек|ул|д|кв|корп|стр|обл|респ|пос|дер|им|"
    r"тел|руб|коп|мл|мг|мкг|см|мм|кг|шт|табл|амп|мес|нед|сут|др|пр|рис|прим|№)\.$"
)
# Строка оборвана на предлоге/союзе — продолжение точно ниже.
_DANGLING_TAIL_RE = re.compile(
    r"(?i)(?:^|\s)(?:в|во|с|со|на|по|к|ко|у|из|изо|от|ото|для|при|над|под|о|об|обо|"
    r"за|до|перед|через|между|и|а|но|или|что|чтобы|как|чем|же)$"
)
# Голая дата (возможно с возрастом) на своей строке — это значение поля из
# соседней ячейки таблицы, приклеивать её к предыдущей строке нельзя.
_REFLOW_BARE_DATE_LINE_RE = re.compile(
    r"^\s*\d{1,2}\s*[.\-/]\s*\d{1,2}\s*[.\-/]\s*\d{2,4}"
    r"\s*(?:,\s*\d{1,3}(?:\s*(?:лет|года?|л\.))?)?\s*$"
)


def _reflow_should_join(prev: str, nxt: str) -> bool:
    p = prev.strip()
    if not p:
        return False
    if _DANGLING_TAIL_RE.search(p):
        return True
    if p.endswith(_REFLOW_TERMINATORS) and not _ABBREV_TAIL_RE.search(p):
        return False
    first = nxt[:1]
    if p.endswith(":"):
        return True
    if first.islower():
        return True
    if first in _REFLOW_CONT_PUNCT:
        return True
    if first.isascii() and first.isalpha():
        return True
    # Хвост, оторванный по ширине колонки: «…, ОГРН» / «1023402636575».
    if (
        first.isdigit()
        and not NUMBERED_ITEM_RE.match(nxt)
        and not _REFLOW_BARE_DATE_LINE_RE.match(nxt)
    ):
        return True
    if p.endswith("-") and not p.endswith(("—", "–")):
        return True
    return False


# ==================== НОРМАЛИЗАЦИЯ ВЁРСТКИ ====================
# МИС-выгрузка выравнивает поля пробелами, из-за чего в выходном PDF остаются
# «дыры» вида «Камни мочеточника          код по МКБ N20.1» и рваные отступы.
# Приводим к обычному виду: один пробел между словами, без висячих отступов.
#
# Поставьте False, чтобы сохранить исходное выравнивание колонок (например,
# чтобы таблицы лабораторных результатов остались «столбиками»).
NORMALIZE_LAYOUT = True

_MULTISPACE_RE = re.compile(r"[ \t\u00a0]{2,}")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,;:.!?%)»\]])")
_SPACE_AFTER_OPEN_RE = re.compile(r"([(«\[])\s+")


def normalize_layout(text: str) -> str:
    if not text or not NORMALIZE_LAYOUT:
        return text
    out = []
    blank_run = 0
    for raw in text.split("\n"):
        line = _MULTISPACE_RE.sub(" ", raw.replace("\t", " ")).strip()
        if line:
            line = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", line)
            line = _SPACE_AFTER_OPEN_RE.sub(r"\1", line)
            line = re.sub(r"\s+", " ", line)
            blank_run = 0
        else:
            blank_run += 1
            if blank_run > 1:
                continue
        out.append(line)
    while out and not out[0]:
        out.pop(0)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


def reflow_text(text: str) -> str:
    if not text:
        return text
    out = []
    for raw in text.split("\n"):
        line = raw.rstrip()
        stripped = line.strip()
        is_boundary = stripped == "" or set(stripped) <= {"-"}
        prev_boundary = (not out) or out[-1].strip() == "" or set(out[-1].strip()) <= {"-"}
        if is_boundary or prev_boundary:
            out.append(line)
            continue
        prev_r = out[-1].rstrip()
        if _reflow_should_join(prev_r, stripped):
            if prev_r.endswith("-") and not prev_r.endswith(("—", "–")):
                out[-1] = prev_r[:-1] + stripped
            else:
                out[-1] = prev_r + " " + stripped
        else:
            out.append(line)
    return "\n".join(out)


# ==================== ПОИСК ШРИФТА С КИРИЛЛИЦЕЙ (кроссплатформенно) ====================
_FONT_CANDIDATES = (
    # Windows
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
    r"C:\Windows\Fonts\times.ttf",
    r"C:\Windows\Fonts\verdana.ttf",
    # macOS
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Tahoma.ttf",
    "/System/Library/Fonts/Supplemental/Verdana.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "/Library/Fonts/Arial.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/Library/Fonts/Tahoma.ttf",
    "/Library/Fonts/Verdana.ttf",
    "/Library/Fonts/Times New Roman.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
    "/usr/share/fonts/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
)

_FONT_DIRS = (
    "/System/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
    "/Library/Fonts",
    os.path.expanduser("~/Library/Fonts"),
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    os.path.expanduser("~/.fonts"),
    os.path.expanduser("~/.local/share/fonts"),
    r"C:\Windows\Fonts",
)

_FONT_NAME_PREFERENCE = (
    "arial.ttf",
    "arialuni.ttf", "arial unicode.ttf",
    "tahoma.ttf",
    "verdana.ttf",
    "times.ttf", "times new roman.ttf",
    "dejavusans.ttf",
    "liberationsans-regular.ttf",
    "notosans-regular.ttf",
    "helvetica.ttc",
    "helveticaneue.ttc",
)


def _find_cyrillic_font():
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    preference = {name: i for i, name in enumerate(_FONT_NAME_PREFERENCE)}
    best_rank = None
    best_path = None
    for d in _FONT_DIRS:
        if not os.path.isdir(d):
            continue
        for ext in ("*.ttf", "*.ttc", "*.otf", "*.TTF", "*.TTC", "*.OTF"):
            for p in glob.iglob(os.path.join(d, "**", ext), recursive=True):
                rank = preference.get(os.path.basename(p).lower())
                if rank is None:
                    continue
                if best_rank is None or rank < best_rank:
                    best_rank, best_path = rank, p
                    if rank == 0:
                        return best_path
    return best_path


def _wrap_line(line, font, fontsize, max_width):
    line = line.rstrip()
    if not line:
        return [""]
    result = []
    current = ""
    for word in line.split(" "):
        trial = word if current == "" else current + " " + word
        if font.text_length(trial, fontsize) <= max_width:
            current = trial
            continue
        if current:
            result.append(current)
            current = ""
        if font.text_length(word, fontsize) > max_width:
            chunk = ""
            for ch in word:
                if chunk == "" or font.text_length(chunk + ch, fontsize) <= max_width:
                    chunk += ch
                else:
                    result.append(chunk)
                    chunk = ch
            current = chunk
        else:
            current = word
    if current:
        result.append(current)
    return result or [""]


def _should_report_progress(current, total):
    """Ограничивает число событий прогресса примерно сотней на один этап."""
    if total <= 0:
        return False
    step = max(1, total // 100)
    return current == 1 or current == total or current % step == 0


def render_text_pdf(page_texts, page_rects, fontsize=9.0, margin=36.0, on_progress=None):
    if fitz is None:
        return None
    fontfile = _find_cyrillic_font()
    if fontfile is None:
        return None

    font = fitz.Font(fontfile=fontfile)
    fontname = "doc"
    leading = fontsize * 1.35
    out = fitz.open()

    total_lines = sum(max(1, len(text.split("\n"))) for text in page_texts)
    processed_lines = 0

    for text, rect in zip(page_texts, page_rects):
        width = rect.width or 595.0
        height = rect.height or 842.0
        max_width = width - 2 * margin
        bottom = height - margin

        wrapped = []
        for line in text.split("\n"):
            wrapped.extend(_wrap_line(line, font, fontsize, max_width))
            processed_lines += 1
            if on_progress and _should_report_progress(processed_lines, total_lines):
                on_progress("render", processed_lines, total_lines)

        page = out.new_page(width=width, height=height)
        page.insert_font(fontname=fontname, fontfile=fontfile)
        y = margin + fontsize
        for line in wrapped:
            if y > bottom:
                page = out.new_page(width=width, height=height)
                page.insert_font(fontname=fontname, fontfile=fontfile)
                y = margin + fontsize
            if line:
                page.insert_text((margin, y), line, fontname=fontname, fontsize=fontsize)
            y += leading

    if out.page_count == 0:
        out.new_page()
    return out


# ==================== PDF: ИЗВЛЕЧЕНИЕ + ДЕТЕКТ СКАНОВ ====================

SCAN_PLACEHOLDER = "[СКАН/ИЗОБРАЖЕНИЕ: текст не извлечён — ТРЕБУЕТСЯ РУЧНАЯ ПРОВЕРКА]"
A4_RECT_WH = (595.0, 842.0)


def build_pages_from_pdf(path: str, on_progress=None):
    doc = fitz.open(path)
    page_texts, page_rects = [], []
    scan_pages, image_pages = [], []
    mem = PIIMemory()
    text_page_idx = []
    try:
        for idx, page in enumerate(doc, start=1):
            rect = page.rect
            raw = page.get_text("text", sort=True)
            has_images = bool(page.get_images(full=True))
            page_rects.append(rect)
            if raw.strip() == "":
                page_texts.append(SCAN_PLACEHOLDER if has_images else "")
                if has_images:
                    scan_pages.append(idx)
                if on_progress:
                    on_progress("anonymize", idx, doc.page_count)
                continue
            if has_images:
                image_pages.append(idx)
            page_texts.append(depersonalize(reflow_text(raw), mem=mem, sweep=False))
            text_page_idx.append(len(page_texts) - 1)
            if on_progress:
                on_progress("anonymize", idx, doc.page_count)
        for position, k in enumerate(text_page_idx, start=1):
            page_texts[k] = normalize_layout(
                sanitize_for_windows(mem.sweep_fio(page_texts[k]))
            )
            if on_progress:
                on_progress("finalize", position, len(text_page_idx))
        return page_texts, page_rects, scan_pages, image_pages
    finally:
        doc.close()


def build_pages_from_text(text: str):
    cleaned = normalize_layout(depersonalize(text or ""))
    rect = fitz.Rect(0, 0, *A4_RECT_WH)
    return [cleaned], [rect]


def save_clean_pdf(page_texts, page_rects, out_path: str, on_progress=None):
    out = render_text_pdf(page_texts, page_rects, on_progress=on_progress)
    if out is None:
        raise RuntimeError("не найден шрифт с кириллицей — PDF не собран")
    try:
        out.set_metadata({})
        try:
            out.del_xml_metadata()
        except Exception:
            pass
        out.save(out_path, garbage=4, deflate=True)
    finally:
        out.close()


# ==================== АУДИТ ОСТАТОЧНЫХ ПДн ====================

AUDIT_PATTERNS = (
    ("ТЕЛЕФОН", strict_phone_re),
    ("ТЕЛЕФОН-МЕЖД", intl_phone_re),
    ("EMAIL", email_re),
    ("СНИЛС", snils_re),
    ("ИНН", inn_labeled_re),
    ("ПАСПОРТ", passport_num_re),
    ("ЕНП/ПОЛИС-16", enp_re),
    ("МЕДКАРТА", medical_record_inline_re),
    ("ФИО-ТРИПЛЕТ", fio_triplet_inline_re),
    ("ФИО-ИНИЦИАЛЫ", fio_with_initials_inline_re),
    ("ФИО-КАПС", fio_upper_triplet_inline_re),
    ("ГОД-РОЖДЕНИЯ", year_birth_re),
    ("ЛИСТ-НЕТРУДОСП", sick_leave_labeled_re),
)
_NUMERIC_AUDIT_KINDS = {"ТЕЛЕФОН", "ТЕЛЕФОН-МЕЖД", "СНИЛС", "ЕНП/ПОЛИС-16"}
_FIO_AUDIT_KINDS = {"ФИО-ТРИПЛЕТ", "ФИО-ИНИЦИАЛЫ", "ФИО-КАПС"}


def audit_pdf(out_path: str, on_progress=None):
    findings = []
    try:
        doc = fitz.open(out_path)
    except Exception:
        return findings
    try:
        pages = []
        for idx, page in enumerate(doc, start=1):
            pages.append(page.get_text("text"))
            if on_progress:
                on_progress("audit", idx, doc.page_count)
        full = "\n".join(pages)
    finally:
        doc.close()

    full = norm(full)
    for line in full.splitlines():
        s = line.strip()
        if not s or s.startswith("[СКАН"):
            continue
        low = s.lower()
        if org_id_re.search(low):
            continue
        card_ctx = bool(card_context_inline_re.search(low)) or "карт" in low or "истори" in low
        doctor_ctx = bool(DOCTOR_CONTEXT_RE.search(low))
        for kind, rx in AUDIT_PATTERNS:
            if card_ctx and kind in _NUMERIC_AUDIT_KINDS:
                continue
            if doctor_ctx and kind in _FIO_AUDIT_KINDS:
                continue
            if rx.search(s):
                findings.append((kind, s[:160]))
                break
    return findings


def write_audit_report(reports):
    path = os.path.join(OUTPUT_DIR, "_ОТЧЁТ_audit.txt")
    lines = [
        "ОТЧЁТ ПО ОБЕЗЛИЧИВАНИЮ",
        f"Дата: {datetime.now():%Y-%m-%d %H:%M}",
        f"Обработано файлов: {len(reports)}",
        "",
    ]
    warned = 0
    for r in reports:
        problems = []
        if r.get("error"):
            problems.append(f"ОШИБКА ОБРАБОТКИ: {r['error']}")
        if r.get("scan_pages"):
            problems.append(
                "СКАН без извлекаемого текста на стр. "
                f"{r['scan_pages']} — проверить исходник вручную"
            )
        for kind, snippet in r.get("findings", []):
            problems.append(f"ВОЗМОЖНА ПДн [{kind}]: {snippet}")
        if r.get("image_pages"):
            problems.append(
                f"картинки отброшены (текст сохранён) на стр. {r['image_pages']}"
            )
        if problems:
            warned += 1
            lines.append(f"### {r['name']}  ->  {r.get('out', '-')}")
            lines.extend(f"   - {p}" for p in problems)
            lines.append("")

    if warned == 0:
        lines.append("OK: подозрительных ПДн-паттернов в выходных PDF не найдено,")
        lines.append("    сканов и нечитаемых страниц нет.")
    else:
        lines.insert(4, f"ВНИМАНИЕ: файлов с предупреждениями — {warned}. См. ниже.\n")

    with open(path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines))
    return path, warned


# ==================== БЕЗОПАСНЫЕ ИМЕНА ФАЙЛОВ ====================

INVALID_WIN_CHARS = r'<>:"/\\|?*\x00-\x1F'
invalid_re = re.compile(f"[{INVALID_WIN_CHARS}]")


def safe_filename(base: str, limit: int = 180) -> str:
    base = unicodedata.normalize("NFC", base)
    base = invalid_re.sub("_", base)
    base = re.sub(r"\s+", " ", base).strip().rstrip(" .")
    if not base:
        base = "file"
    if len(base) > limit:
        h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:6]
        base = base[: max(1, limit - 7)] + "_" + h
    return base


def extract_history_number(base: str) -> str | None:
    nums = re.findall(r"\d{6,20}", base)
    return nums[-1] if nums else None


# ==================== ОБРАБОТКА ФАЙЛОВ ====================

SUPPORTED_EXT = set(READERS) | {".pdf"}


def should_skip_filename(name: str) -> bool:
    return name.startswith(("~$", ".~lock.", "."))


def get_unique_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(f"{base}_{n}{ext}"):
        n += 1
    return f"{base}_{n}{ext}"


def process(path: str):
    name = os.path.basename(path)
    if should_skip_filename(name):
        return None
    base, ext = os.path.splitext(name)
    ext = ext.lower()
    if ext not in SUPPORTED_EXT:
        print(f"Пропускаю {name}: неподдерживаемый формат ({ext})")
        return None

    report = {"name": name, "out": "-", "scan_pages": [], "image_pages": [], "findings": []}
    try:
        if ext == ".pdf":
            page_texts, page_rects, scan_pages, image_pages = build_pages_from_pdf(path)
            report["scan_pages"] = scan_pages
            report["image_pages"] = image_pages
        else:
            raw = READERS[ext](path)
            page_texts, page_rects = build_pages_from_text(raw)
    except Exception as e:
        print(f"Ошибка при чтении {name}: {e}")
        report["error"] = str(e)
        return report

    history_no = extract_history_number(base)
    out_base = safe_filename(history_no if history_no else base)
    out_path = get_unique_path(os.path.join(OUTPUT_DIR, out_base + ".pdf"))
    try:
        save_clean_pdf(page_texts, page_rects, out_path)
    except Exception as e:
        print(f"Ошибка при сборке PDF для {name}: {e}")
        report["error"] = str(e)
        return report

    report["out"] = os.path.basename(out_path)
    report["findings"] = audit_pdf(out_path)
    return report


def main():
    if fitz is None:
        print("PyMuPDF (fitz) не установлен. Установите: pip install PyMuPDF")
        return
    if _find_cyrillic_font() is None:
        print("Не найден шрифт с кириллицей (arial.ttf / DejaVuSans / Helvetica и др.) — PDF не собрать.")
        if sys.platform == "darwin":
            print("  macOS: обычно шрифты лежат в /System/Library/Fonts/Supplemental/")
            print("  Если их нет — установите Arial или запустите:")
            print("    brew install --cask font-dejavu-sans")
        elif sys.platform.startswith("linux"):
            print("  Linux: установите пакет со шрифтами, напр.:")
            print("    Debian/Ubuntu: sudo apt install fonts-dejavu")
            print("    Fedora/RHEL:   sudo dnf install dejavu-sans-fonts")
            print("    Arch:          sudo pacman -S ttf-dejavu")
        else:
            print("  Windows: ожидается наличие arial.ttf в C:\\Windows\\Fonts")
        return

    files = [os.path.join(INPUT_DIR, f) for f in os.listdir(INPUT_DIR)
             if os.path.isfile(os.path.join(INPUT_DIR, f))]
    print(f"Найдено файлов: {len(files)}")

    reports = []
    for f in tqdm(files, desc="Деперсонализация"):
        r = process(f)
        if r is not None:
            reports.append(r)

    report_path, warned = write_audit_report(reports)
    print(f"Готово! Обезличенные PDF лежат в папке {OUTPUT_DIR}")
    if warned:
        print(f"ВНИМАНИЕ: {warned} файл(ов) с предупреждениями — см. {report_path}")
    else:
        print(f"Отчёт аудита: {report_path} (предупреждений нет)")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        print("\n!!! Произошла ошибка:")
        traceback.print_exc()
    finally:
        try:
            input("\nГотово. Нажмите Enter, чтобы закрыть окно...")
        except EOFError:
            pass
