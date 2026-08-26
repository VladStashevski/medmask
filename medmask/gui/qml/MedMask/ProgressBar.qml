import QtQuick
import MedMask

/*
  Толстая полоса с полностью круглыми концами. Значение подтягивается
  плавно, но короче четверти секунды: рывок вперед должен читаться как
  событие, а не как отдельная анимация.
*/
Item {
    id: bar

    property real value: 0            // 0..1
    property bool indeterminate: false
    property string tone: "primary"

    implicitHeight: Theme.progressHeight
    implicitWidth: 200

    Rectangle {
        id: track
        anchors.fill: parent
        radius: height / 2
        color: Theme.track
        antialiasing: true

        Rectangle {
            id: fill
            anchors.left: parent.left
            height: parent.height
            visible: !bar.indeterminate
            // Пустая полоса не показывает огрызок: ширина ниже высоты
            // превращает капсулу в точку.
            width: bar.value <= 0 ? 0
                 : Math.max(height, parent.width * Math.min(1, bar.value))
            radius: height / 2
            antialiasing: true
            color: Theme.toneColor(bar.tone)

            Behavior on width { NumberAnimation { duration: Theme.slow; easing.type: Theme.easing } }
            Behavior on color { ColorAnimation { duration: Theme.base } }
        }

        // Пока движок только считает документы, процента еще нет: бегущий
        // отрезок показывает, что работа идет. Он ходит внутри дорожки от
        // края до края, а не выезжает за нее: обрезанный краем отрезок
        // терял скругление и выглядел обрубком.
        Rectangle {
            id: pulse
            height: parent.height
            width: parent.width * 0.3
            radius: height / 2
            antialiasing: true
            visible: bar.indeterminate
            color: Theme.toneColor(bar.tone)

            SequentialAnimation on x {
                running: bar.indeterminate && Theme.motion
                loops: Animation.Infinite
                NumberAnimation {
                    from: 0
                    to: Math.max(0, track.width - pulse.width)
                    duration: 900
                    easing.type: Easing.InOutQuad
                }
                NumberAnimation {
                    from: Math.max(0, track.width - pulse.width)
                    to: 0
                    duration: 900
                    easing.type: Easing.InOutQuad
                }
            }
        }
    }
}
