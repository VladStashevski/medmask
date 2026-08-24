/* Regex escapes are kept explicit so the medical-data patterns remain auditable. */
/* eslint-disable no-control-regex, no-misleading-character-class, no-useless-escape */

const TAGS = Object.freeze({
  fio: "[FIO]",
  address: "[ADDRESS]",
  phone: "[PHONE]",
  email: "[EMAIL]",
  snils: "[SNILS]",
  inn: "[INN]",
  policy: "[POLICY]",
  passport: "[PASSPORT]",
  record: "[MEDICAL_RECORD]",
  workplace: "[WORKPLACE]",
  position: "[POSITION]",
  sickLeave: "[SICK_LEAVE]",
  age: "[AGE]",
});

export const DEFAULT_OPTIONS = Object.freeze({
  maskStaffNames: true,
  maskRecordNumbers: true,
});

const MONTHS = new Map([
  ["январь", 1], ["января", 1], ["февраль", 2], ["февраля", 2],
  ["март", 3], ["марта", 3], ["апрель", 4], ["апреля", 4],
  ["май", 5], ["мая", 5], ["июнь", 6], ["июня", 6],
  ["июль", 7], ["июля", 7], ["август", 8], ["августа", 8],
  ["сентябрь", 9], ["сентября", 9], ["октябрь", 10], ["октября", 10],
  ["ноябрь", 11], ["ноября", 11], ["декабрь", 12], ["декабря", 12],
]);

const MONTH_WORD =
  "январ[ья]|феврал[ья]|март[а]?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|" +
  "август[а]?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья]";
const NUMERIC_DATE = "\\d{1,2}\\s*[.\\-/]\\s*\\d{1,2}\\s*[.\\-/]\\s*\\d{4}";
const WORD_DATE = `\\d{1,2}\\s+(?:${MONTH_WORD})\\s+\\d{4}(?:\\s*(?:г\\.?|года?))?`;
const ANY_DOB = `(?:${NUMERIC_DATE}|${WORD_DATE})`;

const RUS_WORD = "[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?";
const PATRONYMIC =
  "[А-ЯЁ][а-яё]+(?:ович|евич|иевич|ьевич|ич|овна|евна|иевна|ьевна|ична|инична|оглы|кызы)";
const UPPER_WORD = "[А-ЯЁ]{2,}(?:-[А-ЯЁ]{2,})?";
const UPPER_PATRONYMIC =
  "[А-ЯЁ]+(?:ОВИЧ|ЕВИЧ|ИЕВИЧ|ЬЕВИЧ|ИЧ|ОВНА|ЕВНА|ИЕВНА|ЬЕВНА|ИЧНА|ИНИЧНА|ОГЛЫ|КЫЗЫ)";
const CYR_LEFT = "(?<![А-Яа-яЁё])";
const CYR_RIGHT = "(?![А-Яа-яЁё])";

const fioTripletRe = new RegExp(
  `${CYR_LEFT}(${RUS_WORD}\\s+${RUS_WORD}\\s+${PATRONYMIC})${CYR_RIGHT}`,
  "gu",
);
const fioInitialsRe = new RegExp(
  `${CYR_LEFT}(${RUS_WORD}\\s+[А-ЯЁ]\\.\\s*[А-ЯЁ]\\.)${CYR_RIGHT}`,
  "gu",
);
const fioUpperRe = new RegExp(
  `${CYR_LEFT}(${UPPER_WORD}\\s+${UPPER_WORD}\\s+${UPPER_PATRONYMIC})${CYR_RIGHT}`,
  "gu",
);

const FIRST_NAMES = [
  "Александр", "Алексей", "Анатолий", "Андрей", "Антон", "Аркадий", "Арсений",
  "Артём", "Артем", "Артур", "Богдан", "Борис", "Вадим", "Валентин", "Валерий",
  "Василий", "Виктор", "Виталий", "Владимир", "Владислав", "Вячеслав", "Геннадий",
  "Георгий", "Глеб", "Григорий", "Даниил", "Данил", "Денис", "Дмитрий", "Евгений",
  "Егор", "Иван", "Игорь", "Илья", "Кирилл", "Константин", "Лев", "Леонид",
  "Максим", "Марк", "Матвей", "Михаил", "Никита", "Николай", "Олег", "Павел",
  "Пётр", "Петр", "Роман", "Руслан", "Семён", "Семен", "Сергей", "Станислав",
  "Степан", "Тимофей", "Тимур", "Фёдор", "Федор", "Эдуард", "Юрий", "Ярослав",
  "Александра", "Алёна", "Алена", "Алина", "Алла", "Анастасия", "Ангелина",
  "Анжела", "Анна", "Антонина", "Валентина", "Валерия", "Варвара", "Вера",
  "Вероника", "Виктория", "Галина", "Дарья", "Диана", "Евгения", "Екатерина",
  "Елена", "Елизавета", "Жанна", "Зинаида", "Зоя", "Инна", "Ирина", "Карина",
  "Кристина", "Ксения", "Лариса", "Лидия", "Любовь", "Людмила", "Маргарита",
  "Марина", "Мария", "Надежда", "Наталья", "Наталия", "Нина", "Оксана", "Ольга",
  "Полина", "Раиса", "Регина", "Светлана", "София", "Софья", "Тамара", "Татьяна",
  "Ульяна", "Юлия", "Яна",
];
const firstNamesAlt = FIRST_NAMES.sort((a, b) => b.length - a.length)
  .map(escapeRegExp)
  .join("|");
const nameFirstRe = new RegExp(
  `${CYR_LEFT}((?:${firstNamesAlt})\\s+${RUS_WORD}(?:\\s+${PATRONYMIC})?)${CYR_RIGHT}`,
  "gu",
);
const nameSecondRe = new RegExp(
  `${CYR_LEFT}(${RUS_WORD}\\s+(?:${firstNamesAlt})(?:\\s+${PATRONYMIC})?)${CYR_RIGHT}`,
  "gu",
);

const doctorContextRe =
  /(?<![А-Яа-яЁё])(?:врач[а-яё]*|доктор[а-яё]*|лечащ[а-яё]*|медсестр[а-яё]*|медбрат[а-яё]*|фельдшер[а-яё]*|акушер[а-яё]*|анестезиолог[а-яё]*|хирург[а-яё]*|терапевт[а-яё]*|кардиолог[а-яё]*|невролог[а-яё]*|гинеколог[а-яё]*|уролог[а-яё]*|онколог[а-яё]*|ординатор[а-яё]*|заведующ[а-яё]*|лаборант[а-яё]*|рентгенолог[а-яё]*|реаниматолог[а-яё]*|подпис[а-яё]*)(?![А-Яа-яЁё])/iu;
const clinicalContextRe =
  /^\s*(?:жалоб[а-яё]*|анамнез[а-яё]*|диагноз[а-яё]*|осмотр[а-яё]*|назначени[а-яё]*|рекомендац[а-яё]*|протокол[а-яё]*|исследовани[а-яё]*|заключени[а-яё]*)(?![А-Яа-яЁё])/iu;
const medicalOrgRe =
  /(?<![А-Яа-яЁё])(?:больниц[а-яё]*|поликлиник[а-яё]*|диспансер[а-яё]*|госпитал[а-яё]*|медицинск[а-яё]*\s+центр[а-яё]*|гбуз|буз|фгбу|ооо|ао)(?![А-Яа-яЁё])/iu;

const emailRe = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/giu;
const strictPhoneRe =
  /(?<!\w)(?:(?:\+7|7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2}|9\d{2}[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2})(?!\w)/gu;
const snilsRe = /(?<!\d)\d{3}[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{2}(?!\d)/gu;
const enpRe = /(?<!\d)\d{4}\s?\d{4}\s?\d{4}\s?\d{4}(?!\d)/gu;
const innLabeledRe = /((?<![А-Яа-яЁё])инн(?![А-Яа-яЁё])\s*[:№\-]?\s*)\d{10,12}/giu;
const policyLabeledRe = /((?<![А-Яа-яЁё])(?:полис|полиса|енп)(?![А-Яа-яЁё])[^\d\n]{0,60})\d(?:[\s\-]*\d){7,24}/giu;
const passportLabeledRe =
  /((?<![А-Яа-яЁё])(?:паспорт|документ\s*,?\s*удостоверяющий\s+личность)(?![А-Яа-яЁё])[^\d\n]{0,80})(?:\d{2}\s?\d{2}\s?\d{6}|\d{6,10})/giu;
const sickLeaveRe =
  /((?<![А-Яа-яЁё])лист(?:ок|ка|а)?\s+нетрудоспособности(?![А-Яа-яЁё])[^\d\n]{0,60}(?:№|номер)?\s*[:\-]?\s*)\d{4,}/giu;
const recordLabeledRe =
  /((?<![А-Яа-яЁё])(?:№|номер)?\s*(?:медицинск[а-яё]*\s+карт[а-яё]*|истори[ия]\s+болезни|номер\s+иб|иб)(?![А-Яа-яЁё])\s*[:№\-]?\s*)[A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9/._\-]{2,}/giu;
const phoneLabeledRe =
  /((?<![А-Яа-яЁё])(?:номер\s+телефона|контактн[а-яё]*\s+телефон|телефон|тел\.?|моб\.?|сот\.?)(?![А-Яа-яЁё])\s*[:\-]?\s*)(?:\+?\d[\d\s\-()]{8,18}\d)/giu;

const addressInlineRe =
  /((?<![А-Яа-яЁё])(?:адрес(?:\s+(?:регистрации|проживания|места\s+жительства))?|место\s+(?:жительства|регистрации|проживания|пребывания)|прописка|домашний\s+адрес)(?![А-Яа-яЁё])(?!\s*[:\-]?\s*\[ADDRESS\])\s*[:\-]?\s*)[^\n]+/giu;
const addressStrongRe =
  /(?<![А-Яа-яЁё])(?:улиц[а-яё]*|проспект[а-яё]*|переул[а-яё]*|шоссе|бульвар[а-яё]*|набережн[а-яё]*|площад[а-яё]*|проезд[а-яё]*|микрорайон[а-яё]*)(?![А-Яа-яЁё])|(?<![а-яё])(?:ул|пр-?т|пер|б-р|наб|пл|мкр)\./giu;
const addressWeakRe =
  /(?<![А-Яа-яЁё])(?:город|област[а-яё]*|край|республик[а-яё]*|дом|квартир[а-яё]*|корпус[а-яё]*|строени[а-яё]*|пос[её]лок|село|деревн[а-яё]*)(?![А-Яа-яЁё])|(?<![а-яё])(?:г|обл|респ|д|кв|корп|стр|пос|дер)\./giu;
const workplaceRe =
  /((?<![А-Яа-яЁё])место\s+работы(?![А-Яа-яЁё])(?:\s*[,/]?\s*должность)?(?!\s*[:\-]?\s*\[WORKPLACE\])\s*[:\-]?\s*)[^\n]+/giu;
const positionRe = /((?<![А-Яа-яЁё])должность(?![А-Яа-яЁё])(?!\s*[:\-]?\s*\[POSITION\])\s*[:\-]?\s*)[^\n]+/giu;

const fieldLabelOnly = [
  { kind: "fio", re: /^\s*(?:ф\.?\s*и\.?\s*о\.?|фио|фамилия(?:\s+имя\s+отчество)?|пациент[а-яё]*)\s*[:.\-]?\s*$/iu },
  { kind: "dob", re: /^\s*(?:дата\s+рождения|д\.?\s*р\.?)\s*[:.\-]?\s*$/iu },
  { kind: "address", re: /^\s*(?:адрес\w*|место\s+(?:жительства|регистрации|проживания)|прописка)\s*[:.\-]?\s*$/iu },
  { kind: "phone", re: /^\s*(?:телефон|тел\.?|контактный\s+телефон)\s*[:.\-]?\s*$/iu },
  { kind: "snils", re: /^\s*снилс\s*[:.\-]?\s*$/iu },
  { kind: "inn", re: /^\s*инн\s*[:.\-]?\s*$/iu },
  { kind: "policy", re: /^\s*(?:полис|енп)\s*[:.\-]?\s*$/iu },
  { kind: "passport", re: /^\s*(?:паспорт|серия\s+и\s+номер\s+паспорта)\s*[:.\-]?\s*$/iu },
  { kind: "workplace", re: /^\s*место\s+работы\s*[:.\-]?\s*$/iu },
  { kind: "position", re: /^\s*должность\s*[:.\-]?\s*$/iu },
  { kind: "record", re: /^\s*(?:№|номер)?\s*(?:медицинской\s+карты|истории\s+болезни|иб)\s*[:.\-]?\s*$/iu },
];

const NAME_STOPWORDS = new Set([
  "дата", "пациент", "пациента", "фамилия", "имя", "отчество", "адрес",
  "телефон", "полис", "паспорт", "снилс", "инн", "номер", "карта", "история",
  "врач", "доктор", "отделение", "заключение", "исследование", "диагноз",
  "результат", "назначение", "января", "февраля", "марта", "апреля", "мая",
  "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря",
]);

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function normalizeText(value) {
  return String(value ?? "")
    .replace(/\r\n?/g, "\n")
    .replace(/[\u00a0\u202f\u2007\u2009\u200a]/g, " ")
    .replace(/[\u200b\u200c\u200d\ufeff]/g, "")
    .replace(/[\u2010\u2011\u2012\u2212]/g, "-")
    .replace(/[\u0085\u2028\u2029]/g, "\n")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, "")
    .normalize("NFC");
}

function agePhrase(age) {
  if (!Number.isInteger(age) || age < 0 || age > 150) return TAGS.age;
  const lastTwo = age % 100;
  const last = age % 10;
  const unit = lastTwo >= 11 && lastTwo <= 14
    ? "лет"
    : last === 1
      ? "год"
      : last >= 2 && last <= 4
        ? "года"
        : "лет";
  return `${age} ${unit}`;
}

function ageFromParts(day, month, year, now = new Date()) {
  const d = Number(day);
  const m = Number(month);
  const y = Number(year);
  if (!Number.isInteger(d) || !Number.isInteger(m) || !Number.isInteger(y)) return TAGS.age;
  const birth = new Date(Date.UTC(y, m - 1, d));
  if (birth.getUTCFullYear() !== y || birth.getUTCMonth() !== m - 1 || birth.getUTCDate() !== d)
    return TAGS.age;
  let age = now.getFullYear() - y;
  if (now.getMonth() + 1 < m || (now.getMonth() + 1 === m && now.getDate() < d)) age -= 1;
  return agePhrase(age);
}

function ageFromText(value, now = new Date()) {
  const numeric = String(value).match(/(\d{1,2})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{4})/u);
  if (numeric) return ageFromParts(numeric[1], numeric[2], numeric[3], now);
  const words = String(value).match(new RegExp(`(\\d{1,2})\\s+(${MONTH_WORD})\\s+(\\d{4})`, "iu"));
  if (words) return ageFromParts(words[1], MONTHS.get(words[2].toLowerCase()), words[3], now);
  const explicitAge = String(value).match(/(?<!\d)(\d{1,3})\s*(?:год|года|лет|г\.|л\.)(?![А-Яа-яЁё])/iu);
  if (explicitAge) return agePhrase(Number(explicitAge[1]));
  return TAGS.age;
}

function rememberFio(memory, value) {
  for (const raw of String(value).split(/[\s-]+/u)) {
    const token = raw.replace(/^[^А-Яа-яЁё]+|[^А-Яа-яЁё]+$/gu, "");
    const lower = token.toLowerCase();
    if (token.length >= 3 && /^[А-ЯЁ][А-Яа-яЁё]+$/u.test(token) && !NAME_STOPWORDS.has(lower))
      memory.add(lower);
  }
}

function replaceAndRemember(line, regex, memory) {
  return line.replace(regex, (match, captured) => {
    rememberFio(memory, captured || match);
    return TAGS.fio;
  });
}

function maskInlineNames(line, memory, maskStaffNames) {
  const isStaff = doctorContextRe.test(line);
  const patientLabel = /(пациент[а-яё]*|больн[а-яё]*|пострадавш[а-яё]*|представител[а-яё]*|ф\.?\s*и\.?\s*о\.?)\s*[:\-]/iu.test(line);

  line = line.replace(
    /((?:ф\.?\s*и\.?\s*о\.?|фио|пациент[а-яё]*|больн[а-яё]*|пострадавш[а-яё]*|представител[а-яё]*)\s*[:\-]\s*)((?:[А-ЯЁA-Z][А-Яа-яЁёA-Za-z'’-]+|[А-ЯЁA-Z]\.)+(?:\s+(?:[А-ЯЁA-Z][А-Яа-яЁёA-Za-z'’-]+|[А-ЯЁA-Z]\.)){0,2})/gu,
    (match, label, name) => {
      rememberFio(memory, name);
      return `${label}${TAGS.fio}`;
    },
  );
  line = line.replace(
    /((?<![А-Яа-яЁё])(?:фамилия|имя|отчество)(?![А-Яа-яЁё])\s*[:\-]\s*)([А-ЯЁA-Z][А-Яа-яЁёA-Za-z'’-]+)/gu,
    (match, label, name) => {
      rememberFio(memory, name);
      return `${label}${TAGS.fio}`;
    },
  );

  if (!maskStaffNames && isStaff && !patientLabel) return line;
  line = replaceAndRemember(line, fioTripletRe, memory);
  line = replaceAndRemember(line, fioInitialsRe, memory);
  line = replaceAndRemember(line, fioUpperRe, memory);
  line = replaceAndRemember(line, nameFirstRe, memory);
  line = replaceAndRemember(line, nameSecondRe, memory);
  return line;
}

function looksLikeAddress(line) {
  if (!/\d/u.test(line) || clinicalContextRe.test(line)) return false;
  const strong = [...line.matchAll(addressStrongRe)].length;
  const weak = [...line.matchAll(addressWeakRe)].length;
  return strong >= 1 || weak >= 2 || /^\s*\d{6}\s*,/u.test(line);
}

function maskStandaloneAddress(line) {
  if (!looksLikeAddress(line)) return line;
  if (!medicalOrgRe.test(line)) return TAGS.address;
  const postal = line.search(/(?<!\d)\d{6}(?!\d)/u);
  const street = line.search(addressStrongRe);
  const candidates = [postal, street].filter((index) => index > 0);
  if (!candidates.length) return line;
  return `${line.slice(0, Math.min(...candidates)).trimEnd()} ${TAGS.address}`;
}

function tagForPending(kind, value, options, now) {
  if (kind === "dob") return ageFromText(value, now);
  if (kind === "record" && !options.maskRecordNumbers) return value;
  return TAGS[kind] ?? value;
}

function maskLine(line, memory, options, now) {
  let result = line;
  result = result.replace(emailRe, TAGS.email);
  result = result.replace(phoneLabeledRe, `$1${TAGS.phone}`);
  result = result.replace(strictPhoneRe, TAGS.phone);
  result = result.replace(innLabeledRe, `$1${TAGS.inn}`);
  result = result.replace(policyLabeledRe, `$1${TAGS.policy}`);
  result = result.replace(enpRe, TAGS.policy);
  result = result.replace(passportLabeledRe, `$1${TAGS.passport}`);
  result = result.replace(sickLeaveRe, `$1${TAGS.sickLeave}`);
  result = result.replace(snilsRe, TAGS.snils);
  if (options.maskRecordNumbers)
    result = result.replace(recordLabeledRe, `$1${TAGS.record}`);

  result = result.replace(
    new RegExp(`((?:дата\\s+рождения|д\\.?\\s*р\\.?)\\s*[:\\-]?\\s*)(${ANY_DOB})`, "giu"),
    (match, label, dob) => `${label}${ageFromText(dob, now)}`,
  );
  result = result.replace(
    /((?<![А-Яа-яЁё])(?:год\s+рождения|г\.?\s*р\.?)\s*[:\-]?\s*)((?:19|20)\d{2})(?!\d)/giu,
    (match, label, year) => `${label}${agePhrase(now.getFullYear() - Number(year))}`,
  );

  result = result.replace(addressInlineRe, `$1${TAGS.address}`);
  result = result.replace(/(?<![А-Яа-яЁё])прожива[а-яё]*\s+(?:в|по\s+адресу)(?![А-Яа-яЁё])[^\n]*/giu, `Проживает ${TAGS.address}`);
  result = result.replace(workplaceRe, `$1${TAGS.workplace}`);
  result = result.replace(positionRe, `$1${TAGS.position}`);
  result = maskInlineNames(result, memory, options.maskStaffNames);
  result = maskStandaloneAddress(result);

  result = result.replace(
    new RegExp(`(${escapeRegExp(TAGS.fio)}\\s*[,;:\\-]?\\s*)(${ANY_DOB})(?:\\s*\\(?\\d{1,3}\\s*(?:год|года|лет)\\)?)?`, "giu"),
    (match, fio, dob) => `${fio}${ageFromText(dob, now)}`,
  );
  return result;
}

function sweepRememberedNames(lines, memory, options) {
  const tokens = [...memory].sort((a, b) => b.length - a.length);
  return lines.map((line) => {
    if (!options.maskStaffNames && doctorContextRe.test(line)) return line;
    let result = line;
    for (const token of tokens) {
      const suffix = token.length >= 6 ? "[а-яё]{0,3}" : "";
      const regex = new RegExp(`${CYR_LEFT}${escapeRegExp(token)}${suffix}${CYR_RIGHT}`, "giu");
      result = result.replace(regex, TAGS.fio);
    }
    return result
      .replace(/\[FIO\](?:\s+\[FIO\])+/gu, TAGS.fio)
      .replace(/\[FIO\]\s+[А-ЯЁ]\.\s*[А-ЯЁ]\./gu, TAGS.fio);
  });
}

function normalizeLayout(text) {
  const output = [];
  let blank = false;
  for (const source of text.split("\n")) {
    const line = source
      .replace(/[\t\u00a0 ]{2,}/gu, " ")
      .replace(/\s+([,;:.!?%)»\]])/gu, "$1")
      .replace(/([(«\[])\s+/gu, "$1")
      .trim();
    if (!line) {
      if (!blank && output.length) output.push("");
      blank = true;
      continue;
    }
    output.push(line);
    blank = false;
  }
  while (output.at(-1) === "") output.pop();
  return output.join("\n");
}

function countMatches(text, regex) {
  return [...text.matchAll(regex)].length;
}

function buildAudit(text) {
  const checks = [
    { code: "email", label: "Возможный адрес электронной почты", re: new RegExp(emailRe.source, "giu") },
    { code: "phone", label: "Возможный номер телефона", re: new RegExp(strictPhoneRe.source, "gu") },
    { code: "snils", label: "Возможный СНИЛС", re: new RegExp(snilsRe.source, "gu") },
    { code: "inn", label: "Возможный ИНН", re: /((?<![А-Яа-яЁё])инн(?![А-Яа-яЁё])\s*[:№\-]?\s*)\d{10,12}/giu },
    { code: "policy", label: "Возможный номер полиса", re: new RegExp(enpRe.source, "gu") },
    { code: "passport", label: "Возможные паспортные данные", re: new RegExp(passportLabeledRe.source, "giu") },
    { code: "dob", label: "Возможная дата рождения", re: new RegExp(`(?:дата\\s+рождения|д\\.?\\s*р\\.?).{0,30}${ANY_DOB}`, "giu") },
    { code: "fio", label: "Возможное ФИО", re: new RegExp(fioTripletRe.source, "gu") },
    { code: "record", label: "Возможный номер медицинской карты", re: new RegExp(recordLabeledRe.source, "giu") },
    { code: "address", label: "Возможный адрес", re: new RegExp(addressInlineRe.source, "giu") },
    { code: "workplace", label: "Возможное место работы", re: new RegExp(workplaceRe.source, "giu") },
  ];
  return checks
    .map((check) => ({ code: check.code, label: check.label, count: countMatches(text, check.re) }))
    .filter((warning) => warning.count > 0);
}

function countTags(text) {
  return Object.fromEntries(
    Object.entries(TAGS).map(([kind, tag]) => [kind, text.split(tag).length - 1]),
  );
}

export function depersonalizeText(input, rawOptions = {}, now = new Date()) {
  const options = { ...DEFAULT_OPTIONS, ...rawOptions };
  const normalized = normalizeText(input);
  const memory = new Set();
  const sourceLines = normalized.split("\n");
  const masked = [];
  let pending = null;

  for (const sourceLine of sourceLines) {
    const trimmed = sourceLine.trim();
    if (pending && trimmed) {
      const nextField = fieldLabelOnly.find((field) => field.re.test(trimmed));
      if (!nextField) {
        masked.push(tagForPending(pending, trimmed, options, now));
        pending = null;
        continue;
      }
      pending = null;
    }

    const label = fieldLabelOnly.find((field) => field.re.test(trimmed));
    if (label) {
      masked.push(sourceLine);
      pending = label.kind;
      continue;
    }

    masked.push(maskLine(sourceLine, memory, options, now));
  }

  const swept = sweepRememberedNames(masked, memory, options);
  const text = normalizeLayout(swept.join("\n"));
  return {
    text,
    stats: countTags(text),
    warnings: buildAudit(text),
  };
}

export function depersonalizePages(pages, options = {}, now = new Date()) {
  const marker = "___LOCAL_PAGE_BREAK_8E4F4A67___";
  const result = depersonalizeText(pages.join(`\n${marker}\n`), options, now);
  return {
    ...result,
    pages: result.text.split(marker).map((page) => page.trim()),
  };
}

export { TAGS };
