"""Тонкая обертка над Win32 для окна Windows.

Окно рисует свою полосу заголовка, поэтому системная снимается. Взамен нужно
вернуть то, что дает системная рамка: скругленные углы Windows 11 и Snap
Layouts — всплывающие макеты при наведении на кнопку разворачивания.
"""

from __future__ import annotations

import ctypes
import os

WM_NCHITTEST = 0x0084
WM_NCLBUTTONDOWN = 0x00A1
WM_NCLBUTTONUP = 0x00A2
WM_NCMOUSELEAVE = 0x02A2
HTCLIENT = 1
HTMAXBUTTON = 9

SPI_GETHIGHCONTRAST = 0x0042
SPI_GETCLIENTAREAANIMATION = 0x1042
HCF_HIGHCONTRASTON = 0x00000001

DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2


def available() -> bool:
    return os.name == "nt"


class _HighContrast(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwFlags", ctypes.c_uint),
        ("lpszDefaultScheme", ctypes.c_wchar_p),
    ]


class _Message(ctypes.Structure):
    _fields_ = [
        ("hWnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint),
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
    ]


def high_contrast() -> bool:
    if not available():
        return False
    try:
        info = _HighContrast()
        info.cbSize = ctypes.sizeof(_HighContrast)
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETHIGHCONTRAST, ctypes.sizeof(info), ctypes.byref(info), 0
        )
        return bool(ok) and bool(info.dwFlags & HCF_HIGHCONTRASTON)
    except Exception:
        return False


def reduce_motion() -> bool:
    """Системный переключатель «показывать анимацию в Windows»."""
    if not available():
        return False
    try:
        enabled = ctypes.c_int(1)
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0
        )
        return bool(ok) and not enabled.value
    except Exception:
        return False


def round_corners(window) -> bool:
    """Возвращает скругление углов, которое система дает окнам с рамкой."""
    if not available():
        return False
    try:
        handle = ctypes.c_void_p(int(window.winId()))
        preference = ctypes.c_int(DWMWCP_ROUND)
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            handle,
            ctypes.c_int(DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(preference),
            ctypes.sizeof(preference),
        )
        return result == 0
    except Exception:
        return False


class SnapLayoutFilter:
    """Возвращает Snap Layouts окну без системной полосы заголовка.

    Windows 11 показывает макеты размещения, когда окно на запрос WM_NCHITTEST
    отвечает HTMAXBUTTON. Прямоугольник своей кнопки разворачивания сообщает
    QML — здесь он только сравнивается с положением курсора.

    Ошибка здесь не должна ломать окно: если что-то не сходится, фильтр
    отвечает «не мое», и обработку продолжает Qt.
    """

    def __init__(self, window) -> None:
        self._window = window
        self._rect = (0.0, 0.0, 0.0, 0.0)
        self._hovered = False

    def set_button_rect(self, x: float, y: float, width: float, height: float) -> None:
        self._rect = (x, y, width, height)

    @property
    def hovered(self) -> bool:
        return self._hovered

    def _inside(self, message) -> bool:
        x, y, width, height = self._rect
        if width <= 0 or height <= 0:
            return False
        ratio = self._window.devicePixelRatio() or 1.0
        global_x = ctypes.c_short(message.lParam & 0xFFFF).value / ratio
        global_y = ctypes.c_short((message.lParam >> 16) & 0xFFFF).value / ratio
        origin = self._window.position()
        local_x = global_x - origin.x()
        local_y = global_y - origin.y()
        return x <= local_x <= x + width and y <= local_y <= y + height

    def handle(self, message_pointer: int):
        """Возвращает (обработано, результат) для nativeEventFilter."""
        try:
            message = ctypes.cast(
                message_pointer, ctypes.POINTER(_Message)
            ).contents
            if int(message.hWnd or 0) != int(self._window.winId()):
                return False, 0
            if message.message == WM_NCHITTEST:
                self._hovered = self._inside(message)
                if self._hovered:
                    return True, HTMAXBUTTON
                return False, 0
            if message.message == WM_NCMOUSELEAVE:
                self._hovered = False
                return False, 0
            if message.message in (WM_NCLBUTTONDOWN, WM_NCLBUTTONUP):
                if message.wParam != HTMAXBUTTON:
                    return False, 0
                if message.message == WM_NCLBUTTONUP:
                    self.toggle_maximize()
                return True, 0
        except Exception:
            return False, 0
        return False, 0

    def toggle_maximize(self) -> None:
        from PySide6.QtGui import QWindow

        if self._window.visibility() == QWindow.Visibility.Maximized:
            self._window.showNormal()
        else:
            self._window.showMaximized()
