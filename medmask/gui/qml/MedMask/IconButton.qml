import QtQuick
import QtQuick.Templates as T
import MedMask

/*
  Кнопка полосы заголовка Windows: прямоугольник в системных пропорциях,
  подсветка под курсором, закрытие краснеет.
*/
T.Button {
    id: control

    property string glyph: "close"
    property bool danger: false

    implicitWidth: Theme.captionButtonWidth
    implicitHeight: Theme.titleBarHeight
    hoverEnabled: true
    focusPolicy: Qt.NoFocus

    background: Rectangle {
        // Прозрачный цвет берется от той же краски, иначе переход идет
        // через серую вспышку.
        color: control.danger
            ? (control.down ? Theme.closePress
             : control.hovered ? Theme.closeHover
             : Qt.rgba(Theme.closeHover.r, Theme.closeHover.g, Theme.closeHover.b, 0))
            : (control.down ? Qt.rgba(Theme.ink.r, Theme.ink.g, Theme.ink.b, 0.14)
             : control.hovered ? Qt.rgba(Theme.ink.r, Theme.ink.g, Theme.ink.b, 0.08)
             : Qt.rgba(Theme.ink.r, Theme.ink.g, Theme.ink.b, 0))
        Behavior on color { ColorAnimation { duration: Theme.fast } }
    }

    contentItem: Item {
        Glyph {
            anchors.centerIn: parent
            name: control.glyph
            size: 15
            weight: 1.5
            color: control.danger && control.hovered ? "#FFFFFF" : Theme.text
            Behavior on color { ColorAnimation { duration: Theme.fast } }
        }
    }
}
