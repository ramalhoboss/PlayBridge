import QtQuick
import QtQuick.Controls.Basic

// A round icon button for the footer, with its name and key under the pointer.
Item {
    id: tool
    property string icon: ""
    property color iconColor: Theme.text
    property string tip: ""
    property bool lit: false
    property bool navigable: visible && enabled
    signal clicked()
    function activate() { Theme.keys = true; clicked() }
    implicitWidth: 42
    implicitHeight: 42
    activeFocusOnTab: true
    Keys.onReturnPressed: activate()
    Keys.onSpacePressed: activate()
    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: tool.lit ? Qt.rgba(1, 0.35, 0.39, 0.22) : area.containsMouse ? Qt.rgba(1, 1, 1, 0.16) : Qt.rgba(1, 1, 1, 0.07)
        border.width: 1
        border.color: tool.lit ? Theme.danger : Qt.rgba(1, 1, 1, area.containsMouse ? 0.3 : 0.13)
        scale: area.pressed ? 0.93 : area.containsMouse ? 1.06 : 1
        Behavior on scale { NumberAnimation { duration: Theme.ms(110) } }
        Behavior on color { ColorAnimation { duration: Theme.ms(120) } }
        Icon { anchors.centerIn: parent; width: 19; height: 19; name: tool.icon; color: tool.iconColor }
    }
    FocusGlow { on: tool.activeFocus; radius: tool.width / 2 - 5 }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: { Theme.keys = false; tool.clicked() }
    }
    ToolTip {
        visible: area.containsMouse && tool.tip !== ""
        delay: 500
        text: tool.tip
        popupType: Popup.Window
        y: -height - 8
        contentItem: Text { text: tool.tip; color: Theme.text; font.family: Theme.face; font.pixelSize: 12 }
        background: Rectangle { color: Theme.raised; radius: 6; border.color: Theme.line }
    }
}
