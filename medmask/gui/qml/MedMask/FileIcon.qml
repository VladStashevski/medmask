import QtQuick
import QtQuick.Shapes
import MedMask

/*
  Значок документа: лист с отворотом угла и пометки внутри по виду файла.
  Цвет несет смысл — скан, таблица и текст различаются с одного взгляда,
  поэтому подписи «PDF» на 26 пикселях не нужны.
*/
Item {
    id: icon

    property string kind: "text"
    readonly property color tint: Theme.kindColor(kind)

    implicitWidth: Theme.fileIconWidth
    implicitHeight: Theme.fileIconHeight

    Item {
        id: art
        width: 22
        height: 28
        anchors.centerIn: parent

        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer

            ShapePath {
                fillColor: Qt.rgba(icon.tint.r, icon.tint.g, icon.tint.b, Theme.tintMedium)
                strokeColor: Qt.rgba(icon.tint.r, icon.tint.g, icon.tint.b, 0.55)
                strokeWidth: 1.1
                joinStyle: ShapePath.RoundJoin
                PathSvg {
                    path: "M1.6 3a2 2 0 0 1 2-2h8.6L20.4 8.6V25a2 2 0 0 1-2 2H3.6a2 2 0 0 1-2-2z"
                }
            }

            ShapePath {
                fillColor: Qt.rgba(icon.tint.r, icon.tint.g, icon.tint.b, 0.42)
                strokeColor: "transparent"
                PathSvg { path: "M12.2 1 20.4 8.6h-6.2a2 2 0 0 1-2-2z" }
            }
        }

        // Текст и PDF: строки. Таблица: клетки. Скан: картинка.
        Item {
            anchors.fill: parent
            visible: icon.kind !== "sheet" && icon.kind !== "image"
            Repeater {
                model: [12.5, 9.5, 6.5]
                Rectangle {
                    x: 5
                    y: 13.5 + index * 4
                    width: modelData
                    height: 1.7
                    radius: 0.85
                    antialiasing: true
                    color: Qt.rgba(icon.tint.r, icon.tint.g, icon.tint.b, 0.6)
                }
            }
        }

        Item {
            anchors.fill: parent
            visible: icon.kind === "sheet"
            Repeater {
                model: 6
                Rectangle {
                    x: 5 + (index % 3) * 4.4
                    y: 14 + Math.floor(index / 3) * 4.6
                    width: 3.4
                    height: 3.2
                    radius: 0.8
                    antialiasing: true
                    color: Qt.rgba(icon.tint.r, icon.tint.g, icon.tint.b,
                                   index === 0 || index === 4 ? 0.75 : 0.4)
                }
            }
        }

        Shape {
            anchors.fill: parent
            visible: icon.kind === "image"
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                fillColor: Qt.rgba(icon.tint.r, icon.tint.g, icon.tint.b, 0.62)
                strokeColor: "transparent"
                PathSvg { path: "M5 21.4l3.6-4.6 2.6 3 2.2-2.6 3.6 4.2z" }
            }
            ShapePath {
                fillColor: Qt.rgba(icon.tint.r, icon.tint.g, icon.tint.b, 0.62)
                strokeColor: "transparent"
                PathSvg { path: "M8.6 12.4a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3z" }
            }
        }
    }
}
