"""Токены оформления: палитра, ритм, типографика, стили кнопок.

Один источник значений для всего окна. Логические пиксели соответствуют
96 dpi; реальные размеры считает MedMaskApp.px() — при системном масштабе
125-200 % коробки растут вместе со шрифтами.
"""

from __future__ import annotations

import sys
import tkinter.font as tkfont

# ---------- цвет ----------

PAGE = "#F7F7F8"        # фон окна
CARD = "#FFFFFF"        # лист
BORDER = "#E4E4E7"      # рамка листа
HAIRLINE = "#F0F0F2"    # разделители внутри листа
ROW_HOVER = "#F7F7F8"   # подсветка строки под курсором
ROW_ACTIVE = "#F4F7FF"  # строка, которая обрабатывается прямо сейчас

INK = "#09090B"         # основной текст
TEXT = "#3F3F46"        # вторичный текст
MUTED = "#71717A"       # подписи и стадии
FAINT = "#A1A1AA"       # выключенное и ожидающее

PRIMARY = "#2563EB"
PRIMARY_HOVER = "#1D4ED8"
PRIMARY_PRESS = "#1E40AF"
TRACK = "#EFEFF1"

SUCCESS = "#059669"
WARNING = "#D97706"
DANGER = "#DC2626"

# ---------- ритм ----------

# Шкала отступов: только эти значения, иначе группы перестают читаться.
SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
SPACE_4 = 16
SPACE_5 = 20
SPACE_6 = 24
SPACE_8 = 32

CARD_RADIUS = 12
BUTTON_RADIUS = 8
ROW_RADIUS = 8

BUTTON_HEIGHT = 34
ROW_HEIGHT = 30
PROGRESS_HEIGHT = 5
ICON_SIZE = 16
HEADER_ICON = 22
FOOTER_HEIGHT = 18

# Полоса заголовка рисуется самим приложением: на macOS контент уходит под
# системную шапку, на Windows системная полоса снимается совсем.
TITLEBAR_HEIGHT = 30
# Слева в шапке macOS стоит светофор — эта зона занята системой.
TRAFFIC_LIGHTS = 78
WINDOW_BUTTON = 26

# Лист не растягивается на всю ширину: длинная строка теряет левый край из
# виду, а список коротких имен превращается в поле пустоты справа.
MAX_CONTENT_WIDTH = 760

WINDOW_WIDTH = 640
WINDOW_HEIGHT = 560
MIN_WIDTH = 520
MIN_HEIGHT = 420

# ---------- шрифт ----------

def build_fonts() -> dict[str, tkfont.Font]:
    """Четыре размера и один моноширинный — больше уровней не нужно."""
    family = tkfont.nametofont("TkDefaultFont").actual("family")
    mono = "Menlo" if sys.platform == "darwin" else "Consolas"
    if mono not in tkfont.families():
        mono = tkfont.nametofont("TkFixedFont").actual("family")
    return {
        "heading": tkfont.Font(family=family, size=15, weight="bold"),
        "body": tkfont.Font(family=family, size=12),
        "small": tkfont.Font(family=family, size=11),
        "button": tkfont.Font(family=family, size=12),
        # Цифры процентов и времени скачут в пропорциональном шрифте,
        # поэтому проценты, минуты и счетчики набраны моноширинным.
        "mono": tkfont.Font(family=mono, size=11),
    }


# ---------- кнопки ----------

PRIMARY_STYLE = {
    "fill": PRIMARY,
    "hover": PRIMARY_HOVER,
    "press": PRIMARY_PRESS,
    "text": "#FFFFFF",
    "disabled_fill": "#EAEAEC",
    "disabled_text": FAINT,
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

# Отмена не красная заливка: посреди работы алый прямоугольник читается как
# авария. Красным становится только текст на наведении.
CANCEL_STYLE = {
    "fill": CARD,
    "hover": "#FEF2F2",
    "press": "#FEE2E2",
    "text": DANGER,
    "outline": "#F3D2D2",
    "disabled_outline": "#EDEDEF",
    "disabled_fill": CARD,
    "disabled_text": FAINT,
}

GHOST_STYLE = {
    "fill": PAGE,
    "hover": "#EFEFF1",
    "press": "#E7E7EA",
    "text": TEXT,
    "disabled_fill": PAGE,
    "disabled_text": FAINT,
}
