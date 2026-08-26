import QtQuick
import QtQuick.Shapes
import MedMask

/*
  Поверхность окна. Она же фон списка, поэтому держится светлой: холодный
  отлив снизу и едва заметное свечение сверху — ровно столько, чтобы матовые
  панели было видно, и не столько, чтобы мешать читать имена документов.
*/
Item {
    id: backdrop


    // Прозрачное окно: один ровный слой на всю площадь, сквозь него виден
    // рабочий стол. Непрозрачное окно рисует свой холодный градиент.
    Rectangle {
        anchors.fill: parent
        visible: Theme.systemBackdrop
        color: Theme.appFill
    }

    Rectangle {
        anchors.fill: parent
        visible: !Theme.systemBackdrop
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.pageTop }
            GradientStop { position: 1.0; color: Theme.pageBottom }
        }
    }

    Shape {
        anchors.fill: parent
        visible: !Theme.systemBackdrop
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            strokeWidth: -1
            fillGradient: RadialGradient {
                centerX: backdrop.width * 0.86
                centerY: backdrop.height * 0.02
                centerRadius: Math.max(backdrop.width, backdrop.height) * 0.7
                focalX: centerX
                focalY: centerY
                GradientStop { position: 0.0; color: Theme.glowCool }
                GradientStop {
                    position: 1.0
                    color: Qt.rgba(Theme.glowCool.r, Theme.glowCool.g, Theme.glowCool.b, 0)
                }
            }
            PathAngleArc {
                centerX: backdrop.width * 0.86
                centerY: backdrop.height * 0.02
                radiusX: Math.max(backdrop.width, backdrop.height) * 0.7
                radiusY: Math.max(backdrop.width, backdrop.height) * 0.7
                startAngle: 0
                sweepAngle: 360
            }
        }
    }
}
