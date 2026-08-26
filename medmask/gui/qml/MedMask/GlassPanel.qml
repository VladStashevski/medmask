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
    property color sheenColor: Theme.panelSheen
    property bool elevated: true
    property real blurAmount: 1.0
    // Насколько мягко пилюля вступает на строку. Разом она этого делать не
    // должна: строка на кромке получала бы ступеньку — сверху четко и темно,
    // снизу размыто и бледно, и ступенька читается как рез.
    property real edgeSoftness: 20

    readonly property real softStop: Math.min(0.45, edgeSoftness / Math.max(1, height))

    // Радиус размытия и запас, с которым берется слепок под стеклом, ходят
    // парой. Размытию нужны пиксели и за кромкой панели: слепок ровно по ее
    // размеру их не содержит, и содержимое под стеклом обрывалось бледной
    // каймой — внутри капсулы проступал прямоугольник с отступом от краев.
    readonly property real blurRadius: 32
    readonly property real bleed: blurRadius + Theme.space2

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
            x: -panel.bleed
            y: -panel.bleed
            width: panel.width + panel.bleed * 2
            height: panel.height + panel.bleed * 2
            visible: false
            live: panel.frosted
            hideSource: false
            sourceItem: panel.frosted ? panel.blurSource : null
            sourceRect: Qt.rect(panel.x - panel.bleed, panel.y - panel.bleed,
                                slice.width, slice.height)
        }

        Item {
            id: maskShape
            x: slice.x
            y: slice.y
            width: slice.width
            height: slice.height
            visible: false
            // Порог маски срезает полутона ниже половины, поэтому «пусто»
            // в ней записывается половиной: с нее размытие и нарастает.
            // Запас по краям маска не пропускает вовсе: размытие берет
            // сэмплы снаружи капсулы, а видно его ровно по ее силуэту.
            Rectangle {
                anchors.fill: parent
                anchors.margins: panel.bleed
                antialiasing: true
                topLeftRadius: panel.topRadius
                topRightRadius: panel.topRadius
                bottomLeftRadius: panel.bottomRadius
                bottomRightRadius: panel.bottomRadius
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.5) }
                    GradientStop { position: panel.softStop; color: "#FFFFFF" }
                    GradientStop { position: 1 - panel.softStop; color: "#FFFFFF" }
                    GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.5) }
                }
            }
        }

        ShaderEffectSource {
            id: maskTexture
            x: slice.x
            y: slice.y
            width: slice.width
            height: slice.height
            visible: false
            live: true
            hideSource: true
            sourceItem: maskShape
        }

        MultiEffect {
            x: slice.x
            y: slice.y
            width: slice.width
            height: slice.height
            visible: panel.frosted
            source: slice
            autoPaddingEnabled: false
            blurEnabled: true
            blur: panel.blurAmount
            // Стекло матовое: под пилюлей от строки остается цветное пятно,
            // а не читаемый текст.
            blurMax: panel.blurRadius
            blurMultiplier: 0.7
            // Настоящее матовое стекло не только размывает, но и слегка
            // поднимает цвет подложки: без этого слепок под белой заливкой
            // выцветает в серую муть.
            saturation: 0.25
            brightness: 0.06
            maskEnabled: true
            maskSource: maskTexture
            // Порог именно 0.5: при нуле MultiEffect не отсекает ничего, и
            // размытие ложится прямоугольником — его углы торчат за капсулу.
            maskThresholdMin: 0.5
            maskSpreadAtMin: 0.5
        }

        Rectangle {
            anchors.fill: parent
            antialiasing: true
            // Заливка ровная до самого края: если гасить ее у кромки, между
            // строкой и пилюлей проступает фон окна — прозрачная полоса.
            // Рамки у нее нет: кант живет отдельным слоем, под маской.
            color: panel.fillColor
            topLeftRadius: panel.topRadius
            topRightRadius: panel.topRadius
            bottomLeftRadius: panel.bottomRadius
            bottomRightRadius: panel.bottomRadius

            // Блик: свет ложится на верхнюю треть капсулы и сходит на нет к
            // середине. Без него матовая заливка выглядит мутным пятном.
            Rectangle {
                anchors.fill: parent
                antialiasing: true
                topLeftRadius: panel.topRadius
                topRightRadius: panel.topRadius
                bottomLeftRadius: panel.bottomRadius
                bottomRightRadius: panel.bottomRadius
                gradient: Gradient {
                    GradientStop { position: 0.0; color: panel.sheenColor }
                    GradientStop {
                        position: 0.5
                        color: Qt.rgba(panel.sheenColor.r, panel.sheenColor.g,
                                       panel.sheenColor.b, 0)
                    }
                    GradientStop {
                        position: 1.0
                        color: Qt.rgba(panel.sheenColor.r, panel.sheenColor.g,
                                       panel.sheenColor.b, 0)
                    }
                }
            }
        }

        // Стеклянный кант: холодный контур снаружи и светлая нить внутри.
        // Оба под маской, которая гасит их к нижнему краю: строка списка
        // уходит под пилюлю, и ровная нить по кругу перечеркивала бы ее.
        Item {
            id: rim
            anchors.fill: parent
            layer.enabled: true
            layer.effect: MultiEffect {
                maskEnabled: true
                maskSource: rimTexture
                maskThresholdMin: 0.5
                maskSpreadAtMin: 1.0
            }

            Rectangle {
                anchors.fill: parent
                color: "transparent"
                antialiasing: true
                border.width: Theme.hairline
                border.color: panel.borderColor
                topLeftRadius: panel.topRadius
                topRightRadius: panel.topRadius
                bottomLeftRadius: panel.bottomRadius
                bottomRightRadius: panel.bottomRadius
            }

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

        // Маска канта: как и у стекла, «пусто» здесь записано половиной —
        // порог маски срезает все, что ниже.
        Item {
            id: rimShape
            anchors.fill: parent
            visible: false

            Rectangle {
                anchors.fill: parent
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "#FFFFFF" }
                    GradientStop { position: 0.45; color: Qt.rgba(1, 1, 1, 0.85) }
                    GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.5) }
                }
            }
        }

        ShaderEffectSource {
            id: rimTexture
            anchors.fill: parent
            visible: false
            live: true
            hideSource: true
            sourceItem: rimShape
        }
    }

    Item {
        id: holder
        anchors.fill: parent
    }
}
