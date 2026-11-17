import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
import QtQuick.Effects

// The Trophies page: your trophy level and every game you have trophies in on PSN, PS5 and PS4, and a game's trophies with how rare
// each is, with a friend's beside yours when you compare. A click or Enter opens a game; in a game, Enter on a trophy opens its guide.
FocusScope {
    id: page
    property real u: 1
    property real topInset: 0
    property Item frost: null
    property var t: shell.trophies || ({})
    readonly property real side: Math.max(48, 64 * u)
    readonly property bool signedIn: t.state === "on"
    readonly property var opened: t.open || null
    readonly property bool sideBySide: !!opened && (opened.friendName || "") !== ""

    // A game's or a trophy's picture with round corners, or a letter while it loads.
    component Picture: Item {
        id: art
        property string source: ""
        property string initial: ""
        property real radius: 12
        property bool lit: true
        Rectangle { anchors.fill: parent; radius: art.radius; color: Theme.raised; visible: picture.status !== Image.Ready
            Text { anchors.centerIn: parent; text: art.initial; color: Theme.muted; font.family: Theme.strong; font.pixelSize: art.height * 0.4 } }
        Image {
            id: picture
            anchors.fill: parent
            source: art.source
            sourceSize: Qt.size(Math.ceil(width * Screen.devicePixelRatio), Math.ceil(height * Screen.devicePixelRatio))
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            visible: false
        }
        Rectangle { id: shape; anchors.fill: parent; radius: art.radius; visible: false; layer.enabled: true }
        MultiEffect { anchors.fill: parent; source: picture; maskEnabled: true; maskSource: shape; visible: picture.status === Image.Ready; opacity: art.lit ? 1 : 0.4; saturation: art.lit ? 0 : -0.8 }
    }

    // A thin bar for how far along a game is, in platinum once the platinum is earned.
    component Bar: Rectangle {
        property real share: 0
        property color fill: Theme.gold
        height: 6; radius: 3; color: Qt.rgba(1, 1, 1, 0.1)
        Rectangle { width: parent.width * Math.max(0, Math.min(1, parent.share)); height: parent.height; radius: 3; color: parent.fill
            Behavior on width { NumberAnimation { duration: Theme.ms(260); easing.type: Easing.OutCubic } } }
    }

    // Signed out: what this page does, and where to sign in.
    Glass {
        visible: !page.signedIn
        frost: page.frost
        follow: page.x + page.opacity
        anchors.centerIn: parent
        anchors.verticalCenterOffset: page.topInset / 2
        width: Math.min(760, parent.width - 2 * page.side)
        height: welcomeColumn.implicitHeight + 72
        Column {
            id: welcomeColumn
            anchors.centerIn: parent
            width: parent.width - 80
            spacing: 14
            TrophyCup { anchors.horizontalCenter: parent.horizontalCenter; grade: "gold"; width: 54; height: 54 }
            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: page.t.state === "signing" ? "Signing in to PSN…" : "All your trophies, right here"; color: Theme.text; font.family: Theme.light; font.pixelSize: Theme.px(34); wrapMode: Text.WordWrap }
            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap; color: Theme.muted; font.family: Theme.face; font.pixelSize: Theme.px(16)
                text: "Your trophy level and every game you have trophies in, PS5 and PS4, also the ones no longer on your console. Open a game to see how rare each trophy is, and compare with a friend." }
            Text { visible: (page.t.problem || "") !== ""; width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap; color: Theme.alert; font.family: Theme.face; font.pixelSize: Theme.px(15); text: page.t.problem || "" }
            Item { width: 1; height: 6 }
            PillButton { anchors.horizontalCenter: parent.horizontalCenter; width: 240; height: 50; tone: "main"; text: page.t.state === "expired" ? "Sign in again" : "Sign in to PSN"; enabled: page.t.state !== "signing"; onClicked: shell.act("psn_settings", null) }
        }
    }

    Item {
        id: body
        visible: page.signedIn
        anchors.fill: parent
        anchors.topMargin: page.topInset + 24
        anchors.leftMargin: page.side
        anchors.rightMargin: page.side
        anchors.bottomMargin: 28

        // Who you are on PSN, your level and your trophies by grade.
        Row {
            id: heading
            spacing: 16
            Picture { width: 58; height: 58; radius: 29; anchors.verticalCenter: parent.verticalCenter; source: (page.t.me || {}).picture || ""; initial: (((page.t.me || {}).name || "?").charAt(0)).toUpperCase() }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 4
                Text { text: "Trophies"; color: Theme.text; font.family: Theme.light; font.pixelSize: Theme.px(40) }
                Row {
                    spacing: 12
                    Text { anchors.verticalCenter: parent.verticalCenter; text: page.t.level ? "Level " + page.t.level.level : "Reading your trophies…"; color: Theme.goldSoft; font.family: Theme.strong; font.pixelSize: Theme.px(15) }
                    Bar { visible: !!page.t.level; anchors.verticalCenter: parent.verticalCenter; width: 150; share: page.t.level ? page.t.level.share : 0 }
                    Text { visible: !!page.t.level; anchors.verticalCenter: parent.verticalCenter; text: page.t.level ? Math.round(page.t.level.share * 100) + "% to the next level  ·  " + page.t.level.total + " trophies" : ""; color: Theme.muted; font.family: Theme.face; font.pixelSize: Theme.px(14) }
                }
            }
        }
        Row {
            anchors.right: parent.right
            anchors.verticalCenter: heading.verticalCenter
            spacing: 22
            Repeater {
                model: page.t.level ? page.t.level.counts : []
                delegate: Row {
                    required property var modelData
                    spacing: 8
                    TrophyCup { anchors.verticalCenter: parent.verticalCenter; grade: modelData.grade; width: 26; height: 26 }
                    Text { anchors.verticalCenter: parent.verticalCenter; text: modelData.count.toLocaleString(Qt.locale(), "f", 0); color: Theme.text; font.family: Theme.light; font.pixelSize: Theme.px(26) }
                }
            }
        }

        // What to show: the filters, reading again, and a friend to compare with.
        Row {
            id: controls
            anchors.top: heading.bottom
            anchors.topMargin: 18
            spacing: 10
            Repeater {
                model: page.opened ? [] : (page.t.filters || [])
                delegate: PillButton {
                    required property string modelData
                    text: modelData; tone: "ghost"; width: 104; height: 40
                    selected: (page.t.filter || "All") === modelData
                    onClicked: shell.act("trophy_filter", modelData)
                }
            }
            PillButton { visible: !!page.opened; width: 150; height: 40; tone: "ghost"; text: "‹  All games"; onClicked: shell.act("trophy_close", null) }
            GlyphButton { glyph: ""; tip: "Read again"; onClicked: shell.act("trophy_refresh", null) }
        }
        Row {
            anchors.right: parent.right
            anchors.verticalCenter: controls.verticalCenter
            spacing: 12
            Text { anchors.verticalCenter: parent.verticalCenter; text: "Compare with"; color: Theme.muted; font.family: Theme.face; font.pixelSize: Theme.px(15) }
            Choice {
                width: 250; height: 42; fontSize: 15
                model: page.t.friends || []
                value: (page.t.friendName || "") !== "" ? page.t.friendName : "Nobody"
                onPicked: function(v) { shell.act("trophy_compare", v === "Nobody" ? "" : v) }
            }
        }
        Text {
            id: note
            anchors.top: controls.bottom; anchors.topMargin: 10
            width: parent.width; elide: Text.ElideRight
            text: (page.t.problem || "") !== "" ? page.t.problem : (page.t.friendLine || "")
            color: (page.t.problem || "") !== "" ? Theme.alert : Theme.goldSoft
            font.family: Theme.face; font.pixelSize: Theme.px(14)
            height: text !== "" ? implicitHeight : 0
        }

        Glass {
            id: sheet
            frost: page.frost
            follow: page.x + page.opacity + (page.opened ? trophyList.contentY : page.t.hunting ? huntList.contentY : titleList.contentY)
            anchors.top: note.bottom
            anchors.topMargin: 12
            anchors.bottom: parent.bottom
            width: parent.width
            radius: 20

            Text {
                visible: !page.opened && (page.t.empty || "") !== ""
                anchors.centerIn: parent
                width: parent.width - 80
                horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                text: page.t.empty || ""; color: Theme.muted; font.family: Theme.face; font.pixelSize: Theme.px(16)
            }

            // Next up: the trophies most players have that you have not, from your games in progress.
            ListView {
                id: huntList
                visible: !page.opened && !!page.t.hunting
                anchors.fill: parent
                anchors.margins: 10
                clip: true
                spacing: 4
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { width: 8; policy: ScrollBar.AsNeeded }
                model: visible ? (page.t.hunt || []) : []
                header: Text {
                    width: huntList.width - 10
                    leftPadding: 12; rightPadding: 12; topPadding: 8; bottomPadding: 12
                    wrapMode: Text.WordWrap
                    text: page.t.huntLine || ""
                    color: Theme.muted; font.family: Theme.face; font.pixelSize: Theme.px(14)
                }
                delegate: Item {
                    id: hunted
                    required property var modelData
                    required property int index
                    property bool navigable: true
                    function activate() { Theme.keys = true; shell.act("trophy_hunt_open", hunted.index) }
                    width: huntList.width - 10
                    height: hunted.modelData.watch ? 104 : 86
                    activeFocusOnTab: true
                    Keys.onReturnPressed: activate()
                    Keys.onEnterPressed: activate()
                    Accessible.role: Accessible.Button
                    Accessible.name: hunted.modelData.name + ", " + hunted.modelData.game + ", " + hunted.modelData.rare
                    Rectangle { anchors.fill: parent; radius: 12; color: huntArea.containsMouse || hunted.activeFocus ? Qt.rgba(1, 1, 1, 0.07) : "transparent"; Behavior on color { ColorAnimation { duration: Theme.ms(110) } } }
                    MouseArea { id: huntArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { Theme.keys = false; shell.act("trophy_hunt_open", hunted.index) } }
                    Picture { id: huntBadge; x: 12; anchors.verticalCenter: parent.verticalCenter; width: 56; height: 56; radius: 10; source: hunted.modelData.icon || ""; initial: ""; lit: false
                        TrophyCup { visible: (hunted.modelData.icon || "") === ""; anchors.centerIn: parent; grade: hunted.modelData.grade; width: 30; height: 30 } }
                    Column {
                        anchors.left: huntBadge.right; anchors.leftMargin: 16
                        anchors.right: huntTools.left; anchors.rightMargin: 16
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 3
                        Row {
                            width: parent.width
                            spacing: 8
                            TrophyCup { anchors.verticalCenter: parent.verticalCenter; grade: hunted.modelData.grade; width: 16; height: 16 }
                            Text { width: parent.width - 24; elide: Text.ElideRight; text: hunted.modelData.name; color: Theme.text; font.family: Theme.strong; font.pixelSize: Theme.px(16) }
                        }
                        Text { width: parent.width; elide: Text.ElideRight; text: hunted.modelData.game + "  ·  " + hunted.modelData.rare; color: Theme.goldSoft; font.family: Theme.face; font.pixelSize: Theme.px(13) }
                        Text { width: parent.width; elide: Text.ElideRight; maximumLineCount: 1; text: hunted.modelData.detail; color: Theme.muted; font.family: Theme.face; font.pixelSize: Theme.px(14) }
                        Text { visible: !!hunted.modelData.watch; width: parent.width; elide: Text.ElideRight; text: "Watch out: " + hunted.modelData.watch + "."; color: Theme.alert; font.family: Theme.face; font.pixelSize: Theme.px(13) }
                    }
                    Row {
                        id: huntTools
                        anchors.right: parent.right; anchors.rightMargin: 14
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 8
                        PillButton { visible: !!hunted.modelData.watch; width: 118; height: 38; fontSize: 13; text: "Missables"; onClicked: shell.act("trophy_hunt_missable", hunted.index) }
                        GlyphButton { glyph: ""; tip: "Find a guide for this trophy"; onClicked: shell.act("trophy_hunt_guide", hunted.index) }
                    }
                    FocusGlow { on: hunted.activeFocus && Theme.keys; radius: 12 }
                }
            }

            // Every game, the latest trophies first.
            ListView {
                id: titleList
                visible: !page.opened && !page.t.hunting
                anchors.fill: parent
                anchors.margins: 10
                clip: true
                spacing: 4
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { width: 8; policy: ScrollBar.AsNeeded }
                model: page.t.titles || []
                delegate: Item {
                    id: game
                    required property var modelData
                    property bool navigable: true
                    function activate() { Theme.keys = true; shell.act("trophy_open", game.modelData.set) }
                    width: titleList.width - 10
                    height: 92
                    activeFocusOnTab: true
                    Keys.onReturnPressed: activate()
                    Keys.onEnterPressed: activate()
                    Rectangle { anchors.fill: parent; radius: 14; color: gameArea.containsMouse || game.activeFocus ? Qt.rgba(1, 1, 1, 0.07) : "transparent"; Behavior on color { ColorAnimation { duration: Theme.ms(120) } } }
                    MouseArea { id: gameArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { Theme.keys = false; shell.act("trophy_open", game.modelData.set) } }
                    Picture { id: cover; x: 12; anchors.verticalCenter: parent.verticalCenter; width: 68; height: 68; source: game.modelData.icon || ""; initial: game.modelData.initial || "?" }
                    Column {
                        anchors.left: cover.right; anchors.leftMargin: 16
                        anchors.right: progress.left; anchors.rightMargin: 20
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 6
                        Row {
                            width: parent.width
                            spacing: 10
                            Rectangle { anchors.verticalCenter: parent.verticalCenter; width: kind.implicitWidth + 14; height: 20; radius: 6; color: Qt.rgba(1, 1, 1, 0.1); visible: (game.modelData.platform || "") !== ""
                                Text { id: kind; anchors.centerIn: parent; text: game.modelData.platform || ""; color: Theme.muted; font.family: Theme.strong; font.pixelSize: Theme.px(11) } }
                            Text { width: Math.min(implicitWidth, parent.width - 90); elide: Text.ElideRight; text: game.modelData.name; color: Theme.text; font.family: Theme.strong; font.pixelSize: Theme.px(17) }
                            TrophyCup { visible: game.modelData.platinum; anchors.verticalCenter: parent.verticalCenter; grade: "platinum"; width: 18; height: 18 }
                        }
                        Row {
                            spacing: 16
                            Repeater {
                                model: game.modelData.counts || []
                                delegate: Row {
                                    required property var modelData
                                    spacing: 5
                                    TrophyCup { anchors.verticalCenter: parent.verticalCenter; grade: modelData.grade; lit: modelData.count > 0; width: 15; height: 15 }
                                    Text { anchors.verticalCenter: parent.verticalCenter; text: modelData.count + " / " + modelData.of; color: modelData.count > 0 ? Theme.muted : Theme.dim; font.family: Theme.face; font.pixelSize: Theme.px(13) }
                                }
                            }
                            Text { text: game.modelData.when; color: Theme.dim; font.family: Theme.face; font.pixelSize: Theme.px(13) }
                        }
                    }
                    Column {
                        id: progress
                        anchors.right: parent.right; anchors.rightMargin: 18
                        anchors.verticalCenter: parent.verticalCenter
                        width: Math.min(300, game.width * 0.28)
                        spacing: 7
                        Item {
                            width: parent.width; height: 18
                            Text { text: page.t.comparing ? "You" : game.modelData.line; color: Theme.muted; font.family: Theme.face; font.pixelSize: Theme.px(13) }
                            Text { anchors.right: parent.right; text: game.modelData.percent; color: game.modelData.platinum ? "#B0C8E8" : Theme.goldSoft; font.family: Theme.strong; font.pixelSize: Theme.px(15) }
                        }
                        Bar { width: parent.width; share: game.modelData.share; fill: game.modelData.platinum ? "#B0C8E8" : Theme.gold }
                        Item {
                            visible: game.modelData.theirs >= 0
                            width: parent.width; height: 18
                            Text { text: page.t.friendName || ""; color: Theme.muted; font.family: Theme.face; font.pixelSize: Theme.px(13) }
                            Text { anchors.right: parent.right; text: game.modelData.theirsPercent; color: Theme.text; font.family: Theme.strong; font.pixelSize: Theme.px(15) }
                        }
                        Bar { visible: game.modelData.theirs >= 0; width: parent.width; share: Math.max(0, game.modelData.theirs); fill: Qt.rgba(1, 1, 1, 0.6) }
                    }
                    FocusGlow { on: game.activeFocus && Theme.keys; radius: 14 }
                }
            }

            // One game: its trophies, yours and your friend's.
            Item {
                id: gameView
                visible: !!page.opened
                anchors.fill: parent
                Row {
                    id: gameHead
                    x: 22; y: 18
                    width: parent.width - 44
                    spacing: 18
                    Picture { width: 84; height: 84; source: page.opened ? page.opened.icon : ""; initial: page.opened ? page.opened.name.charAt(0).toUpperCase() : "" }
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width - 84 - 18 - (page.sideBySide ? 300 : 0)
                        spacing: 6
                        Text { width: parent.width; elide: Text.ElideRight; text: page.opened ? page.opened.name : ""; color: Theme.text; font.family: Theme.light; font.pixelSize: Theme.px(30) }
                        Row {
                            spacing: 12
                            Text { anchors.verticalCenter: parent.verticalCenter; text: page.opened ? page.opened.line : ""; color: Theme.muted; font.family: Theme.face; font.pixelSize: Theme.px(15) }
                            Bar { anchors.verticalCenter: parent.verticalCenter; width: 180; share: page.opened ? page.opened.share : 0; fill: page.opened && page.opened.platinum ? "#B0C8E8" : Theme.gold }
                        }
                        Text { visible: page.opened && page.opened.theirsLine !== ""; text: page.opened ? page.opened.theirsLine : ""; color: Theme.goldSoft; font.family: Theme.face; font.pixelSize: Theme.px(14) }
                    }
                }
                // Over the dates: whose they are.
                Row {
                    visible: page.sideBySide
                    anchors.right: parent.right; anchors.rightMargin: 38
                    anchors.bottom: rule.top; anchors.bottomMargin: 8
                    Text { width: 150; horizontalAlignment: Text.AlignRight; text: "You"; color: Theme.muted; font.family: Theme.strong; font.pixelSize: Theme.px(14) }
                    Text { width: 150; horizontalAlignment: Text.AlignRight; elide: Text.ElideLeft; text: page.opened ? page.opened.friendName : ""; color: Theme.muted; font.family: Theme.strong; font.pixelSize: Theme.px(14) }
                }
                Rectangle { id: rule; x: 16; y: 120; width: parent.width - 32; height: 1; color: Theme.glassRim }
                Text {
                    visible: !!page.opened && page.opened.loading
                    anchors.centerIn: parent
                    text: "Reading the trophies…"; color: Theme.muted; font.family: Theme.face; font.pixelSize: Theme.px(16)
                }
                ListView {
                    id: trophyList
                    x: 10; y: 128
                    width: parent.width - 20
                    height: parent.height - y - 10
                    clip: true
                    spacing: 2
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { width: 8; policy: ScrollBar.AsNeeded }
                    model: page.opened ? page.opened.rows : []
                    delegate: Item {
                        id: trophy
                        required property var modelData
                        property bool navigable: true
                        function activate() { Theme.keys = true; shell.act("trophy_guide", trophy.modelData.id) }
                        width: trophyList.width - 10
                        height: 78
                        activeFocusOnTab: true
                        Keys.onReturnPressed: activate()
                        Keys.onEnterPressed: activate()
                        Rectangle { anchors.fill: parent; radius: 12; color: trophyArea.containsMouse || trophy.activeFocus ? Qt.rgba(1, 1, 1, 0.07) : "transparent"; Behavior on color { ColorAnimation { duration: Theme.ms(110) } } }
                        MouseArea { id: trophyArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onDoubleClicked: { Theme.keys = false; shell.act("trophy_guide", trophy.modelData.id) } }
                        Picture { id: badge; x: 12; anchors.verticalCenter: parent.verticalCenter; width: 56; height: 56; radius: 10; source: trophy.modelData.icon || ""; initial: ""; lit: trophy.modelData.earned
                            TrophyCup { visible: (trophy.modelData.icon || "") === ""; anchors.centerIn: parent; grade: trophy.modelData.grade; lit: trophy.modelData.earned; width: 30; height: 30 } }
                        Column {
                            anchors.left: badge.right; anchors.leftMargin: 16
                            anchors.right: dates.left; anchors.rightMargin: 16
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 3
                            Row {
                                width: parent.width
                                spacing: 8
                                TrophyCup { anchors.verticalCenter: parent.verticalCenter; grade: trophy.modelData.grade; width: 16; height: 16 }
                                Text { width: parent.width - 24; elide: Text.ElideRight; text: trophy.modelData.name; color: trophy.modelData.earned ? Theme.text : Theme.muted; font.family: Theme.strong; font.pixelSize: Theme.px(16) }
                            }
                            Text { width: parent.width; elide: Text.ElideRight; maximumLineCount: 1; text: trophy.modelData.detail; color: Theme.muted; font.family: Theme.face; font.pixelSize: Theme.px(14) }
                            Text { visible: trophy.modelData.rare !== ""; text: trophy.modelData.rare; color: Theme.dim; font.family: Theme.face; font.pixelSize: Theme.px(12) }
                        }
                        Row {
                            id: dates
                            anchors.right: parent.right; anchors.rightMargin: 18
                            anchors.verticalCenter: parent.verticalCenter
                            Text { width: 150; horizontalAlignment: Text.AlignRight; text: trophy.modelData.when; color: Theme.goldSoft; font.family: Theme.face; font.pixelSize: Theme.px(14) }
                            Text { visible: page.sideBySide; width: 150; horizontalAlignment: Text.AlignRight; text: trophy.modelData.theirs; color: trophy.modelData.theirsEarned ? Theme.text : Theme.dim; font.family: Theme.face; font.pixelSize: Theme.px(14) }
                        }
                        FocusGlow { on: trophy.activeFocus && Theme.keys; radius: 12 }
                    }
                }
            }
        }
    }
}
