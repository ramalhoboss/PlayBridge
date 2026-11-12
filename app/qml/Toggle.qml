import QtQuick

// A switch with its words. The knob slides and the track fills with gold.
Item {
    id: toggle
    property string text: ""
    property bool checked: false
    property real fontSize: 16
    property bool navigable: visible && enabled
    signal toggled(bool on)
    function activate() { Theme.keys = true; toggled(!checked) }
    implicitHeight: 40
    implicitWidth: track.width + 14 + label.implicitWidth
    activeFocusOnTab: true
    Keys.onReturnPressed: activate()
    Keys.onSpacePressed: activate()
    Rectangle {
        id: track
        width: 52; height: 28; radius: 14
        anchors.verticalCenter: parent.verticalCenter
        color: toggle.checked ? Theme.gold : Qt.rgba(1, 1, 1, 0.12)
        border.width: toggle.checked ? 0 : 1
        border.color: Qt.rgba(1, 1, 1, 0.22)
        Behavior on color { ColorAnimation { duration: Theme.ms(160) } }
        Rectangle {
            width: 22; height: 22; radius: 11
            y: 3
            x: toggle.checked ? parent.width - width - 3 : 3
            color: toggle.checked ? Theme.ink : Theme.text
            Behavior on x { NumberAnimation { duration: Theme.ms(180); easing.type: Easing.OutBack; easing.overshoot: 1.6 } }
        }
        FocusGlow { on: toggle.activeFocus; radius: 9 }
    }
    Text {
        id: label
        anchors.left: track.right
        anchors.leftMargin: 14
        anchors.verticalCenter: parent.verticalCenter
        width: Math.max(0, toggle.width - track.width - 14)
        text: toggle.text
        color: Theme.text
        font.family: Theme.face
        font.pixelSize: toggle.fontSize
        wrapMode: Text.WordWrap
    }
    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: { Theme.keys = false; toggle.toggled(!toggle.checked) }
    }
}
