import QtQuick
import QtQuick.Controls.Basic

// Asks before anything that could lose progress or end the session. A window of its own, so it can stand over the video.
Popup {
    id: box
    property var d: shell.dialog
    readonly property bool wanted: !!(d && d.title)
    popupType: Popup.Window
    modal: true
    focus: true
    width: 520
    height: content.implicitHeight + 48
    anchors.centerIn: Overlay.overlay
    closePolicy: Popup.CloseOnEscape
    onWantedChanged: if (wanted) open(); else close()
    onClosed: if (wanted) shell.act("dialog_cancel", null)
    enter: Transition { ParallelAnimation { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.ms(160) } NumberAnimation { property: "scale"; from: 0.95; to: 1; duration: Theme.ms(200); easing.type: Easing.OutCubic } } }
    background: Rectangle {
        radius: 20
        color: "#0E0F13"
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, 0.14)
        gradient: Gradient {
            GradientStop { position: 0; color: "#1A1B21" }
            GradientStop { position: 1; color: "#0B0C0F" }
        }
    }
    contentItem: Column {
        id: content
        spacing: 14
        padding: 8
        Keys.onReturnPressed: shell.act("dialog_accept", null)
        Keys.onEnterPressed: shell.act("dialog_accept", null)
        Text { text: box.d.title || ""; color: Theme.text; font.family: Theme.light; font.pixelSize: 26; width: box.width - 64; wrapMode: Text.WordWrap }
        Text { text: box.d.text || ""; color: Theme.muted; font.family: Theme.face; font.pixelSize: 15; width: box.width - 64; wrapMode: Text.WordWrap; lineHeight: 1.15 }
        Item { width: 1; height: 6 }
        Row {
            anchors.right: parent.right
            anchors.rightMargin: 8
            spacing: 10
            PillButton { text: box.d.action || "OK"; tone: "main"; width: Math.max(150, implicitWidth); height: 42; onClicked: shell.act("dialog_accept", null) }
            PillButton { text: "Cancel"; width: 120; height: 42; onClicked: shell.act("dialog_cancel", null) }
        }
    }
    onOpened: content.forceActiveFocus()
}
