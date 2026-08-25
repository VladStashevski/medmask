"""Тесты интерфейса: обрезка строк, переходы и верстка при разном масштабе.

Окно создаётся по-настоящему, поэтому на машине без графической подсистемы
тесты пропускаются.
"""

from __future__ import annotations

import queue
import tkinter as tk

import pytest

from medmask import ui
from medmask.app import MedMaskApp


@pytest.fixture()
def root():
    try:
        window = tk.Tk()
    except tk.TclError as error:  # pragma: no cover — среда без дисплея
        pytest.skip(f"нет графической подсистемы: {error}")
    window.withdraw()
    yield window
    window.destroy()


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# ---------- обрезка длинных путей ----------

def test_truncate_middle_fits_the_limit(root) -> None:
    import tkinter.font as tkfont

    font = tkfont.Font(root=root, family="Helvetica", size=12)
    path = "/Users/example/" + "очень-длинная-папка/" * 12 + "Карты"
    for limit in (400, 200, 90, 30):
        result = ui.truncate_middle(path, font, limit)
        assert font.measure(result) <= limit or result == "…"
        assert result.startswith("/") or result == "…"


def test_truncate_middle_keeps_short_text(root) -> None:
    import tkinter.font as tkfont

    font = tkfont.Font(root=root, family="Helvetica", size=12)
    assert ui.truncate_middle("/tmp/Карты", font, 1000) == "/tmp/Карты"


# ---------- аниматор ----------

def test_cancelled_tween_never_applies_again() -> None:
    """Отмена изнутри тика не должна оставлять переходу право доиграть.

    Из-за этого путь к папке замирал серым: снятый переход успевал закрасить
    подпись уже после того, как ей выставили нужный цвет.
    """
    clock = FakeClock()
    animator = ui.Animator(clock=clock)
    seen: list[float] = []
    animator.run("canceller", 1.0, lambda _position: animator.cancel("victim"), ease=ui.linear)
    animator.run("victim", 1.0, seen.append, ease=ui.linear)

    for _ in range(3):
        clock.advance(0.5)
        animator.tick()
    assert seen == []


def test_replaced_tween_does_not_finish_the_old_target() -> None:
    clock = FakeClock()
    animator = ui.Animator(clock=clock)
    done: list[str] = []
    animator.run("k", 0.1, lambda _p: None, on_done=lambda: done.append("old"))
    animator.run("k", 0.1, lambda _p: None, on_done=lambda: done.append("new"))
    for _ in range(3):
        clock.advance(0.1)
        animator.tick()
    assert done == ["new"]


def test_tick_coalesces_worker_progress_and_preserves_terminal_event() -> None:
    class StubAnimator:
        busy = False

        @staticmethod
        def tick() -> float:
            return 0.01

    class StubProgressBar:
        @staticmethod
        def update(delta: float) -> bool:
            return False

    class StubRoot:
        def after(self, delay, callback) -> None:
            self.delay = delay

    app = MedMaskApp.__new__(MedMaskApp)
    app.events = queue.Queue()
    app.events.put(("progress", "первый"))
    app.events.put(("progress", "последний"))
    app.animator = StubAnimator()
    app.progress = StubProgressBar()
    app.root = StubRoot()
    app.processing = False
    seen = []
    app._show_progress = lambda payload: seen.append(("progress", payload))
    app._show_scan = lambda payload: seen.append(("scan", payload))
    app._show_done = lambda payload: seen.append(("done", payload))
    app._show_error = lambda payload: seen.append(("error", payload))

    app._tick()
    assert seen == [("progress", "последний")]

    seen.clear()
    app.events.put(("progress", "устаревший"))
    app.events.put(("done", "результат"))
    app._tick()
    assert seen == [("done", "результат")]


# ---------- подписи ----------

def test_text_item_settles_on_the_last_value_after_rapid_updates(root) -> None:
    import tkinter.font as tkfont

    clock = FakeClock()
    animator = ui.Animator(clock=clock)
    canvas = tk.Canvas(root)
    font = tkfont.Font(root=root, family="Helvetica", size=12)
    item = ui.TextItem(canvas, animator, font=font, color="#000000", background="#ffffff")
    item.set("первый", animate=False)

    for index in range(20):
        item.set(f"этап {index}")
        clock.advance(0.01)
        animator.tick()

    for _ in range(20):
        clock.advance(0.05)
        animator.tick()

    assert item.text == "этап 19"
    assert canvas.itemcget(item.item, "text") == "этап 19"
    assert canvas.itemcget(item.item, "fill").lower() == "#000000"


# ---------- кнопки ----------

def test_disabled_button_settles_on_disabled_colors(root) -> None:
    import tkinter.font as tkfont

    clock = FakeClock()
    animator = ui.Animator(clock=clock)
    canvas = tk.Canvas(root)
    font = tkfont.Font(root=root, family="Helvetica", size=12)
    style = {
        "fill": "#2563eb", "hover": "#1d4ed8", "press": "#1e40af", "text": "#ffffff",
        "disabled_fill": "#eaeaec", "disabled_text": "#a1a1aa",
    }
    button = ui.Button(
        canvas, animator, text="Обезличить", command=lambda: None,
        font=font, style=style, background="#ffffff",
    )
    button.set_enabled(False)
    button.set_enabled(True)
    for _ in range(20):
        clock.advance(0.05)
        animator.tick()
    assert button.box.fill_color().lower() == "#2563eb"


def test_button_can_change_label_and_style(root) -> None:
    import tkinter.font as tkfont

    clock = FakeClock()
    animator = ui.Animator(clock=clock)
    canvas = tk.Canvas(root)
    font = tkfont.Font(root=root, family="Helvetica", size=12)
    primary = {
        "fill": "#2563eb", "hover": "#1d4ed8", "press": "#1e40af", "text": "#ffffff",
        "disabled_fill": "#eaeaec", "disabled_text": "#a1a1aa",
    }
    danger = {
        "fill": "#dc2626", "hover": "#b91c1c", "press": "#991b1b", "text": "#ffffff",
        "disabled_fill": "#f1dada", "disabled_text": "#a86a6a",
    }
    button = ui.Button(
        canvas, animator, text="Обезличить", command=lambda: None,
        font=font, style=primary, background="#ffffff",
    )
    original_width = button.width

    button.set_text("Отменить")
    button.set_style(danger)
    for _ in range(20):
        clock.advance(0.05)
        animator.tick()

    assert canvas.itemcget(button.label, "text") == "Отменить"
    assert button.width != original_width
    assert button.box.fill_color().lower() == "#dc2626"


# ---------- верстка ----------

@pytest.mark.parametrize("scaling", [1.0, 1.5, 2.0])
def test_layout_fits_the_card_at_any_display_scale(root, scaling: float) -> None:
    root.tk.call("tk", "scaling", scaling)
    app = MedMaskApp(root)
    root.update_idletasks()
    app._layout()

    pad = app.px(32)
    card_left, card_top, card_right, card_bottom = app.card.box
    buttons = (app.choose_button, app.run_button, app.open_button)
    row_right = buttons[-1]._origin[0] + buttons[-1].width

    assert card_left == pad
    assert row_right <= card_right - app.px(8)
    assert app.progress._geometry[0] + app.progress._geometry[2] <= card_right
    assert card_bottom > card_top


def test_window_height_matches_the_content(root) -> None:
    app = MedMaskApp(root)
    root.update_idletasks()
    height = app._layout()
    assert height == int(app.card.box[3] + app.px(32))
    assert root.resizable() == (True, False)


def test_version_is_shown(root) -> None:
    from medmask import __version__

    app = MedMaskApp(root)
    assert app.version.text == __version__
