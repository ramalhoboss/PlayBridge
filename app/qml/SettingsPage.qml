import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs

// Settings: the sections on a glass rail at the left, and the chosen section's panels floating over PlayBridge's own picture.
// Every setting applies the moment it changes, except the console's address, which waits for Save or Enter.
FocusScope {
    id: page
    property real u: 1
    property real topInset: 0
    property Item frost: null
    property var s: shell.settings
    readonly property real rail: Math.max(250, Math.min(340, width * 0.22))
    readonly property real follow: flick.contentY + page.x + page.opacity

    component Card: Glass {
        id: card
        property string title: ""
        default property alias content: inner.data
        frost: page.frost
        follow: page.follow
        width: cards.cardWidth
        height: inner.height + 48
        radius: 18
        Column {
            id: inner
            x: 24; y: 22
            width: card.width - 48
            spacing: 10
            Text { visible: card.title !== ""; text: card.title; color: Theme.text; font.family: Theme.strong; font.pixelSize: 19; bottomPadding: 4 }
        }
    }
    component Caption: Text { color: Theme.muted; font.family: Theme.face; font.pixelSize: 15 }

    // The rail.
    Glass {
        id: railGlass
        frost: page.frost
        follow: page.x + page.opacity
        x: 28; y: page.topInset + 12
        width: page.rail
        height: page.height - y - 28
        radius: 22
        Column {
            anchors.fill: parent
            anchors.margins: 14
            spacing: 6
            Text { text: "Settings"; color: Theme.text; font.family: Theme.light; font.pixelSize: 36; leftPadding: 12; topPadding: 6; bottomPadding: 14 }
            Repeater {
                model: page.s.sections || []
                delegate: Item {
                    id: entry
                    required property var modelData
                    readonly property bool chosen: page.s.section === modelData.key
                    width: parent.width
                    height: 68
                    Rectangle {
                        anchors.fill: parent
                        radius: 16
                        color: entry.chosen ? Qt.rgba(1, 1, 1, 0.13) : entryArea.containsMouse ? Qt.rgba(1, 1, 1, 0.06) : "transparent"
                        Behavior on color { ColorAnimation { duration: Theme.ms(140) } }
                        Rectangle { visible: entry.chosen; width: 4; height: parent.height * 0.5; radius: 2; color: Theme.gold; x: 6; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Column {
                        x: 22; anchors.verticalCenter: parent.verticalCenter
                        width: parent.width - 34
                        Text { text: entry.modelData.label; color: Theme.text; font.family: entry.chosen ? Theme.strong : Theme.face; font.pixelSize: 18 }
                        Text { width: parent.width; elide: Text.ElideRight; text: entry.modelData.note; color: Theme.dim; font.family: Theme.face; font.pixelSize: 12 }
                    }
                    FocusGlow { on: page.railFocus === entry.modelData.key; radius: 11 }
                    MouseArea { id: entryArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { Theme.keys = false; shell.act("section", entry.modelData.key); flick.contentY = 0 } }
                }
            }
        }
    }
    property string railFocus: ""

    Flickable {
        id: flick
        objectName: "settingsView"
        anchors.left: railGlass.right
        anchors.leftMargin: 28
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.topMargin: page.topInset
        anchors.bottom: footLine.top
        contentHeight: body.height + 40
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { width: 8; policy: ScrollBar.AsNeeded }
        Column {
            id: body
            width: flick.width - 36
            spacing: 18
            topPadding: 18
            Column {
                spacing: 4
                Text { text: (page.s.sections || []).filter(function(x) { return x.key === page.s.section }).map(function(x) { return x.label })[0] || ""; color: Theme.text; font.family: Theme.light; font.pixelSize: 40 }
                Text { text: (page.s.sections || []).filter(function(x) { return x.key === page.s.section }).map(function(x) { return x.note })[0] || ""; color: Theme.muted; font.family: Theme.face; font.pixelSize: 16 }
            }
            Flow {
                id: cards
                width: parent.width
                spacing: 20
                readonly property int across: Math.max(1, Math.min(3, Math.floor((width + spacing) / (480 + spacing))))
                readonly property real cardWidth: Math.min(860, (width - (across - 1) * spacing) / across)

                // Console.
                Card {
                    title: "Your console"
                    visible: page.s.section === "console"
                    Choice { visible: (page.s.favourites || []).length > 0; width: parent.width; model: page.s.favourites || []; placeholder: "Choose a saved console"; onPicked: function(v) { shell.act("favourite", v) } }
                    Caption { text: "IP address" }
                    Row {
                        width: parent.width
                        spacing: 8
                        Field {
                            id: host
                            width: parent.width - 118
                            placeholderText: "192.168.1.20"
                            onEntered: shell.act("host_save", text)
                            onEditingFinished: shell.act("host_left", text)
                        }
                        PillButton { text: "Save"; tone: "main"; width: 110; height: 46; onClicked: shell.act("host_save", host.text) }
                    }
                    Choice { width: parent.width; model: page.s.found || []; value: page.s.foundLabel || ""; onPicked: function(v) { shell.act("found", v) } }
                    Note { text: page.s.scanStatus || "" }
                    PillButton { width: parent.width; height: 48; text: page.s.scanning ? "Scanning…" : "Find console"; enabled: !page.s.scanning; onClicked: shell.act("scan", host.text) }
                }
                Card {
                    title: "Favourite"
                    visible: page.s.section === "console"
                    Field { id: consoleName; width: parent.width; placeholderText: "My PS5" }
                    Note { text: (page.s.favouriteStatus || {}).text || ""; tone: (page.s.favouriteStatus || {}).tone || "plain" }
                    PillButton { width: parent.width; height: 48; text: "Save to favourites"; onClicked: shell.act("favourite_save", { name: consoleName.text, host: host.text }) }
                }
                Card {
                    title: "Connection"
                    visible: page.s.section === "console"
                    Toggle { width: parent.width; text: "Reconnect automatically"; checked: !!page.s.reconnect; onToggled: function(on) { shell.act("reconnect", on) } }
                    Toggle { width: parent.width; text: "ELF already loaded in Payload Manager"; checked: !!page.s.manual; onToggled: function(on) { shell.act("manual", on) } }
                    Note { text: "Off: PlayBridge uploads the ELF automatically.\nOn: load PlayBridge.elf, then connect within 60 seconds." }
                    Toggle { width: parent.width; text: "Notices on the PS5"; checked: !!page.s.notices; onToggled: function(on) { shell.act("notices", on) } }
                    Note { text: "The PS5 shows a notice when PlayBridge starts streaming to this PC and when it stops. A PlayBridge.elf you load yourself has to be from this version, or it refuses the connection while this is on." }
                }
                Card {
                    title: "Send a payload"
                    visible: page.s.section === "console"
                    Choice { width: parent.width; model: page.s.recent || []; placeholder: "Send a recent payload"; value: ""; onPicked: function(v) { shell.act("payload_recent", v) } }
                    PillButton { width: parent.width; height: 48; text: "Choose ELF and send"; onClicked: payloadDialog.open() }
                    Note { text: (page.s.payloadStatus || {}).text || ""; tone: (page.s.payloadStatus || {}).tone || "plain" }
                }
                Card {
                    title: "Power"
                    visible: page.s.section === "console"
                    Grid {
                        width: parent.width
                        columns: 2
                        spacing: 8
                        Repeater {
                            model: [["Soft reset", "soft_reset"], ["Rest mode", "rest"], ["Reboot", "reboot"], ["Turn off", "off"], ["Recovery", "recovery"]]
                            delegate: PillButton { required property var modelData; width: (parent.width - 8) / 2; height: 48; text: modelData[0]; onClicked: shell.act("power", modelData[1]) }
                        }
                    }
                    Note { text: "These need the PS5 connected. After a reboot or a power off, load your exploit again." }
                }

                // Picture.
                Card {
                    title: "Quality profile"
                    visible: page.s.section === "picture"
                    Choice { width: parent.width; model: page.s.profiles || []; value: page.s.profile || ""; onPicked: function(v) { shell.act("profile", v) } }
                    Note { text: "Choosing a profile reconnects to the PS5 with it at once. 30 fps limits PC playback only.\n1440p and 4K need the PS5 video output set to that resolution." }
                    Note { text: page.s.cardSummary || "" }
                }
                Card {
                    title: "Graphics card"
                    visible: page.s.section === "picture" && (page.s.cards || []).length > 1
                    Choice { width: parent.width; model: page.s.cards || []; value: page.s.card || ""; onPicked: function(v) { shell.act("card", v) } }
                    Note { text: "The card that decodes and draws the video. Automatic takes the one with the most memory of its own, such as the NVIDIA or AMD card in a gaming laptop. Applies the next time PlayBridge opens." }
                }
                Card {
                    title: "On screen"
                    visible: page.s.section === "picture"
                    Toggle { width: parent.width; text: "Show performance stats"; checked: !!page.s.diagnostic; onToggled: function(on) { shell.act("diagnostic", on) } }
                }
                Card {
                    title: "Video output"
                    visible: page.s.section === "picture"
                    Toggle { width: parent.width; text: "GPU video output"; checked: !!page.s.gpuOutput; onToggled: function(on) { shell.act("gpu_output", on) } }
                    Note { text: "The graphics card decodes and draws the video, which uses far less of the processor and keeps playing while the window is busy. Applies the next time PlayBridge opens." }
                    Toggle { width: parent.width; text: "Match the screen to the stream"; checked: !!page.s.matchRefresh; onToggled: function(on) { shell.act("match", on) } }
                    Note { text: "60 fps judders on a 144 or 165 Hz screen, because some frames stay up longer than others. While a game streams, PlayBridge switches the screen to 120 or 60 Hz, and back when the stream ends." }
                    Toggle { visible: !!page.s.direct; width: parent.width; text: "Sharpen picture"; checked: !!page.s.sharpen; onToggled: function(on) { shell.act("sharpen", on) } }
                    Toggle { visible: !!page.s.direct; width: parent.width; text: "FSR 1 upscaling"; checked: !!page.s.fsr; onToggled: function(on) { shell.act("fsr", on) } }
                    Note { visible: !!page.s.direct; text: "When the screen is larger than the picture, such as 1080p on a 1440p or 4K monitor, AMD FidelityFX Super Resolution 1 enlarges it, and Sharpen picture uses its sharpening. Works on any graphics card." }
                    Toggle { visible: !!page.s.vrrSupported; width: parent.width; text: "Variable refresh rate"; checked: !!page.s.vrr; onToggled: function(on) { shell.act("vrr", on) } }
                    Note { visible: !!page.s.vrrSupported; text: "For screens with G-Sync, FreeSync or Adaptive-Sync: each frame shows the moment it is due, so 60 fps plays evenly on a 144 Hz screen without switching it to 60 Hz. Works best in full screen (F11), and other screens may show tearing. While it is on, PlayBridge leaves the screen rate alone. Applies the next time PlayBridge opens." }
                }

                // Captures.
                Card {
                    title: "Instant replay"
                    visible: page.s.section === "captures"
                    Choice { width: parent.width; model: page.s.replayLengths || []; value: page.s.replay || ""; onPicked: function(v) { shell.act("replay_length", v) } }
                    Note { text: "F10 saves it to your recordings. It stays in this PC's memory, up to 1 GB, and nothing changes on the PS5." }
                }
                Card {
                    title: "Microphone"
                    visible: page.s.section === "captures"
                    Toggle { width: parent.width; text: "Add my voice"; checked: !!page.s.mic; onToggled: function(on) { shell.act("mic", on) } }
                    Choice { width: parent.width; model: page.s.mics || []; value: page.s.micDevice || ""; onPicked: function(v) { shell.act("mic_device", v) } }
                    Caption { text: "Microphone volume" }
                    LuxSlider { width: parent.width; from: 0; to: page.s.micMax || 2; value: page.s.micLevel || 1; onMoved: shell.act("mic_level", value); onReleased: shell.act("mic_level_done", null) }
                    Note { text: "Your voice goes into recordings, instant replays and Go live, mixed with the game's sound. You do not hear it in PlayBridge. F7 turns it on and off. The middle of the slider is your microphone as Windows gives it." }
                }
                Card {
                    title: "Files"
                    visible: page.s.section === "captures"
                    PillButton { width: parent.width; height: 48; text: "Choose capture folder"; onClicked: folderDialog.open() }
                    PillButton { width: parent.width; height: 48; text: "Export diagnostics"; onClicked: exportDialog.open() }
                    Note { text: page.s.captureFolder || "" }
                }
                Card {
                    title: "Smaller recordings"
                    visible: page.s.section === "captures"
                    Toggle { width: parent.width; text: "Make recordings smaller"; checked: !!page.s.compact; onToggled: function(on) { shell.act("compact", on) } }
                    Note { text: page.s.compactNote || "" }
                    Note { text: page.s.compactProgress || "" }
                }

                // Streaming.
                Card {
                    title: "Go live"
                    visible: page.s.section === "live"
                    Choice { width: parent.width; model: page.s.services || []; value: page.s.service || ""; onPicked: function(v) { shell.act("live_service", v) } }
                    Caption { visible: page.s.serviceKey === "custom"; text: "Server address" }
                    Field { id: server; visible: page.s.serviceKey === "custom"; width: parent.width; placeholderText: "rtmp://"; onTextEdited: shell.act("live_check", { key: key.text, server: server.text }) }
                    Caption { visible: page.s.serviceKey !== "obs"; text: "Stream key" }
                    Row {
                        visible: page.s.serviceKey !== "obs"
                        width: parent.width
                        spacing: 8
                        Field { id: key; width: parent.width - 106; hidden: !shown.on; onTextEdited: shell.act("live_check", { key: key.text, server: server.text }) }
                        PillButton { id: shown; property bool on: false; text: on ? "Hide" : "Show"; width: 98; height: 46; onClicked: on = !on }
                    }
                    Toggle { visible: !!page.s.compressible; width: parent.width; text: "Smaller stream (HEVC or AV1)"; checked: !!page.s.compress; onToggled: function(on) { shell.act("live_compress", on) } }
                    Note { visible: !!page.s.compressible; text: page.s.compressNote || "" }
                    PillButton { width: parent.width; height: 48; text: page.s.liveActive ? "End live stream" : "Go live"; tone: page.s.liveActive ? "danger" : "main"; onClicked: shell.act("live_go", { key: key.text, server: server.text }) }
                    Note { text: (page.s.liveStatus || {}).text || ""; tone: (page.s.liveStatus || {}).tone || "plain" }
                }
                Card {
                    title: "How it works"
                    visible: page.s.section === "live"
                    Note { text: "PlayBridge sends on the video and sound the PS5 already made, without encoding them again, so it costs this PC almost nothing. The stream uses your quality profile, as H.264 and AAC, so check that its bitrate suits your channel." }
                    Note { text: "For YouTube and other RTMP servers, Smaller stream makes the video again as AV1 or HEVC on the graphics card, so 4K fits a slower upload. Twitch takes those only in its Enhanced Broadcasting beta, so it always gets H.264." }
                    Note { text: "Ctrl+B or the button beside the small window starts and ends it with these settings. Recording and instant replay keep working while you are live." }
                }

                // Sound.
                Card {
                    title: "In the library"
                    visible: page.s.section === "sound"
                    Toggle { width: parent.width; text: "Background music"; checked: !!page.s.music; onToggled: function(on) { shell.act("music", on) } }
                    Toggle { width: parent.width; text: "Navigation sounds"; checked: !!page.s.cues; onToggled: function(on) { shell.act("cues", on) } }
                    Caption { text: "Library volume" }
                    LuxSlider { width: parent.width; from: 0; to: 1; value: page.s.level || 0; onMoved: shell.act("library_volume", value); onReleased: shell.act("library_volume_done", null) }
                    Note { text: "These sound only while your games are on screen, never over a game. A game with music of its own plays it; the others share the app's." }
                }

                // Appearance.
                Card {
                    title: "Gaming Mode"
                    visible: page.s.section === "look"
                    Toggle { width: parent.width; text: "Open in Gaming Mode"; checked: !!page.s.gamingOnStart; onToggled: function(on) { shell.act("gaming_on_start", on) } }
                    Note { text: "Your games, fullscreen on this PC, with no console menu. The TV still shows the PS5 as usual." }
                }
                Card {
                    title: "Motion"
                    visible: page.s.section === "look"
                    Toggle { width: parent.width; text: "Animations"; checked: !!page.s.animations; onToggled: function(on) { shell.act("animations", on) } }
                    Note { text: "Page changes, the moving art, the tiles' tilt and the waiting screen. Motion pauses during video playback." }
                }
                Card {
                    title: "Look"
                    visible: page.s.section === "look"
                    Toggle { width: parent.width; text: "Glass look"; checked: !!page.s.qt; onToggled: function(on) { shell.act("qt", on) } }
                    Note { text: "This look, drawn on the graphics card, with glass panels and motion. Off brings back the classic window. Applies the next time PlayBridge opens." }
                }

                // Updates.
                Card {
                    id: updates
                    readonly property var up: page.s.update || {}
                    title: "PlayBridge " + (updates.up.current || "")
                    visible: page.s.section === "updates"
                    Note { text: updates.up.text || ""; tone: updates.up.state === "failed" ? "error" : "plain" }
                    PillButton {
                        width: parent.width; height: 48
                        text: updates.up.state === "checking" ? "Looking…" : updates.up.state === "downloading" ? "Downloading…" : "Check now"
                        enabled: updates.up.state !== "checking" && updates.up.state !== "downloading" && updates.up.state !== "ready"
                        onClicked: shell.act("update_check", null)
                    }
                    PillButton {
                        visible: !!updates.up.installable
                        width: parent.width; height: 48; tone: "main"
                        text: "Restart and update"
                        onClicked: shell.act("update_install", null)
                    }
                    PillButton {
                        visible: !!updates.up.source && updates.up.state === "available"
                        width: parent.width; height: 48
                        text: "Open the release page"
                        onClicked: shell.act("update_page", null)
                    }
                    Toggle { width: parent.width; text: "Update automatically"; checked: !!updates.up.automatic; onToggled: function(on) { shell.act("update_auto", on) } }
                    Note { text: "PlayBridge looks for a new version on GitHub when it opens and every six hours. It downloads it slowly in the background, so a stream keeps its speed, checks it against the release's checksums, and puts it in when you close PlayBridge." }
                }
            }
        }
    }
    // What a change did, or what is wrong with the address, under Console and Picture.
    Text {
        id: footLine
        anchors.left: flick.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 18
        height: visible ? 30 : 0
        visible: (page.s.section === "console" || page.s.section === "picture") && ((page.s.line || {}).text || "") !== ""
        text: (page.s.line || {}).text || ""
        color: Theme.tone((page.s.line || {}).tone || "plain")
        font.family: Theme.face
        font.pixelSize: 16
        elide: Text.ElideRight
    }

    // Text the window fills in itself, as a console that was found or a favourite that was chosen.
    // The fields take what is saved when the page comes up, and are never reset while someone types in them.
    property int filled: 0
    property bool loaded: false
    function load() {
        var s = shell.settings || {}
        if (s.host === undefined) return
        loaded = true
        if (!host.activeFocus) host.text = s.host || ""
        if (!consoleName.activeFocus) consoleName.text = s.consoleName || ""
        if (!server.activeFocus) server.text = s.server || ""
        if (!key.activeFocus) key.text = s.key || ""
    }
    onVisibleChanged: if (visible) load()
    Connections {
        target: shell
        function onSettingsChanged() {
            if (!page.loaded) page.load()
            var fill = (shell.settings || {}).fill || {}
            if (fill.version !== undefined && fill.version !== page.filled) {
                page.filled = fill.version
                if (fill.host) host.text = fill.host
                if (fill.name) consoleName.text = fill.name
            }
        }
    }

    FileDialog { id: payloadDialog; title: "Choose a payload"; nameFilters: ["ELF payload (*.elf)", "All files (*)"]; onAccepted: shell.act("payload_file", selectedFile.toString()) }
    FolderDialog { id: folderDialog; title: "Choose capture folder"; currentFolder: page.s.captureFolder ? "file:///" + page.s.captureFolder.replace(/\\/g, "/") : ""; onAccepted: shell.act("capture_folder", selectedFolder.toString()) }
    FileDialog { id: exportDialog; title: "Export diagnostics"; fileMode: FileDialog.SaveFile; nameFilters: ["ZIP archive (*.zip)"]; defaultSuffix: "zip"; onAccepted: shell.act("export", selectedFile.toString()) }
}
