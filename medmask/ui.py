"""Небольшой набор виджетов поверх Canvas: панели, кнопки, прогресс, переходы.

Tk не умеет скругления, наведение и анимацию, поэтому интерфейс рисуется
на одном холсте: скругленные многоугольники со сглаживанием и переходы
цвета по времени. Внешних зависимостей нет.
"""

from __future__ import annotations

import math
import time
import tkinter as tk
from typing import Callable


# ---------- цвет ----------

def rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def mix(start: str, end: str, position: float) -> str:
    """Линейная интерполяция между двумя цветами."""
    position = min(1.0, max(0.0, position))
    first = rgb(start)
    second = rgb(end)
    channels = tuple(round(first[i] + (second[i] - first[i]) * position) for i in range(3))
    return "#%02x%02x%02x" % channels


# ---------- сглаживание времени ----------

def linear(position: float) -> float:
    return position


def ease_out(position: float) -> float:
    return 1 - (1 - position) ** 3


def ease_in_out(position: float) -> float:
    if position < 0.5:
        return 4 * position ** 3
    return 1 - (-2 * position + 2) ** 3 / 2


class _Tween:
    __slots__ = ("duration", "apply", "ease", "on_done", "delay", "_start")

    def __init__(self, duration, apply, ease, on_done, delay) -> None:
        self.duration = duration
        self.apply = apply
        self.ease = ease
        self.on_done = on_done
        self.delay = delay
        self._start: float | None = None

    def advance(self, now: float) -> bool:
        if self._start is None:
            self._start = now + self.delay
        if now < self._start:
            return False
        position = 1.0 if self.duration <= 0 else min(1.0, (now - self._start) / self.duration)
        self.apply(self.ease(position))
        if position >= 1.0:
            if self.on_done is not None:
                self.on_done()
            return True
        return False


class Animator:
    """Переходы, идущие по реальному времени, а не по числу кадров.

    Часы можно подменить: тестам нужно проматывать время, не засыпая.
    """

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._tweens: dict[str, _Tween] = {}
        self.clock = clock or time.monotonic
        self._last = self.clock()

    def run(
        self,
        key: str,
        duration: float,
        apply: Callable[[float], None],
        ease: Callable[[float], float] = ease_out,
        on_done: Callable[[], None] | None = None,
        delay: float = 0.0,
    ) -> None:
        self._tweens[key] = _Tween(duration, apply, ease, on_done, delay)

    def cancel(self, key: str) -> None:
        self._tweens.pop(key, None)

    @property
    def busy(self) -> bool:
        return bool(self._tweens)

    def tick(self) -> float:
        now = self.clock()
        delta = now - self._last
        self._last = now
        for key, tween in list(self._tweens.items()):
            # переход мог быть снят или заменен уже внутри этого же тика
            if self._tweens.get(key) is not tween:
                continue
            if tween.advance(now) and self._tweens.get(key) is tween:
                del self._tweens[key]
        return delta


# ---------- фигуры ----------

def resolve_color(widget: tk.Misc, color: str) -> str:
    """Приводит цвет к #rrggbb: холст может вернуть системное имя вроде
    systemWindowBackgroundColor, а смешивать нужно числа."""
    if color.startswith("#") and len(color) == 7:
        return color
    try:
        red, green, blue = widget.winfo_rgb(color)
    except tk.TclError:
        return "#ffffff"
    return "#%02x%02x%02x" % (red >> 8, green >> 8, blue >> 8)


def _quantize(color: str, step: int = 4) -> str:
    """Огрубляет цвет для ключа кэша: переход из 14 кадров дает 3-4 картинки."""
    if not color:
        return ""
    return "#%02x%02x%02x" % tuple(min(255, (value // step) * step) for value in rgb(color))


def _corner_cache(canvas: tk.Canvas) -> dict:
    cache = getattr(canvas, "_medmask_corners", None)
    if cache is None:
        cache = {}
        canvas._medmask_corners = cache  # type: ignore[attr-defined]
    return cache


def corner_image(
    canvas: tk.Canvas,
    radius: int,
    fill: str,
    outline: str,
    background: str,
    border: float,
    quadrant: str,
) -> tk.PhotoImage:
    """Сглаженный уголок как картинка.

    Холст Tk рисует фигуры без сглаживания: скругление, собранное полигоном,
    выглядит лесенкой. Поэтому углы считаются попиксельно — доля пикселя внутри
    окружности смешивает цвет фигуры с цветом подложки. Прозрачности здесь не
    нужно: подложка под углом всегда одноцветная.
    """
    key = (
        radius,
        _quantize(fill),
        _quantize(outline),
        _quantize(background),
        round(border, 1),
        quadrant,
    )
    cache = _corner_cache(canvas)
    ready = cache.get(key)
    if ready is not None:
        return ready

    image = tk.PhotoImage(master=canvas, width=radius, height=radius)
    rows = []
    for y in range(radius):
        row = []
        for x in range(radius):
            offset_x = x + 0.5 if quadrant in ("ne", "se") else radius - x - 0.5
            offset_y = y + 0.5 if quadrant in ("sw", "se") else radius - y - 0.5
            distance = math.hypot(offset_x, offset_y)
            outer = min(1.0, max(0.0, radius - distance + 0.5))
            if outline:
                color = mix(background, outline, outer)
                inner = min(1.0, max(0.0, radius - border - distance + 0.5))
                color = mix(color, fill, inner)
            else:
                color = mix(background, fill, outer)
            row.append(color)
        rows.append("{" + " ".join(row) + "}")
    image.put(" ".join(rows))

    cache[key] = image
    while len(cache) > 512:
        cache.pop(next(iter(cache)))
    return image


class RoundedBox:
    """Прямоугольник со скругленными углами и сглаженным краем.

    Собирается из трех прямоугольников, четырех угловых картинок и — если
    задана рамка — четырех линий по сторонам.
    """

    def __init__(
        self,
        canvas: tk.Canvas,
        radius: float,
        fill: str,
        outline: str | None = None,
        tags=(),
        background: str | None = None,
        border: float = 1.0,
    ) -> None:
        self.canvas = canvas
        self.radius = radius
        self.fill = fill
        self.outline = outline or ""
        self.border = border if outline else 0.0
        self.background = resolve_color(canvas, background or str(canvas.cget("bg")))
        self.box = (0.0, 0.0, 0.0, 0.0)
        self.visible = True
        self.parts = [
            canvas.create_rectangle(0, 0, 0, 0, fill=fill, outline="", tags=tags)
            for _ in range(3)
        ]
        self.corners = {
            quadrant: canvas.create_image(0, 0, anchor="nw", tags=tags)
            for quadrant in ("nw", "ne", "sw", "se")
        }
        self.edges = [
            canvas.create_line(0, 0, 0, 0, fill=self.outline or fill,
                               width=self.border or 1, state="hidden", tags=tags)
            for _ in range(4)
        ]
        self._images: dict[str, tk.PhotoImage] = {}

    # положение

    def place(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.box = (x0, y0, x1, y1)
        self._redraw()

    def _radius(self) -> int:
        x0, y0, x1, y1 = self.box
        return max(0, int(round(min(self.radius, (x1 - x0) / 2, (y1 - y0) / 2))))

    def _redraw(self) -> None:
        if not self.visible:
            return
        x0, y0, x1, y1 = self.box
        if x1 - x0 <= 0 or y1 - y0 <= 0:
            self._show(False)
            return
        self._show(True)
        radius = self._radius()

        middle, top, bottom = self.parts
        self.canvas.coords(middle, x0, y0 + radius, x1, y1 - radius)
        self.canvas.coords(top, x0 + radius, y0, x1 - radius, y0 + radius)
        self.canvas.coords(bottom, x0 + radius, y1 - radius, x1 - radius, y1)

        corners = {
            "nw": (x0, y0),
            "ne": (x1 - radius, y0),
            "sw": (x0, y1 - radius),
            "se": (x1 - radius, y1 - radius),
        }
        for quadrant, (x, y) in corners.items():
            item = self.corners[quadrant]
            if radius <= 0:
                self.canvas.itemconfigure(item, state="hidden")
                continue
            image = corner_image(
                self.canvas, radius, self.fill, self.outline,
                self.background, self.border, quadrant,
            )
            # ссылка держит картинку живой, пока она стоит на холсте
            self._images[quadrant] = image
            self.canvas.itemconfigure(item, image=image, state="normal")
            self.canvas.coords(item, x, y)

        if self.outline:
            half = self.border / 2
            lines = [
                (x0 + radius, y0 + half, x1 - radius, y0 + half),
                (x0 + radius, y1 - half, x1 - radius, y1 - half),
                (x0 + half, y0 + radius, x0 + half, y1 - radius),
                (x1 - half, y0 + radius, x1 - half, y1 - radius),
            ]
            for item, points in zip(self.edges, lines):
                self.canvas.coords(item, *points)
                self.canvas.itemconfigure(item, state="normal", fill=self.outline)
        else:
            for item in self.edges:
                self.canvas.itemconfigure(item, state="hidden")

    def _show(self, visible: bool) -> None:
        state = "normal" if visible else "hidden"
        for item in self.parts:
            self.canvas.itemconfigure(item, state=state)
        for item in self.corners.values():
            self.canvas.itemconfigure(item, state=state)
        for item in self.edges:
            self.canvas.itemconfigure(
                item, state=state if (visible and self.outline) else "hidden"
            )

    # цвет

    def configure(self, fill: str | None = None, outline: str | None = None,
                  background: str | None = None) -> None:
        changed = False
        if fill is not None and fill != self.fill:
            self.fill = fill
            for item in self.parts:
                self.canvas.itemconfigure(item, fill=fill)
            changed = True
        if outline is not None and outline != self.outline:
            self.outline = outline
            self.border = self.border or 1.0
            changed = True
        if background is not None:
            resolved = resolve_color(self.canvas, background)
            if resolved != self.background:
                self.background = resolved
                changed = True
        if changed:
            self._redraw()

    def fill_color(self) -> str:
        return self.fill

    def outline_color(self) -> str:
        return self.outline

    def set_visible(self, visible: bool) -> None:
        self.visible = visible
        self._show(visible)
        if visible:
            self._redraw()


# ---------- иконки ----------

# Контуры в сетке 24x24, как в наборах со штриховыми иконками: линия рисуется
# скругленными стыками, поэтому мелкий размер не превращается в кашу.
ICON_PATHS: dict[str, list[tuple[str, list[float]]]] = {
    "folder": [("line", [3, 19.5, 3, 5, 9.5, 5, 11.5, 7.5, 21, 7.5, 21, 19.5, 3, 19.5])],
    "shield": [
        ("line", [12, 2.8, 20, 5.8, 20, 12, 12, 21.2, 4, 12, 4, 5.8, 12, 2.8]),
        ("line", [8.8, 11.8, 11, 14, 15.4, 9]),
    ],
    "check": [("line", [5, 12.6, 9.8, 17.4, 19, 7])],
    "alert": [
        ("line", [12, 3.4, 21.2, 19.6, 2.8, 19.6, 12, 3.4]),
        ("line", [12, 9, 12, 13.6]),
        ("dot", [12, 16.8]),
    ],
    "cross": [("line", [6.5, 6.5, 17.5, 17.5]), ("line", [17.5, 6.5, 6.5, 17.5])],
    "stop": [("box", [7.5, 7.5, 16.5, 16.5])],
    "arrow-out": [("line", [6.5, 17.5, 17, 7]), ("line", [9.5, 7, 17, 7, 17, 14.5])],
    "circle": [("ring", [7.5, 7.5, 16.5, 16.5])],
    "minus": [("line", [6.5, 12, 17.5, 12])],
    "file": [
        ("line", [6, 21, 6, 3, 14, 3, 18, 7, 18, 21, 6, 21]),
        ("line", [13.6, 3.4, 13.6, 7.4, 17.6, 7.4]),
    ],
}


class Icon:
    """Штриховая иконка на холсте. Цвет меняется целиком, размер задан один раз."""

    def __init__(
        self,
        canvas: tk.Canvas,
        name: str,
        size: float,
        color: str,
        tags=(),
        width: float | None = None,
    ) -> None:
        self.canvas = canvas
        self.size = size
        self.color = color
        self.tags = tags
        self.width = width if width is not None else max(1.0, size / 11.5)
        self.name = ""
        self.center = (0.0, 0.0)
        self.items: list[int] = []
        self.visible = True
        self.set_name(name)

    def set_name(self, name: str) -> None:
        if name == self.name:
            return
        for item in self.items:
            self.canvas.delete(item)
        self.items = []
        self.name = name
        for kind, _coords in ICON_PATHS.get(name, []):
            if kind == "line":
                item = self.canvas.create_line(
                    0, 0, 0, 0,
                    fill=self.color,
                    width=self.width,
                    capstyle="round",
                    joinstyle="round",
                    tags=self.tags,
                )
            elif kind == "ring":
                item = self.canvas.create_oval(
                    0, 0, 0, 0, outline=self.color, width=self.width, tags=self.tags
                )
            elif kind == "dot":
                item = self.canvas.create_oval(
                    0, 0, 0, 0, outline="", fill=self.color, tags=self.tags
                )
            else:  # box — единственная залитая фигура набора
                item = self.canvas.create_rectangle(
                    0, 0, 0, 0, outline="", fill=self.color, tags=self.tags
                )
            self.items.append(item)
        if not self.visible:
            self.set_visible(False)
        self._redraw()

    def place(self, x: float, y: float) -> None:
        """Ставит иконку по центру (x, y)."""
        self.center = (x, y)
        self._redraw()

    def _redraw(self) -> None:
        cx, cy = self.center
        scale = self.size / 24.0
        left = cx - self.size / 2
        top = cy - self.size / 2
        for item, (kind, coords) in zip(self.items, ICON_PATHS.get(self.name, [])):
            if kind == "dot":
                radius = max(0.8, self.width * 0.85)
                x, y = left + coords[0] * scale, top + coords[1] * scale
                self.canvas.coords(item, x - radius, y - radius, x + radius, y + radius)
                continue
            points = [
                (left + value * scale) if index % 2 == 0 else (top + value * scale)
                for index, value in enumerate(coords)
            ]
            self.canvas.coords(item, *points)

    def configure(self, color: str) -> None:
        if color == self.color:
            return
        self.color = color
        for item, (kind, _coords) in zip(self.items, ICON_PATHS.get(self.name, [])):
            if kind in {"dot", "box"}:
                self.canvas.itemconfigure(item, fill=color)
            elif kind == "ring":
                self.canvas.itemconfigure(item, outline=color)
            else:
                self.canvas.itemconfigure(item, fill=color)

    def set_visible(self, visible: bool) -> None:
        self.visible = visible
        state = "normal" if visible else "hidden"
        for item in self.items:
            self.canvas.itemconfigure(item, state=state)


class Spinner:
    """Дуга, которая крутится, пока документ обрабатывается."""

    def __init__(self, canvas: tk.Canvas, size: float, color: str, width: float | None = None) -> None:
        self.canvas = canvas
        self.size = size
        self.angle = 0.0
        self.center = (0.0, 0.0)
        self.visible = False
        self.item = canvas.create_arc(
            0, 0, 0, 0,
            start=0,
            extent=100,
            style="arc",
            outline=color,
            width=width if width is not None else max(1.2, size / 8),
            state="hidden",
        )

    def place(self, x: float, y: float) -> None:
        self.center = (x, y)
        radius = self.size / 2
        self.canvas.coords(self.item, x - radius, y - radius, x + radius, y + radius)

    def configure(self, color: str) -> None:
        self.canvas.itemconfigure(self.item, outline=color)

    def set_visible(self, visible: bool) -> None:
        if visible == self.visible:
            return
        self.visible = visible
        self.canvas.itemconfigure(self.item, state="normal" if visible else "hidden")

    def update(self, delta: float) -> None:
        if not self.visible:
            return
        # против часовой в терминах Tk — визуально это привычное вращение по часовой
        self.angle = (self.angle - delta * 300) % 360
        self.canvas.itemconfigure(self.item, start=self.angle)


# ---------- текст ----------

class TextItem:
    """Подпись на холсте, которая меняется через затухание, а не рывком."""

    def __init__(
        self,
        canvas: tk.Canvas,
        animator: Animator,
        *,
        font,
        color: str,
        background: str,
        anchor: str = "w",
        width: int = 0,
    ) -> None:
        self.canvas = canvas
        self.animator = animator
        self.font = font
        self.color = color
        self.background = background
        self.text = ""
        self.item = canvas.create_text(
            0, 0, text="", font=font, fill=background, anchor=anchor, width=width
        )
        self._key = f"text-{id(self)}"
        self._pending: tuple[str, str, float] | None = None
        self._fading = False

    def place(self, x: float, y: float) -> None:
        self.canvas.coords(self.item, x, y)

    def configure_width(self, width: int) -> None:
        self.canvas.itemconfigure(self.item, width=width)

    def measure(self) -> int:
        return self.font.measure(self.text)

    def set(self, text: str, color: str | None = None, animate: bool = True, delay: float = 0.0) -> None:
        color = color or self.color
        if text == self.text and color == self.color and self._pending is None:
            return
        if not animate:
            self._pending = None
            self._fading = False
            self.animator.cancel(self._key)
            self.text = text
            self.color = color
            self.canvas.itemconfigure(self.item, text=text, fill=color)
            return

        self._pending = (text, color, delay)
        if self._fading:
            return
        if not self.text:
            self._commit()
            return

        start = str(self.canvas.itemcget(self.item, "fill"))
        self._fading = True
        self.animator.run(
            self._key,
            0.11,
            lambda position: self.canvas.itemconfigure(self.item, fill=mix(start, self.background, position)),
            ease=linear,
            on_done=self._commit,
        )

    def _commit(self) -> None:
        pending = self._pending
        self._pending = None
        self._fading = False
        if pending is None:
            return
        text, color, delay = pending
        self.text = text
        self.color = color
        self.canvas.itemconfigure(self.item, text=text)
        self._fade_in(delay)

    def _fade_in(self, delay: float = 0.0) -> None:
        if not self.text:
            self.canvas.itemconfigure(self.item, fill=self.background)
            return
        target = self.color
        self.animator.run(
            self._key,
            0.18,
            lambda position: self.canvas.itemconfigure(self.item, fill=mix(self.background, target, position)),
            delay=delay,
        )


def truncate_middle(text: str, font, limit: int) -> str:
    """Обрезает длинный путь по середине, сохраняя начало и конец."""
    if limit <= 0 or font.measure(text) <= limit:
        return text
    best = "…"
    low, high = 0, len(text)
    while low <= high:
        keep = (low + high) // 2
        head = text[: (keep + 1) // 2]
        tail = text[-(keep // 2):] if keep // 2 else ""
        candidate = f"{head}…{tail}"
        if font.measure(candidate) <= limit:
            best = candidate
            low = keep + 1
        else:
            high = keep - 1
    return best


class SegmentRow:
    """Строка из нескольких подписей разного цвета, разделенных точкой."""

    def __init__(self, canvas: tk.Canvas, animator: Animator, *, font, background: str, separator_color: str) -> None:
        self.canvas = canvas
        self.animator = animator
        self.font = font
        self.background = background
        self.separator_color = separator_color
        self.items: list[TextItem] = []
        self.segments: list[tuple[str, str]] = []
        self.origin = (0.0, 0.0)

    def _item(self, index: int) -> TextItem:
        while len(self.items) <= index:
            self.items.append(
                TextItem(
                    self.canvas,
                    self.animator,
                    font=self.font,
                    color=self.separator_color,
                    background=self.background,
                )
            )
        return self.items[index]

    def place(self, x: float, y: float) -> None:
        self.origin = (x, y)
        self._layout()

    def set(self, segments: list[tuple[str, str]]) -> None:
        self.segments = segments
        for index, (text, color) in enumerate(segments):
            self._item(index).set(text, color, delay=0.04 * index)
        for extra in range(len(segments), len(self.items)):
            self.items[extra].set("", animate=False)
        self._layout()

    def _layout(self) -> None:
        x, y = self.origin
        gap = self.font.measure("  ·  ")
        for index, (text, _) in enumerate(self.segments):
            item = self._item(index)
            item.place(x, y)
            x += self.font.measure(text) + gap
        for extra in range(len(self.segments), len(self.items)):
            self.items[extra].place(x, y)


def truncate_end(text: str, font, limit: int) -> str:
    """Обрезает хвост строки: у имени документа важнее начало."""
    if limit <= 0 or font.measure(text) <= limit:
        return text
    low, high = 0, len(text)
    best = "…"
    while low <= high:
        keep = (low + high) // 2
        candidate = f"{text[:keep]}…"
        if font.measure(candidate) <= limit:
            best = candidate
            low = keep + 1
        else:
            high = keep - 1
    return best


# ---------- список документов ----------

class FileEntry:
    """Строка списка в терминах данных, а не холста."""

    __slots__ = ("name", "outcome", "badge", "stage", "active")

    def __init__(self, name: str) -> None:
        self.name = name
        self.outcome = ""   # "", done, review, failed
        self.badge = ""
        self.stage = ""
        self.active = False


class _Row:
    """Переиспользуемая строка. Их ровно столько, сколько влезает в окно."""

    def __init__(self, parent: "FileList") -> None:
        canvas = parent.canvas
        style = parent.style
        self.parent = parent
        self.canvas = canvas
        self.background = RoundedBox(canvas, parent.radius, style["card"])
        self.icon = Icon(canvas, "circle", parent.icon_size, style["faint"])
        self.spinner = Spinner(canvas, parent.icon_size, style["primary"])
        self.name = canvas.create_text(
            0, 0, text="", font=parent.fonts["body"], fill=style["text"], anchor="w"
        )
        self.note = canvas.create_text(
            0, 0, text="", font=parent.fonts["small"], fill=style["muted"], anchor="e"
        )
        self.visible = True
        self.set_visible(False)

    def set_visible(self, visible: bool) -> None:
        if visible == self.visible:
            return
        self.visible = visible
        state = "normal" if visible else "hidden"
        self.background.set_visible(visible)
        self.icon.set_visible(visible and not self.spinner.visible)
        if not visible:
            self.spinner.set_visible(False)
        self.canvas.itemconfigure(self.name, state=state)
        self.canvas.itemconfigure(self.note, state=state)

    def draw(self, entry: FileEntry, x: float, y: float, width: float) -> None:
        parent = self.parent
        style = parent.style
        height = parent.row_height
        self.set_visible(True)

        if entry.active:
            self.background.configure(fill=style["row_active"])
            self.background.place(x, y, x + width, y + height)
            self.background.set_visible(True)
        else:
            self.background.set_visible(False)

        middle = y + height / 2
        icon_x = x + parent.pad + parent.icon_size / 2
        running = entry.active and not entry.outcome
        self.spinner.set_visible(running)
        self.spinner.place(icon_x, middle)
        self.icon.set_visible(not running)
        if not running:
            name, color = parent.mark(entry)
            self.icon.set_name(name)
            self.icon.configure(color)
            self.icon.place(icon_x, middle)

        note = entry.badge or entry.stage
        note_color = style["warning"] if entry.outcome == "review" and entry.badge else style["muted"]
        if entry.outcome == "failed":
            note_color = style["danger"]
        self.canvas.itemconfigure(self.note, text=note, fill=note_color)
        note_width = parent.fonts["small"].measure(note) if note else 0
        right = x + width - parent.pad
        self.canvas.coords(self.note, right, middle)

        left = icon_x + parent.icon_size / 2 + parent.gap
        limit = int(right - left - (parent.gap * 2 if note else 0) - note_width)
        # До запуска список читается как содержимое папки, поэтому строки
        # обычного цвета. Гаснут они только в работе — тогда бледность значит
        # «очередь еще не дошла».
        waiting = style["faint"] if parent.dim_waiting else style["text"]
        color = style["ink"] if entry.outcome or entry.active else waiting
        self.canvas.itemconfigure(
            self.name,
            text=truncate_end(entry.name, parent.fonts["body"], limit),
            fill=color,
        )
        self.canvas.coords(self.name, left, middle)


class FileList:
    """Документы папки строками: статус слева, имя, пометка справа.

    Строки не создаются на каждый файл: холст держит ровно столько объектов,
    сколько видно, — папка на тысячу документов открывается так же быстро,
    как папка на десять.
    """

    def __init__(
        self,
        canvas: tk.Canvas,
        animator: Animator,
        *,
        fonts: dict,
        style: dict[str, str],
        row_height: float,
        radius: float,
        icon_size: float,
        pad: float,
        gap: float,
    ) -> None:
        self.canvas = canvas
        self.animator = animator
        self.fonts = fonts
        self.style = style
        self.row_height = row_height
        self.radius = radius
        self.icon_size = icon_size
        self.pad = pad
        self.gap = gap
        self.entries: list[FileEntry] = []
        self.rows: list[_Row] = []
        self.dim_waiting = False
        self.offset = 0.0
        self.target_offset = 0.0
        self.area = (0.0, 0.0, 0.0, 0.0)
        self.touched_at = -1e9
        self.clock = animator.clock
        self.scrollbar = RoundedBox(canvas, 2, "#D4D4D8")
        self.scrollbar.set_visible(False)

    # данные

    def set_files(self, names: list[str]) -> None:
        self.dim_waiting = False
        self.entries = [FileEntry(name) for name in names]
        self.offset = self.target_offset = 0.0
        self.touched_at = -1e9
        self._redraw()

    def reset_progress(self) -> None:
        self.dim_waiting = True
        for entry in self.entries:
            entry.outcome = ""
            entry.badge = ""
            entry.stage = ""
            entry.active = False
        self._redraw()

    def refresh(self) -> None:
        self._redraw()

    def update_file(
        self,
        number: int,
        *,
        stage: str = "",
        outcome: str = "",
        badge: str = "",
        redraw: bool = True,
    ) -> None:
        if not 1 <= number <= len(self.entries):
            return
        entry = self.entries[number - 1]
        if outcome:
            entry.outcome = outcome
            entry.badge = badge
            entry.stage = ""
            entry.active = False
        else:
            entry.active = True
            entry.stage = stage
        self._follow(number)
        if redraw:
            self._redraw()

    def finish(self) -> None:
        for entry in self.entries:
            entry.active = False
        self._redraw()

    # геометрия

    def place(self, x: float, y: float, width: float, height: float) -> None:
        self.area = (x, y, width, height)
        self._clamp()
        self._redraw()

    @property
    def content_height(self) -> float:
        return len(self.entries) * self.row_height

    def _limit(self) -> float:
        _x, _y, _width, height = self.area
        return max(0.0, self.content_height - height)

    def _clamp(self) -> None:
        limit = self._limit()
        self.target_offset = min(limit, max(0.0, self.target_offset))
        self.offset = min(limit, max(0.0, self.offset))
        # у нижнего края остаток меньше строки — там прокрутка останавливается
        # ровно на нем, иначе последняя строка не была бы видна целиком

    def _follow(self, number: int) -> None:
        """Держит работающую строку в поле зрения, пока список не тронули рукой."""
        if self.clock() - self.touched_at < 3.0:
            return
        _x, _y, _width, height = self.area
        top = (number - 1) * self.row_height
        bottom = top + self.row_height
        if top < self.target_offset:
            self.target_offset = top
        elif bottom > self.target_offset + height:
            self.target_offset = bottom - height
        self._clamp()

    def scroll_by(self, amount: float) -> None:
        self.touched_at = self.clock()
        # Шаг кратен строке: колесо не оставляет список на полстроки.
        steps = round(amount / self.row_height)
        if steps == 0:
            steps = 1 if amount > 0 else -1
        self.target_offset += steps * self.row_height
        self._clamp()

    # кадр

    def update(self, delta: float) -> bool:
        moving = False
        if abs(self.target_offset - self.offset) > 0.4:
            self.offset += (self.target_offset - self.offset) * min(1.0, delta * 12)
            moving = True
        elif self.offset != self.target_offset:
            self.offset = self.target_offset
            moving = True
        spinning = False
        for row in self.rows:
            if row.spinner.visible:
                row.spinner.update(delta)
                spinning = True
        if moving:
            self._redraw()
        return moving or spinning

    def mark(self, entry: FileEntry) -> tuple[str, str]:
        style = self.style
        if entry.outcome == "done":
            return "check", style["success"]
        if entry.outcome == "review":
            return "alert", style["warning"]
        if entry.outcome == "failed":
            return "cross", style["danger"]
        return "circle", style["faint"]

    def _row(self, index: int) -> _Row:
        while len(self.rows) <= index:
            self.rows.append(_Row(self))
        return self.rows[index]

    def _redraw(self) -> None:
        x, y, width, height = self.area
        if width <= 0 or height <= 0:
            return
        first = max(0, int(self.offset // self.row_height))
        visible = int(height // self.row_height) + 2
        used = 0
        for index in range(first, min(len(self.entries), first + visible)):
            row = self._row(used)
            row.draw(
                self.entries[index],
                x,
                y + index * self.row_height - self.offset,
                width,
            )
            used += 1
        for extra in range(used, len(self.rows)):
            self.rows[extra].set_visible(False)
        self._draw_scrollbar()

    def _draw_scrollbar(self) -> None:
        x, y, width, height = self.area
        limit = self._limit()
        if limit <= 0:
            self.scrollbar.set_visible(False)
            return
        visible_part = height / self.content_height
        bar_height = max(height * visible_part, self.row_height)
        travel = height - bar_height
        top = y + travel * (self.offset / limit)
        self.scrollbar.set_visible(True)
        self.scrollbar.place(x + width - 3, top, x + width, top + bar_height)


# ---------- кнопка ----------

class Button:
    """Кнопка на холсте: наведение, нажатие и появление идут через переходы."""

    def __init__(
        self,
        canvas: tk.Canvas,
        animator: Animator,
        *,
        text: str,
        command: Callable[[], None],
        font,
        style: dict[str, str],
        background: str,
        radius: float = 10,
        padding: int = 18,
        height: int = 36,
        icon: str | None = None,
        icon_size: float = 15,
        gap: float = 7,
    ) -> None:
        self.canvas = canvas
        self.animator = animator
        self.command = command
        self.style = style
        self.background = background
        self.font = font
        self.padding = padding
        self.text = text
        self.enabled = True
        self.visible = True
        self._hovered = False
        self._pressed = False
        self._origin = (0.0, 0.0)
        self.height = height
        self.icon_size = icon_size
        self.gap = gap
        self.tag = f"button-{id(self)}"
        self.box = RoundedBox(canvas, radius, style["fill"], style.get("outline"), tags=self.tag)
        self.icon = (
            Icon(canvas, icon, icon_size, style["text"], tags=self.tag)
            if icon
            else None
        )
        self.width = self._measure(text)
        self.label = canvas.create_text(
            0, 0,
            text=text,
            font=font,
            fill=style["text"],
            anchor="w" if self.icon else "center",
            tags=self.tag,
        )
        canvas.tag_bind(self.tag, "<Enter>", self._on_enter)
        canvas.tag_bind(self.tag, "<Leave>", self._on_leave)
        canvas.tag_bind(self.tag, "<ButtonPress-1>", self._on_press)
        canvas.tag_bind(self.tag, "<ButtonRelease-1>", self._on_release)

    # положение

    def place(self, x: float, y: float) -> None:
        self._origin = (x, y)
        self._redraw()

    def _measure(self, text: str) -> float:
        content = self.font.measure(text)
        if self.icon is not None:
            content += self.icon_size + self.gap
        return content + self.padding * 2

    def set_icon(self, name: str) -> None:
        if self.icon is None:
            return
        self.icon.set_name(name)

    def set_text(self, text: str) -> None:
        if text == self.text:
            return
        self.text = text
        self.width = self._measure(text)
        self.canvas.itemconfigure(self.label, text=text)
        self._redraw()

    def set_style(self, style: dict[str, str]) -> None:
        if style is self.style:
            return
        self.style = style
        self._animate_colors()

    def _redraw(self) -> None:
        x, y = self._origin
        self.box.place(x, y, x + self.width, y + self.height)
        # нажатие опускает содержимое на пиксель — короткая физическая подсказка
        shift = 1 if self._pressed else 0
        middle = y + self.height / 2 + shift
        if self.icon is None:
            self.canvas.coords(self.label, x + self.width / 2, middle)
            return
        content = self.icon_size + self.gap + self.font.measure(self.text)
        left = x + (self.width - content) / 2
        self.icon.place(left + self.icon_size / 2, middle)
        self.canvas.coords(self.label, left + self.icon_size + self.gap, middle)

    # состояние

    def set_visible(self, visible: bool) -> None:
        if visible == self.visible:
            return
        self.visible = visible
        state = "normal" if visible else "hidden"
        self.box.set_visible(visible)
        self.canvas.itemconfigure(self.label, state=state)
        if self.icon is not None:
            self.icon.set_visible(visible)

    def reveal(self) -> None:
        """Показывает кнопку проявлением из фона."""
        self.set_visible(True)
        fill = self._target_fill()
        text = self._target_text()
        outline = self._target_outline()
        self.animator.run(
            f"{self.tag}-reveal",
            0.28,
            lambda position: (
                self.box.configure(
                    fill=mix(self.background, fill, position),
                    outline=mix(self.background, outline, position),
                ),
                self.canvas.itemconfigure(self.label, fill=mix(self.background, text, position)),
                self.icon.configure(mix(self.background, text, position)) if self.icon else None,
            ),
        )

    def set_enabled(self, enabled: bool) -> None:
        if enabled == self.enabled:
            return
        self.enabled = enabled
        if not enabled:
            self._hovered = False
            self._pressed = False
            self._redraw()
        self._animate_colors()
        self.canvas.configure(cursor="")

    # события

    def _on_enter(self, _event) -> None:
        self._hovered = True
        if self.enabled and self.visible:
            self.canvas.configure(cursor="hand2")
            self._animate_colors()

    def _on_leave(self, _event) -> None:
        self._hovered = False
        self._pressed = False
        self.canvas.configure(cursor="")
        self._redraw()
        self._animate_colors()

    def _on_press(self, _event) -> None:
        if not (self.enabled and self.visible):
            return
        self._pressed = True
        self._redraw()
        self._animate_colors(duration=0.05)

    def _on_release(self, _event) -> None:
        if not (self.enabled and self.visible and self._pressed):
            return
        self._pressed = False
        self._redraw()
        self._animate_colors()
        self.command()

    # цвета

    def _target_fill(self) -> str:
        if not self.enabled:
            return self.style["disabled_fill"]
        if self._pressed:
            return self.style["press"]
        if self._hovered:
            return self.style["hover"]
        return self.style["fill"]

    def _target_text(self) -> str:
        return self.style["text"] if self.enabled else self.style["disabled_text"]

    def _target_outline(self) -> str:
        """Стиль без рамки — это рамка цвета заливки: так она незаметно тает,
        когда кнопка меняет вид, и не остается от прошлого стиля."""
        outline = self.style.get("outline")
        if outline is None:
            return self._target_fill()
        return outline if self.enabled else self.style.get("disabled_outline", outline)

    def _animate_colors(self, duration: float = 0.14) -> None:
        start_fill = self.box.fill_color()
        start_text = str(self.canvas.itemcget(self.label, "fill"))
        start_outline = self.box.outline_color() or start_fill
        fill = self._target_fill()
        text = self._target_text()
        outline = self._target_outline()
        key = f"{self.tag}-colors"
        self.animator.cancel(key)
        if start_fill == fill and start_text == text and start_outline == outline:
            return

        def apply(position: float) -> None:
            self.box.configure(fill=mix(start_fill, fill, position))
            self.canvas.itemconfigure(self.label, fill=mix(start_text, text, position))
            if self.icon is not None:
                self.icon.configure(mix(start_text, text, position))
            self.box.configure(outline=mix(start_outline, outline, position))

        self.animator.run(key, duration, apply)


# ---------- прогресс ----------

class ProgressBar:
    """Полоса прогресса: значение догоняется плавно, поиск идет бегунком."""

    def __init__(self, canvas: tk.Canvas, animator: Animator, *, track: str, fill: str, height: int = 8) -> None:
        self.canvas = canvas
        self.animator = animator
        self.height = height
        self.track = RoundedBox(canvas, height / 2, track)
        self.bar = RoundedBox(canvas, height / 2, fill)
        self.value = 0.0
        self.target = 0.0
        self.scanning = False
        self.visible = True
        self.phase = 0.0
        self._geometry = (0.0, 0.0, 0.0)

    def place(self, x: float, y: float, width: float) -> None:
        self._geometry = (x, y, width)
        self.track.place(x, y, x + width, y + self.height)
        self._redraw()

    def set_value(self, value: float, immediate: bool = False) -> None:
        self.scanning = False
        self.target = min(100.0, max(0.0, value))
        if immediate:
            self.value = self.target
        self._redraw()

    def start_scan(self) -> None:
        self.scanning = True
        self.phase = 0.0
        self.value = 0.0
        self.target = 0.0

    def set_visible(self, visible: bool) -> None:
        """В покое рельса нет: пустая полоса читается как несделанная работа."""
        self.visible = visible
        self.track.set_visible(visible)
        if not visible:
            self.bar.set_visible(False)
        else:
            self._redraw()

    def set_color(self, color: str) -> None:
        start = self.bar.fill_color()
        key = f"progress-{id(self)}"
        self.animator.cancel(key)
        if start == color:
            return
        self.animator.run(
            key,
            0.32,
            lambda position: self.bar.configure(fill=mix(start, color, position)),
        )

    def update(self, delta: float) -> bool:
        if not self.visible:
            return False
        if self.scanning:
            self.phase = (self.phase + delta / 1.7) % 1.0
            self._redraw()
            return True
        if abs(self.target - self.value) > 0.05:
            self.value += (self.target - self.value) * min(1.0, delta * 7)
            self._redraw()
            return True
        if self.value != self.target:
            self.value = self.target
            self._redraw()
        return False

    def _redraw(self) -> None:
        x, y, width = self._geometry
        if width <= 0 or not self.visible:
            return
        if self.scanning:
            segment = max(self.height * 4, width * 0.28)
            offset = (1 - math.cos(self.phase * math.tau)) / 2
            left = x + (width - segment) * offset
            self.bar.set_visible(True)
            self.bar.place(left, y, left + segment, y + self.height)
            return
        filled = width * self.value / 100
        if filled < 1:
            self.bar.set_visible(False)
            return
        self.bar.set_visible(True)
        self.bar.place(x, y, x + max(filled, self.height), y + self.height)
