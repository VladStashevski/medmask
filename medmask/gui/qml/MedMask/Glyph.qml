import QtQuick
import QtQuick.Shapes
import MedMask

/*
  Штриховые значки одной толщины. Рисуются как контуры на сетке 24×24 и
  масштабируются: на Retina и при 200 % они остаются четкими, а перекрасить
  их можно в любой цвет темы.
*/
Item {
    id: glyph

    property string name: "folder"
    property color color: Theme.muted
    property real size: 16
    property real weight: 1.8
    property bool filled: false

    implicitWidth: size
    implicitHeight: size
    width: size
    height: size

    readonly property var paths: ({
        "folder": "M3.5 7.6a2 2 0 0 1 2-2h3.6l1.9 2.4h7.5a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5.5a2 2 0 0 1-2-2z",
        "search": "M11 4.2a6.8 6.8 0 1 0 0 13.6 6.8 6.8 0 0 0 0-13.6M20.2 20.2l-4.4-4.4",
        "document": "M7 3.6h6.6l4.4 4.4v12.4H7zM13.6 3.6V8H18",
        "alert": "M12 4.6 20.8 19.4H3.2zM12 10v4.6M12 17.1v.2",
        "shield": "M12 3.4 19 6.1v5.3c0 4.3-2.9 7.7-7 9.2-4.1-1.5-7-4.9-7-9.2V6.1z",
        "stop": "M9 8.6h6a0.9 0.9 0 0 1 0.9 0.9v5a0.9 0.9 0 0 1-0.9 0.9H9a0.9 0.9 0 0 1-0.9-0.9v-5A0.9 0.9 0 0 1 9 8.6z",
        "open": "M14 4h6v6M20 4l-7.6 7.6M19 13.6V19a1.4 1.4 0 0 1-1.4 1.4H6.4A1.4 1.4 0 0 1 5 19V7.8a1.4 1.4 0 0 1 1.4-1.4h5.4",
        "check": "M5.4 12.6 10 17.2 18.6 7.4",
        "cross": "M7 7l10 10M17 7 7 17",
        "bang": "M12 6.4v7.2M12 16.9v.2",
        "minus": "M5 12h14",
        "square": "M6.4 6.4h11.2v11.2H6.4z",
        "restore": "M8.6 8.6h9v9h-9zM6 15.4V6h9.4",
        "close": "M6.8 6.8l10.4 10.4M17.2 6.8 6.8 17.2"
    })

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        transform: Scale { xScale: glyph.size / 24; yScale: glyph.size / 24 }

        ShapePath {
            strokeColor: glyph.color
            fillColor: glyph.filled ? glyph.color : "transparent"
            strokeWidth: glyph.filled ? 0 : glyph.weight
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathSvg {
                path: glyph.paths[glyph.name] !== undefined
                    ? glyph.paths[glyph.name]
                    : glyph.paths["document"]
            }
        }
    }
}
