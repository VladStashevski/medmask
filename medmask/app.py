"""Настольный экран MedMask: лист с документами, панель действий, переходы.

Экран построен вокруг того, что происходит с папкой: строка на документ,
статус слева, пометка справа. Пока папка не выбрана, лист показывает
приглашение, а не пустой каркас с нулевым прогрессом.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

from typing import TYPE_CHECKING

from . import __version__, theme
from .theme import (
    BORDER,
    CANCEL_STYLE,
    CARD,
    DANGER,
    FAINT,
    HAIRLINE,
    INK,
    MUTED,
    PAGE,
    PRIMARY,
    PRIMARY_STYLE,
    SECONDARY_STYLE,
    SUCCESS,
    TEXT,
    TRACK,
    WARNING,
)
from .ui import (
    Animator,
    Button,
    FileList,
    Icon,
    ProgressBar,
    RoundedBox,
    TextItem,
    truncate_end,
    truncate_middle,
)

if TYPE_CHECKING:  # движок импортируется только когда действительно нужен
    from .batch import BatchResult, Progress


PAD = theme.SPACE_5


def open_folder(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    elif os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def _round_icon(image: tk.PhotoImage, radius_ratio: float = 0.22) -> tk.PhotoImage:
    """Скругляет углы картинки прозрачностью.

    Иконка приложения хранится квадратной: в окне она смотрелась бы плиткой,
    а не значком программы.
    """
    width, height = image.width(), image.height()
    radius = max(1, int(min(width, height) * radius_ratio))
    for y in range(height):
        for x in range(width):
            offset_x = radius - x if x < radius else x - (width - radius - 1)
            offset_y = radius - y if y < radius else y - (height - radius - 1)
            if offset_x <= 0 or offset_y <= 0:
                continue
            if offset_x * offset_x + offset_y * offset_y > radius * radius:
                image.transparency_set(x, y, True)
    return image


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
        self.show_footer = False
        self.rise = 0.0
        self.name_limit = 0
        self.path_limit = 0
        self.stage_limit = 0
        self.stage_text = ""
        self.stage_color = MUTED

        self.fonts = theme.build_fonts()
        self.animator = Animator()
        self.scale = self._scale_factor(root)

        root.title("MedMask")
        root.configure(bg=PAGE)
        root.resizable(True, True)
        self._set_window_icon()
        self.seamless = False
        self.custom_titlebar = False
        self._drag_origin = None
        self._style_window()

        self.canvas = tk.Canvas(root, bg=PAGE, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self._build()
        self._place_window(self.px(theme.WINDOW_WIDTH), self.px(theme.WINDOW_HEIGHT))
        root.minsize(self.px(theme.MIN_WIDTH), self.px(theme.MIN_HEIGHT))
        self._layout()

        self._bind_keys()
        self._build_menu()
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

    def _style_window(self) -> None:
        """Снимает системную полосу заголовка, если система это позволяет.

        macOS: окно остается обычным, но контент рисуется под шапкой, а
        светофор висит поверх — окно читается как один лист.
        Windows: полоса снимается совсем, и приложение рисует свою.
        Если это не удалось, остается системная шапка: закрыть окно
        пользователь сможет в любом случае.
        """
        if sys.platform == "darwin":
            try:
                self.root.tk.call(
                    "wm", "attributes", ".", "-stylemask",
                    ("titled", "closable", "miniaturizable", "resizable",
                     "fullsizecontentview"),
                )
                # системная подпись иначе ложится поверх содержимого
                self.root.title("")
                self.seamless = True
            except tk.TclError:
                self.seamless = False
            return

        if os.name == "nt":
            self.seamless = self.custom_titlebar = self._drop_windows_caption()

    def _drop_windows_caption(self) -> bool:
        """Убирает полосу заголовка Windows, оставляя окно в панели задач."""
        try:
            import ctypes

            self.root.update_idletasks()
            user32 = ctypes.windll.user32  # type: ignore[attr-defined]
            handle = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            style_index, caption = -16, 0x00C00000
            style = user32.GetWindowLongW(handle, style_index)
            if not style:
                return False
            user32.SetWindowLongW(handle, style_index, style & ~caption)
            # SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED
            user32.SetWindowPos(handle, 0, 0, 0, 0, 0, 0x0027)
            return True
        except Exception:  # noqa: BLE001 — на любой осечке остается обычная шапка
            return False

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

        self.card = RoundedBox(canvas, self.px(theme.CARD_RADIUS), CARD, BORDER)
        self.header_line = canvas.create_line(0, 0, 0, 0, fill=HAIRLINE, width=self.px(1))
        self.footer_line = canvas.create_line(0, 0, 0, 0, fill=HAIRLINE, width=self.px(1))

        self.folder_icon = Icon(canvas, "folder", self.px(theme.HEADER_ICON), MUTED)
        self.folder_name = TextItem(canvas, animator, font=fonts["heading"], color=INK,
                                    background=CARD, anchor="nw")
        self.folder_path = TextItem(canvas, animator, font=fonts["small"], color=MUTED,
                                    background=CARD, anchor="nw")
        self.count = TextItem(canvas, animator, font=fonts["small"], color=MUTED,
                              background=CARD, anchor="ne")

        # Отдельный холст, а не общий: элементы Tk не обрезаются рамкой области,
        # и строка на границе прокрутки залезала бы на подвал и шапку листа.
        self.list_canvas = tk.Canvas(canvas, bg=CARD, highlightthickness=0, bd=0)
        self.list_window = canvas.create_window(0, 0, anchor="nw", window=self.list_canvas)
        self.files = FileList(
            self.list_canvas, animator,
            fonts=fonts,
            style={
                "card": CARD,
                "row_active": theme.ROW_ACTIVE,
                "ink": INK,
                "text": TEXT,
                "muted": MUTED,
                "faint": FAINT,
                "primary": PRIMARY,
                "success": SUCCESS,
                "warning": WARNING,
                "danger": DANGER,
            },
            row_height=self.px(theme.ROW_HEIGHT),
            radius=self.px(theme.ROW_RADIUS),
            icon_size=self.px(theme.ICON_SIZE),
            # внутренний отступ равен сдвигу холста влево, поэтому иконки строк
            # стоят на одной вертикали с иконкой папки в шапке
            pad=self.px(theme.SPACE_2),
            gap=self.px(theme.SPACE_3),
        )

        # приглашение вместо пустого каркаса
        self.empty_icon = Icon(self.list_canvas, "folder", self.px(28), "#D4D4D8")
        self.empty_title = TextItem(self.list_canvas, animator, font=fonts["body"], color=TEXT,
                                    background=CARD, anchor="n")
        self.empty_hint = TextItem(self.list_canvas, animator, font=fonts["small"], color=FAINT,
                                   background=CARD, anchor="n")

        self.stage = TextItem(canvas, animator, font=fonts["small"], color=MUTED,
                              background=CARD, anchor="nw")
        self.meta = TextItem(canvas, animator, font=fonts["mono"], color=MUTED,
                             background=CARD, anchor="ne")
        self.progress = ProgressBar(canvas, animator, track=TRACK, fill=PRIMARY,
                                    height=self.px(theme.PROGRESS_HEIGHT))

        # В шапке macOS слева стоит светофор, поэтому подпись уходит вправо;
        # на Windows своя шапка и слева свободно.
        self.brand = TextItem(
            canvas, animator, font=fonts["small"], color=FAINT, background=PAGE,
            anchor="w" if self.custom_titlebar else "e",
        )
        self.close_button = None
        self.minimize_button = None
        if self.custom_titlebar:
            size = self.px(theme.WINDOW_BUTTON)
            self.minimize_button = Button(
                canvas, animator, text="", command=self.root.iconify,
                font=fonts["small"], style=GHOST_STYLE, background=PAGE,
                padding=0, radius=size / 2, height=size,
                icon="minus", icon_size=self.px(14), gap=0,
            )
            self.close_button = Button(
                canvas, animator, text="", command=self.root.destroy,
                font=fonts["small"], style=GHOST_STYLE, background=PAGE,
                padding=0, radius=size / 2, height=size,
                icon="cross", icon_size=self.px(14), gap=0,
            )

        self.version = TextItem(canvas, animator, font=fonts["small"], color=FAINT,
                                background=PAGE, anchor="e")
        self.hint = TextItem(canvas, animator, font=fonts["small"], color=FAINT,
                             background=PAGE, anchor="w")

        # Скругление в половину высоты: кнопка становится пилюлей, а край
        # у нее сглаженный, поэтому мелкая ступенчатость больше не видна.
        pill = self.px(theme.BUTTON_HEIGHT) / 2
        self.choose_button = Button(
            canvas, animator,
            text="Выбрать папку", command=self._choose_folder,
            font=fonts["button"], style=SECONDARY_STYLE, background=PAGE,
            padding=self.px(theme.SPACE_5), radius=pill,
            height=self.px(theme.BUTTON_HEIGHT),
        )
        self.open_button = Button(
            canvas, animator,
            text="Открыть результат", command=self._open_result,
            font=fonts["button"], style=SECONDARY_STYLE, background=PAGE,
            padding=self.px(theme.SPACE_5), radius=pill,
            height=self.px(theme.BUTTON_HEIGHT),
        )
        self.run_button = Button(
            canvas, animator,
            text="Обезличить", command=self._start,
            font=fonts["button"], style=PRIMARY_STYLE, background=PAGE,
            padding=self.px(theme.SPACE_6), radius=pill,
            height=self.px(theme.BUTTON_HEIGHT),
        )
        self.run_button.set_enabled(False)
        self.open_button.set_visible(False)

        self.version.set(__version__, animate=False)
        self.hint.set("Все обрабатывается на этом компьютере, без интернета", animate=False)
        self.brand.set("MedMask", animate=False)
        self._refresh_path()
        self._show_empty(
            "Выберите папку с документами",
            "PDF, изображения, DOCX, RTF, ODT, TXT и XLSX",
        )

        canvas.bind("<Configure>", lambda _event: self._layout())
        if self.custom_titlebar:
            canvas.bind("<ButtonPress-1>", self._start_drag, add="+")
            canvas.bind("<B1-Motion>", self._drag_window, add="+")
        self.list_canvas.bind("<MouseWheel>", self._on_wheel)
        self.list_canvas.bind("<Button-4>", lambda event: self._on_wheel(event, 1))
        self.list_canvas.bind("<Button-5>", lambda event: self._on_wheel(event, -1))

    # ---------- верстка ----------

    def _layout(self) -> int:
        px = self.px
        fonts = self.fonts
        line = lambda name: fonts[name].metrics("linespace")
        pad = px(PAD)
        inner = px(theme.SPACE_4)
        width = max(self.canvas.winfo_width(), px(theme.MIN_WIDTH))
        height = max(self.canvas.winfo_height(), px(theme.MIN_HEIGHT))
        rise = self.rise

        titlebar = px(theme.TITLEBAR_HEIGHT) if self.seamless else 0
        footer_middle = height - pad - px(theme.FOOTER_HEIGHT) / 2 + rise
        panel_top = (
            height - pad - px(theme.FOOTER_HEIGHT) - px(theme.SPACE_3)
            - px(theme.BUTTON_HEIGHT) + rise
        )
        content = min(width - pad * 2, px(theme.MAX_CONTENT_WIDTH))
        card_left = round((width - content) / 2)
        card_right = card_left + content
        card_top = (titlebar + px(theme.SPACE_3) if titlebar else pad) + rise

        # содержимое шапки
        middle = titlebar / 2 + rise
        if self.custom_titlebar:
            self.brand.place(card_left, middle)
            x = card_right
            for button in (self.close_button, self.minimize_button):
                if button is None:
                    continue
                x -= button.width
                button.place(x, middle - button.height / 2)
                x -= px(theme.SPACE_1)
        else:
            self.brand.place(card_right, middle)
        card_bottom = panel_top - px(theme.SPACE_4)
        self.card.place(card_left, card_top, card_right, card_bottom)

        left = card_left + inner
        right = card_right - inner

        # шапка листа: имя папки, путь и счетчик документов
        y = card_top + inner
        icon_size = px(theme.ICON_SIZE)
        self.folder_icon.place(left + icon_size / 2, y + line("heading") / 2)
        text_left = left + icon_size + px(theme.SPACE_3)
        self.folder_name.place(text_left, y)
        self.count.place(right, y + px(theme.SPACE_1))
        y += line("heading") + px(theme.SPACE_1)
        self.folder_path.place(text_left, y)
        y += line("small") + px(theme.SPACE_3)

        # Правый край шапки занят счетчиком и версией: имя и путь обрезаются
        # по остатку, иначе на узком окне строки налезают друг на друга.
        gap = px(theme.SPACE_4)
        self.name_limit = int(right - self.count.measure() - gap - text_left)
        self.path_limit = int(right - text_left)
        self._refresh_path()

        self.canvas.coords(self.header_line, card_left, y + 0.5, card_right, y + 0.5)
        list_top = y + px(theme.SPACE_2)

        # подвал листа появляется только когда есть что показывать
        if self.show_footer:
            footer_height = (
                line("small") + px(theme.SPACE_3) + self.progress.height + inner + px(theme.SPACE_3)
            )
            footer_top = card_bottom - footer_height
            self.canvas.coords(self.footer_line, card_left, footer_top + 0.5, card_right, footer_top + 0.5)
            self.canvas.itemconfigure(self.footer_line, state="normal")
            self.stage.place(left, footer_top + px(theme.SPACE_3))
            self.meta.place(right, footer_top + px(theme.SPACE_3))
            self.stage_limit = int(right - left - self.meta.measure() - px(theme.SPACE_4))
            self._refresh_stage()
            self.progress.place(
                left,
                footer_top + px(theme.SPACE_3) + line("small") + px(theme.SPACE_3),
                right - left,
            )
            self.progress.set_visible(True)
            list_bottom = footer_top - px(theme.SPACE_2)
        else:
            self.canvas.itemconfigure(self.footer_line, state="hidden")
            self.progress.set_visible(False)
            self.stage.place(left, card_bottom)
            self.meta.place(right, card_bottom)
            list_bottom = card_bottom - px(theme.SPACE_2)

        list_x = left - px(theme.SPACE_2)
        list_width = max(1, right - left + px(theme.SPACE_4))
        # Высота кратна строке: тогда прокрутка никогда не оставляет половину
        # строки у верхнего или нижнего края.
        row = self.files.row_height
        list_height = max(row, int((list_bottom - list_top) // row) * row)
        self.canvas.coords(self.list_window, list_x, list_top)
        self.canvas.itemconfigure(self.list_window, width=list_width, height=list_height)
        self.files.place(0, 0, list_width, list_height)

        # приглашение по центру области списка (координаты ее холста)
        middle_x = list_width / 2
        block = px(28) + px(theme.SPACE_4) + line("body") + px(theme.SPACE_1) + line("small")
        top = max(0, (list_height - block) / 2)
        self.empty_icon.place(middle_x, top + px(14))
        self.empty_title.place(middle_x, top + px(28) + px(theme.SPACE_4))
        self.empty_hint.place(middle_x, top + px(28) + px(theme.SPACE_4) + line("body") + px(theme.SPACE_1))

        # нижняя строка окна: слева обещание, справа версия
        self.hint.place(card_left, footer_middle)
        self.version.place(card_right, footer_middle)

        # панель действий под листом
        x = card_right
        for button in (self.run_button, self.open_button):
            if not button.visible:
                continue
            x -= button.width
            button.place(x, panel_top)
            x -= px(theme.SPACE_2)
        self.choose_button.place(x - self.choose_button.width, panel_top)
        return height

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

        start = self.px(10)

        def rise(position: float) -> None:
            self.rise = start * (1 - position)
            self._layout()

        self.animator.run("rise", 0.5, rise)

    def _bind_keys(self) -> None:
        """Клавиши те же, что ожидаешь от настольной программы."""
        root = self.root
        for shortcut in ("<Command-o>", "<Control-o>"):
            root.bind(shortcut, lambda _event: self._choose_folder())
        for shortcut in ("<Command-Return>", "<Control-Return>"):
            root.bind(shortcut, lambda _event: self._start())
        for shortcut in ("<Command-Shift-O>", "<Control-Shift-O>"):
            root.bind(shortcut, lambda _event: self._open_result())
        root.bind("<Escape>", self._on_escape)

    def _on_escape(self, _event) -> None:
        if self.processing:
            self._request_cancel()

    def _build_menu(self) -> None:
        """Меню приложения: без него программа выглядит окном, а не программой."""
        if sys.platform != "darwin":
            return
        try:
            menubar = tk.Menu(self.root)
            apple = tk.Menu(menubar, name="apple")
            menubar.add_cascade(menu=apple)
            apple.add_command(label="О программе MedMask", command=self._show_about)
            file_menu = tk.Menu(menubar)
            menubar.add_cascade(label="Файл", menu=file_menu)
            file_menu.add_command(
                label="Выбрать папку…", accelerator="Cmd+O", command=self._choose_folder
            )
            file_menu.add_command(
                label="Обезличить", accelerator="Cmd+Return", command=self._start
            )
            file_menu.add_command(
                label="Открыть результат", accelerator="Cmd+Shift+O", command=self._open_result
            )
            self.root.configure(menu=menubar)
        except tk.TclError:
            pass

    def _show_about(self) -> None:
        """Небольшое окно о программе — в том же оформлении, что и главное."""
        window = tk.Toplevel(self.root)
        window.title("")
        window.configure(bg=PAGE)
        window.resizable(False, False)
        window.transient(self.root)
        if sys.platform == "darwin":
            try:
                window.tk.call(
                    "wm", "attributes", window, "-stylemask",
                    ("titled", "closable", "fullsizecontentview"),
                )
            except tk.TclError:
                pass

        # Размер задается после стиля: смена stylemask сбрасывает геометрию
        # окна в 1x1.
        width, height = self.px(330), self.px(330)
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + self.px(60)
        window.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

        canvas = tk.Canvas(window, bg=PAGE, highlightthickness=0, bd=0)
        canvas.pack(fill="both", expand=True)
        animator = self.animator
        fonts = self.fonts
        middle = width / 2

        mark = None
        if self.icon_image is not None:
            # PhotoImage уменьшается только целым делителем, поэтому берем
            # ближайший к нужной высоте
            factor = max(1, round(self.icon_image.height() / self.px(64)))
            mark = _round_icon(self.icon_image.subsample(factor, factor))
            canvas.create_image(middle, self.px(78), image=mark)
        else:
            Icon(canvas, "shield", self.px(52), PRIMARY).place(middle, self.px(78))

        title = TextItem(canvas, animator, font=fonts["heading"], color=INK,
                         background=PAGE, anchor="n")
        title.set("MedMask", animate=False)
        title.place(middle, self.px(120))

        version = TextItem(canvas, animator, font=fonts["small"], color=MUTED,
                           background=PAGE, anchor="n")
        version.set(f"Версия {__version__}", animate=False)
        version.place(middle, self.px(148))

        about = TextItem(canvas, animator, font=fonts["small"], color=TEXT,
                         background=PAGE, anchor="n", width=self.px(250))
        about.set(
            "Локальное обезличивание медицинских документов.\n"
            "Файлы не покидают компьютер.",
            animate=False,
        )
        about.place(middle, self.px(184))

        close = Button(
            canvas, animator, text="Закрыть", command=window.destroy,
            font=fonts["button"], style=SECONDARY_STYLE, background=PAGE,
            padding=self.px(theme.SPACE_5), radius=self.px(theme.BUTTON_HEIGHT) / 2,
            height=self.px(theme.BUTTON_HEIGHT),
        )
        close.place(middle - close.width / 2, height - self.px(theme.BUTTON_HEIGHT) - self.px(theme.SPACE_5))

        window.bind("<Escape>", lambda _event: window.destroy())
        # ссылки держат объекты живыми, пока открыто окно
        window._medmask_parts = (title, version, about, close, mark)  # type: ignore[attr-defined]
        window.focus_set()

    def _warm_engine(self) -> None:
        """Подгружает движок в фоне: окно появляется сразу, а к моменту выбора
        папки тяжелые модули уже в памяти."""

        def warm() -> None:
            try:
                from . import batch  # noqa: F401
            except Exception:
                pass

        threading.Thread(target=warm, daemon=True).start()

    def _start_drag(self, event) -> None:
        """Своя шапка тянет окно так же, как системная."""
        if event.y > self.px(theme.TITLEBAR_HEIGHT):
            self._drag_origin = None
            return
        self._drag_origin = (
            event.x_root - self.root.winfo_x(),
            event.y_root - self.root.winfo_y(),
        )

    def _drag_window(self, event) -> None:
        if self._drag_origin is None:
            return
        shift_x, shift_y = self._drag_origin
        self.root.geometry(f"+{event.x_root - shift_x}+{event.y_root - shift_y}")

    def _on_wheel(self, event, direction: int = 0) -> None:
        if not self.files.entries:
            return
        step = self.files.row_height
        if direction:
            amount = -direction * step
        else:
            # macOS отдает небольшие значения с инерцией, X11 — кратные 120
            delta = event.delta
            amount = -delta * step / 3 if abs(delta) < 30 else -delta / 120 * step
        self.files.scroll_by(amount)

    # ---------- состояния листа ----------

    def _show_empty(self, title: str, hint: str, color: str = TEXT, icon: str = "folder") -> None:
        self.files.set_files([])
        self.empty_icon.set_name(icon)
        self.empty_icon.configure("#D4D4D8" if icon == "folder" else WARNING)
        self.empty_icon.set_visible(True)
        self.empty_title.set(title, color)
        self.empty_hint.set(hint)

    def _hide_empty(self) -> None:
        self.empty_icon.set_visible(False)
        self.empty_title.set("", animate=False)
        self.empty_hint.set("", animate=False)

    def _set_stage(self, text: str, color: str = MUTED, animate: bool = True) -> None:
        self.stage_text = text
        self.stage_color = color
        self._refresh_stage(animate=animate)

    def _refresh_stage(self, animate: bool = False) -> None:
        self.stage.set(
            truncate_end(self.stage_text, self.fonts["small"], self.stage_limit),
            self.stage_color,
            animate=animate,
        )

    def _set_footer(self, visible: bool) -> None:
        if visible == self.show_footer:
            return
        self.show_footer = visible
        self._layout()

    # ---------- цикл ----------

    def _tick(self) -> None:
        """Кадр всегда планирует следующий.

        Сбой в одном переходе не должен подвешивать окно: без этого любая
        ошибка перерисовки останавливала цикл, и работающее приложение
        выглядело зависшим.
        """
        delay = 60
        try:
            delay = self._frame()
        finally:
            self.root.after(delay, self._tick)

    def _frame(self) -> int:
        latest_progress = None
        terminal_event = None
        updates: list["Progress"] = []
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "progress":
                    # Worker-процессы могут прислать сотни событий между двумя
                    # кадрами. Для полосы важен самый свежий снимок, а для
                    # списка — каждое событие, которое меняет строку.
                    latest_progress = payload
                    updates.append(payload)  # type: ignore[arg-type]
                elif kind == "scan":
                    self._show_scan(payload)  # type: ignore[arg-type]
                elif kind in {"done", "error"}:
                    terminal_event = (kind, payload)
        except queue.Empty:
            pass

        if updates:
            # На документ приходит много событий подряд; строке важно только
            # последнее, поэтому список перерисовывается один раз за кадр.
            newest: dict[int, "Progress"] = {}
            for update in updates:
                if update.number:
                    newest[update.number] = update
            for progress in newest.values():
                self._apply_row(progress)
            if newest:
                self.files.refresh()

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
        listing = self.files.update(delta)
        now = time.monotonic()
        if self.processing and now >= self.next_meta_refresh:
            self._refresh_meta()
            self.next_meta_refresh = now + 0.25
        busy = moving or listing or self.animator.busy
        return 16 if busy else 80 if self.processing else 60

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
        self._refresh_path()
        self.count.set("подсчет файлов", MUTED)
        self._set_stage("")
        self.meta.set("")
        self._set_footer(False)
        self.progress.set_color(PRIMARY)
        self.progress.set_value(0, immediate=True)
        self.has_documents = False
        self.run_button.set_enabled(False)
        self.open_button.set_visible(False)
        self._show_empty("Читаем папку", "")
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

    def _show_scan(self, payload: tuple[int, list[Path], dict[str, int]]) -> None:
        token, files, skipped_by_extension = payload
        if token != self.scan_token or self.processing:
            return
        found = len(files)
        skipped = sum(skipped_by_extension.values())
        if not found:
            self.count.set("", MUTED)
            self._show_empty(
                "В папке нет подходящих документов",
                "Подходят PDF, изображения, DOCX, RTF, ODT, TXT и XLSX",
                color=INK,
                icon="alert",
            )
            self.run_button.set_enabled(False)
            self._layout()
            return
        self._hide_empty()
        parts = [f"{found} {plural(found, 'документ', 'документа', 'документов')}"]
        if skipped:
            parts.append(f"{skipped} без поддержки")
        self.count.set("  ·  ".join(parts), MUTED)
        self.files.set_files([path.name for path in files])
        self.discovered = (files, skipped_by_extension)
        self.has_documents = True
        self.run_button.set_enabled(True)
        self._layout()

    def _refresh_path(self) -> None:
        if self.source_dir is None:
            self.folder_name.set("Папка не выбрана", FAINT)
            self.folder_path.set("")
            self.folder_icon.configure(FAINT)
            return
        self.folder_icon.configure(MUTED)
        self.folder_name.set(
            truncate_end(self.source_dir.name or str(self.source_dir),
                         self.fonts["heading"], self.name_limit),
            INK,
        )
        self.folder_path.set(
            truncate_middle(str(self.source_dir), self.fonts["small"], self.path_limit), MUTED
        )

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
        self.run_button.set_icon("stop")
        self.run_button.set_style(CANCEL_STYLE)
        self.run_button.set_enabled(True)
        self.open_button.set_visible(False)
        self.files.reset_progress()
        self._set_footer(True)
        self._layout()
        self.progress.set_color(PRIMARY)
        self.progress.start_scan()
        self._set_stage("Поиск документов", MUTED)
        threading.Thread(target=self._run_worker, args=(self.source_dir,), daemon=True).start()

    def _request_cancel(self) -> None:
        if self.cancel_event.is_set():
            return
        self.cancel_event.set()
        self.run_button.set_enabled(False)
        self._set_stage("Останавливаем обработку", WARNING)

    def _restore_run_button(self) -> None:
        self.run_button.set_text("Обезличить")
        self.run_button.set_icon("shield")
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

    def _apply_row(self, progress: "Progress") -> None:
        if not progress.number:
            return
        self.files.update_file(
            progress.number,
            stage=progress.detail or progress.stage,
            outcome=progress.outcome,
            badge=progress.badge,
            redraw=False,
        )

    def _show_progress(self, progress: "Progress") -> None:
        self.last_progress = progress
        if progress.stage != "Анализ документов" or progress.percent > 0:
            self.progress.set_value(progress.percent)
        done = progress.completed
        self._set_stage(
            f"{progress.stage}  ·  готово {done} из {progress.total}", MUTED, animate=False
        )

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
        from .batch import badge_of, outcome_of

        self.output_dir = result.output_dir
        elapsed = self._elapsed()
        self.processing = False
        self.cancel_event.clear()
        self._restore_run_button()
        self.progress.set_value(100)
        self.progress.set_color(
            DANGER if not result.successful else SUCCESS if not result.needs_review else WARNING
        )
        self.meta.set(f"100%   {elapsed}", MUTED, animate=False)
        self.choose_button.set_enabled(True)
        self.run_button.set_enabled(self.has_documents)
        self.open_button.set_visible(True)
        self.open_button.reveal()

        for item in result.files:
            self.files.update_file(
                item.number,
                outcome=outcome_of(item),
                badge=badge_of(item),
                redraw=False,
            )
        self.files.finish()

        parts = [f"{result.successful} {plural(result.successful, 'файл', 'файла', 'файлов')}"]
        if result.recognized_with_ocr:
            parts.append(f"OCR {result.recognized_with_ocr}")
        if result.needs_review:
            parts.append(f"проверить {len(result.needs_review)}")
        if result.failed:
            parts.append(f"с ошибкой {result.failed}")
        skipped = sum(result.skipped_by_extension.values())
        if skipped:
            parts.append(f"пропущено {skipped}")
        head = "Готово" if result.successful else "Ничего не создано"
        # имя созданной папки прямо в итоге: пользователю не нужно гадать,
        # куда лег результат, даже если он не нажмет «Открыть результат»
        parts.append(result.output_dir.name)
        self._set_stage(
            f"{head}  ·  " + "  ·  ".join(parts),
            SUCCESS if result.successful else DANGER,
        )
        self._layout()

    def _show_error(self, error: Exception) -> None:
        self.processing = False
        self._restore_run_button()
        self.progress.set_value(self.progress.value, immediate=True)
        self.choose_button.set_enabled(True)
        self.run_button.set_enabled(self.has_documents)
        self.meta.set(self._elapsed(), MUTED, animate=False)
        self.files.finish()
        from .batch import BatchCancelled, MedMaskError

        if isinstance(error, BatchCancelled):
            self.progress.set_color(WARNING)
            message = "Отменено  ·  исходные файлы не изменены"
            color = WARNING
        elif isinstance(error, MedMaskError):
            self.progress.set_color(DANGER)
            message = str(error)
            color = DANGER
        else:
            self.progress.set_color(DANGER)
            message = "Не удалось завершить обработку  ·  исходные файлы не изменены"
            color = DANGER
        self._set_stage(message, color)

    def _open_result(self) -> None:
        if self.output_dir is not None and self.output_dir.exists():
            open_folder(self.output_dir)


def main() -> None:
    root = tk.Tk()
    MedMaskApp(root)
    root.mainloop()
