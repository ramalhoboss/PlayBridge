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
                    id: awayCard
                    title: "Away from home"
                    visible: page.s.section === "console"
                    property var a: page.s.away || ({})
                    Toggle { width: parent.width; text: awayCard.a.busy ? (awayCard.a.on ? "Ending away play…" : "Getting ready…") : "Play away from home"; checked: !!awayCard.a.on; enabled: !awayCard.a.busy; onToggled: function(on) { shell.act("away", on) } }
                    Note { visible: !!awayCard.a.now; text: awayCard.a.now || ""; tone: "news" }
                    Note { text: awayCard.a.text || "" }
                    Note { visible: !!awayCard.a.problem; text: awayCard.a.problem || ""; tone: "error" }
                    Caption { visible: !!awayCard.a.typed; text: "Your home address" }
                    Row {
                        visible: !!awayCard.a.typed
                        width: parent.width
                        spacing: 8
                        Field { id: awayAddress; width: parent.width - 118; placeholderText: "Your home IP or a name such as home.example.net"; onEntered: shell.act("away_address", text) }
                        PillButton { text: "Save"; tone: "main"; width: 110; height: 46; onClicked: shell.act("away_address", awayAddress.text) }
                    }
                    Caption { text: "The PS5 waits for this PC" }
                    Choice { width: parent.width; model: awayCard.a.hoursList || []; value: awayCard.a.hours || ""; enabled: !awayCard.a.on && !awayCard.a.busy; onPicked: function(v) { shell.act("away_hours", v) } }
                    Note { visible: !!awayCard.a.on; text: "Turn away play off to change how long the PS5 waits." }
                    Caption { text: "Quality away from home" }
                    Choice { width: parent.width; model: awayCard.a.profiles || []; value: awayCard.a.profile || ""; enabled: !awayCard.a.busy; onPicked: function(v) { shell.act("away_profile", v) } }
                    Caption { text: "How the picture travels" }
                    Choice { width: parent.width; model: awayCard.a.transports || []; value: awayCard.a.transport || ""; enabled: !awayCard.a.busy; onPicked: function(v) { shell.act("away_transport", v) } }
                    Note { text: "Turn it on at home, with the PS5 on and nothing streaming: PlayBridge opens the way in and sends the payload that waits for this PC. Away, connect as usual. The stream starts at the quality above and steps down when the line loses too much, then back up after a few minutes without loss. Only this PC opens it: everything is encrypted with this PC's key, and nothing can be sent to the PS5 from outside, as the ELF loader's port stays closed." }
                }
                Card {
                    title: "Controller"
                    visible: page.s.section === "console"
                    Toggle { width: parent.width; text: "Play on your PS5"; checked: !!page.s.consolePad; onToggled: function(on) { shell.act("console_pad", on) } }
                    Note { text: "Your controller and keyboard play on your PS5 from the live view. PlayBridge sends a small second payload that adds a controller on the PS5 for this PC; each PC or phone gets its own, up to four. It is there only while you play: it joins with your first press in the live view and leaves when you leave the live view or after two minutes with nothing pressed, so your own DualSense always connects." }
                    Note { text: "In a game, the PS5 reads only the controller that connected first. If your DualSense is on, turn it off (Control Center › Accessories) so the game takes this one, and turn it on again when you are done here." }
                    Note { visible: !!page.s.consolePad; text: page.s.padStatus || ""; tone: "news" }
                    Note { visible: !!page.s.consolePad; text: "Keyboard: " + (page.s.keyboardHelp || "") }
                }
                Card {
                    title: "Controller profile"
                    visible: page.s.section === "console"
                    property var p: page.s.padProfile || ({})
                    property string pairFrom: ""
                    property string pairTo: ""
                    id: profileCard
                    Note { text: profileCard.p.forText || ""; tone: "news" }
                    Note { text: profileCard.p.text || "" }
                    Toggle { width: parent.width; text: "Swap ✕ and ○"; checked: !!profileCard.p.swap_face; onToggled: function(on) { shell.act("pad_profile", { name: "swap_face", value: on }) } }
                    Toggle { width: parent.width; text: "Swap L1 and R1 with L2 and R2"; checked: !!profileCard.p.swap_shoulders; onToggled: function(on) { shell.act("pad_profile", { name: "swap_shoulders", value: on }) } }
                    Toggle { width: parent.width; text: "Swap the sticks"; checked: !!profileCard.p.swap_sticks; onToggled: function(on) { shell.act("pad_profile", { name: "swap_sticks", value: on }) } }
                    Toggle { width: parent.width; text: "Invert up and down on the left stick"; checked: !!profileCard.p.invert_ly; onToggled: function(on) { shell.act("pad_profile", { name: "invert_ly", value: on }) } }
                    Toggle { width: parent.width; text: "Invert up and down on the right stick"; checked: !!profileCard.p.invert_ry; onToggled: function(on) { shell.act("pad_profile", { name: "invert_ry", value: on }) } }
                    Caption { text: "One hand" }
                    Choice { width: parent.width; model: page.s.padHands || []; value: profileCard.p.hand || ""; onPicked: function(v) { shell.act("pad_profile", { name: "one_hand", value: v }) } }
                    Note { text: "Left hand: hold L1 and the D-pad plays as △ ○ ✕ □, the left stick as the right stick. Right hand: hold R1 and the face buttons play as the D-pad, the right stick as the left stick." }
                    Caption { text: "Turbo: repeats a button while you hold it" }
                    Flow {
                        width: parent.width
                        spacing: 8
                        Repeater {
                            model: profileCard.p.turboButtons || []
                            delegate: PillButton { required property var modelData; text: modelData.label; tone: "ghost"; width: 64; height: 40; selected: modelData.on; onClicked: shell.act("pad_turbo", modelData.key) }
                        }
                    }
                    Choice { width: parent.width; model: page.s.padRates || []; value: profileCard.p.rate || ""; onPicked: function(v) { shell.act("pad_profile", { name: "turbo_rate", value: v }) } }
                    Caption { text: "Your own buttons" }
                    Repeater {
                        model: profileCard.p.pairs || []
                        delegate: Item {
                            required property string modelData
                            required property int index
                            width: profileCard.width - 48; height: 42
                            Text { anchors.verticalCenter: parent.verticalCenter; text: modelData; color: Theme.text; font.family: Theme.face; font.pixelSize: 15 }
                            PillButton { anchors.right: parent.right; width: 100; height: 38; text: "Remove"; onClicked: shell.act("pad_pair_remove", index) }
                        }
                    }
                    Row {
                        width: parent.width
                        spacing: 8
                        Choice { width: (parent.width - 116) / 2; model: page.s.padButtons || []; placeholder: "Button"; value: profileCard.pairFrom; onPicked: function(v) { profileCard.pairFrom = v } }
                        Choice { width: (parent.width - 116) / 2; model: page.s.padButtons || []; placeholder: "plays as"; value: profileCard.pairTo; onPicked: function(v) { profileCard.pairTo = v } }
                        PillButton { width: 100; height: 46; text: "Add"; enabled: profileCard.pairFrom !== "" && profileCard.pairTo !== ""; onClicked: { shell.act("pad_pair_add", [profileCard.pairFrom, profileCard.pairTo]); profileCard.pairFrom = ""; profileCard.pairTo = "" } }
                    }
                    PillButton { visible: !!profileCard.p.own; width: parent.width; height: 48; text: "Use the profile for every game"; onClicked: shell.act("pad_profile_forget", null) }
                    Note { text: "The profile changes what this PC's controller, keyboard and mouse send, before they reach the PS5. Your DualSense on the console is not changed." }
                }
                Card {
                    title: "Mouse aim"
                    visible: page.s.section === "console"
                    Toggle { width: parent.width; text: "Aim with the mouse"; checked: !!page.s.mouseAim; onToggled: function(on) { shell.act("mouse_aim", on) } }
                    Note { text: "Click the picture to aim: the pointer hides and the mouse moves the right stick, with the keyboard for the rest. Escape, or leaving the window, lets go. " + (page.s.mouseHelp || "") + ". It needs Play on your PS5." }
                    Note { visible: !!page.s.mouseAim; text: (page.s.aim || {}).forText || ""; tone: "news" }
                    Note { visible: !!page.s.mouseAim; text: "Speed  " + aimSpeed.value.toFixed(1) + "×" }
                    LuxSlider { id: aimSpeed; visible: !!page.s.mouseAim; width: parent.width; from: 0.1; to: 5; value: (page.s.aim || {}).sensitivity || 1; onMoved: shell.act("aim_value", { name: "sensitivity", value: value }); onReleased: shell.act("aim_done", null) }
                    Note { visible: !!page.s.mouseAim; text: "The game's stick curve  " + aimCurve.value.toFixed(1) + (aimCurve.value < 1.05 ? " (even)" : "") }
                    LuxSlider { id: aimCurve; visible: !!page.s.mouseAim; width: parent.width; from: 1; to: 3; value: (page.s.aim || {}).curve || 1; onMoved: shell.act("aim_value", { name: "curve", value: value }); onReleased: shell.act("aim_done", null) }
                    Note { visible: !!page.s.mouseAim; text: "The game's dead zone  " + Math.round(aimDead.value * 100) + "%" }
                    LuxSlider { id: aimDead; visible: !!page.s.mouseAim; width: parent.width; from: 0; to: 0.4; value: (page.s.aim || {}).deadzone || 0; onMoved: shell.act("aim_value", { name: "deadzone", value: value }); onReleased: shell.act("aim_done", null) }
                    Toggle { visible: !!page.s.mouseAim; width: parent.width; text: "Invert up and down"; checked: !!(page.s.aim || {}).invert; onToggled: function(on) { shell.act("aim_value", { name: "invert", value: on }) } }
                    Note { visible: !!page.s.mouseAim; text: "If slow movements do nothing, raise the dead zone; if the view turns slowly and then all at once, raise the curve." }
                }
                Card {
                    title: "PS5 fans"
                    visible: page.s.section === "console"
                    Note { text: page.s.fanText || ""; tone: "news" }
                    Caption { text: "Every game" }
                    Choice { width: parent.width; model: page.s.fanLevels || []; value: page.s.fanEvery || ""; onPicked: function(v) { shell.act("fan_every", v) } }
                    Caption { visible: !!page.s.fanGame; text: page.s.fanGame ? "For " + page.s.fanGame.name : "" }
                    Choice { visible: !!page.s.fanGame; width: parent.width; model: page.s.fanGameLevels || []; value: page.s.fanGame ? page.s.fanGame.level : ""; onPicked: function(v) { shell.act("fan_game", v) } }
                    Note { text: "The PS5 keeps its own fan control, which holds the console at a target temperature. A lower target makes the fans speed up sooner: cooler, and louder. PlayBridge only ever lowers it, never above the PS5's own, and the PS5's own comes back as soon as PlayBridge disconnects. While a game runs you can give it a level of its own." }
                }
                Card {
                    title: "Send a payload"
                    visible: page.s.section === "console"
                    Choice { width: parent.width; model: page.s.recent || []; placeholder: "Send a recent payload"; value: ""; onPicked: function(v) { shell.act("payload_recent", v) } }
                    PillButton { width: parent.width; height: 48; text: "Choose ELF and send"; onClicked: payloadDialog.open() }
                    Note { text: (page.s.payloadStatus || {}).text || ""; tone: (page.s.payloadStatus || {}).tone || "plain" }
                }
                Card {
                    title: "Payload shelf"
                    visible: page.s.section === "console"
                    Note { text: "Payloads published as .elf files in a GitHub repository's releases. Name the repository as owner/name; PlayBridge lists them and marks one whose release has a newer copy than the one on your PC. Getting a payload only downloads it; Send asks first, as above." }
                    Row {
                        width: parent.width
                        spacing: 8
                        Field { id: payloadRepo; width: parent.width - 134; placeholderText: "owner/name"; onEntered: shell.act("payload_repo", text) }
                        PillButton { width: 126; height: 46; text: "Read payloads"; onClicked: shell.act("payload_repo", payloadRepo.text) }
                    }
                    Note { visible: !!page.s.payloadShelfStatus; text: page.s.payloadShelfStatus || "" }
                    Repeater {
                        model: page.s.payloadItems || []
                        delegate: Item {
                            required property var modelData
                            width: parent.width
                            height: 54
                            Column {
                                anchors.left: parent.left
                                anchors.right: shelfButtons.left
                                anchors.rightMargin: 8
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 2
                                Text { width: parent.width; elide: Text.ElideRight; text: modelData.label; color: Theme.text; font.family: Theme.face; font.pixelSize: 15 }
                                Text { text: (modelData.size || "") + (modelData.have ? (modelData.update ? "  ·  on your PC, update ready" : "  ·  on your PC") : ""); color: modelData.update ? Theme.gold : Theme.dim; font.family: Theme.face; font.pixelSize: 12 }
                            }
                            Row {
                                id: shelfButtons
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 8
                                PillButton { visible: !modelData.have || modelData.update; width: 86; height: 40; text: modelData.update ? "Update" : "Get"; tone: "ghost"; onClicked: shell.act("payload_get", modelData.name) }
                                PillButton { width: 86; height: 40; text: "Send"; onClicked: shell.act("payload_send", modelData.name) }
                            }
                        }
                    }
                }
                Card {
                    id: devCard
                    title: "Developer"
                    visible: page.s.section === "console"
                    Note { text: "For building your own payloads. Watch an ELF you are compiling: resend it by hand, or turn on resending each time it changes. The kernel log reads the console's own log over the network, only listening, so you can watch what a payload prints." }
                    Caption { text: page.s.devWatchName ? "Watching " + page.s.devWatchName : "No ELF watched" }
                    Row {
                        width: parent.width
                        spacing: 8
                        PillButton { width: (parent.width - 8) / 2; height: 46; text: page.s.devWatchName ? "Watch another ELF" : "Choose ELF to watch"; onClicked: devWatchDialog.open() }
                        PillButton { width: (parent.width - 8) / 2; height: 46; text: "Resend now"; enabled: !!page.s.devWatchName; onClicked: shell.act("dev_resend", null) }
                    }
                    Toggle { width: parent.width; text: "Resend each time it changes"; checked: !!page.s.devAuto; onToggled: function(on) { shell.act("dev_auto", on) } }
                    Note { text: (page.s.devLine || {}).text || ""; tone: (page.s.devLine || {}).tone || "plain" }
                    Caption { text: "Kernel log" }
                    Row {
                        width: parent.width
                        spacing: 8
                        PillButton { width: (parent.width - 8) / 2; height: 44; text: page.s.devLogOn ? "Stop" : "Start"; selected: !!page.s.devLogOn; onClicked: shell.act("dev_log", !page.s.devLogOn) }
                        PillButton { width: (parent.width - 8) / 2; height: 44; text: "Clear"; tone: "ghost"; onClicked: shell.act("dev_log_clear", null) }
                    }
                    Note { visible: !!page.s.devLogError; text: page.s.devLogError || ""; tone: "error" }
                    Rectangle {
                        visible: !!page.s.devLogOn || (page.s.devLog || "") !== ""
                        width: parent.width
                        height: 200
                        radius: 12
                        color: Qt.rgba(0, 0, 0, 0.45)
                        border.width: 1
                        border.color: Qt.rgba(1, 1, 1, 0.12)
                        Flickable {
                            id: logFlick
                            anchors.fill: parent
                            anchors.margins: 12
                            contentHeight: logText.height
                            clip: true
                            boundsBehavior: Flickable.StopAtBounds
                            Text {
                                id: logText
                                width: logFlick.width
                                text: page.s.devLog || "The log will show here."
                                color: Theme.dim
                                wrapMode: Text.Wrap
                                font.family: "Consolas"
                                font.pixelSize: 12
                                onTextChanged: logFlick.contentY = Math.max(0, logText.height - logFlick.height)
                            }
                        }
                    }
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
                    Toggle { width: parent.width; text: "PS5 performance overlay"; checked: !!page.s.perfOverlay; onToggled: function(on) { shell.act("perf_overlay", on) } }
                    Note { text: "Over the game, as the PS5 measures it: the frames the game draws each second, with a minute of them, the CPU and SoC temperatures and the power the chip and its memory draw. F12 turns it on and off." + (page.s.direct ? "" : " It needs the GPU video output.") }
                }
                Card {
                    title: "Speedrun timer"
                    visible: page.s.section === "picture"
                    Toggle { width: parent.width; text: "Show the timer"; checked: !!page.s.timerShown; onToggled: function(on) { shell.act("timer_shown", on) } }
                    Toggle { width: parent.width; text: "Start when a game opens"; checked: !!page.s.timerAuto; onToggled: function(on) { shell.act("timer_auto", on) } }
                    Toggle { width: parent.width; text: "Split at each trophy"; checked: !!page.s.timerTrophies; onToggled: function(on) { shell.act("timer_trophies", on) } }
                    Note { text: "Over the game, beside the performance overlay. Ctrl+T starts it, and marks a split while it runs. Ctrl+Shift+T stops it, and clears it once stopped. Each game keeps its best run on this PC, and every split shows how far ahead or behind it is." }
                }
                Card {
                    title: "Video output"
                    visible: page.s.section === "picture"
                    Toggle { width: parent.width; text: "GPU video output"; checked: !!page.s.gpuOutput; onToggled: function(on) { shell.act("gpu_output", on) } }
                    Note { text: "The graphics card decodes and draws the video, which uses far less of the processor and keeps playing while the window is busy. Applies the next time PlayBridge opens." }
                    Toggle { width: parent.width; text: "Match the screen to the stream"; checked: !!page.s.matchRefresh; onToggled: function(on) { shell.act("match", on) } }
                    Note { text: "60 fps judders on a 144 or 165 Hz screen, because some frames stay up longer than others. While a game streams, PlayBridge switches the screen to 120 or 60 Hz, and back when the stream ends." }
                    Toggle { visible: !!page.s.direct; width: parent.width; text: "Smooth motion"; checked: !!page.s.smooth; onToggled: function(on) { shell.act("smooth", on) } }
                    Note { visible: !!page.s.direct; text: (page.s.smoothNote || "") + (page.s.smoothState ? "\n" + page.s.smoothState : "") }
                    Toggle { visible: !!page.s.vrrSupported; width: parent.width; text: "Variable refresh rate"; checked: !!page.s.vrr; onToggled: function(on) { shell.act("vrr", on) } }
                    Note { visible: !!page.s.vrrSupported; text: "For screens with G-Sync, FreeSync or Adaptive-Sync: each frame shows the moment it is due, so 60 fps plays evenly on a 144 Hz screen without switching it to 60 Hz. Works best in full screen (F11), and other screens may show tearing. While it is on, PlayBridge leaves the screen rate alone. Applies the next time PlayBridge opens." }
                }
                Card {
                    title: "Picture Studio"
                    visible: page.s.section === "picture"
                    Note { visible: !page.s.direct; text: "Picture Studio needs the GPU video output, above." }
                    Toggle { visible: !!page.s.direct; width: parent.width; text: "Graphics card super resolution"; checked: !!page.s.superResolution; onToggled: function(on) { shell.act("super_resolution", on) } }
                    Note { visible: !!page.s.direct; text: "When the window is larger than the picture, such as 1080p on a 1440p or 4K screen, the graphics card's own video engine enlarges it: NVIDIA RTX Video Super Resolution on an RTX card, Intel's video super resolution on Intel Arc and recent Intel graphics. On an NVIDIA card it also needs RTX Video super resolution on in the NVIDIA app. Other cards use FSR 1 instead." + (page.s.engineScaling && page.s.engineScaling !== "off" ? "\nNow: " + page.s.engineScaling + "." : "") }
                    Toggle { visible: !!page.s.direct; width: parent.width; text: "RTX Video HDR"; checked: !!page.s.videoHdr; onToggled: function(on) { shell.act("video_hdr", on) } }
                    Note { visible: !!page.s.direct; text: "On an NVIDIA RTX card with Windows HDR on for this screen, the graphics card turns the PS5's SDR picture into HDR, with brighter highlights and deeper colour. It is the card's own estimate of HDR, not HDR from the console. Needs RTX Video HDR on in the NVIDIA app. While it is on, Deband, Sharpen picture and the comparison wait." + (page.s.engineHdr && page.s.engineHdr !== "off" ? "\nNow: " + page.s.engineHdr + "." : "") }
                    Toggle { visible: !!page.s.direct; width: parent.width; text: "FSR 1 upscaling"; checked: !!page.s.fsr; onToggled: function(on) { shell.act("fsr", on) } }
                    Note { visible: !!page.s.direct; text: "AMD FidelityFX Super Resolution 1 enlarges the picture where the graphics card's super resolution is off or not on this card. Works on any graphics card." }
                    Toggle { visible: !!page.s.direct; width: parent.width; text: "Sharpen picture"; checked: !!page.s.sharpen; onToggled: function(on) { shell.act("sharpen", on) } }
                    Toggle { visible: !!page.s.direct; width: parent.width; text: "Deband"; checked: !!page.s.deband; onToggled: function(on) { shell.act("deband", on) } }
                    Note { visible: !!page.s.direct; text: "Smooths the steps the stream's compression leaves in skies, fog and shadows, and leaves edges and textures as they are." }
                    Toggle { visible: !!page.s.direct; width: parent.width; text: "Compare before and after"; checked: !!page.s.compare; onToggled: function(on) { shell.act("compare", on) } }
                    Note { visible: !!page.s.direct; text: "Left of the white line, the picture as the PS5 sends it. Right of it, with these settings. Only until PlayBridge closes." }
                    Caption { visible: !!page.s.direct && !!page.s.studioGame; text: page.s.studioOwn ? "These settings are " + page.s.studioGame + "'s own" : "For " + page.s.studioGame }
                    PillButton { visible: !!page.s.direct && !!page.s.studioGame && !page.s.studioOwn; width: parent.width; height: 48; text: "Keep these for " + (page.s.studioGame || "this game"); onClicked: shell.act("studio_keep", null) }
                    PillButton { visible: !!page.s.direct && !!page.s.studioOwn; width: parent.width; height: 48; text: "Use my usual settings for this game"; onClicked: shell.act("studio_forget", null) }
                    Note { visible: !!page.s.direct; text: (page.s.studioGame ? "A game's own settings come back each time it runs, and the switches above change them while it does." : "While a game runs you can keep these settings as its own, and they come back each time it runs.") + ((page.s.studioGames || []).length ? "\nGames with their own: " + page.s.studioGames.join(", ") + "." : "") }
                }

                // Captures.
                Card {
                    title: "Instant replay"
                    visible: page.s.section === "captures"
                    Choice { width: parent.width; model: page.s.replayLengths || []; value: page.s.replay || ""; onPicked: function(v) { shell.act("replay_length", v) } }
                    Note { text: "F10 saves it to your recordings. It stays in this PC's memory, up to 1 GB, and nothing changes on the PS5." }
                    Toggle { width: parent.width; text: "Keep a clip when a trophy unlocks"; checked: !!page.s.trophyClips; onToggled: function(on) { shell.act("trophy_clips", on) } }
                    Note { text: "While a game runs, PlayBridge reads your trophy list on the PS5 every 10 seconds. When a trophy appears, the 30 seconds before it and 5 after go to your recordings from the instant replay, named after the trophy. Needs instant replay on." }
                }
                Card {
                    title: "Microphone"
                    visible: page.s.section === "captures"
                    Toggle { width: parent.width; text: "Add my voice"; checked: !!page.s.mic; onToggled: function(on) { shell.act("mic", on) } }
                    Choice { width: parent.width; model: page.s.mics || []; value: page.s.micDevice || ""; onPicked: function(v) { shell.act("mic_device", v) } }
                    Caption { text: "Microphone volume" }
                    LuxSlider { width: parent.width; from: 0; to: page.s.micMax || 2; value: page.s.micLevel || 1; onMoved: shell.act("mic_level", value); onReleased: shell.act("mic_level_done", null) }
                    Note { visible: !!page.s.micState; text: page.s.micState || ""; tone: "news" }
                    Note { text: "Your voice goes into recordings, instant replays and Go live, mixed with the game's sound. You do not hear it in PlayBridge. F7 turns it on and off. The middle of the slider is your microphone as Windows gives it. With DualSense on your PS5, the controller's own microphone is heard through the PS5 while the stream runs." }
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
                Card {
                    title: "PS5 saves"
                    visible: page.s.section === "captures"
                    Toggle { width: parent.width; text: "Copy a game's saves when it closes"; checked: !!page.s.saveBackup; onToggled: function(on) { shell.act("save_backup", on) } }
                    Note { text: "When a game closes, PlayBridge reads its saves on your PS5 and keeps a copy in PS5 saves, in your capture folder: a new one only when they changed, the last 10 for each game. It only reads them and never writes to the PS5. A copy is the PS5's own sealed file, for this console and this user, so a PC or another console cannot open it." }
                    PillButton { width: parent.width; height: 48; text: "Copy every game's saves now"; enabled: !page.s.savesBusy; onClicked: shell.act("saves_now", null) }
                    PillButton { width: parent.width; height: 48; text: "Open the folder of saves"; onClicked: shell.act("saves_folder", null) }
                    Note { text: page.s.savesStatus || ""; tone: "news" }
                }

                // Streaming.
                Card {
                    title: "Go live"
                    visible: page.s.section === "live"
                    Note { text: page.s.liveSummary || ""; tone: (page.s.liveCount || 0) > 1 ? "news" : "plain" }
                    Note { visible: !!page.s.liveMissing; text: page.s.liveMissing || ""; tone: "error" }
                    Caption { text: "Service" }
                    Choice { width: parent.width; model: page.s.services || []; value: page.s.service || ""; onPicked: function(v) { shell.act("live_service", { label: v, key: key.text, server: server.text }) } }
                    Toggle { width: parent.width; text: "Go live on " + (page.s.service || ""); checked: !!page.s.liveOn; enabled: !page.s.liveActive; onToggled: function(on) { shell.act("live_target", { on: on, key: key.text, server: server.text }) } }
                    Caption { visible: page.s.serviceKey === "custom" || page.s.serviceKey === "tiktok" || page.s.serviceKey === "kick"; text: "Server address" }
                    Field { id: server; visible: page.s.serviceKey === "custom" || page.s.serviceKey === "tiktok" || page.s.serviceKey === "kick"; width: parent.width; placeholderText: "rtmp://"; onTextEdited: shell.act("live_check", { key: key.text, server: server.text }) }
                    Caption { visible: page.s.serviceKey !== "obs"; text: "Stream key" }
                    Row {
                        visible: page.s.serviceKey !== "obs"
                        width: parent.width
                        spacing: 8
                        Field { id: key; width: parent.width - 106; hidden: !shown.on; onTextEdited: shell.act("live_check", { key: key.text, server: server.text }) }
                        PillButton { id: shown; property bool on: false; text: on ? "Hide" : "Show"; width: 98; height: 46; onClicked: on = !on }
                    }
                    Toggle { visible: page.s.serviceKey !== "obs"; width: parent.width; text: "Show the overlay in the stream"; checked: !!page.s.liveOverlay; onToggled: function(on) { shell.act("live_overlay", on) } }
                    Note { visible: page.s.serviceKey !== "obs"; text: "Your viewers see the game's real frame rate, temperatures and power, the speedrun timer, each trophy as it unlocks and the buttons you press on this PC's controller. The graphics card makes the video again to draw them in, as H.264 unless Smaller stream is on." }
                    Toggle { visible: !!page.s.compressible; width: parent.width; text: "Smaller stream (HEVC or AV1)"; checked: !!page.s.compress; onToggled: function(on) { shell.act("live_compress", on) } }
                    Note { visible: !!page.s.compressible; text: page.s.compressNote || "" }
                    PillButton { width: parent.width; height: 48; text: page.s.liveEnding ? "Ending the live stream…" : page.s.liveActive ? "End live stream" : "Go live"; tone: page.s.liveActive ? "danger" : "main"; enabled: !page.s.liveEnding; onClicked: shell.act("live_go", { key: key.text, server: server.text }) }
                    Note { text: (page.s.liveStatus || {}).text || ""; tone: (page.s.liveStatus || {}).tone || "plain" }
                }
                Card {
                    title: "How it works"
                    visible: page.s.section === "live"
                    Note { text: "PlayBridge sends on the video and sound the PS5 already made, without encoding them again, so it costs this PC almost nothing. The stream uses your quality profile, as H.264 and AAC, so check that its bitrate suits your channel." }
                    Note { text: "Switch on several services and Go live sends the same stream to each at once, through a queue of its own: one that is slow or refuses the stream never holds up the others, and one that drops it is called again. Your upload carries the stream once for each service." }
                    Note { text: "For YouTube and other RTMP servers, Smaller stream makes the video again as AV1 or HEVC on the graphics card, so 4K fits a slower upload. Twitch takes those only in its Enhanced Broadcasting beta, so it always gets H.264." }
                    Note { text: "Ctrl+B or the button beside the small window starts and ends it with these settings. Recording and instant replay keep working while you are live." }
                }

                // Connections.
                Card {
                    title: "Discord profile"
                    visible: page.s.section === "connect"
                    Note { text: "Your Discord profile shows the game you play on your PS5, how long you have played it, and when you are live. Discord must be open on this PC. Nothing signs in: PlayBridge tells the Discord app through the channel it opens on this PC for this." }
                    Caption { text: "Application ID" }
                    Field { id: discordApp; width: parent.width; placeholderText: "A number of 17 to 21 digits"; inputMethodHints: Qt.ImhDigitsOnly; onTextEdited: shell.act("discord_app", text) }
                    Note { visible: ((page.s.discordState || {}).text || "") !== ""; text: (page.s.discordState || {}).text || ""; tone: (page.s.discordState || {}).tone || "plain" }
                    Note { text: "Make an application once, for free, on Discord's developer page. Its name is what your profile says you are playing, so call it PlayStation 5 or PlayBridge. Copy the Application ID from its General Information page. For a picture beside it, add one named playbridge in Rich Presence › Art Assets." }
                    PillButton { width: parent.width; height: 48; text: "Open Discord's developer page"; onClicked: shell.act("discord_page", null) }
                }
                Card {
                    title: "Discord channel"
                    visible: page.s.section === "connect"
                    Note { text: "Your screenshots and clips go to a channel of yours as you save them, with the game's name and, for a trophy, the trophy's." }
                    Caption { text: "Webhook URL" }
                    Row {
                        width: parent.width
                        spacing: 8
                        Field { id: discordUrl; width: parent.width - 106; hidden: !hookShown.on; placeholderText: "https://discord.com/api/webhooks/…"; onTextEdited: shell.act("discord_url", text) }
                        PillButton { id: hookShown; property bool on: false; text: on ? "Hide" : "Show"; width: 98; height: 46; onClicked: on = !on }
                    }
                    Toggle { width: parent.width; text: "Screenshots"; checked: !!page.s.discordShots; onToggled: function(on) { shell.act("discord_shots", on) } }
                    Toggle { width: parent.width; text: "Trophy clips"; checked: !!page.s.discordTrophies; onToggled: function(on) { shell.act("discord_trophies", on) } }
                    Toggle { width: parent.width; text: "Replays and recordings"; checked: !!page.s.discordClips; onToggled: function(on) { shell.act("discord_clips", on) } }
                    PillButton { width: parent.width; height: 48; text: "Send a test message"; enabled: !!page.s.discordReady; onClicked: shell.act("discord_test", null) }
                    Note { visible: ((page.s.discordStatus || {}).text || "") !== ""; text: (page.s.discordStatus || {}).text || ""; tone: (page.s.discordStatus || {}).tone || "plain" }
                    Note { text: "In Discord, open the channel's settings › Integrations › Webhooks › New Webhook, and copy its URL. It can only post in that channel, and PlayBridge keeps it encrypted for your Windows account, like the stream key." }
                    Note { text: "A clip is made again as H.264 at 720p, under Discord's 10 MB, and the file on this PC stays as it is. A clip longer than 95 seconds goes as words only. While a stream plays, that work goes no faster than the clip plays." }
                }
                Card {
                    title: "Twitch chat"
                    visible: page.s.section === "connect"
                    Note { text: "The newest messages in your channel's chat, over the game and, if you like, in your live stream, with emoji, badges and each name in its colour. PlayBridge reads it as an anonymous viewer, so nothing signs in and it never writes in your chat." }
                    Caption { text: "Channel" }
                    Field { id: chatChannel; width: parent.width; placeholderText: "Your channel's name, or its twitch.tv address"; onEditingFinished: shell.act("chat_channel", text) }
                    Note { visible: (page.s.chatProblem || "") !== ""; text: page.s.chatProblem || ""; tone: "error" }
                    Note { visible: (page.s.chatProblem || "") === "" && ((page.s.chatState || {}).text || "") !== ""; text: (page.s.chatState || {}).text || ""; tone: (page.s.chatState || {}).tone || "plain" }
                    Toggle { width: parent.width; text: "Show chat over the game"; checked: !!page.s.chatScreen; onToggled: function(on) { shell.act("chat_screen", on) } }
                    Toggle { width: parent.width; text: "Show chat in the live stream"; checked: !!page.s.chatStream; onToggled: function(on) { shell.act("chat_stream", on) } }
                    Note { text: "In the stream it is drawn like the overlay: the graphics card makes the video again, as H.264 unless Smaller stream is on. It applies the next time you go live." }
                    Toggle { width: parent.width; text: "Hide messages after a minute"; checked: !!page.s.chatFade; onToggled: function(on) { shell.act("chat_fade", on) } }
                    Note { text: "What your moderators delete, and the messages of anyone they time out or ban, disappear here too." }
                }
                Card {
                    title: "Stream Deck and OBS"
                    visible: page.s.section === "connect"
                    Note { text: "Press PlayBridge's buttons from a Stream Deck, Touch Portal, a hotkey program or a script, and show the game, its numbers, REC and LIVE, trophies and the chat in OBS." }
                    Toggle { width: parent.width; text: "Local control"; checked: !!page.s.apiOn; onToggled: function(on) { shell.act("api", on) } }
                    Note { visible: ((page.s.apiState || {}).text || "") !== ""; text: (page.s.apiState || {}).text || ""; tone: (page.s.apiState || {}).tone || "plain" }
                    Caption { visible: !!page.s.apiRunning; text: "Control address" }
                    Field { visible: !!page.s.apiRunning; width: parent.width; readOnly: true; text: page.s.apiAddress || ""; font.family: "Consolas"; font.pixelSize: 14 }
                    PillButton { visible: !!page.s.apiRunning; width: parent.width; height: 48; tone: "main"; text: "Copy the control address"; onClicked: shell.act("api_copy", "control") }
                    PillButton { visible: !!page.s.apiRunning; width: parent.width; height: 48; text: "Copy the OBS overlay address"; onClicked: shell.act("api_copy", "overlay") }
                    PillButton { visible: !!page.s.apiRunning; width: parent.width; height: 48; text: "Show every command"; onClicked: shell.act("api_open", null) }
                    PillButton { visible: !!page.s.apiRunning; width: parent.width; height: 48; text: "Make a new secret"; onClicked: shell.act("api_secret", null) }
                    Note { text: "Stream Deck: add a Website action, paste the control address with a command at its end, and tick GET request in background. The commands are screenshot, record, replay, live, mic, timer and timer-stop; status gives everything as JSON." }
                    Note { text: "OBS: add a Browser source with the overlay address, 1920 × 1080. Add ?chat=1 to it for the Twitch chat." }
                    Note { text: "Every address starts with a secret made on this PC, and only programs on this PC can reach them. Make a new secret if one was shared by mistake." }
                }

                Card {
                    title: "PlayStation Network"
                    visible: page.s.section === "connect"
                    Note { text: "Your PSN friends in PlayBridge: who is online and what they play, alerts when one comes online or opens a game you watch, and your PSN messages, read and answered on the Friends page." }
                    Note { text: (page.s.psnState || {}).text || ""; tone: (page.s.psnState || {}).tone || "plain" }
                    Note { visible: (page.s.psnProblem || "") !== ""; text: page.s.psnProblem || ""; tone: "error" }
                    Column {
                        visible: !page.s.psnOn
                        width: parent.width
                        spacing: 12
                        Note { text: "1. Sign in to your PlayStation account on playstation.com, in your browser." }
                        PillButton { width: parent.width; height: 48; text: "Open playstation.com"; onClicked: shell.act("psn_signin_page", null) }
                        Note { text: "2. In the same browser, open Sony's code page. It shows a line with npsso and 64 letters and numbers: copy them, or the whole line." }
                        PillButton { width: parent.width; height: 48; text: "Open Sony's code page"; onClicked: shell.act("psn_code_page", null) }
                        Caption { text: "3. Paste the code" }
                        Row {
                            width: parent.width
                            spacing: 8
                            Field { id: psnCode; width: parent.width - 106; hidden: !codeShown.on; placeholderText: "64 letters and numbers"; onEntered: psnSign.activate() }
                            PillButton { id: codeShown; property bool on: false; text: on ? "Hide" : "Show"; width: 98; height: 46; onClicked: on = !on }
                        }
                        PillButton { id: psnSign; width: parent.width; height: 48; tone: "main"; text: page.s.psnSigning ? "Signing in…" : "Sign in"; enabled: !page.s.psnSigning && psnCode.text.trim() !== ""; onClicked: { shell.act("psn_connect", psnCode.text); psnCode.text = "" } }
                        Note { text: "PlayBridge never sees your password. It trades the code once for a sign-in that lasts about two months, keeps that encrypted for your Windows account and forgets the code. Treat the code like a password: whoever has it can use your account." }
                    }
                    Column {
                        visible: !!page.s.psnOn
                        width: parent.width
                        spacing: 12
                        Toggle { width: parent.width; text: "Tell me when a friend comes online"; checked: !!page.s.psnOnline; onToggled: function(on) { shell.act("psn_online", on) } }
                        Toggle { width: parent.width; text: "Tell me when a friend starts a game"; checked: !!page.s.psnGames; onToggled: function(on) { shell.act("psn_games", on) } }
                        Toggle { width: parent.width; text: "Tell me about new messages"; checked: !!page.s.psnMessages; onToggled: function(on) { shell.act("psn_messages", on) } }
                        Toggle { width: parent.width; text: "Tell me about friend requests"; checked: !!page.s.psnRequests; onToggled: function(on) { shell.act("psn_requests", on) } }
                        Toggle { width: parent.width; text: "Only for my favourites"; checked: !!page.s.psnFavsOnly; onToggled: function(on) { shell.act("psn_favs_only", on) } }
                        Caption { text: "Games to watch" }
                        Field { id: psnWatch; width: parent.width; placeholderText: "XPS5, Elden Ring"; onEditingFinished: shell.act("psn_watch", text) }
                        Note { text: "When a friend opens a game whose name holds one of these words, PlayBridge tells you, even with the game alert off. Separate them with commas. A homebrew app shows only while your friend's PS5 is signed in to PSN." }
                        PillButton { width: parent.width; height: 48; tone: "main"; text: "Open Friends"; onClicked: shell.act("tab", "friends") }
                        PillButton { width: parent.width; height: 48; text: "Sign out"; onClicked: shell.act("psn_signout", null) }
                    }
                    Note { text: "This is not an official Sony service. PlayBridge talks to PSN the way the PlayStation App does, at most about 18 times a minute, and Sony can change that at any time. The alerts reach Windows and your phones, as the other alerts do." }
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
                    title: "Games page"
                    visible: page.s.section === "look"
                    Caption { text: "View" }
                    Choice { width: parent.width; model: page.s.gamesViews || []; value: page.s.gamesView || ""; onPicked: function(v) { shell.act("games_view", v) } }
                    Note { text: page.s.gamesView === "Grid" ? "Every game on one sheet of glass, the focused one larger and lit. The arrows move in all four directions." : page.s.gamesView === "List" ? "One game a row, with its type, when you last played, your time, trophies and size. Left and right change the shelf." : "Your games in one row, as on your PS5. Up and down change the shelf." }
                    Caption { text: page.s.gamesView === "List" ? "Row size" : "Tile size" }
                    Choice { width: parent.width; model: page.s.tileSizes || []; value: page.s.tileSize || ""; onPicked: function(v) { shell.act("tile_size", v) } }
                    Toggle { visible: page.s.gamesView === "Grid"; width: parent.width; text: "Names under tiles"; checked: !!page.s.tileNames; onToggled: function(on) { shell.act("tile_names", on) } }
                    Toggle { visible: page.s.gamesView !== "List"; width: parent.width; text: "Badges on tiles"; checked: !!page.s.tileBadges; onToggled: function(on) { shell.act("tile_badges", on) } }
                    Note { visible: page.s.gamesView !== "List"; text: "Open on the game that runs, PS4 on PS4 games, and a bar with your trophy progress, in platinum once earned." }
                    Note { text: "Also on the Games page: the View button at the top, View options in the … menu, and Ctrl+1, Ctrl+2 and Ctrl+3." }
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

                // Phone.
                Card {
                    title: "Your phone"
                    visible: page.s.section === "phone"
                    Toggle { width: parent.width; text: "Phone access"; checked: !!page.s.phoneOn; onToggled: function(on) { shell.act("phone", on) } }
                    Note { text: "Watch the game on your phone and play with touch controls, or with a controller paired to the phone, in its browser: nothing to install. Only phones on this PC's network can open it, and only after pairing once with a code." }
                    Note { visible: !!page.s.phoneOn; text: page.s.phoneAddress ? "On your phone, on the same Wi-Fi, open " + page.s.phoneAddress : ""; tone: "news" }
                    Note { visible: !!page.s.phoneOn && !!page.s.phoneAddress; text: page.s.phoneAddress ? "On a TV, a Steam Deck or another computer, open " + page.s.phoneAddress + "/tv in its browser, and play with a controller, the TV remote or a keyboard. It pairs like a phone." : "" }
                    Note { visible: !!page.s.phoneOn; text: "Chrome on Android 17 opens it only with its Nearby devices permission: Settings › Apps › Chrome › Permissions › Nearby devices › Allow. Other browsers may not need it." }
                    Note { visible: !page.s.phoneOn && !!page.s.phoneState; text: page.s.phoneState || ""; tone: "error" }
                    Note { visible: !!page.s.phoneOn; text: page.s.phoneState || "" }
                    Note { visible: !!page.s.phoneOn && !page.s.phonePlay; text: "To play from the phone, also turn on Play on your PS5 in Settings › Console. Until then the phone only watches." }
                }
                Card {
                    title: "Pairing"
                    visible: page.s.section === "phone" && !!page.s.phoneOn
                    Text {
                        visible: !!page.s.phoneCode
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: (page.s.phoneCode || "").replace(/(\d{3})(\d{3})/, "$1 $2")
                        color: Theme.gold
                        font.pixelSize: 44; font.letterSpacing: 6; font.weight: Font.DemiBold
                        Accessible.name: "Pairing code " + (page.s.phoneCode || "")
                    }
                    Note { visible: !!page.s.phoneCode; text: "Enter this code on the phone. It works once, for " + Math.max(1, Math.ceil((page.s.phoneCodeLeft || 0) / 60)) + " more minute" + ((page.s.phoneCodeLeft || 0) > 60 ? "s" : "") + "." }
                    PillButton { width: parent.width; height: 48; text: page.s.phoneCode ? "New code" : "Pair a phone"; onClicked: shell.act("phone_pair", null) }
                    PillButton {
                        width: parent.width; height: 48; text: "Disconnect phones"
                        enabled: (page.s.phoneWatching || 0) > 0
                        onClicked: shell.act("phone_disconnect", null)
                    }
                    Note { text: "Closes the picture on every phone connected now and takes their controllers off your PS5. They stay paired and connect again from their own page." }
                    Note { text: page.s.phonePaired || "" }
                    PillButton { width: parent.width; height: 48; text: "Forget paired phones"; onClicked: shell.act("phone_forget", null) }
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
                    Note { text: "PlayBridge looks for a new version on GitHub when it opens and every six hours. It downloads it slowly in the background, so a stream keeps its speed, checks it against the release's checksums, and then asks whether to restart and update now. Otherwise it goes in when you close PlayBridge." }
                    Toggle { width: parent.width; text: "Beta versions"; checked: updates.up.channel === "beta"; onToggled: function(on) { shell.act("update_beta", on) } }
                    Note { text: "Beta versions come out before the final ones: new things sooner, and sometimes bugs. Turned off again, PlayBridge waits for the next final version and never goes back to an older one." }
                    Note { text: updates.up.check || ""; tone: updates.up.slower ? "error" : "plain" }
                    PillButton { width: parent.width; height: 48; text: "Report a problem"; onClicked: shell.act("bug_report", null) }
                    Note { text: "Opens a new issue on PlayBridge's GitHub page with this PC's details filled in: the version, Windows, the graphics card, the stream settings and how long each frame takes. No addresses, names or files. Nothing is sent until you submit it there; the details are also copied, to paste anywhere." }
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
    property string awayAddressSeen: ""
    function load() {
        var s = shell.settings || {}
        if (s.host === undefined) return
        loaded = true
        if (!host.activeFocus) host.text = s.host || ""
        if (!consoleName.activeFocus) consoleName.text = s.consoleName || ""
        if (!server.activeFocus) server.text = s.server || ""
        if (!key.activeFocus) key.text = s.key || ""
        if (!discordApp.activeFocus) discordApp.text = s.discordApp || ""
        if (!discordUrl.activeFocus) discordUrl.text = s.discordUrl || ""
        if (!chatChannel.activeFocus) chatChannel.text = s.chatChannel || ""
        if (!psnWatch.activeFocus) psnWatch.text = s.psnWatch || ""
        if (!payloadRepo.activeFocus) payloadRepo.text = s.payloadRepo || ""
        if (!awayAddress.activeFocus) awayAddress.text = (s.away || {}).address || ""
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
            var away = (shell.settings || {}).away || {}
            if (!awayAddress.activeFocus && away.address !== undefined && away.address !== page.awayAddressSeen) { page.awayAddressSeen = away.address; awayAddress.text = away.address }
        }
    }

    FileDialog { id: payloadDialog; title: "Choose a payload"; nameFilters: ["ELF payload (*.elf)", "All files (*)"]; onAccepted: shell.act("payload_file", selectedFile.toString()) }
    FileDialog { id: devWatchDialog; title: "Choose an ELF to watch"; nameFilters: ["ELF payload (*.elf)", "All files (*)"]; onAccepted: shell.act("dev_watch_file", selectedFile.toString()) }
    FolderDialog { id: folderDialog; title: "Choose capture folder"; currentFolder: page.s.captureFolder ? "file:///" + page.s.captureFolder.replace(/\\/g, "/") : ""; onAccepted: shell.act("capture_folder", selectedFolder.toString()) }
    FileDialog { id: exportDialog; title: "Export diagnostics"; fileMode: FileDialog.SaveFile; nameFilters: ["ZIP archive (*.zip)"]; defaultSuffix: "zip"; onAccepted: shell.act("export", selectedFile.toString()) }
}
