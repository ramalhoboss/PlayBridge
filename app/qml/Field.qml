import QtQuick
import QtQuick.Controls.Basic

// A text field. Up and down leave it for the next control; Enter does what the page says, or leaves it.
TextField {
    id: field
    property bool navigable: visible && enabled
    property bool hidden: false
    signal entered()
    function activate() { forceActiveFocus(); selectAll() }
    implicitHeight: 46
    font.family: Theme.face
    font.pixelSize: 16
    color: Theme.text
    placeholderTextColor: Theme.dim
    selectionColor: Theme.gold
    selectedTextColor: Theme.ink
    echoMode: hidden ? TextInput.Password : TextInput.Normal
    passwordCharacter: "•"
    leftPadding: 16
    rightPadding: 16
    verticalAlignment: TextInput.AlignVCenter
    background: Rectangle {
        radius: 12
        color: field.activeFocus ? Qt.rgba(0, 0, 0, 0.5) : Qt.rgba(0, 0, 0, 0.32)
        border.width: field.activeFocus ? 1.5 : 1
        border.color: field.activeFocus ? Theme.gold : Qt.rgba(1, 1, 1, 0.16)
        Behavior on border.color { ColorAnimation { duration: Theme.ms(120) } }
    }
    Keys.onReturnPressed: entered()
    Keys.onEnterPressed: entered()
}
