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
                    Text { text: "Your captures"; color: Theme.text; font.family: Theme.light; font.pixelSize: Theme.px(44) }
                    Text { width: parent.width; wrapMode: Text.WordWrap; text: "Screenshots and recordings on this PC. F8 takes a screenshot, F9 starts or stops a recording."; color: Theme.muted; font.family: Theme.face; font.pixelSize: Theme.px(16) }
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
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Make a moment worth keeping"; color: Theme.text; font.family: Theme.light; font.pixelSize: Theme.px(32) }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; horizontalAlignment: Text.AlignHCenter; text: "F8 takes a screenshot. F9 starts or stops a recording.\nYour captures will appear here."; color: Theme.muted; font.family: Theme.face; font.pixelSize: Theme.px(16) }
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
                                Text { anchors.centerIn: parent; anchors.horizontalCenterOffset: 2; text: "▶"; color: Theme.text; font.pixelSize: Theme.px(20) }
                            }
                            MouseArea { id: cardArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: shell.act("media_open", card.modelData.path) }
                        }
                        Column {
                            anchors.top: still.bottom
                            anchors.topMargin: 12
                            x: 18
                            width: parent.width - 36
                            spacing: 2
                            Text { text: card.modelData.when; color: Theme.text; font.family: Theme.face; font.pixelSize: Theme.px(16) }
                            Text { text: card.modelData.detail; color: Theme.muted; font.family: Theme.face; font.pixelSize: Theme.px(14) }
                            Item { width: 1; height: 10 }
                            Row {
                                width: parent.width
                                spacing: 8
                                PillButton { width: card.modelData.kind === "video" ? (parent.width - 8) * 0.58 : parent.width; height: 42; text: card.modelData.action; onClicked: shell.act("media_open", card.modelData.path) }
                                PillButton { visible: card.modelData.kind === "video"; width: (parent.width - 8) * 0.42; height: 42; text: "Edit"; onClicked: shell.act("clip_edit", card.modelData.path) }
                            }
                        }
                    }
                }
            }
            Item {
                width: parent.width
                height: 44
                Text { anchors.verticalCenter: parent.verticalCenter; text: page.m.status || ""; color: Theme.muted; font.family: Theme.face; font.pixelSize: Theme.px(15) }
                Row {
                    anchors.right: parent.right
                    spacing: 10
                    PillButton { text: "Previous"; width: 120; height: 42; enabled: !!page.m.previous; onClicked: shell.act("media_move", -1) }
                    PillButton { text: "Next"; width: 120; height: 42; enabled: !!page.m.next; onClicked: shell.act("media_move", 1) }
                }
            }
        }
    }

    // The clip editor: over the page while a recording is open in it.
    Item {
        id: editor
        property var c: shell.clip || ({})
        readonly property real start: range.first.value
        readonly property real end: range.second.value
        function clock(seconds) {
            var whole = Math.max(0, seconds || 0); var minutes = Math.floor(whole / 60); var rest = whole - minutes * 60
            return minutes + ":" + (rest < 10 ? "0" : "") + rest.toFixed(1)
        }
        visible: !!c.path
        anchors.fill: parent
        z: 10
        Rectangle { anchors.fill: parent; color: Qt.rgba(0, 0, 0, 0.6); MouseArea { anchors.fill: parent; hoverEnabled: true } }
        Glass {
            frost: page.frost
            follow: page.x + page.opacity
            anchors.centerIn: parent
            anchors.verticalCenterOffset: page.topInset / 2
            width: Math.min(1120, parent.width - 2 * page.side)
            height: Math.min(parent.height - page.topInset - 40, sheet.implicitHeight + 56)
            Column {
                id: sheet
                x: 28; y: 28
                width: parent.width - 56
                spacing: 16
                Item {
                    width: parent.width
                    height: 46
                    Column {
                        anchors.left: parent.left; anchors.right: closer.left; anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        Text { text: "Edit clip"; color: Theme.text; font.family: Theme.light; font.pixelSize: Theme.px(30) }
                        Text { width: parent.width; elide: Text.ElideMiddle; text: editor.c.name || ""; color: Theme.muted; font.family: Theme.face; font.pixelSize: Theme.px(14) }
                    }
                    GlyphButton { id: closer; anchors.right: parent.right; glyph: "\uE711"; tip: "Close · Esc"; enabled: !editor.c.busy; onClicked: shell.act("clip_close", null) }
                }
                // Where the stretch starts and where it ends.
                Row {
                    width: parent.width
                    spacing: 16
                    Repeater {
                        model: 2
                        delegate: Column {
                            required property int index
                            width: (sheet.width - 16) / 2
                            spacing: 6
                            Rectangle {
                                width: parent.width; height: width * 9 / 16; radius: 12; color: Theme.raised; clip: true
                                Image { anchors.fill: parent; source: (editor.c.stills || [])[index] || ""; fillMode: Image.PreserveAspectFit; asynchronous: true; retainWhileLoading: true }
                                Text { visible: !!editor.c.loading; anchors.centerIn: parent; text: "Reading the recording…"; color: Theme.muted; font.family: Theme.face; font.pixelSize: Theme.px(15) }
                            }
                            Text { text: (index === 0 ? "Starts at " + editor.clock(editor.start) : "Ends at " + editor.clock(editor.end)); color: Theme.text; font.family: Theme.face; font.pixelSize: Theme.px(15) }
                        }
                    }
                }
                // The recording from end to end, and the stretch chosen on it.
                Item {
                    width: parent.width
                    height: 64
                    Row {
                        anchors.fill: parent
                        Repeater {
                            model: editor.c.strip || []
                            delegate: Rectangle {
                                required property string modelData
                                width: sheet.width / Math.max(1, (editor.c.strip || []).length); height: 64; color: Theme.raised; clip: true
                                Image { anchors.fill: parent; source: parent.modelData; fillMode: Image.PreserveAspectCrop; asynchronous: true }
                            }
                        }
                    }
                    RangeSlider {
                        id: range
                        anchors.fill: parent
                        padding: 0
                        enabled: !editor.c.busy && !editor.c.loading
                        from: 0
                        to: Math.max(0.1, editor.c.seconds || 0.1)
                        stepSize: 0.1
                        first.value: editor.c.start || 0
                        second.value: editor.c.end || 0
                        first.onPressedChanged: if (!first.pressed) shell.act("clip_range", [first.value, second.value])
                        second.onPressedChanged: if (!second.pressed) shell.act("clip_range", [first.value, second.value])
                        background: Item {
                            Rectangle { x: 0; width: range.first.visualPosition * parent.width; height: parent.height; color: Qt.rgba(0, 0, 0, 0.62) }
                            Rectangle { x: range.second.visualPosition * parent.width; width: parent.width - x; height: parent.height; color: Qt.rgba(0, 0, 0, 0.62) }
                            Rectangle { x: range.first.visualPosition * parent.width; width: (range.second.visualPosition - range.first.visualPosition) * parent.width; height: parent.height; color: "transparent"; border.width: 2; border.color: Theme.gold; radius: 4 }
                        }
                        first.handle: Rectangle { x: range.first.visualPosition * range.availableWidth - width / 2; y: -4; width: 12; height: range.height + 8; radius: 4; color: range.first.pressed ? Theme.goldHover : Theme.gold }
                        second.handle: Rectangle { x: range.second.visualPosition * range.availableWidth - width / 2; y: -4; width: 12; height: range.height + 8; radius: 4; color: range.second.pressed ? Theme.goldHover : Theme.gold }
                    }
                    // Each highlight, as a mark on the recording.
                    Repeater {
                        model: editor.c.moments || []
                        delegate: Rectangle {
                            required property var modelData
                            x: Math.max(0, Math.min(parent.width - width, parent.width * modelData.at - width / 2)); y: parent.height - 10
                            width: 8; height: 8; radius: 4; rotation: 45
                            color: modelData.kind === "trophy" ? Theme.gold : Theme.goldSoft
                            border.width: 1; border.color: Qt.rgba(0, 0, 0, 0.6)
                        }
                    }
                }
                Text {
                    text: "Length " + editor.clock(editor.end - editor.start) + "  ·  the whole recording is " + editor.clock(editor.c.seconds) + ". A GIF can be up to 20 seconds."
                    color: Theme.muted; font.family: Theme.face; font.pixelSize: Theme.px(14)
                }
                // The highlights PlayBridge found: a pick makes the stretch that moment.
                Column {
                    width: parent.width
                    spacing: 8
                    Text {
                        width: parent.width; wrapMode: Text.WordWrap; color: Theme.muted; font.family: Theme.face; font.pixelSize: Theme.px(14)
                        text: editor.c.finding ? "Looking for highlights: trophies, loud moments and busy stretches…"
                            : (editor.c.moments || []).length ? "Highlights. Pick one to make it the stretch, or make a reel of the best of them."
                            : "No highlights found in this recording. Trophies, loud moments and stretches of fast button presses on this PC's controller show here."
                    }
                    Flow {
                        width: parent.width
                        spacing: 8
                        Repeater {
                            model: editor.c.moments || []
                            delegate: PillButton {
                                required property var modelData
                                required property int index
                                text: modelData.text
                                tone: "ghost"
                                height: 38
                                fontSize: 13
                                enabled: !editor.c.busy && !editor.c.loading
                                selected: Math.abs(editor.start - modelData.start) < 0.06 && Math.abs(editor.end - modelData.end) < 0.06
                                onClicked: shell.act("clip_moment", index)
                            }
                        }
                    }
                }
                Flow {
                    width: parent.width
                    spacing: 10
                    Repeater {
                        model: editor.c.kinds || []
                        delegate: PillButton {
                            required property var modelData
                            text: modelData.label
                            tone: "ghost"
                            height: 42
                            enabled: !editor.c.busy
                            selected: editor.c.kind === modelData.key
                            onClicked: shell.act("clip_kind", modelData.key)
                        }
                    }
                }
                Text {
                    width: parent.width; wrapMode: Text.WordWrap; color: Theme.dim; font.family: Theme.face; font.pixelSize: Theme.px(14)
                    text: editor.c.kind === "gif" ? "A GIF plays everywhere, without sound: 480 pixels wide, 15 pictures a second."
                        : editor.c.kind === "vertical" ? "For TikTok, Shorts and Reels: 1080 x 1920 with the sound, cut from the middle of the picture. The highlights reel is made the same way."
                        : editor.c.kind === "vertical_fit" ? "For TikTok, Shorts and Reels: 1080 x 1920 with the sound, the whole picture across the middle over a blurred copy of itself, so nothing at its edges is lost. The highlights reel is made the same way."
                        : editor.c.kind === "full" ? "The stretch at the recording's own size, with its sound. The picture is made again, so it starts exactly where you chose."
                        : "Small enough for Discord, WhatsApp and most chats: H.264 under 10 MB, 720p when it is short enough."
                }
                // Progress while the clip is made.
                Rectangle {
                    visible: !!editor.c.busy
                    width: parent.width; height: 6; radius: 3; color: Qt.rgba(1, 1, 1, 0.1)
                    Rectangle { width: parent.width * (editor.c.share || 0); height: parent.height; radius: 3; color: Theme.gold; Behavior on width { NumberAnimation { duration: Theme.ms(200) } } }
                }
                Text {
                    visible: (editor.c.status || "") !== ""
                    width: parent.width; wrapMode: Text.WordWrap; font.family: Theme.face; font.pixelSize: Theme.px(15)
                    text: editor.c.status || ""
                    color: editor.c.tone === "error" ? Theme.alert : editor.c.tone === "news" ? Theme.online : Theme.muted
                }
                Row {
                    spacing: 12
                    PillButton { width: 200; height: 48; tone: "main"; text: editor.c.busy ? "Making…" : "Save the clip"; enabled: !editor.c.busy && !editor.c.loading && editor.end - editor.start >= 0.5; onClicked: shell.act("clip_export", null) }
                    PillButton { visible: (editor.c.moments || []).length > 0; height: 48; text: "Make the highlights reel · " + (editor.c.reelSeconds || 0) + " s"; enabled: !editor.c.busy && !editor.c.loading; onClicked: shell.act("clip_reel", null) }
                    PillButton { visible: (editor.c.made || "") !== ""; width: 180; height: 48; text: "Show in folder"; onClicked: shell.act("clip_show", null) }
                }
            }
        }
    }
}
