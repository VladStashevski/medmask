import QtQuick
import QtQuick.Effects
import MedMask

/*
  Матовое стекло: размытый слепок того, что лежит под панелью, полупрозрачная
  холодная заливка, светлая внутренняя рамка и деликатная тень.

  blurSource — слой, который видно сквозь панель. Панель обязана быть его
  соседом, а не потомком: слепок берется по собственным x и y, и вложенность
  дала бы и смещение, и рекурсию.

  Когда стекло выключено (высокий контраст, программный рендерер, настройка
  пользователя), размытие не создается вовсе, а заливка становится плотной.
*/
Item {
    id: panel

    property Item blurSource: null
    property real radius: Theme.panelRadius
    property real topRadius: radius
    property real bottomRadius: radius
    property color fillColor: Theme.panelFill
    property color edgeColor: Theme.panelEdge
    property color borderColor: Theme.panelBorder
    property bool elevated: true
    property real blurAmount: 1.0

    default property alias content: holder.data

    readonly property bool frosted: Theme.glass && blurSource !== null

    Item {
        id: body
        anchors.fill: parent
        // Тень снимается общим слоем поверх панели, а размытое стекло такого
        // слоя не переживает: Qt отдает его сплошным пятном. У матовой панели
        // тени нет — ее отделяет само размытие; на непрозрачной тень остается.
        layer.enabled: panel.elevated && !panel.frosted
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowBlur: 0.7
            blurMax: 24
            shadowVerticalOffset: 3
            shadowColor: Theme.shadow
        }

        ShaderEffectSource {
            id: slice
            anchors.fill: parent
            visible: false
            live: panel.frosted
            hideSource: false
            sourceItem: panel.frosted ? panel.blurSource : null
            sourceRect: Qt.rect(panel.x, panel.y, panel.width, panel.height)
        }

        Item {
            id: maskShape
            anchors.fill: parent
            visible: false
            Rectangle {
                anchors.fill: parent
                color: "white"
                antialiasing: true
                topLeftRadius: panel.topRadius
                topRightRadius: panel.topRadius
                bottomLeftRadius: panel.bottomRadius
                bottomRightRadius: panel.bottomRadius
            }
        }

        ShaderEffectSource {
            id: maskTexture
            anchors.fill: parent
            visible: false
            live: true
            hideSource: true
            sourceItem: maskShape
        }

        MultiEffect {
            anchors.fill: parent
            visible: panel.frosted
            source: slice
            autoPaddingEnabled: false
            blurEnabled: true
            blur: panel.blurAmount
            blurMax: 40
            blurMultiplier: 0.6
            maskEnabled: true
            maskSource: maskTexture
        }

        Rectangle {
            anchors.fill: parent
            antialiasing: true
            color: panel.fillColor
            border.width: Theme.hairline
            border.color: panel.borderColor
            topLeftRadius: panel.topRadius
            topRightRadius: panel.topRadius
            bottomLeftRadius: panel.bottomRadius
            bottomRightRadius: panel.bottomRadius

            Behavior on color { ColorAnimation { duration: Theme.base } }
        }

        // Внутренний блик: без него стекло выглядит просто мутным пятном.
        Rectangle {
            anchors.fill: parent
            anchors.margins: Theme.hairline
            color: "transparent"
            antialiasing: true
            border.width: Theme.hairline
            border.color: panel.edgeColor
            topLeftRadius: Math.max(0, panel.topRadius - Theme.hairline)
            topRightRadius: Math.max(0, panel.topRadius - Theme.hairline)
            bottomLeftRadius: Math.max(0, panel.bottomRadius - Theme.hairline)
            bottomRightRadius: Math.max(0, panel.bottomRadius - Theme.hairline)
        }
    }

    Item {
        id: holder
        anchors.fill: parent
    }
}
