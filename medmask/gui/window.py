"""Действия над окном, которых нет в QML: родное перетаскивание и рамка.

QML вызывает эти слоты вместо того, чтобы двигать окно вручную. Родные циклы
перетаскивания и изменения размера дают привычное поведение системы —
прилипание к краям в Windows и рывок в Mission Control в macOS.
"""

from __future__ import annotations

import os

from PySide6.QtCore import (
    QAbstractNativeEventFilter,
    QCoreApplication,
    QObject,
    Qt,
    QTimer,
    Slot,
)
from PySide6.QtGui import QGuiApplication, QWindow

from . import macos, windows


class WindowControls(QObject):
    def __init__(self, environment=None, parent=None) -> None:
        super().__init__(parent)
        self._environment = environment
        self._filter: _NativeFilter | None = None
        self._snap: windows.SnapLayoutFilter | None = None
        self._styled = False
        self._glass = True

    @Slot(QObject)
    def configure(self, window: QWindow) -> None:
        """Донастраивает окно после появления на экране.

        Родные приемы применяются только к родной платформе: под offscreen и
        minimal winId указывает не на окно системы, и обращение к нему роняет
        процесс вместо того, чтобы просто ничего не сделать.
        """
        if window is None:
            return
        platform = QGuiApplication.platformName()
        if platform not in ("cocoa", "windows"):
            return
        if os.name == "nt":
            windows.round_corners(window)
            snap = windows.SnapLayoutFilter(window)
            native = _NativeFilter(snap)
            QCoreApplication.instance().installNativeEventFilter(native)
            # Ссылки держат фильтр живым: Qt хранит только указатель.
            self._filter = native
            self._snap = snap
        else:
            self._style_macos(window)

    def _style_macos(self, window: QWindow, attempt: int = 0) -> None:
        """Своя шапка окна macOS, с повтором до готовности окна.

        NSWindow появляется не в тот же миг, что объект Qt. Если попасть в
        промежуток, приемы молча не сработают и окно останется с обычной
        серой полосой — поэтому попытка повторяется, пока система не отдаст
        окно. Повтор безвреден: все вызовы идемпотентны.
        """
        glass = True if self._environment is None else bool(self._environment.glass)
        if macos.style_window(window, glass=glass):
            self._styled = True
            if self._environment is not None:
                self._environment.note_backdrop(glass)
            return
        if attempt < 20:
            QTimer.singleShot(50, lambda: self._style_macos(window, attempt + 1))

    @Slot(QObject)
    def startMove(self, window: QWindow) -> None:
        if window is not None:
            window.startSystemMove()

    @Slot(QObject, int)
    def startResize(self, window: QWindow, edges: int) -> None:
        if window is not None:
            window.startSystemResize(Qt.Edges(edges))

    @Slot(QObject)
    def minimize(self, window: QWindow) -> None:
        if window is not None:
            window.showMinimized()

    @Slot(QObject)
    def toggleMaximize(self, window: QWindow) -> None:
        if window is None:
            return
        if window.visibility() == QWindow.Visibility.Maximized:
            window.showNormal()
        else:
            window.showMaximized()

    @Slot(QObject)
    def toggleFullScreen(self, window: QWindow) -> None:
        if window is None:
            return
        if window.visibility() == QWindow.Visibility.FullScreen:
            window.showNormal()
        else:
            window.showFullScreen()

    @Slot(QObject)
    def close(self, window: QWindow) -> None:
        if window is not None:
            window.close()

    @Slot(float, float, float, float)
    def setMaximizeButtonRect(self, x: float, y: float, width: float, height: float) -> None:
        """Сообщает Windows, где своя кнопка разворачивания: без этого система
        не показывает Snap Layouts."""
        if self._snap is not None:
            self._snap.set_button_rect(x, y, width, height)


class _NativeFilter(QAbstractNativeEventFilter):
    def __init__(self, snap: "windows.SnapLayoutFilter") -> None:
        super().__init__()
        self._snap = snap

    def nativeEventFilter(self, event_type, message):  # pragma: no cover — только Windows
        if event_type != b"windows_generic_MSG":
            return False, 0
        return self._snap.handle(int(message))
