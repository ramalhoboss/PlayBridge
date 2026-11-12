import QtQuick
import QtQuick.Effects

// The gold ring of the keys and the controller, with a soft glow. It shows only while they are in use, never after a click.
Item {
    id: ring
    property bool on: false
    property real radius: 12
    anchors.fill: parent
    anchors.margins: -5
    opacity: on && Theme.keys ? 1 : 0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: Theme.ms(140) } }
    Rectangle {
        id: line
        anchors.fill: parent
        radius: ring.radius + 5
        color: "transparent"
        border.width: 2.5
        border.color: Theme.gold
        layer.enabled: true
        layer.effect: MultiEffect { shadowEnabled: true; shadowColor: Theme.gold; shadowBlur: 0.8; shadowOpacity: 0.9; shadowHorizontalOffset: 0; shadowVerticalOffset: 0; blurMax: 24 }
    }
}
