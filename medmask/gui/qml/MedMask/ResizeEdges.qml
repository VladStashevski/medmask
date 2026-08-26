import QtQuick

/*
  Невидимые полосы по краям окна без системной рамки. Тянут они не сами:
  нажатие передается родному циклу изменения размера, поэтому прилипание к
  краям и раскладки Windows работают как у обычного окна.
*/
Item {
    id: edges

    property int thickness: 6
    signal resizeRequested(int edge)

    anchors.fill: parent

    Repeater {
        model: [
            { edge: Qt.LeftEdge, cursor: Qt.SizeHorCursor },
            { edge: Qt.RightEdge, cursor: Qt.SizeHorCursor },
            { edge: Qt.TopEdge, cursor: Qt.SizeVerCursor },
            { edge: Qt.BottomEdge, cursor: Qt.SizeVerCursor },
            { edge: Qt.LeftEdge | Qt.TopEdge, cursor: Qt.SizeFDiagCursor },
            { edge: Qt.RightEdge | Qt.BottomEdge, cursor: Qt.SizeFDiagCursor },
            { edge: Qt.RightEdge | Qt.TopEdge, cursor: Qt.SizeBDiagCursor },
            { edge: Qt.LeftEdge | Qt.BottomEdge, cursor: Qt.SizeBDiagCursor }
        ]

        MouseArea {
            required property var modelData
            // left, right, top и bottom у Item заняты линиями привязки.
            readonly property bool atLeft: (modelData.edge & Qt.LeftEdge) !== 0
            readonly property bool atRight: (modelData.edge & Qt.RightEdge) !== 0
            readonly property bool atTop: (modelData.edge & Qt.TopEdge) !== 0
            readonly property bool atBottom: (modelData.edge & Qt.BottomEdge) !== 0
            readonly property bool corner: (atLeft || atRight) && (atTop || atBottom)

            x: atLeft ? 0 : atRight ? edges.width - width : edges.thickness
            y: atTop ? 0 : atBottom ? edges.height - height : edges.thickness
            width: corner ? edges.thickness * 2
                 : (atLeft || atRight) ? edges.thickness
                 : edges.width - edges.thickness * 2
            height: corner ? edges.thickness * 2
                  : (atTop || atBottom) ? edges.thickness
                  : edges.height - edges.thickness * 2

            cursorShape: modelData.cursor
            acceptedButtons: Qt.LeftButton
            onPressed: edges.resizeRequested(modelData.edge)
        }
    }
}
