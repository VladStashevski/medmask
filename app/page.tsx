"use client";

import { useEffect, useRef, useState, type DragEvent } from "react";

import {
  MAX_PDF_BYTES,
  SAFE_OUTPUT_NAME,
  processPdfLocally,
  type PdfProcessingResult,
  type ProcessingProgress,
} from "@/lib/pdf-processor";

type ReadyResult = PdfProcessingResult & { url: string };

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} КБ`;
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
}

function totalRedactions(result: PdfProcessingResult) {
  return Object.values(result.stats).reduce((sum, value) => sum + value, 0);
}

export default function Home() {
  const inputRef = useRef<HTMLInputElement>(null);
  const resultRef = useRef<ReadyResult | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState<ProcessingProgress>({
    percent: 0,
    message: "",
  });
  const [result, setResult] = useState<ReadyResult | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    resultRef.current = result;
  }, [result]);

  useEffect(
    () => () => {
      if (resultRef.current) URL.revokeObjectURL(resultRef.current.url);
    },
    [],
  );

  const clearResult = () => {
    if (resultRef.current) URL.revokeObjectURL(resultRef.current.url);
    resultRef.current = null;
    setResult(null);
  };

  const chooseFile = (nextFile: File | undefined) => {
    if (!nextFile) return;
    clearResult();
    setError("");
    setProgress({ percent: 0, message: "" });
    if (!nextFile.name.toLowerCase().endsWith(".pdf") && nextFile.type !== "application/pdf") {
      setFile(null);
      setError("Нужен файл в формате PDF.");
      return;
    }
    if (nextFile.size > MAX_PDF_BYTES) {
      setFile(null);
      setError("PDF больше 120 МБ. Разделите его на несколько документов.");
      return;
    }
    setFile(nextFile);
  };

  const dropFile = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setDragging(false);
    chooseFile(event.dataTransfer.files?.[0]);
  };

  const processFile = async () => {
    if (!file || processing) return;
    clearResult();
    setError("");
    setProcessing(true);
    try {
      const processed = await processPdfLocally(file, setProgress);
      const ready = { ...processed, url: URL.createObjectURL(processed.blob) };
      resultRef.current = ready;
      setResult(ready);
      setFile(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось обработать PDF.");
      setProgress({ percent: 0, message: "" });
    } finally {
      setProcessing(false);
    }
  };

  const reset = () => {
    clearResult();
    setFile(null);
    setError("");
    setProgress({ percent: 0, message: "" });
  };

  return (
    <main className="app-shell">
      <section className="workspace" aria-labelledby="page-title">
        <header className="hero">
          <div className="brand-row" aria-label="MedMask">
            <span className="brand-mark" aria-hidden="true">M</span>
            <span>MedMask</span>
          </div>
          <div className="privacy-pill">
            <span className="privacy-dot" aria-hidden="true" />
            Обработка только в вашем браузере
          </div>
          <h1 id="page-title">Обезличить историю болезни</h1>
          <p>
            Выберите PDF — приложение удалит ФИО, контакты, адреса и номера
            документов, а затем сразу подготовит новую копию.
          </p>
        </header>

        {!result ? (
          <section className="tool-card" aria-label="Загрузка документа">
            <div className="step-label">1 · Исходный документ</div>
            <input
              ref={inputRef}
              className="visually-hidden"
              type="file"
              accept="application/pdf,.pdf"
              disabled={processing}
              onChange={(event) => {
                chooseFile(event.target.files?.[0]);
                event.target.value = "";
              }}
            />
            <button
              type="button"
              className={`dropzone${dragging ? " is-dragging" : ""}${processing ? " is-processing" : ""}`}
              disabled={processing}
              onClick={() => inputRef.current?.click()}
              onDragEnter={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget as Node | null))
                  setDragging(false);
              }}
              onDrop={dropFile}
            >
              <span className="file-mark" aria-hidden="true">PDF</span>
              <span className="dropzone-title">
                {file ? file.name : "Перетащите PDF сюда"}
              </span>
              <span className="dropzone-copy">
                {file
                  ? `${formatBytes(file.size)} · нажмите, чтобы заменить`
                  : "или нажмите, чтобы выбрать файл на компьютере"}
              </span>
            </button>

            {processing && (
              <div className="progress-block" role="status" aria-live="polite">
                <div className="progress-heading">
                  <span>{progress.message || "Обрабатываю документ…"}</span>
                  <strong>{progress.percent}%</strong>
                </div>
                <div
                  className="progress-track"
                  role="progressbar"
                  aria-label="Обработка PDF"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={progress.percent}
                >
                  <span style={{ width: `${progress.percent}%` }} />
                </div>
                <p>Не закрывайте эту вкладку. Файл остаётся в памяти браузера.</p>
              </div>
            )}

            {error && <div className="error-message" role="alert">{error}</div>}

            <div className="action-row">
              <span className="local-note">
                <span className="lock" aria-hidden="true">●</span>
                PDF не загружается в облако и не сохраняется
              </span>
              <button
                className="primary-button"
                type="button"
                disabled={!file || processing}
                onClick={processFile}
              >
                {processing ? "Обезличиваю…" : "Обезличить PDF"}
              </button>
            </div>
          </section>
        ) : (
          <section className="result-card" aria-labelledby="result-title">
            <div className="result-mark" aria-hidden="true">✓</div>
            <div className="result-copy">
              <div className="step-label">2 · Результат</div>
              <h2 id="result-title">Обезличенная копия готова</h2>
              <p>
                Исходный файл уже не удерживается приложением. Результат живёт
                в памяти этой вкладки до её закрытия или очистки.
              </p>
            </div>

            <div className="result-metrics">
              <div><strong>{result.inputPages}</strong><span>страниц прочитано</span></div>
              <div><strong>{totalRedactions(result)}</strong><span>замен выполнено</span></div>
              <div><strong>{result.scanPages.length}</strong><span>страниц без текста</span></div>
            </div>

            <div className="audit-summary">
              <h3>Автоматическая проверка</h3>
              {result.scanPages.length === 0 && result.warnings.length === 0 ? (
                <p className="audit-ok">
                  Явных остаточных идентификаторов и нечитаемых страниц не найдено.
                </p>
              ) : (
                <ul>
                  {result.scanPages.length > 0 && (
                    <li>
                      Страницы без извлекаемого текста: {result.scanPages.join(", ")}.
                      В результате они заменены предупреждением.
                    </li>
                  )}
                  {result.warnings.map((warning) => (
                    <li key={warning.code}>
                      {warning.label}: {warning.count}. Проверьте документ вручную.
                    </li>
                  ))}
                </ul>
              )}
              <small>
                Автоматическое обезличивание снижает риск, но перед передачей
                документа внешней системе итоговый PDF нужно просмотреть.
              </small>
            </div>

            <div className="result-actions">
              <button type="button" className="secondary-button" onClick={reset}>
                Другой документ
              </button>
              <a className="primary-button download-button" href={result.url} download={SAFE_OUTPUT_NAME}>
                Скачать PDF
              </a>
            </div>
          </section>
        )}

        <div className="assurances" aria-label="Как защищён документ">
          <article>
            <span>01</span>
            <div>
              <h2>Локально</h2>
              <p>PDF разбирается и пересобирается внутри браузера.</p>
            </div>
          </article>
          <article>
            <span>02</span>
            <div>
              <h2>Без следов</h2>
              <p>Нет API, аккаунтов, базы и журнала загрузок.</p>
            </div>
          </article>
          <article>
            <span>03</span>
            <div>
              <h2>Строгий режим</h2>
              <p>Также удаляются ФИО сотрудников и номер медкарты.</p>
            </div>
          </article>
        </div>
      </section>
    </main>
  );
}
