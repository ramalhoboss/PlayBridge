import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects

// A short list in a window of its own, so it can lie over the video. Frosted dark glass, the chosen row lit, gold at its edge.
// items: [{label}] or plain strings. It answers the mouse here; keys and the controller come through current/accepted.
Popup {
    id: menu
    property var items: []
    property int current: 0
    property real rowHeight: 46
    property real menuWidth: 300
    signal chosen(int index)
    // A key while the list has the keyboard: up, down, accept or back. The owner decides what it does.
    signal keyed(string event)
    popupType: Popup.Window
    padding: 8
    width: menuWidth
    height: Math.min(560, items.length * rowHeight + 16)
    modal: false
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    function label(item) { return typeof item === "string" ? item : item.label }
    enter: Transition { ParallelAnimation { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.ms(140) } NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: Theme.ms(160); easing.type: Easing.OutCubic } } }
    exit: Transition { NumberAnimation { property: "opacity"; to: 0; duration: Theme.ms(100) } }
    background: Rectangle {
        radius: 16
        color: Qt.rgba(0.07, 0.075, 0.095, 0.97)
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, 0.14)
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.rgba(0.13, 0.135, 0.16, 0.98) }
            GradientStop { position: 1; color: Qt.rgba(0.05, 0.05, 0.065, 0.98) }
        }
    }
    contentItem: ListView {
        id: list
        clip: true
        focus: true
        keyNavigationEnabled: false
        Keys.onPressed: function(event) {
            var names = {}
            names[Qt.Key_Up] = "up"; names[Qt.Key_Down] = "down"; names[Qt.Key_Return] = "accept"; names[Qt.Key_Enter] = "accept"; names[Qt.Key_Space] = "accept"
            if (names[event.key] !== undefined) { Theme.keys = true; menu.keyed(names[event.key]); event.accepted = true }
        }
        model: menu.items
        currentIndex: menu.current
        boundsBehavior: Flickable.StopAtBounds
        highlightMoveDuration: Theme.ms(120)
        highlight: Rectangle {
            radius: 12
            color: Qt.rgba(1, 1, 1, 0.12)
            Rectangle { width: 4; height: parent.height * 0.5; radius: 2; color: Theme.gold; anchors.verticalCenter: parent.verticalCenter; x: 6 }
        }
        delegate: Item {
            required property var modelData
            required property int index
            width: list.width
            height: menu.rowHeight
            Text {
                anchors.verticalCenter: parent.verticalCenter
                x: 22
                width: parent.width - 30
                elide: Text.ElideRight
                text: menu.label(modelData)
                color: index === menu.current ? Theme.text : Theme.muted
                font.family: Theme.face
                font.pixelSize: 15
            }
            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onEntered: menu.current = index
                onClicked: { Theme.keys = false; menu.chosen(index) }
            }
        }
    }
}
