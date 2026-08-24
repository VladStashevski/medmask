import type { PDFFont, PDFPage } from "pdf-lib";

import {
  depersonalizePages,
  type AuditWarning,
  type RedactionStats,
} from "./deidentify.mjs";

export const MAX_PDF_BYTES = 120 * 1024 * 1024;
export const SAFE_OUTPUT_NAME = "обезличенный-документ.pdf";

const SCAN_PLACEHOLDER =
  "[СКАН/ИЗОБРАЖЕНИЕ: текст не извлечён — требуется ручная проверка]";

export type ProcessingProgress = {
  percent: number;
  message: string;
};

export type PdfProcessingResult = {
  blob: Blob;
  inputPages: number;
  outputPages: number;
  scanPages: number[];
  stats: RedactionStats;
  warnings: AuditWarning[];
};

type PageSize = { width: number; height: number };
type PositionedText = {
  text: string;
  x: number;
  y: number;
  width: number;
  height: number;
};

function ensurePdf(file: File) {
  if (!file.name.toLowerCase().endsWith(".pdf") && file.type !== "application/pdf")
    throw new Error("Выберите документ в формате PDF.");
  if (file.size === 0) throw new Error("Выбранный PDF пуст.");
  if (file.size > MAX_PDF_BYTES)
    throw new Error("PDF больше 120 МБ. Разделите его на несколько документов.");
}

function extractPositionedText(item: unknown): PositionedText | null {
  if (!item || typeof item !== "object" || !("str" in item) || !("transform" in item))
    return null;
  const value = item as {
    str?: unknown;
    transform?: unknown;
    width?: unknown;
    height?: unknown;
  };
  if (typeof value.str !== "string" || !Array.isArray(value.transform)) return null;
  const x = Number(value.transform[4]);
  const y = Number(value.transform[5]);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return {
    text: value.str,
    x,
    y,
    width: Number(value.width) || 0,
    height: Math.max(1, Number(value.height) || Math.abs(Number(value.transform[3])) || 10),
  };
}

function pageTextFromItems(items: unknown[]) {
  const positioned = items
    .map(extractPositionedText)
    .filter((item): item is PositionedText => item !== null)
    .filter((item) => item.text.trim().length > 0)
    .sort((a, b) => {
      const tolerance = Math.max(2, Math.min(a.height, b.height) * 0.35);
      return Math.abs(a.y - b.y) <= tolerance ? a.x - b.x : b.y - a.y;
    });

  const lines: Array<{ y: number; height: number; items: PositionedText[] }> = [];
  for (const item of positioned) {
    const previous = lines.at(-1);
    const tolerance = Math.max(2, Math.min(previous?.height ?? item.height, item.height) * 0.45);
    if (!previous || Math.abs(previous.y - item.y) > tolerance) {
      lines.push({ y: item.y, height: item.height, items: [item] });
      continue;
    }
    previous.items.push(item);
    previous.height = Math.max(previous.height, item.height);
  }

  return lines
    .map((line) => {
      line.items.sort((a, b) => a.x - b.x);
      let text = "";
      let previousEnd = Number.NEGATIVE_INFINITY;
      for (const item of line.items) {
        const needsSpace =
          text.length > 0 &&
          !/\s$/u.test(text) &&
          !/^\s/u.test(item.text) &&
          item.x - previousEnd > Math.max(1.5, item.height * 0.12);
        text += `${needsSpace ? " " : ""}${item.text}`;
        previousEnd = item.x + item.width;
      }
      return text.trim();
    })
    .filter(Boolean)
    .join("\n");
}

function base64Bytes(value: string) {
  const decoded = atob(value);
  const bytes = new Uint8Array(decoded.length);
  for (let index = 0; index < decoded.length; index += 1)
    bytes[index] = decoded.charCodeAt(index);
  return bytes;
}

function safePageSize(size: PageSize): PageSize {
  return {
    width: Math.min(1400, Math.max(320, size.width || 595.28)),
    height: Math.min(2000, Math.max(320, size.height || 841.89)),
  };
}

function safeGlyphs(value: string, characters: Set<number>) {
  return Array.from(value, (character) => {
    const point = character.codePointAt(0) ?? 63;
    return characters.has(point) ? character : "?";
  }).join("");
}

function wrapLine(line: string, font: PDFFont, size: number, maxWidth: number) {
  if (!line.trim()) return [""];
  const output: string[] = [];
  let current = "";

  for (const word of line.split(/\s+/u)) {
    const attempt = current ? `${current} ${word}` : word;
    if (font.widthOfTextAtSize(attempt, size) <= maxWidth) {
      current = attempt;
      continue;
    }
    if (current) output.push(current);
    current = "";
    if (font.widthOfTextAtSize(word, size) <= maxWidth) {
      current = word;
      continue;
    }

    let part = "";
    for (const character of word) {
      const next = `${part}${character}`;
      if (part && font.widthOfTextAtSize(next, size) > maxWidth) {
        output.push(part);
        part = character;
      } else {
        part = next;
      }
    }
    current = part;
  }
  if (current) output.push(current);
  return output.length ? output : [""];
}

function addTextPage(
  document: import("pdf-lib").PDFDocument,
  size: PageSize,
) {
  return document.addPage([size.width, size.height]);
}

function drawTextPages(
  document: import("pdf-lib").PDFDocument,
  source: string,
  rawSize: PageSize,
  font: PDFFont,
  characters: Set<number>,
) {
  const size = safePageSize(rawSize);
  const margin = Math.max(32, Math.min(48, size.width * 0.065));
  const fontSize = size.width < 450 ? 8.2 : 9.2;
  const lineHeight = fontSize * 1.42;
  const maxWidth = size.width - margin * 2;
  const safeText = safeGlyphs(source, characters);
  const lines = safeText.split("\n").flatMap((line) => wrapLine(line, font, fontSize, maxWidth));
  let page: PDFPage = addTextPage(document, size);
  let pagesAdded = 1;
  let y = size.height - margin - fontSize;

  for (const line of lines) {
    if (y < margin) {
      page = addTextPage(document, size);
      pagesAdded += 1;
      y = size.height - margin - fontSize;
    }
    if (line)
      page.drawText(line, {
        x: margin,
        y,
        size: fontSize,
        font,
      });
    y -= lineHeight;
  }
  return pagesAdded;
}

function friendlyPdfError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  if (/password|encrypted/i.test(message))
    return new Error("PDF защищён паролем. Снимите защиту и попробуйте снова.");
  if (/invalid pdf|missing pdf|format/i.test(message))
    return new Error("Не удалось прочитать PDF. Возможно, файл повреждён.");
  return error instanceof Error ? error : new Error("Не удалось обработать PDF.");
}

export async function processPdfLocally(
  file: File,
  onProgress: (progress: ProcessingProgress) => void = () => undefined,
): Promise<PdfProcessingResult> {
  ensurePdf(file);
  onProgress({ percent: 3, message: "Читаю PDF…" });

  const fileBuffer = await file.arrayBuffer();
  const header = new TextDecoder("latin1").decode(new Uint8Array(fileBuffer, 0, Math.min(1024, fileBuffer.byteLength)));
  if (!header.includes("%PDF-")) throw new Error("Файл не похож на корректный PDF.");

  try {
    const [{ getDocument, GlobalWorkerOptions }, workerModule] = await Promise.all([
      import("pdfjs-dist"),
      import("pdfjs-dist/build/pdf.worker.min.mjs?url"),
    ]);
    GlobalWorkerOptions.workerSrc = workerModule.default;

    const loadingTask = getDocument({
      data: new Uint8Array(fileBuffer),
      isEvalSupported: false,
      useWorkerFetch: false,
    });
    const sourcePdf = await loadingTask.promise;
    const pageTexts: string[] = [];
    const pageSizes: PageSize[] = [];
    const scanPages: number[] = [];

    try {
      for (let pageNumber = 1; pageNumber <= sourcePdf.numPages; pageNumber += 1) {
        const page = await sourcePdf.getPage(pageNumber);
        const viewport = page.getViewport({ scale: 1 });
        const content = await page.getTextContent();
        const text = pageTextFromItems(content.items);
        if (!text.trim()) scanPages.push(pageNumber);
        pageTexts.push(text.trim() || SCAN_PLACEHOLDER);
        pageSizes.push({ width: viewport.width, height: viewport.height });
        page.cleanup();
        onProgress({
          percent: 6 + Math.round((pageNumber / sourcePdf.numPages) * 46),
          message: `Извлекаю текст: ${pageNumber} из ${sourcePdf.numPages}`,
        });
      }
    } finally {
      await sourcePdf.destroy();
    }

    onProgress({ percent: 58, message: "Удаляю персональные данные…" });
    const cleaned = depersonalizePages(pageTexts, {
      maskRecordNumbers: true,
      maskStaffNames: true,
    });

    onProgress({ percent: 66, message: "Собираю новый PDF…" });
    const [{ PDFDocument }, fontkitModule, fontsModule] = await Promise.all([
      import("pdf-lib"),
      import("@pdf-lib/fontkit"),
      import("pdfmake/build/vfs_fonts.js"),
    ]);
    const output = await PDFDocument.create();
    output.registerFontkit(fontkitModule.default);
    const fontData = fontsModule.default["Roboto-Regular.ttf"];
    if (!fontData) throw new Error("Не удалось загрузить локальный шрифт PDF.");
    const font = await output.embedFont(base64Bytes(fontData), { subset: true });
    const characters = new Set(font.getCharacterSet());
    let outputPages = 0;
    for (let index = 0; index < cleaned.pages.length; index += 1) {
      outputPages += drawTextPages(
        output,
        cleaned.pages[index] || "[ПУСТАЯ СТРАНИЦА]",
        pageSizes[index] ?? { width: 595.28, height: 841.89 },
        font,
        characters,
      );
      onProgress({
        percent: 68 + Math.round(((index + 1) / cleaned.pages.length) * 29),
        message: `Собираю страницы: ${index + 1} из ${cleaned.pages.length}`,
      });
    }

    output.setTitle("Обезличенный медицинский документ");
    output.setSubject("Локально обезличенная копия");
    output.setAuthor("Локальный обезличиватель");
    output.setCreator("Локальный обезличиватель");
    output.setProducer("Локальный обезличиватель");
    const bytes = await output.save({ useObjectStreams: true });
    onProgress({ percent: 100, message: "Готово" });

    return {
      blob: new Blob([bytes], { type: "application/pdf" }),
      inputPages: pageTexts.length,
      outputPages,
      scanPages,
      stats: cleaned.stats,
      warnings: cleaned.warnings,
    };
  } catch (error) {
    throw friendlyPdfError(error);
  }
}
