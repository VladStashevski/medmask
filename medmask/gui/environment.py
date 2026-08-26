"""Что окно должно знать о системе: рамка, стекло, анимации, контраст.

Тема у программы одна — светлая, за системной она не следует: медицинский
документ читают с белого листа, и окно держится того же.

Стекло — украшение, а не смысл программы. Если система просит высокий
контраст или сцену рисует процессор, окно переходит на непрозрачные панели:
читаемость важнее эффекта.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Property, QObject, Signal

from . import macos, windows

# Светофор macOS занимает левый край строки, содержимое начинается за ним.
TRAFFIC_LIGHTS_INSET = 64.0


def _flag(name: str) -> bool | None:
    value = os.environ.get(name, "").strip().lower()
    if value in ("1", "on", "yes", "true"):
        return True
    if value in ("0", "off", "no", "false"):
        return False
    return None


class Environment(QObject):
    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._high_contrast = macos.increase_contrast() or windows.high_contrast()
        self._reduced_motion = macos.reduce_motion() or windows.reduce_motion()
        self._software_renderer = False
        self._system_backdrop = False

        forced_frame = _flag("MEDMASK_NATIVE_FRAME")
        # На macOS системная рамка остается: она дает светофор, полноэкранный
        # режим и родное перетаскивание, а содержимое все равно уходит под
        # прозрачную полосу. Своя рамка нужна только Windows.
        self._frameless = os.name == "nt" if forced_frame is None else not forced_frame
        self._glass_override = _flag("MEDMASK_GLASS")
        self._motion_override = _flag("MEDMASK_MOTION")

    def note_backdrop(self, installed: bool) -> None:
        """Система подложила под окно свое матовое стекло."""
        if installed == self._system_backdrop:
            return
        self._system_backdrop = installed
        self.changed.emit()

    def note_renderer(self, software: bool) -> None:
        if software == self._software_renderer:
            return
        self._software_renderer = software
        self.changed.emit()

    def _get_glass(self) -> bool:
        if self._glass_override is not None:
            return self._glass_override
        return not (self._high_contrast or self._software_renderer)

    def _get_motion(self) -> bool:
        if self._motion_override is not None:
            return self._motion_override
        return not self._reduced_motion

    def _get_glass_opacity(self) -> float:
        """Плотность белой пелены поверх системного стекла.

        Ниже 0.6 сквозь окно проступают обои и мешают читать имена файлов,
        выше 0.7 пелена съедает само размытие — окно становится просто белым.
        """
        raw = os.environ.get("MEDMASK_GLASS_OPACITY", "").strip()
        try:
            value = float(raw)
        except ValueError:
            return 0.64
        return min(1.0, max(0.2, value))

    def _get_system_backdrop(self) -> bool:
        return self._system_backdrop and self._get_glass()

    def _get_frameless(self) -> bool:
        return self._frameless

    def _get_macos(self) -> bool:
        return sys.platform == "darwin"

    def _get_high_contrast(self) -> bool:
        return self._high_contrast

    def _get_title_inset(self) -> float:
        return TRAFFIC_LIGHTS_INSET if self._get_macos() and not self._frameless else 0.0

    glass = Property(bool, _get_glass, notify=changed)
    systemBackdrop = Property(bool, _get_system_backdrop, notify=changed)
    glassOpacity = Property(float, _get_glass_opacity, constant=True)
    motion = Property(bool, _get_motion, notify=changed)
    frameless = Property(bool, _get_frameless, constant=True)
    macos = Property(bool, _get_macos, constant=True)
    highContrast = Property(bool, _get_high_contrast, notify=changed)
    titleInset = Property(float, _get_title_inset, constant=True)
