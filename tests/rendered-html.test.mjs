import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  depersonalizePages,
  depersonalizeText,
} from "../lib/deidentify.mjs";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the local depersonalization tool", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>MedMask — обезличивание медицинских PDF<\/title>/i);
  assert.match(html, /MedMask/);
  assert.match(html, /Обезличить историю болезни/);
  assert.match(html, /Обработка только в вашем браузере/);
  assert.match(html, /PDF не загружается в облако и не сохраняется/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/i);
});

test("the product has no API, auth, or durable storage path", async () => {
  const [page, processor, packageJson, hosting] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../lib/pdf-processor.ts", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
    readFile(new URL("../.openai/hosting.json", import.meta.url), "utf8"),
  ]);

  assert.doesNotMatch(page, /fetch\s*\(/);
  assert.doesNotMatch(processor, /fetch\s*\(|\/api\//);
  assert.doesNotMatch(packageJson, /auth|drizzle|database|react-loading-skeleton/i);
  const hostingConfig = JSON.parse(hosting);
  assert.match(hostingConfig.project_id, /^appgprj_/);
  assert.equal(hostingConfig.d1, null);
  assert.equal(hostingConfig.r2, null);
});

test("redacts direct identifiers and fixes the original INN gap", () => {
  const result = depersonalizeText(
    [
      "Пациент: Иванов Иван Иванович",
      "Дата рождения: 21.08.1982",
      "ИНН: 123456789012",
      "СНИЛС: 123-456-789 01",
      "Телефон: +7 912 345-67-89",
      "E-mail: patient@example.ru",
      "Паспорт: 12 34 567890",
      "Полис: 1234 5678 9012 3456",
      "Адрес: г. Москва, ул. Ленина, д. 1",
      "№ медицинской карты: 12345/26",
    ].join("\n"),
    {},
    new Date("2026-08-24T12:00:00Z"),
  );

  assert.match(result.text, /Пациент: \[FIO\]/);
  assert.match(result.text, /Дата рождения: 44 года/);
  assert.match(result.text, /ИНН: \[INN\]/);
  assert.match(result.text, /СНИЛС: \[SNILS\]/);
  assert.match(result.text, /Телефон: \[PHONE\]/);
  assert.match(result.text, /E-mail: \[EMAIL\]/);
  assert.match(result.text, /Паспорт: \[PASSPORT\]/);
  assert.match(result.text, /Полис: \[POLICY\]/);
  assert.match(result.text, /Адрес: \[ADDRESS\]/);
  assert.match(result.text, /№ медицинской карты: \[MEDICAL_RECORD\]/);
  assert.doesNotMatch(result.text, /Иванов|123456789012|patient@example/);
  assert.deepEqual(result.warnings, []);
});

test("remembers patient names across pages and masks staff in strict mode", () => {
  const strict = depersonalizePages([
    "ФИО: Петрова Мария Сергеевна",
    "Пациентке Петровой М.С. выполнено исследование. Врач: Сидоров С.С.",
  ]);
  assert.equal(strict.pages.length, 2);
  assert.doesNotMatch(strict.text, /Петров|Сидоров/);
  assert.match(strict.text, /\[FIO\]/);

  const patientOnly = depersonalizeText(
    "Врач: Сидоров С.С.\nПациент: Петрова Мария Сергеевна",
    { maskStaffNames: false },
  );
  assert.match(patientOnly.text, /Врач: Сидоров С\.С\./);
  assert.doesNotMatch(patientOnly.text, /Петрова/);
});
