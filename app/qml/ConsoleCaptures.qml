import QtQuick
import QtQuick.Controls.Basic

// The PS5's own screenshots and clips, listed through the payload, copied on request into the capture folder.
Popup {
    id: box
    property var c: shell.consoleCaptures
    popupType: Popup.Window
    modal: true
    focus: true
    width: 780
    height: 620
    anchors.centerIn: Overlay.overlay
    closePolicy: Popup.CloseOnEscape
    onClosed: if (box.c.open) shell.act("ps5_close", null)
    background: Rectangle {
        radius: 18
        color: "#0C0D11"
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, 0.14)
    }
    contentItem: Item {
        Column {
            id: head
            x: 10; y: 6
            width: parent.width - 20
            spacing: 4
            Text { text: "On your PS5"; color: Theme.text; font.family: Theme.light; font.pixelSize: 30 }
            Text { width: parent.width; wrapMode: Text.WordWrap; text: "Screenshots and clips the console saved. Copies go to your capture folder and show in Media."; color: Theme.muted; font.family: Theme.face; font.pixelSize: 13 }
        }
        ListView {
            id: rows
            anchors.top: head.bottom
            anchors.topMargin: 14
            anchors.bottom: foot.top
            anchors.bottomMargin: 12
            width: parent.width
            clip: true
            model: box.c.rows || []
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { width: 8 }
            delegate: Item {
                required property var modelData
                width: rows.width - 12
                height: 46
                Rectangle { anchors.fill: parent; radius: 10; color: rowArea.containsMouse ? Qt.rgba(1, 1, 1, 0.06) : "transparent" }
                Rectangle {
                    id: tick
                    x: 10; anchors.verticalCenter: parent.verticalCenter
                    width: 22; height: 22; radius: 6
                    color: modelData.chosen ? Theme.gold : "transparent"
                    border.width: 1.5; border.color: modelData.chosen ? Theme.gold : Qt.rgba(1, 1, 1, 0.4)
                    Text { anchors.centerIn: parent; visible: modelData.chosen; text: "✓"; color: Theme.ink; font.pixelSize: 15; font.bold: true }
                }
                Text { x: 44; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.38; elide: Text.ElideMiddle; text: modelData.name; color: Theme.text; font.family: Theme.face; font.pixelSize: 13 }
                Text { anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.55; horizontalAlignment: Text.AlignRight; elide: Text.ElideLeft; text: modelData.detail; color: Theme.muted; font.family: Theme.face; font.pixelSize: 11 }
                MouseArea { id: rowArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: shell.act("ps5_toggle", modelData.path) }
            }
        }
        Item {
            id: foot
            anchors.bottom: parent.bottom
            width: parent.width
            height: 44
            Text { anchors.verticalCenter: parent.verticalCenter; width: parent.width - 330; elide: Text.ElideRight; text: box.c.status || ""; color: Theme.muted; font.family: Theme.face; font.pixelSize: 13 }
            Row {
                anchors.right: parent.right
                spacing: 8
                PillButton { text: "Copy new"; width: 130; height: 40; fontSize: 14; enabled: !!box.c.canNew; onClicked: shell.act("ps5_copy_new", null) }
                PillButton { text: "Copy selected"; tone: "main"; width: 150; height: 40; fontSize: 14; enabled: !!box.c.canChosen; onClicked: shell.act("ps5_copy_chosen", null) }
                PillButton { text: "Close"; width: 96; height: 40; fontSize: 14; onClicked: shell.act("ps5_close", null) }
            }
        }
    }
}
