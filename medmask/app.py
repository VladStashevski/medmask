"""Минимальный настольный интерфейс MedMask на стандартном Tk."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .batch import BatchResult, MedMaskError, Progress, process_folder


BG = "#F5F6F8"
CARD = "#FFFFFF"
INK = "#17202A"
MUTED = "#667085"
ACCENT = "#176B5B"
ACCENT_ACTIVE = "#105548"
LINE = "#D9DEE7"
WARNING = "#9A6700"
ERROR = "#B42318"


def open_folder(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    elif os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


class MedMaskApp:
    ACTIVITY_FRAMES = ("●··", "·●·", "··●", "·●·")

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.source_dir: Path | None = None
        self.output_dir: Path | None = None
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.processing = False
        self.started_at: float | None = None
        self.last_progress: Progress | None = None

        root.title("MedMask")
        root.geometry("720x520")
        root.minsize(620, 480)
        root.configure(bg=BG)

        self._configure_styles()
        self._build()
        self._select_from_arguments()
        self.root.after(100, self._poll_events)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="white",
            borderwidth=0,
            padding=(18, 11),
            font=("TkDefaultFont", 11, "bold"),
        )
        style.map("Accent.TButton", background=[("active", ACCENT_ACTIVE), ("disabled", LINE)])
        style.configure(
            "Secondary.TButton",
            background=CARD,
            foreground=INK,
            bordercolor=LINE,
            padding=(16, 10),
            font=("TkDefaultFont", 10),
        )
        style.configure(
            "MedMask.Horizontal.TProgressbar",
            troughcolor="#E7EBF0",
            background=ACCENT,
            bordercolor="#E7EBF0",
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            thickness=10,
        )

    def _build(self) -> None:
        outer = tk.Frame(self.root, bg=BG, padx=36, pady=30)
        outer.pack(fill="both", expand=True)

        tk.Label(
            outer,
            text="MedMask",
            bg=BG,
            fg=INK,
            font=("TkDefaultFont", 26, "bold"),
        ).pack(anchor="w")
        tk.Label(
            outer,
            text="Локальное обезличивание медицинских документов",
            bg=BG,
            fg=MUTED,
            font=("TkDefaultFont", 12),
        ).pack(anchor="w", pady=(4, 22))

        card = tk.Frame(
            outer,
            bg=CARD,
            highlightbackground=LINE,
            highlightthickness=1,
            padx=28,
            pady=26,
        )
        card.pack(fill="both", expand=True)

        self.folder_title = tk.Label(
            card,
            text="Выберите папку с историями",
            bg=CARD,
            fg=INK,
            font=("TkDefaultFont", 16, "bold"),
        )
        self.folder_title.pack(anchor="w")

        self.folder_path = tk.Label(
            card,
            text="PDF, изображения и офисные документы",
            bg=CARD,
            fg=MUTED,
            justify="left",
            anchor="w",
            wraplength=590,
            font=("TkDefaultFont", 10),
        )
        self.folder_path.pack(fill="x", pady=(8, 18))

        controls = tk.Frame(card, bg=CARD)
        controls.pack(fill="x")
        self.choose_button = ttk.Button(
            controls,
            text="Выбрать папку",
            style="Secondary.TButton",
            command=self._choose_folder,
        )
        self.choose_button.pack(side="left")
        self.run_button = ttk.Button(
            controls,
            text="Обезличить",
            style="Accent.TButton",
            command=self._start,
            state="disabled",
        )
        self.run_button.pack(side="left", padx=(12, 0))
        self.open_button = ttk.Button(
            controls,
            text="Открыть результат",
            style="Secondary.TButton",
            command=self._open_result,
        )

        progress_info = tk.Frame(card, bg=CARD)
        progress_info.pack(fill="x", pady=(28, 0))
        self.progress_stage = tk.Label(
            progress_info,
            text="Ожидание",
            bg=CARD,
            fg=INK,
            anchor="w",
            font=("TkDefaultFont", 10, "bold"),
        )
        self.progress_stage.pack(side="left")
        self.progress_time = tk.Label(
            progress_info,
            text="",
            bg=CARD,
            fg=MUTED,
            anchor="e",
            font=("TkDefaultFont", 10),
        )
        self.progress_time.pack(side="right")

        self.progress = ttk.Progressbar(
            card,
            mode="determinate",
            maximum=100,
            style="MedMask.Horizontal.TProgressbar",
        )
        self.progress.pack(fill="x", pady=(8, 12))

        self.status = tk.Label(
            card,
            text="",
            bg=CARD,
            fg=MUTED,
            justify="left",
            anchor="nw",
            wraplength=590,
            font=("TkDefaultFont", 10),
        )
        self.status.pack(fill="both", expand=True)

    def _select_from_arguments(self) -> None:
        if len(sys.argv) > 1:
            candidate = Path(sys.argv[1]).expanduser()
            if candidate.is_dir():
                self._set_folder(candidate)

    def _choose_folder(self) -> None:
        selected = filedialog.askdirectory(
            parent=self.root,
            title="Выберите папку с медицинскими документами",
            mustexist=True,
        )
        if selected:
            self._set_folder(Path(selected))

    def _set_folder(self, path: Path) -> None:
        self.source_dir = path.resolve()
        self.output_dir = None
        self.folder_title.configure(text="Папка выбрана")
        self.folder_path.configure(text=str(self.source_dir))
        self.status.configure(text="", fg=MUTED)
        self.progress_stage.configure(text="Готово к запуску", fg=INK)
        self.progress_time.configure(text="")
        self.progress.configure(value=0)
        self.run_button.configure(state="normal")
        self.open_button.pack_forget()

    def _start(self) -> None:
        if self.source_dir is None:
            return
        self.choose_button.configure(state="disabled")
        self.run_button.configure(state="disabled")
        self.open_button.pack_forget()
        self.processing = True
        self.started_at = time.monotonic()
        self.last_progress = None
        self.progress.configure(mode="indeterminate", value=0)
        self.progress.start(12)
        self.progress_stage.configure(text="Поиск документов", fg=INK)
        self.progress_time.configure(text=f"{self.ACTIVITY_FRAMES[0]}  00:00")
        self.status.configure(text="Подготовка…", fg=MUTED)
        worker = threading.Thread(target=self._run_worker, args=(self.source_dir,), daemon=True)
        worker.start()

    def _run_worker(self, source_dir: Path) -> None:
        try:
            result = process_folder(
                source_dir,
                on_progress=lambda progress: self.events.put(("progress", progress)),
            )
            self.events.put(("done", result))
        except Exception as error:
            self.events.put(("error", error))

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "progress":
                    self._show_progress(payload)  # type: ignore[arg-type]
                elif kind == "done":
                    self._show_done(payload)  # type: ignore[arg-type]
                elif kind == "error":
                    self._show_error(payload)  # type: ignore[arg-type]
        except queue.Empty:
            pass
        self._refresh_elapsed()
        self.root.after(100, self._poll_events)

    def _show_progress(self, progress: Progress) -> None:
        self.last_progress = progress
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.configure(value=progress.percent)
        self.progress_stage.configure(text=progress.stage, fg=INK)
        file_number = min(progress.completed + 1, progress.total)
        lines = [f"Файл {file_number} из {progress.total}: {progress.current_name}"]
        if progress.detail:
            lines.append(progress.detail)
        self.status.configure(
            text="\n".join(lines),
            fg=MUTED,
        )
        self._refresh_elapsed()

    def _elapsed(self) -> str:
        seconds = 0 if self.started_at is None else int(time.monotonic() - self.started_at)
        minutes, seconds = divmod(seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def _refresh_elapsed(self) -> None:
        if not self.processing:
            return
        elapsed = self._elapsed()
        started_at = self.started_at or time.monotonic()
        frame = self.ACTIVITY_FRAMES[int((time.monotonic() - started_at) * 4) % len(self.ACTIVITY_FRAMES)]
        if self.last_progress is None:
            self.progress_time.configure(text=f"{frame}  {elapsed}")
        else:
            self.progress_time.configure(
                text=f"{frame}  {self.last_progress.percent}%  ·  {elapsed}"
            )

    def _show_done(self, result: BatchResult) -> None:
        self.output_dir = result.output_dir
        elapsed = self._elapsed()
        self.processing = False
        self.progress.stop()
        self.progress.configure(mode="determinate", value=100)
        self.progress_stage.configure(text="Готово", fg=ACCENT)
        self.progress_time.configure(text=f"100%  ·  {elapsed}")
        self.choose_button.configure(state="normal")
        self.run_button.configure(state="normal")
        self.open_button.pack(side="left", padx=(12, 0))

        review = result.needs_review
        skipped = sum(result.skipped_by_extension.values())
        lines = [
            f"Создано PDF: {result.successful}.",
            f"Результат: {result.output_dir}",
        ]
        if result.recognized_with_ocr:
            lines.append(f"OCR применён к документам: {result.recognized_with_ocr}.")
        if result.failed:
            lines.append(f"Не удалось обработать: {result.failed}.")
            errors = sorted({item.error for item in result.files if item.error})
            if errors:
                lines.append(f"Причина: {'; '.join(errors)}.")
        if review:
            lines.append(f"Требуют проверки: {len(review)}. Подробности находятся в _ОТЧЁТ.txt.")
        if skipped:
            lines.append(f"Неподдерживаемых файлов пропущено: {skipped}.")
        color = ERROR if result.successful == 0 else WARNING if review else ACCENT
        self.status.configure(text="\n".join(lines), fg=color)

    def _show_error(self, error: Exception) -> None:
        self.processing = False
        self.progress.stop()
        self.choose_button.configure(state="normal")
        self.run_button.configure(state="normal" if self.source_dir else "disabled")
        self.progress.configure(mode="determinate", value=0)
        self.progress_stage.configure(text="Ошибка", fg=ERROR)
        self.progress_time.configure(text=self._elapsed())
        if isinstance(error, MedMaskError):
            message = str(error)
        else:
            message = "Не удалось завершить обработку. Исходные файлы не изменены."
        self.status.configure(text=message, fg=ERROR)
        messagebox.showerror("MedMask", message, parent=self.root)

    def _open_result(self) -> None:
        if self.output_dir is not None and self.output_dir.exists():
            open_folder(self.output_dir)


def main() -> None:
    root = tk.Tk()
    MedMaskApp(root)
    root.mainloop()
