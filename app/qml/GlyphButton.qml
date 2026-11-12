import QtQuick
import QtQuick.Controls.Basic

// A round button with a Windows symbol, for the top bar.
Item {
    id: button
    property string glyph: ""
    property string tip: ""
    property real u: 1
    property bool lit: false
    property bool navigable: false
    signal clicked()
    width: 42 * u
    height: 42 * u
    anchors.verticalCenter: parent ? parent.verticalCenter : undefined
    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: button.lit ? Qt.rgba(0.83, 0.69, 0.22, 0.22) : area.containsMouse ? Qt.rgba(1, 1, 1, 0.16) : Qt.rgba(1, 1, 1, 0.06)
        border.width: 1
        border.color: button.lit ? Theme.gold : Qt.rgba(1, 1, 1, area.containsMouse ? 0.3 : 0.1)
        scale: area.pressed ? 0.92 : 1
        Behavior on scale { NumberAnimation { duration: Theme.ms(90) } }
        Behavior on color { ColorAnimation { duration: Theme.ms(120) } }
        Text {
            anchors.centerIn: parent
            text: button.glyph
            color: button.lit ? Theme.goldSoft : Theme.text
            font.family: "Segoe MDL2 Assets"
            font.pixelSize: 16 * button.u
        }
    }
    MouseArea { id: area; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { Theme.keys = false; button.clicked() } }
    ToolTip {
        visible: area.containsMouse && button.tip !== ""
        delay: 500
        popupType: Popup.Window
        y: button.height + 8
        contentItem: Text { text: button.tip; color: Theme.text; font.family: Theme.face; font.pixelSize: 12 }
        background: Rectangle { color: Theme.raised; radius: 6; border.color: Theme.line }
    }
}
