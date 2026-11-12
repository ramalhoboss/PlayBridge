import QtQuick
import QtQuick.Controls.Basic

// A slider with a gold fill. moved(value) while it changes, released() once it is let go, for saving.
Slider {
    id: slider
    property bool navigable: visible && enabled
    signal released()
    function activate() { forceActiveFocus() }
    implicitHeight: 32
    onPressedChanged: if (!pressed) released()
    Keys.onReleased: function(event) { if (event.key === Qt.Key_Left || event.key === Qt.Key_Right) slider.released() }
    background: Rectangle {
        x: slider.leftPadding
        y: slider.topPadding + slider.availableHeight / 2 - height / 2
        width: slider.availableWidth
        height: 6
        radius: 3
        color: Qt.rgba(1, 1, 1, 0.14)
        Rectangle {
            width: slider.visualPosition * parent.width
            height: parent.height
            radius: 3
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: "#B8932A" }
                GradientStop { position: 1; color: Theme.goldSoft }
            }
        }
    }
    handle: Rectangle {
        x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
        y: slider.topPadding + slider.availableHeight / 2 - height / 2
        width: 20
        height: 20
        radius: 10
        color: slider.pressed ? Theme.goldSoft : Theme.text
        scale: slider.hovered || slider.pressed ? 1.15 : 1
        Behavior on scale { NumberAnimation { duration: Theme.ms(100) } }
        FocusGlow { on: slider.activeFocus; radius: 5 }
    }
}
