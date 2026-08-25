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

class RoundedBox:
    """Прямоугольник со скругленными углами; сглаживание берет сам Tk."""

    def __init__(self, canvas: tk.Canvas, radius: float, fill: str, outline: str | None = None, tags=()) -> None:
        self.canvas = canvas
        self.radius = radius
        self.item = canvas.create_polygon(
            0, 0, 0, 0, 0, 0,
            smooth=True,
            splinesteps=28,
            fill=fill,
            outline=outline or "",
            width=1 if outline else 0,
            tags=tags,
        )
        self.box = (0.0, 0.0, 0.0, 0.0)

    def place(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.box = (x0, y0, x1, y1)
        self.canvas.coords(self.item, *self._points())

    def _points(self) -> list[float]:
        x0, y0, x1, y1 = self.box
        radius = min(self.radius, (x1 - x0) / 2, (y1 - y0) / 2)
        return [
            x0 + radius, y0, x1 - radius, y0, x1, y0, x1, y0 + radius,
            x1, y1 - radius, x1, y1, x1 - radius, y1, x0 + radius, y1,
            x0, y1, x0, y1 - radius, x0, y0 + radius, x0, y0,
        ]

    def configure(self, fill: str | None = None, outline: str | None = None) -> None:
        options: dict[str, str] = {}
        if fill is not None:
            options["fill"] = fill
        if outline is not None:
            options["outline"] = outline
        if options:
            self.canvas.itemconfigure(self.item, **options)

    def fill_color(self) -> str:
        return str(self.canvas.itemcget(self.item, "fill"))

    def set_visible(self, visible: bool) -> None:
        self.canvas.itemconfigure(self.item, state="normal" if visible else "hidden")


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
    ) -> None:
        self.canvas = canvas
        self.animator = animator
        self.command = command
        self.style = style
        self.background = background
        self.enabled = True
        self.visible = True
        self._hovered = False
        self._pressed = False
        self._origin = (0.0, 0.0)
        self.height = height
        self.width = font.measure(text) + padding * 2
        self.tag = f"button-{id(self)}"
        self.box = RoundedBox(canvas, radius, style["fill"], style.get("outline"), tags=self.tag)
        self.label = canvas.create_text(
            0, 0, text=text, font=font, fill=style["text"], anchor="center", tags=self.tag
        )
        canvas.tag_bind(self.tag, "<Enter>", self._on_enter)
        canvas.tag_bind(self.tag, "<Leave>", self._on_leave)
        canvas.tag_bind(self.tag, "<ButtonPress-1>", self._on_press)
        canvas.tag_bind(self.tag, "<ButtonRelease-1>", self._on_release)

    # положение

    def place(self, x: float, y: float) -> None:
        self._origin = (x, y)
        self._redraw()

    def _redraw(self) -> None:
        x, y = self._origin
        self.box.place(x, y, x + self.width, y + self.height)
        shift = 1 if self._pressed else 0
        self.canvas.coords(self.label, x + self.width / 2, y + self.height / 2 + shift)

    # состояние

    def set_visible(self, visible: bool) -> None:
        if visible == self.visible:
            return
        self.visible = visible
        state = "normal" if visible else "hidden"
        self.box.set_visible(visible)
        self.canvas.itemconfigure(self.label, state=state)

    def reveal(self) -> None:
        """Показывает кнопку проявлением из фона."""
        self.set_visible(True)
        fill = self._target_fill()
        text = self._target_text()
        outline = self.style.get("outline")
        self.animator.run(
            f"{self.tag}-reveal",
            0.28,
            lambda position: (
                self.box.configure(
                    fill=mix(self.background, fill, position),
                    outline=mix(self.background, outline, position) if outline else None,
                ),
                self.canvas.itemconfigure(self.label, fill=mix(self.background, text, position)),
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

    def _target_outline(self) -> str | None:
        outline = self.style.get("outline")
        if outline is None:
            return None
        return outline if self.enabled else self.style.get("disabled_outline", outline)

    def _animate_colors(self, duration: float = 0.14) -> None:
        start_fill = self.box.fill_color()
        start_text = str(self.canvas.itemcget(self.label, "fill"))
        start_outline = str(self.canvas.itemcget(self.box.item, "outline"))
        fill = self._target_fill()
        text = self._target_text()
        outline = self._target_outline()
        key = f"{self.tag}-colors"
        self.animator.cancel(key)
        if start_fill == fill and start_text == text and (outline is None or start_outline == outline):
            return

        def apply(position: float) -> None:
            self.box.configure(fill=mix(start_fill, fill, position))
            self.canvas.itemconfigure(self.label, fill=mix(start_text, text, position))
            if outline is not None:
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
        if width <= 0:
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
