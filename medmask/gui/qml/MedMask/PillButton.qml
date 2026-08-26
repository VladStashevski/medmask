import QtQuick
import QtQuick.Templates as T
import MedMask

/*
  Капсульная кнопка: радиус равен половине высоты. Три роли — основная
  синяя, обычная и спокойная кнопка отмены.

  Отмена не красная заливка: посреди работы алый прямоугольник читается как
  авария. Красным становится только текст и рамка на наведении.
*/
T.Button {
    id: control

    property string variant: "secondary"   // primary | secondary | quiet
    property string glyph: ""
    property color accent: variant === "quiet" ? Theme.danger : Theme.primary

    implicitHeight: Theme.buttonHeight
    implicitWidth: row.implicitWidth + Theme.space5 * 2
    padding: 0
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus

    readonly property bool primaryStyle: variant === "primary"

    readonly property color fillColor: {
        if (!enabled)
            return primaryStyle ? Qt.rgba(0.06, 0.09, 0.16, 0.06)
                                : "transparent";
        if (primaryStyle)
            return down ? Theme.primaryPress : hovered ? Theme.primaryHover : Theme.primary;
        if (variant === "quiet")
            return down ? Qt.rgba(control.accent.r, control.accent.g, control.accent.b, 0.16)
                 : hovered ? Qt.rgba(control.accent.r, control.accent.g, control.accent.b, 0.09)
                 : Theme.controlFill;
        return down ? Theme.controlPress : hovered ? Theme.controlHover : Theme.controlFill;
    }

    readonly property color strokeColor: {
        if (primaryStyle)
            return "transparent";
        if (!enabled)
            return Qt.rgba(Theme.controlBorder.r, Theme.controlBorder.g, Theme.controlBorder.b, 0.4);
        if (variant === "quiet")
            return Qt.rgba(control.accent.r, control.accent.g, control.accent.b, hovered ? 0.45 : 0.28);
        return Theme.controlBorder;
    }

    readonly property color labelColor: {
        if (!enabled)
            return Theme.faint;
        if (primaryStyle)
            return Theme.inkOnPrimary;
        if (variant === "quiet")
            return control.accent;
        return Theme.ink;
    }

    background: Item {
        // Кольцо фокуса снаружи капсулы: клавиатурный обход должен быть виден
        // и на синей кнопке, и на светлой.
        Rectangle {
            anchors.fill: parent
            anchors.margins: -3
            radius: height / 2
            color: "transparent"
            antialiasing: true
            border.width: 2
            border.color: Theme.focusRing
            opacity: control.visualFocus ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.fast } }
        }

        Rectangle {
            anchors.fill: parent
            radius: height / 2
            antialiasing: true
            color: control.fillColor
            border.width: control.primaryStyle ? 0 : Theme.hairline
            border.color: control.strokeColor
            scale: control.down && control.enabled ? 0.985 : 1

            Behavior on color { ColorAnimation { duration: Theme.fast } }
            Behavior on border.color { ColorAnimation { duration: Theme.fast } }
            Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Theme.easing } }
        }
    }

    contentItem: Item {
        implicitWidth: row.implicitWidth
        implicitHeight: row.implicitHeight

        Row {
            id: row
            anchors.centerIn: parent
            spacing: Theme.space2
            opacity: control.enabled ? 1 : 0.85

            Glyph {
                visible: control.glyph !== ""
                anchors.verticalCenter: parent.verticalCenter
                name: control.glyph
                size: 15
                weight: 1.9
                filled: control.glyph === "stop"
                color: control.labelColor
                Behavior on color { ColorAnimation { duration: Theme.fast } }
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: control.text
                color: control.labelColor
                font.family: Theme.uiFamily
                font.pixelSize: Theme.fontBody
                font.weight: control.primaryStyle ? Font.DemiBold : Font.Medium
                Behavior on color { ColorAnimation { duration: Theme.fast } }
            }
        }
    }
}
