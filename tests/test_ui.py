"""Тесты интерфейса: обрезка строк, переходы и верстка при разном масштабе.

Окно создаётся по-настоящему, поэтому на машине без графической подсистемы
тесты пропускаются.
"""

from __future__ import annotations

import queue
import time
import tkinter as tk

import pytest

from medmask import theme, ui
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

    class StubFileList:
        @staticmethod
        def update(delta: float) -> bool:
            return False

    class StubRoot:
        def after(self, delay, callback) -> None:
            self.delay = delay

    class Event:
        """Прогресс без номера документа: строку списка он не трогает."""

        number = 0

        def __init__(self, label: str) -> None:
            self.label = label

        def __repr__(self) -> str:
            return self.label

    app = MedMaskApp.__new__(MedMaskApp)
    app.events = queue.Queue()
    app.events.put(("progress", Event("первый")))
    app.events.put(("progress", Event("последний")))
    app.animator = StubAnimator()
    app.progress = StubProgressBar()
    app.files = StubFileList()
    app.root = StubRoot()
    app.processing = False
    seen = []
    app._apply_row = lambda progress: None
    app._show_progress = lambda payload: seen.append(("progress", payload))
    app._show_scan = lambda payload: seen.append(("scan", payload))
    app._show_done = lambda payload: seen.append(("done", payload))
    app._show_error = lambda payload: seen.append(("error", payload))

    app._tick()
    assert [(kind, str(payload)) for kind, payload in seen] == [("progress", "последний")]

    seen.clear()
    app.events.put(("progress", Event("устаревший")))
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
def test_layout_keeps_card_and_panel_inside_the_window(root, scaling: float) -> None:
    root.tk.call("tk", "scaling", scaling)
    app = MedMaskApp(root)
    root.update_idletasks()
    app._layout()

    pad = app.px(theme.SPACE_5)
    width = max(app.canvas.winfo_width(), app.px(theme.MIN_WIDTH))
    card_left, card_top, card_right, card_bottom = app.card.box
    assert card_left >= pad
    # лист центрирован и не шире предела: на широком окне он не растягивается
    assert card_left == pytest.approx(width - card_right, abs=1)
    assert card_right - card_left <= app.px(theme.MAX_CONTENT_WIDTH)
    assert card_bottom > card_top

    # панель действий стоит под листом, а ее правый край совпадает с краем листа
    assert app.run_button._origin[1] >= card_bottom
    assert app.run_button._origin[0] + app.run_button.width <= card_right + 1
    assert app.choose_button._origin[0] >= card_left

    # область списка остается положительной при любом масштабе
    _x, _y, list_width, list_height = app.files.area
    assert list_width > 0 and list_height > 0


def test_window_can_be_resized(root) -> None:
    MedMaskApp(root)
    root.update_idletasks()
    assert root.resizable() == (True, True)


def test_version_is_shown(root) -> None:
    from medmask import __version__

    app = MedMaskApp(root)
    assert app.version.text == __version__


# ---------- список документов ----------

def test_progress_stays_hidden_until_work_starts(root) -> None:
    """Пустая полоса в покое читается как несделанная работа, поэтому ее нет."""
    app = MedMaskApp(root)
    root.update_idletasks()
    assert app.progress.visible is False

    app._set_footer(True)
    assert app.progress.visible is True


def test_finished_summary_contains_only_count_and_time(root, tmp_path) -> None:
    from medmask.batch import BatchResult, FileResult

    app = MedMaskApp(root)
    app.files.set_files(["карта.txt"])
    app.has_documents = True
    app.started_at = time.monotonic()

    output = tmp_path / "Обезличенные"
    output.mkdir()
    item = FileResult(
        number=1,
        source_path=tmp_path / "карта.txt",
        output_path=output / "document_0001.pdf",
        low_confidence_pages=[1],
    )
    result = BatchResult(
        source_dir=tmp_path,
        output_dir=output,
        files=[item],
        skipped_by_extension={},
        report_path=output / "_ОТЧЁТ.txt",
    )

    app._show_done(result)

    assert app.stage_text == "1 файл за 00:00"


def test_big_folder_does_not_create_a_row_per_file(root) -> None:
    app = MedMaskApp(root)
    root.update_idletasks()
    app.files.set_files([f"документ_{number}.pdf" for number in range(500)])
    app._layout()

    assert len(app.files.entries) == 500
    # строк на холсте столько, сколько видно, плюс запас на прокрутку
    assert len(app.files.rows) <= int(app.files.area[3] // app.files.row_height) + 3


def test_row_mark_follows_the_outcome(root) -> None:
    app = MedMaskApp(root)
    root.update_idletasks()
    app.files.set_files(["первый.pdf", "второй.pdf", "третий.pdf"])
    app._layout()

    app.files.update_file(1, outcome="done")
    app.files.update_file(2, outcome="review", badge="проверить")
    app.files.update_file(3, stage="страница 1 из 3")

    assert app.files.mark(app.files.entries[0]) == ("check", theme.SUCCESS)
    assert app.files.mark(app.files.entries[1]) == ("alert", theme.WARNING)
    assert app.files.entries[2].active is True
    assert app.files.entries[2].stage == "страница 1 из 3"


def test_scrolling_stops_at_the_edges(root) -> None:
    app = MedMaskApp(root)
    root.update_idletasks()
    app.files.set_files([f"документ_{number}.pdf" for number in range(200)])
    app._layout()

    app.files.scroll_by(-500)
    assert app.files.target_offset == 0

    app.files.scroll_by(10 ** 6)
    limit = app.files.content_height - app.files.area[3]
    assert app.files.target_offset == pytest.approx(limit)


def test_truncate_end_keeps_the_beginning(root) -> None:
    import tkinter.font as tkfont

    font = tkfont.Font(root=root, family="Helvetica", size=12)
    name = "Выписной_эпикриз_кардиология_2026.pdf"
    result = ui.truncate_end(name, font, 90)
    assert result.endswith("…")
    assert name.startswith(result[:-1])
    assert font.measure(result) <= 90


# ---------- шапка окна ----------

def test_titlebar_leaves_room_for_the_card(root) -> None:
    """Лист не должен налезать на полосу заголовка, которую рисуем сами."""
    app = MedMaskApp(root)
    root.update_idletasks()
    app._layout()

    card_top = app.card.box[1]
    if app.seamless:
        assert card_top >= app.px(theme.TITLEBAR_HEIGHT)
    assert app.brand.text == "MedMask"


def test_version_moved_to_the_bottom(root) -> None:
    app = MedMaskApp(root)
    root.update_idletasks()
    app._layout()

    version_y = app.canvas.coords(app.version.item)[1]
    assert version_y > app.card.box[3]


# ---------- сглаженные скругления ----------

def test_corner_image_is_cached_and_sized(root) -> None:
    canvas = tk.Canvas(root, bg="#ffffff")
    first = ui.corner_image(canvas, 8, "#2563eb", "", "#ffffff", 0.0, "nw")
    again = ui.corner_image(canvas, 8, "#2563eb", "", "#ffffff", 0.0, "nw")

    assert first.width() == first.height() == 8
    # тот же угол не пересчитывается заново
    assert first is again


def test_corner_blends_the_shape_with_its_background(root) -> None:
    """Внешний угол картинки — фон, внутренний — заливка, между ними переход."""
    canvas = tk.Canvas(root, bg="#ffffff")
    image = ui.corner_image(canvas, 10, "#000000", "", "#ffffff", 0.0, "nw")

    assert image.get(0, 0)[:3] == (255, 255, 255)
    assert image.get(9, 9)[:3] == (0, 0, 0)

    # вдоль дуги обязаны быть полутона, иначе край снова лесенка
    shades = {image.get(x, y)[:3] for y in range(10) for x in range(10)}
    middle = [tone for tone in shades if tone not in {(255, 255, 255), (0, 0, 0)}]
    assert middle, "край угла не сглажен"
