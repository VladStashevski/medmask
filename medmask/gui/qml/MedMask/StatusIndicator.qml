import QtQuick
import QtQuick.Shapes
import MedMask

/*
  Состояние документа одним значком: ожидает, в работе, обезличено, требует
  проверки, ошибка. Смена состояния занимает один короткий переход, чтобы
  список не мерцал при быстрой обработке.
*/
Item {
    id: indicator

    property string status: ""
    property real size: Theme.statusIconSize

    implicitWidth: size
    implicitHeight: size
    width: size
    height: size

    readonly property color tint: Theme.statusColor(status)
    readonly property bool filled: status === "done" || status === "review" || status === "failed"

    // Ожидает: небольшая точка, которая не спорит с готовыми строками.
    Rectangle {
        anchors.centerIn: parent
        width: indicator.size * 0.5
        height: width
        radius: width / 2
        color: Theme.faint
        opacity: indicator.status === "" ? 1 : 0
        scale: indicator.status === "" ? 1 : 0.6
        antialiasing: true
        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
        Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Theme.easing } }
    }

    // В работе: незамкнутая дуга. Вращение — единственная бесконечная
    // анимация в окне и означает ровно то, что показывает.
    Item {
        id: spinner
        anchors.fill: parent
        opacity: indicator.status === "active" ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: Theme.fast } }

        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: Theme.primary
                fillColor: "transparent"
                strokeWidth: Math.max(1.5, indicator.size * 0.13)
                capStyle: ShapePath.RoundCap
                PathAngleArc {
                    centerX: indicator.size / 2
                    centerY: indicator.size / 2
                    radiusX: indicator.size / 2 - Math.max(1.5, indicator.size * 0.13) / 2 - 0.5
                    radiusY: radiusX
                    startAngle: -90
                    sweepAngle: 285
                }
            }
        }

        RotationAnimator on rotation {
            from: 0
            to: 360
            duration: 950
            loops: Animation.Infinite
            running: Theme.motion && spinner.visible
        }
    }

    // Итог: залитый кружок и белый знак внутри.
    Rectangle {
        id: badge
        anchors.fill: parent
        radius: width / 2
        antialiasing: true
        color: indicator.tint
        opacity: indicator.filled ? 1 : 0
        scale: indicator.filled ? 1 : 0.65
        Behavior on opacity { NumberAnimation { duration: Theme.base } }
        Behavior on scale { NumberAnimation { duration: Theme.base; easing.type: Theme.easing } }
        Behavior on color { ColorAnimation { duration: Theme.base } }

        Glyph {
            anchors.centerIn: parent
            size: indicator.size * 0.82
            weight: 2.4
            color: "#FFFFFF"
            name: indicator.status === "done" ? "check"
                : indicator.status === "failed" ? "cross" : "bang"
        }
    }
}
