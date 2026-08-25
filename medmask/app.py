"""Настольный экран MedMask: один холст, светлая тема, плавные переходы."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog

from typing import TYPE_CHECKING

from . import __version__
from .ui import Animator, Button, ProgressBar, RoundedBox, SegmentRow, TextItem, truncate_middle

if TYPE_CHECKING:  # движок импортируется только когда действительно нужен
    from .batch import BatchResult, Progress


# Палитра светлой темы Civium: нейтрали zinc, акцент blue-600.
PAGE = "#F7F7F8"
CARD = "#FFFFFF"
BORDER = "#E4E4E7"
HAIRLINE = "#F0F0F2"
INK = "#09090B"
TEXT = "#3F3F46"
MUTED = "#71717A"
FAINT = "#A1A1AA"
PRIMARY = "#2563EB"
PRIMARY_HOVER = "#1D4ED8"
PRIMARY_PRESS = "#1E40AF"
TRACK = "#EFEFF1"
SUCCESS = "#059669"
WARNING = "#D97706"
DANGER = "#DC2626"

# Логические пиксели при 96 dpi. Реальные размеры даёт MedMaskApp.px():
# в Windows системный масштаб 125-200 % увеличивает шрифты, и коробки должны
# расти вместе с ними, иначе текст перестаёт помещаться.
PAD = 32
CARD_PAD = 24
WINDOW_WIDTH = 700
MIN_WIDTH = 620
BUTTON_HEIGHT = 36
CARD_RADIUS = 14
BUTTON_RADIUS = 10
PROGRESS_HEIGHT = 8


def open_folder(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    elif os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def plural(count: int, one: str, few: str, many: str) -> str:
    tail = abs(count) % 100
    if 11 <= tail <= 14:
        return many
    tail %= 10
    if tail == 1:
        return one
    if 2 <= tail <= 4:
        return few
    return many


def _fonts() -> dict[str, tkfont.Font]:
    family = tkfont.nametofont("TkDefaultFont").actual("family")
    mono = "Menlo" if sys.platform == "darwin" else "Consolas"
    if mono not in tkfont.families():
        mono = tkfont.nametofont("TkFixedFont").actual("family")
    return {
        "title": tkfont.Font(family=family, size=21, weight="bold"),
        "subtitle": tkfont.Font(family=family, size=12),
        "label": tkfont.Font(family=family, size=11),
        "path": tkfont.Font(family=family, size=14),
        "button": tkfont.Font(family=family, size=12),
        "stage": tkfont.Font(family=family, size=13),
        "body": tkfont.Font(family=family, size=12),
        "meta": tkfont.Font(family=mono, size=11),
    }


PRIMARY_STYLE = {
    "fill": PRIMARY,
    "hover": PRIMARY_HOVER,
    "press": PRIMARY_PRESS,
    "text": "#FFFFFF",
    "disabled_fill": "#EAEAEC",
    "disabled_text": FAINT,
}

CANCEL_STYLE = {
    "fill": DANGER,
    "hover": "#B91C1C",
    "press": "#991B1B",
    "text": "#FFFFFF",
    "disabled_fill": "#F1DADA",
    "disabled_text": "#A86A6A",
}

SECONDARY_STYLE = {
    "fill": CARD,
    "hover": "#F4F4F5",
    "press": "#E9E9EC",
    "text": INK,
    "outline": "#DCDCE0",
    "disabled_outline": "#EDEDEF",
    "disabled_fill": CARD,
    "disabled_text": FAINT,
}

GHOST_STYLE = {
    "fill": CARD,
    "hover": "#F4F4F5",
    "press": "#E9E9EC",
    "text": TEXT,
    "disabled_fill": CARD,
    "disabled_text": FAINT,
}


class MedMaskApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.source_dir: Path | None = None
        self.output_dir: Path | None = None
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.processing = False
        self.cancel_event = threading.Event()
        self.started_at: float | None = None
        self.next_meta_refresh = 0.0
        self.last_progress: "Progress | None" = None
        self.discovered: tuple[list[Path], dict[str, int]] | None = None
        self.has_documents = False
        self.scan_token = 0
        self.content_width = 0
        self.detail_text = ""
        self.detail_color = MUTED
        self.rise = 0.0

        self.fonts = _fonts()
        self.animator = Animator()
        self.scale = self._scale_factor(root)

        root.title("MedMask")
        root.configure(bg=PAGE)
        root.resizable(True, False)
        self._set_window_icon()

        self.canvas = tk.Canvas(root, bg=PAGE, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self._build()
        height = self._layout()
        self._place_window(self.px(WINDOW_WIDTH), height)
        root.minsize(self.px(MIN_WIDTH), height)

        self._select_from_arguments()
        self._intro()
        self._warm_engine()
        self.root.after(16, self._tick)

    def _set_window_icon(self) -> None:
        icon_path = Path(__file__).resolve().parent / "assets" / "app_icon.png"
        try:
            self.icon_image = tk.PhotoImage(file=str(icon_path))
            self.root.iconphoto(True, self.icon_image)
        except (OSError, tk.TclError):
            self.icon_image = None

    @staticmethod
    def _scale_factor(root: tk.Tk) -> float:
        """Во сколько раз система крупнее стандартных 96 dpi."""
        try:
            return max(1.0, root.winfo_fpixels("1i") / 96.0)
        except tk.TclError:
            return 1.0

    def px(self, value: float) -> int:
        return max(1, round(value * self.scale))

    # ---------- сцена ----------

    def _build(self) -> None:
        canvas = self.canvas
        animator = self.animator
        fonts = self.fonts

        self.title = TextItem(canvas, animator, font=fonts["title"], color=INK, background=PAGE, anchor="nw")
        self.subtitle = TextItem(canvas, animator, font=fonts["subtitle"], color=MUTED, background=PAGE, anchor="nw")
        self.version = TextItem(canvas, animator, font=fonts["label"], color=FAINT, background=PAGE, anchor="ne")

        self.card = RoundedBox(canvas, self.px(CARD_RADIUS), CARD, BORDER)
        self.hairline = canvas.create_line(0, 0, 0, 0, fill=HAIRLINE, width=self.px(1))

        self.folder_label = TextItem(canvas, animator, font=fonts["label"], color=MUTED, background=CARD, anchor="nw")
        self.folder_path = TextItem(canvas, animator, font=fonts["path"], color=INK, background=CARD, anchor="nw")

        self.choose_button = Button(
            canvas, animator,
            text="Выбрать папку", command=self._choose_folder,
            font=fonts["button"], style=SECONDARY_STYLE, background=CARD,
            padding=self.px(16), radius=self.px(BUTTON_RADIUS), height=self.px(BUTTON_HEIGHT),
        )
        self.run_button = Button(
            canvas, animator,
            text="Обезличить", command=self._start,
            font=fonts["button"], style=PRIMARY_STYLE, background=CARD,
            padding=self.px(20), radius=self.px(BUTTON_RADIUS), height=self.px(BUTTON_HEIGHT),
        )
        self.open_button = Button(
            canvas, animator,
            text="Открыть результат", command=self._open_result,
            font=fonts["button"], style=GHOST_STYLE, background=CARD,
            padding=self.px(14), radius=self.px(BUTTON_RADIUS), height=self.px(BUTTON_HEIGHT),
        )
        self.run_button.set_enabled(False)
        self.open_button.set_visible(False)

        self.stage = TextItem(canvas, animator, font=fonts["stage"], color=INK, background=CARD, anchor="nw")
        self.meta = TextItem(canvas, animator, font=fonts["meta"], color=MUTED, background=CARD, anchor="ne")
        self.progress = ProgressBar(canvas, animator, track=TRACK, fill=PRIMARY,
                                    height=self.px(PROGRESS_HEIGHT))
        self.detail = TextItem(canvas, animator, font=fonts["body"], color=MUTED, background=CARD, anchor="nw")
        self.summary = SegmentRow(canvas, animator, font=fonts["body"], background=CARD, separator_color=MUTED)

        self.title.set("MedMask", animate=False)
        self.subtitle.set("Обезличивание медицинских документов", animate=False)
        self.version.set(__version__, animate=False)
        self.folder_label.set("Папка", animate=False)
        self.folder_path.set("не выбрана", FAINT, animate=False)
        self.stage.set("Ожидание", MUTED, animate=False)

        canvas.bind("<Configure>", lambda _event: self._layout())

    def _layout(self) -> int:
        fonts = self.fonts
        px = self.px
        pad = px(PAD)
        card_pad = px(CARD_PAD)
        width = max(self.canvas.winfo_width(), px(MIN_WIDTH))
        rise = self.rise
        line = lambda name: fonts[name].metrics("linespace")

        y = pad + rise
        self.title.place(pad, y)
        self.version.place(width - pad, y + px(9))
        y += line("title") + px(4)
        self.subtitle.place(pad, y)
        y += line("subtitle") + px(24)

        card_top = y
        left = pad + card_pad
        right = width - pad - card_pad
        self.content_width = right - left

        y += card_pad
        self.folder_label.place(left, y)
        y += line("label") + px(4)
        self.folder_path.place(left, y)
        self._refresh_path()
        y += line("path") + px(20)

        x = left
        for button in (self.choose_button, self.run_button, self.open_button):
            button.place(x, y)
            x += button.width + px(10)
        y += self.run_button.height + px(22)

        self.canvas.coords(self.hairline, left, y + 0.5, right, y + 0.5)
        y += px(21)

        self.stage.place(left, y)
        self.meta.place(right, y + px(1))
        y += line("stage") + px(13)

        self.progress.place(left, y, right - left)
        y += self.progress.height + px(15)

        self.detail.place(left, y)
        self._refresh_detail()
        y += line("body") + px(6)

        self.summary.place(left, y)
        y += line("body")

        # снизу текст занимает меньше, чем строка, поэтому отступ чуть меньше
        card_bottom = y + card_pad - px(5)
        self.card.place(pad, card_top, width - pad, card_bottom)
        return int(card_bottom - rise + pad)

    def _place_window(self, width: int, height: int) -> None:
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, int((screen_height - height) / 2.6))
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _intro(self) -> None:
        try:
            self.root.attributes("-alpha", 0.0)
            self.animator.run(
                "window",
                0.26,
                lambda position: self.root.attributes("-alpha", position),
            )
            # страховка: окно не должно остаться прозрачным, если переход сорвется
            self.root.after(700, lambda: self.root.attributes("-alpha", 1.0))
        except tk.TclError:
            pass

        start = self.px(14)

        def rise(position: float) -> None:
            self.rise = start * (1 - position)
            self._layout()

        self.animator.run("rise", 0.5, rise)

    def _warm_engine(self) -> None:
        """Подгружает движок в фоне: окно появляется сразу, а к моменту выбора
        папки тяжелые модули уже в памяти."""

        def warm() -> None:
            try:
                from . import batch  # noqa: F401
            except Exception:
                pass

        threading.Thread(target=warm, daemon=True).start()

    # ---------- цикл ----------

    def _tick(self) -> None:
        latest_progress = None
        terminal_event = None
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "progress":
                    # Worker-процессы могут прислать сотни событий между двумя
                    # кадрами. Для UI важен самый свежий снимок, а не отрисовка
                    # каждого промежуточного значения.
                    latest_progress = payload
                elif kind == "scan":
                    self._show_scan(payload)  # type: ignore[arg-type]
                elif kind in {"done", "error"}:
                    terminal_event = (kind, payload)
        except queue.Empty:
            pass

        if terminal_event is not None:
            kind, payload = terminal_event
            if kind == "done":
                self._show_done(payload)  # type: ignore[arg-type]
            else:
                self._show_error(payload)  # type: ignore[arg-type]
        elif latest_progress is not None:
            self._show_progress(latest_progress)  # type: ignore[arg-type]

        delta = self.animator.tick()
        moving = self.progress.update(delta)
        now = time.monotonic()
        if self.processing and now >= self.next_meta_refresh:
            self._refresh_meta()
            self.next_meta_refresh = now + 0.25
        busy = moving or self.animator.busy
        delay = 16 if busy else 80 if self.processing else 60
        self.root.after(delay, self._tick)

    # ---------- выбор папки ----------

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
        self.last_progress = None
        self.discovered = None
        self._refresh_path(animate=True)
        self.stage.set("Подсчет файлов", MUTED)
        self.meta.set("")
        self._set_detail("")
        self.summary.set([])
        self.progress.set_color(PRIMARY)
        self.progress.set_value(0, immediate=True)
        self.has_documents = False
        self.run_button.set_enabled(False)
        self.open_button.set_visible(False)
        self.scan_token += 1
        token = self.scan_token
        threading.Thread(target=self._scan_worker, args=(self.source_dir, token), daemon=True).start()

    def _scan_worker(self, path: Path, token: int) -> None:
        from .batch import discover_files

        try:
            files, skipped = discover_files(path)
        except OSError:
            files, skipped = [], {}
        self.events.put(("scan", (token, files, skipped)))

    def _show_scan(
        self, payload: tuple[int, list[Path], dict[str, int]]
    ) -> None:
        token, files, skipped_by_extension = payload
        if token != self.scan_token or self.processing:
            return
        found = len(files)
        skipped = sum(skipped_by_extension.values())
        if not found:
            self.stage.set("Нет документов", WARNING)
            self._set_detail("Поддерживаются PDF, изображения, DOCX, RTF, ODT, TXT и XLSX.")
            self.run_button.set_enabled(False)
            return
        self.stage.set("Готово к запуску", INK)
        parts = [f"{found} {plural(found, 'документ', 'документа', 'документов')}"]
        if skipped:
            parts.append(f"{skipped} без поддержки")
        self._set_detail("  ·  ".join(parts))
        self.discovered = (files, skipped_by_extension)
        self.has_documents = True
        self.run_button.set_enabled(True)

    def _refresh_path(self, animate: bool = False) -> None:
        if self.source_dir is None:
            self.folder_path.set("не выбрана", FAINT, animate=animate)
            return
        text = truncate_middle(str(self.source_dir), self.fonts["path"], self.content_width)
        self.folder_path.set(text, INK, animate=animate)

    def _set_detail(self, text: str, color: str = MUTED, animate: bool = True) -> None:
        self.detail_text = text
        self.detail_color = color
        self._refresh_detail(animate=animate)

    def _refresh_detail(self, animate: bool = False) -> None:
        text = truncate_middle(self.detail_text, self.fonts["body"], self.content_width)
        self.detail.set(text, self.detail_color, animate=animate)

    # ---------- обработка ----------

    def _start(self) -> None:
        if self.processing:
            self._request_cancel()
            return
        if self.source_dir is None:
            return
        self.processing = True
        self.cancel_event.clear()
        self.started_at = time.monotonic()
        self.next_meta_refresh = self.started_at
        self.last_progress = None
        self.choose_button.set_enabled(False)
        self.run_button.set_text("Отменить")
        self.run_button.set_style(CANCEL_STYLE)
        self.run_button.set_enabled(True)
        self._layout()
        self.open_button.set_visible(False)
        self.progress.set_color(PRIMARY)
        self.progress.start_scan()
        self.stage.set("Поиск документов", INK)
        self._set_detail("")
        self.summary.set([])
        threading.Thread(target=self._run_worker, args=(self.source_dir,), daemon=True).start()

    def _request_cancel(self) -> None:
        if self.cancel_event.is_set():
            return
        self.cancel_event.set()
        self.run_button.set_enabled(False)
        self.stage.set("Отмена обработки", WARNING)
        self._set_detail("Завершаем текущую страницу и останавливаем задания.", MUTED)

    def _restore_run_button(self) -> None:
        self.run_button.set_text("Обезличить")
        self.run_button.set_style(PRIMARY_STYLE)
        self._layout()

    def _run_worker(self, source_dir: Path) -> None:
        from .batch import process_folder

        try:
            result = process_folder(
                source_dir,
                on_progress=lambda progress: self.events.put(("progress", progress)),
                is_cancelled=self.cancel_event.is_set,
                discovered=self.discovered,
            )
            self.events.put(("done", result))
        except Exception as error:  # noqa: BLE001 — окно показывает любую ошибку
            self.events.put(("error", error))

    def _show_progress(self, progress: "Progress") -> None:
        self.last_progress = progress
        if progress.stage != "Анализ документов" or progress.percent > 0:
            self.progress.set_value(progress.percent)
        self.stage.set(progress.stage, INK)
        if progress.overall_fraction is None:
            prefix = f"{min(progress.completed + 1, progress.total)} из {progress.total}"
        else:
            prefix = f"готово {progress.completed} из {progress.total}"
        self._set_detail(
            f"{prefix}  ·  {progress.current_name}", MUTED, animate=False
        )
        self.summary.set([(progress.detail, FAINT)] if progress.detail else [])

    def _elapsed(self) -> str:
        seconds = 0 if self.started_at is None else int(time.monotonic() - self.started_at)
        return self._format_duration(seconds)

    @staticmethod
    def _format_duration(seconds: int) -> str:
        minutes, seconds = divmod(seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def _refresh_meta(self) -> None:
        percent = self.last_progress.percent if self.last_progress else 0
        elapsed_seconds = (
            0 if self.started_at is None else int(time.monotonic() - self.started_at)
        )
        eta = ""
        if 2 <= percent < 100 and elapsed_seconds >= 3:
            remaining = round(elapsed_seconds * (100 - percent) / percent)
            eta = f"   осталось ~{self._format_duration(remaining)}"
        self.meta.set(
            f"{percent:>3d}%   {self._format_duration(elapsed_seconds)}{eta}",
            MUTED,
            animate=False,
        )

    def _show_done(self, result: "BatchResult") -> None:
        self.output_dir = result.output_dir
        elapsed = self._elapsed()
        self.processing = False
        self.cancel_event.clear()
        self._restore_run_button()
        self.progress.set_value(100)
        self.progress.set_color(DANGER if not result.successful else SUCCESS if not result.needs_review else WARNING)
        self.stage.set("Готово" if result.successful else "Ничего не создано", SUCCESS if result.successful else DANGER)
        self.meta.set(f"100%   {elapsed}", MUTED, animate=False)
        self.choose_button.set_enabled(True)
        self.run_button.set_enabled(self.has_documents)
        self.open_button.reveal()

        self._set_detail(str(result.output_dir), TEXT)

        segments: list[tuple[str, str]] = [
            (f"{result.successful} {plural(result.successful, 'файл', 'файла', 'файлов')}", INK)
        ]
        if result.recognized_with_ocr:
            segments.append((f"OCR {result.recognized_with_ocr}", MUTED))
        if result.needs_review:
            segments.append((f"проверить {len(result.needs_review)}", WARNING))
        if result.failed:
            segments.append((f"с ошибкой {result.failed}", DANGER))
        skipped = sum(result.skipped_by_extension.values())
        if skipped:
            segments.append((f"пропущено {skipped}", FAINT))
        self.summary.set(segments)

    def _show_error(self, error: Exception) -> None:
        self.processing = False
        self._restore_run_button()
        self.progress.set_value(self.progress.value, immediate=True)
        self.choose_button.set_enabled(True)
        self.run_button.set_enabled(self.has_documents)
        self.meta.set(self._elapsed(), MUTED, animate=False)
        from .batch import BatchCancelled, MedMaskError

        if isinstance(error, BatchCancelled):
            self.progress.set_color(WARNING)
            self.stage.set("Отменено", WARNING)
            message = "Обработка отменена. Исходные файлы не изменены."
        elif isinstance(error, MedMaskError):
            self.progress.set_color(DANGER)
            self.stage.set("Ошибка", DANGER)
            message = str(error)
        else:
            self.progress.set_color(DANGER)
            self.stage.set("Ошибка", DANGER)
            message = "Не удалось завершить обработку. Исходные файлы не изменены."
        self._set_detail(
            message,
            WARNING if isinstance(error, BatchCancelled) else DANGER,
        )
        self.summary.set([])

    def _open_result(self) -> None:
        if self.output_dir is not None and self.output_dir.exists():
            open_folder(self.output_dir)


def main() -> None:
    root = tk.Tk()
    MedMaskApp(root)
    root.mainloop()
