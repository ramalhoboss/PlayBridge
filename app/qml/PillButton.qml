import QtQuick
import QtQuick.Effects

// PlayBridge's button. tone: main (gold), plain, ghost (outline) or danger. It lifts under the pointer and glows gold for the keys.
Item {
    id: button
    property string text: ""
    property string icon: ""
    property string tone: "plain"
    property bool selected: false
    property real fontSize: 15
    property bool navigable: enabled && visible
    signal clicked()
    function activate() { if (enabled) { Theme.keys = true; clicked() } }
    implicitHeight: 44
    implicitWidth: Math.max(implicitHeight, row.implicitWidth + 40)
    activeFocusOnTab: true
    opacity: enabled ? 1 : 0.42
    Keys.onReturnPressed: activate()
    Keys.onEnterPressed: activate()
    Keys.onSpacePressed: activate()

    readonly property bool hot: area.containsMouse && enabled
    readonly property color fill: tone === "main" ? (hot ? Theme.goldHover : Theme.gold)
        : tone === "danger" ? (hot ? "#FF737B" : "#E0444E")
        : selected ? Qt.rgba(1, 1, 1, 0.16)
        : tone === "ghost" ? (hot ? Qt.rgba(1, 1, 1, 0.08) : "transparent")
        : (hot ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.075))
    readonly property color ink: tone === "main" ? Theme.ink : Theme.text

    Rectangle {
        id: face
        anchors.fill: parent
        radius: height / 2
        color: button.fill
        border.width: button.tone === "main" || button.tone === "danger" ? 0 : 1
        border.color: button.selected ? Theme.gold : Qt.rgba(1, 1, 1, button.hot ? 0.28 : 0.14)
        Behavior on color { ColorAnimation { duration: Theme.ms(120) } }
        transform: Translate { y: button.hot && !area.pressed ? -1.5 : 0; Behavior on y { NumberAnimation { duration: Theme.ms(120) } } }
        scale: area.pressed ? 0.97 : 1
        Behavior on scale { NumberAnimation { duration: Theme.ms(90) } }
        layer.enabled: button.tone === "main" && button.enabled
        layer.effect: MultiEffect { shadowEnabled: true; shadowColor: Theme.gold; shadowOpacity: button.hot ? 0.55 : 0.32; shadowBlur: 0.7; shadowVerticalOffset: 2; blurMax: 24 }
        Row {
            id: row
            anchors.centerIn: parent
            spacing: 8
            Icon { visible: button.icon !== ""; name: button.icon; color: button.ink; width: button.fontSize + 3; height: width; anchors.verticalCenter: parent.verticalCenter }
            Text {
                visible: button.text !== ""
                text: button.text
                color: button.ink
                font.family: button.tone === "main" ? Theme.strong : Theme.face
                font.pixelSize: button.fontSize
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }
    FocusGlow { on: button.activeFocus; radius: button.height / 2 - 5 }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: button.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: { Theme.keys = false; if (button.enabled) button.clicked() }
    }
}
