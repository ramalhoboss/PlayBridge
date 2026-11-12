import QtQuick

// A dropdown: the value in a field, and its choices in a glass list under it. The arrows never change it by accident:
// Enter, a click or the controller's cross opens the list, and the list takes the keys until it closes.
Item {
    id: choice
    property var model: []
    property string value: ""
    property string placeholder: ""
    property real fontSize: 16
    property bool navigable: visible && enabled
    signal picked(string value)
    function activate() { Theme.keys = true; open() }
    function open() {
        if (!model || model.length === 0) return
        list.current = Math.max(0, model.indexOf(value))
        list.menuWidth = choice.width
        list.open()
    }
    implicitHeight: 46
    implicitWidth: 320
    activeFocusOnTab: true
    opacity: enabled ? 1 : 0.45
    Keys.onReturnPressed: open()
    Keys.onSpacePressed: open()
    Rectangle {
        anchors.fill: parent
        radius: 12
        color: area.containsMouse ? Qt.rgba(1, 1, 1, 0.11) : Qt.rgba(0, 0, 0, 0.32)
        border.width: 1
        border.color: list.opened ? Theme.gold : Qt.rgba(1, 1, 1, area.containsMouse ? 0.28 : 0.16)
        Behavior on color { ColorAnimation { duration: Theme.ms(120) } }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            x: 16
            width: parent.width - 52
            elide: Text.ElideRight
            text: choice.value || choice.placeholder
            color: choice.value ? Theme.text : Theme.dim
            font.family: Theme.face
            font.pixelSize: choice.fontSize
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            anchors.right: parent.right
            anchors.rightMargin: 16
            text: "▾"
            color: Theme.muted
            font.pixelSize: choice.fontSize
            rotation: list.opened ? 180 : 0
            Behavior on rotation { NumberAnimation { duration: Theme.ms(150) } }
        }
    }
    FocusGlow { on: choice.activeFocus && !list.opened; radius: 7 }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: { Theme.keys = false; choice.open() }
    }
    GlassMenu {
        id: list
        y: choice.height + 6
        items: choice.model
        onChosen: function(index) { list.close(); choice.picked(choice.model[index]); choice.forceActiveFocus() }
        onKeyed: function(event) { choice.answer(event) }
        onOpened: Theme.openChoice = choice
        onClosed: if (Theme.openChoice === choice) Theme.openChoice = null
    }
    // The controller's moves while the list is open: Main hands them here.
    function answer(event) {
        if (!list.opened) return false
        if (event === "up") list.current = (list.current - 1 + model.length) % model.length
        else if (event === "down") list.current = (list.current + 1) % model.length
        else if (event === "accept") list.chosen(list.current)
        else if (event === "back" || event === "leave") list.close()
        return true
    }
    readonly property bool listOpen: list.opened
}
