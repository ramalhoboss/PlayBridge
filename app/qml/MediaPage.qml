import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
import QtQuick.Effects

// The Media page: this PC's screenshots and recordings as glass cards over PlayBridge's own picture, twelve at a time.
FocusScope {
    id: page
    property real u: 1
    property real topInset: 0
    property Item frost: null
    property var m: shell.media
    readonly property real side: Math.max(48, 64 * u)

    Flickable {
        id: flick
        anchors.fill: parent
        anchors.topMargin: page.topInset
        contentHeight: body.height + 60
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { width: 8; policy: ScrollBar.AsNeeded }
        Column {
            id: body
            x: page.side
            width: flick.width - 2 * page.side
            spacing: 22
            topPadding: 24
            Item {
                width: parent.width
                height: titleColumn.height
                Column {
                    id: titleColumn
                    width: parent.width - buttons.width - 20
                    spacing: 6
                    Text { text: "Your captures"; color: Theme.text; font.family: Theme.light; font.pixelSize: 44 }
                    Text { width: parent.width; wrapMode: Text.WordWrap; text: "Screenshots and recordings on this PC. F8 takes a screenshot, F9 starts or stops a recording."; color: Theme.muted; font.family: Theme.face; font.pixelSize: 16 }
                }
                Row {
                    id: buttons
                    anchors.right: parent.right
                    anchors.verticalCenter: titleColumn.verticalCenter
                    spacing: 12
                    PillButton { text: "From your PS5"; tone: "main"; width: 180; onClicked: shell.act("ps5_open", null) }
                    PillButton { text: "Open folder"; width: 150; onClicked: shell.act("media_folder", null) }
                }
            }
            Item {
                width: parent.width
                height: 44
                Row {
                    spacing: 10
                    Repeater {
                        model: ["All", "Photos", "Videos"]
                        delegate: PillButton {
                            required property string modelData
                            text: modelData
                            tone: "ghost"
                            width: 104; height: 42
                            selected: (page.m.filter || "All") === modelData
                            onClicked: shell.act("media_filter", modelData)
                        }
                    }
                }
                PillButton { anchors.right: parent.right; text: "Refresh"; width: 120; height: 42; onClicked: shell.act("media_refresh", null) }
            }
            // The empty page says what to do.
            Glass {
                visible: !!page.m.empty && !page.m.busy
                frost: page.frost
                follow: flick.contentY + page.x + page.opacity
                width: parent.width
                height: 250
                Column {
                    anchors.centerIn: parent
                    spacing: 12
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Make a moment worth keeping"; color: Theme.text; font.family: Theme.light; font.pixelSize: 32 }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; horizontalAlignment: Text.AlignHCenter; text: "F8 takes a screenshot. F9 starts or stops a recording.\nYour captures will appear here."; color: Theme.muted; font.family: Theme.face; font.pixelSize: 16 }
                }
            }
            Flow {
                id: grid
                width: parent.width
                spacing: 20
                readonly property int across: Math.max(1, Math.min(4, Math.floor((width + spacing) / (340 + spacing))))
                readonly property real cardWidth: (width - (across - 1) * spacing) / across
                Repeater {
                    model: page.m.cards || []
                    delegate: Glass {
                        id: card
                        required property var modelData
                        required property int index
                        frost: page.frost
                        follow: flick.contentY + page.x + page.opacity
                        width: grid.cardWidth
                        height: still.height + 150
                        scale: cardArea.containsMouse ? 1.015 : 1
                        Behavior on scale { NumberAnimation { duration: Theme.ms(140) } }
                        Item {
                            id: still
                            x: 12; y: 12
                            width: parent.width - 24
                            height: width * 9 / 16
                            Image {
                                id: picture
                                anchors.fill: parent
                                source: card.modelData.still || ""
                                sourceSize: Qt.size(Math.ceil(width * Screen.devicePixelRatio), Math.ceil(height * Screen.devicePixelRatio))
                                retainWhileLoading: true
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                visible: false
                            }
                            Rectangle { id: stillMask; anchors.fill: parent; radius: 12; visible: false; layer.enabled: true }
                            Rectangle { anchors.fill: parent; radius: 12; color: Theme.raised; visible: picture.status !== Image.Ready }
                            MultiEffect { anchors.fill: parent; source: picture; maskEnabled: true; maskSource: stillMask }
                            Rectangle {
                                visible: card.modelData.kind === "video"
                                anchors.centerIn: parent
                                width: 54; height: 54; radius: 27
                                color: Qt.rgba(0, 0, 0, 0.6); border.width: 2; border.color: Theme.text
                                Text { anchors.centerIn: parent; anchors.horizontalCenterOffset: 2; text: "▶"; color: Theme.text; font.pixelSize: 20 }
                            }
                            MouseArea { id: cardArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: shell.act("media_open", card.modelData.path) }
                        }
                        Column {
                            anchors.top: still.bottom
                            anchors.topMargin: 12
                            x: 18
                            width: parent.width - 36
                            spacing: 2
                            Text { text: card.modelData.when; color: Theme.text; font.family: Theme.face; font.pixelSize: 16 }
                            Text { text: card.modelData.detail; color: Theme.muted; font.family: Theme.face; font.pixelSize: 14 }
                            Item { width: 1; height: 10 }
                            PillButton { width: parent.width; height: 42; text: card.modelData.action; onClicked: shell.act("media_open", card.modelData.path) }
                        }
                    }
                }
            }
            Item {
                width: parent.width
                height: 44
                Text { anchors.verticalCenter: parent.verticalCenter; text: page.m.status || ""; color: Theme.muted; font.family: Theme.face; font.pixelSize: 15 }
                Row {
                    anchors.right: parent.right
                    spacing: 10
                    PillButton { text: "Previous"; width: 120; height: 42; enabled: !!page.m.previous; onClicked: shell.act("media_move", -1) }
                    PillButton { text: "Next"; width: 120; height: 42; enabled: !!page.m.next; onClicked: shell.act("media_move", 1) }
                }
            }
        }
    }
}
