import QtQuick
import QtQuick.Controls.Basic

// A round button with a Windows symbol. lit: gold, for something that is on; danger: red under the pointer, for something that deletes.
// navigable: the keys and the controller reach it, and Enter or the controller's button presses it.
Item {
    id: button
    property string glyph: ""
    property string tip: ""
    property real u: 1
    property bool lit: false
    property bool danger: false
    property bool navigable: false
    signal clicked()
    function activate() { if (enabled) { Theme.keys = true; clicked() } }
    activeFocusOnTab: navigable
    opacity: enabled ? 1 : 0.42
    Keys.onReturnPressed: activate()
    Keys.onEnterPressed: activate()
    Keys.onSpacePressed: activate()
    readonly property bool hot: area.containsMouse && enabled
    width: 42 * u
    height: 42 * u
    anchors.verticalCenter: parent ? parent.verticalCenter : undefined
    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: button.danger && button.hot ? Qt.rgba(1, 0.35, 0.39, 0.2) : button.lit ? Theme.glow(button.hot ? 0.32 : 0.22) : button.hot ? Qt.rgba(1, 1, 1, 0.16) : Qt.rgba(1, 1, 1, 0.06)
        border.width: 1
        border.color: button.danger && button.hot ? Theme.danger : button.lit ? Theme.gold : Qt.rgba(1, 1, 1, button.hot ? 0.3 : 0.1)
        scale: area.pressed ? 0.92 : 1
        Behavior on scale { NumberAnimation { duration: Theme.ms(90) } }
        Behavior on color { ColorAnimation { duration: Theme.ms(120) } }
        Text {
            anchors.centerIn: parent
            text: button.glyph
            color: button.danger && button.hot ? Theme.danger : button.lit ? Theme.goldSoft : Theme.text
            Behavior on color { ColorAnimation { duration: Theme.ms(120) } }
            font.family: "Segoe MDL2 Assets"
            font.pixelSize: 16 * button.u
        }
    }
    FocusGlow { on: button.activeFocus; radius: button.height / 2 - 5 }
    MouseArea { id: area; anchors.fill: parent; hoverEnabled: true; cursorShape: button.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor; onClicked: { Theme.keys = false; if (button.enabled) button.clicked() } }
    ToolTip {
        visible: area.containsMouse && button.tip !== ""
        delay: 500
        popupType: Popup.Window
        y: button.height + 8
        contentItem: Text { text: button.tip; color: Theme.text; font.family: Theme.face; font.pixelSize: Theme.px(12) }
        background: Rectangle { color: Theme.raised; radius: 6; border.color: Theme.line }
    }
}
