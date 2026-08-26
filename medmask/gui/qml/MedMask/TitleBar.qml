import QtQuick
import MedMask

/*
  Верхняя полоса панели инструментов: слева системные кнопки, справа значок
  программы. Своего фона у нее нет — она часть той же поверхности.

  В macOS кнопки рисует система, там остается светофор. В Windows системная
  полоса снята, и окно показывает свои кнопки справа от значка.
*/
Item {
    id: bar

    property bool frameless: false
    property bool maximized: false

    signal moveRequested()
    signal toggleMaximizeRequested()
    signal minimizeRequested()
    signal closeRequested()

    // Прямоугольник своей кнопки разворачивания в координатах окна:
    // по нему Windows решает, показывать ли Snap Layouts.
    readonly property rect maximizeRect: frameless
        ? Qt.rect(bar.x + buttons.x + maximizeButton.x, bar.y + buttons.y + maximizeButton.y,
                  maximizeButton.width, maximizeButton.height)
        : Qt.rect(0, 0, 0, 0)

    implicitHeight: Theme.titleBarHeight

    MouseArea {
        id: dragArea
        anchors.fill: parent
        anchors.rightMargin: bar.frameless ? buttons.width : 0
        acceptedButtons: Qt.LeftButton
        property bool armed: false

        // Родной цикл перетаскивания запускается только при настоящем
        // движении: иначе система забирает мышь и съедает двойной щелчок.
        onPressed: armed = true
        onReleased: armed = false
        onPositionChanged: {
            if (armed) {
                armed = false;
                bar.moveRequested();
            }
        }
        onDoubleClicked: bar.toggleMaximizeRequested()
    }

    Image {
        id: mark
        anchors.verticalCenter: parent.verticalCenter
        anchors.right: buttons.visible ? buttons.left : parent.right
        anchors.rightMargin: Theme.contentMargin
        // В шапке — рисунок без белой подложки: фон у полосы уже есть, и
        // плитка на нем читалась бы наклейкой поверх стекла.
        source: Qt.resolvedUrl("../../../assets/app_glyph.png")
        sourceSize.width: 36
        sourceSize.height: 36
        width: 18
        height: 18
        smooth: true
        mipmap: true
        opacity: 0.9
    }

    Row {
        id: buttons
        anchors.right: parent.right
        anchors.top: parent.top
        visible: bar.frameless

        IconButton {
            glyph: "minus"
            onClicked: bar.minimizeRequested()
        }

        IconButton {
            id: maximizeButton
            glyph: bar.maximized ? "restore" : "square"
            onClicked: bar.toggleMaximizeRequested()
        }

        IconButton {
            glyph: "close"
            danger: true
            onClicked: bar.closeRequested()
        }
    }
}
