import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
import QtQuick.Effects
import QtQuick.Dialogs
import QtCore

// The Friends page: your PSN friends, who is online and what they play, and your PSN messages, as glass panels over PlayBridge's picture.
FocusScope {
    id: page
    property real u: 1
    property real topInset: 0
    property Item frost: null
    property var f: shell.friends || ({})
    readonly property real side: Math.max(48, 64 * u)
    readonly property bool signedIn: f.state === "on"
    readonly property var thread: f.thread || null
    readonly property bool finderOpen: signedIn && !!f.finderOpen
    readonly property var find: f.find || ({})
    // A card over the page (the conversation's options or a new group), held by the shell so Esc closes it; under any card the page waits.
    readonly property string card: signedIn ? f.chatCard || "" : ""
    readonly property bool covered: finderOpen || card !== ""
    // The message the keys or the controller are on, so it keeps the focus when the conversation is put again.
    property string heldMessage: ""
    function savePicture(row) {
        saveDialog.message = row.id
        saveDialog.currentFolder = StandardPaths.writableLocation(StandardPaths.PicturesLocation)
        saveDialog.selectedFile = saveDialog.currentFolder + "/" + (row.saveName || "PSN picture.png")
        saveDialog.open()
    }
    onFinderOpenChanged: if (finderOpen) Qt.callLater(function() { findField.forceActiveFocus(); findField.selectAll() })

    // Signed out: what this page does, and where to sign in.
    Glass {
        id: welcome
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
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: ""; font.family: "Segoe MDL2 Assets"; font.pixelSize: 46; color: Theme.gold }
            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: page.f.state === "signing" ? "Signing in to PSN…" : "Your PSN friends, right here"; color: Theme.text; font.family: Theme.light; font.pixelSize: 34; wrapMode: Text.WordWrap }
            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap; color: Theme.muted; font.family: Theme.face; font.pixelSize: 16
                text: "See who is online and what they play, get told when a friend comes online or opens a game you watch, such as XPS5, and read and answer your PSN messages without picking up the controller." }
            Text { visible: (page.f.problem || "") !== ""; width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap; color: Theme.alert; font.family: Theme.face; font.pixelSize: 15; text: page.f.problem || "" }
            Item { width: 1; height: 6 }
            PillButton { anchors.horizontalCenter: parent.horizontalCenter; width: 240; height: 50; tone: "main"; text: page.f.state === "expired" ? "Sign in again" : "Sign in to PSN"; enabled: page.f.state !== "signing"; onClicked: shell.act("psn_settings", null) }
        }
    }

    Item {
        id: body
        visible: page.signedIn
        // Under a card the page waits, dimmed, out of the keys' and controller's reach.
        enabled: !page.covered
        opacity: page.covered ? 0.3 : 1
        Behavior on opacity { NumberAnimation { duration: Theme.ms(160) } }
        anchors.fill: parent
        anchors.topMargin: page.topInset + 24
        anchors.leftMargin: page.side
        anchors.rightMargin: page.side
        anchors.bottomMargin: 28

        // Left: the friends.
        Item {
            id: left
            width: Math.min(560, Math.max(380, parent.width * 0.42))
            height: parent.height
            Row {
                id: heading
                spacing: 16
                // You stand here as in the top bar: the same words and the same green dot, both PSN's own word for your account.
                Avatar { source: (page.f.me || {}).picture || ""; initial: (((page.f.me || {}).name || "?").charAt(0)).toUpperCase(); tone: (page.f.me || {}).tone || "off"; width: 58; height: 58; anchors.verticalCenter: parent.verticalCenter }
                Column {
                    width: left.width - 74
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2
                    Item {
                        width: parent.width
                        height: Math.max(title.implicitHeight, addFriend.height)
                        Text { id: title; anchors.verticalCenter: parent.verticalCenter; text: "Friends"; color: Theme.text; font.family: Theme.light; font.pixelSize: 40 }
                        PillButton { id: addFriend; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: 142; height: 42; tone: "main"; text: "Add friend"; onClicked: shell.act("friend_find_open", null) }
                    }
                    Row {
                        width: parent.width
                        Text { id: meName; text: ((page.f.me || {}).name || "") + ((page.f.me || {}).name && (page.f.me || {}).line ? "  ·  " : ""); color: Theme.muted; font.family: Theme.face; font.pixelSize: 15 }
                        Text { id: meLine; text: (page.f.me || {}).line || ""; font.family: Theme.face; font.pixelSize: 15
                            color: (page.f.me || {}).tone === "playing" || (page.f.me || {}).tone === "online" ? Theme.online : Theme.muted }
                        Text { width: Math.max(0, parent.width - meName.width - meLine.width); elide: Text.ElideRight; color: Theme.muted; font.family: Theme.face; font.pixelSize: 15
                            text: (page.f.summary || "") !== "" ? "  ·  " + page.f.summary : "" }
                    }
                    Text { visible: text !== ""; width: parent.width; wrapMode: Text.WordWrap; text: (page.f.me || {}).why || ""; color: Theme.dim; font.family: Theme.face; font.pixelSize: 13 }
                }
            }
            Row {
                id: filters
                anchors.top: heading.bottom
                anchors.topMargin: 18
                spacing: 10
                Repeater {
                    model: page.f.filters || []
                    delegate: PillButton {
                        required property string modelData
                        text: modelData
                        tone: "ghost"
                        width: 112; height: 40
                        selected: (page.f.filter || "All") === modelData
                        onClicked: shell.act("friends_filter", modelData)
                    }
                }
                GlyphButton { glyph: ""; tip: "Read again"; onClicked: shell.act("psn_refresh", null) }
            }
            // What went wrong reading PSN, else what came of the last friend change (it stays a minute and a half).
            Note {
                id: notice
                anchors.top: filters.bottom; anchors.topMargin: 10
                width: parent.width
                text: (page.f.problem || "") !== "" ? page.f.problem : (page.f.friendLine || {}).text || ""
                tone: (page.f.problem || "") !== "" ? "error" : (page.f.friendLine || {}).tone || "plain"
            }
            Glass {
                id: friendsPanel
                frost: page.frost
                follow: page.x + page.opacity + friendList.contentY
                anchors.top: notice.visible ? notice.bottom : filters.bottom
                anchors.topMargin: notice.visible ? 12 : 18
                anchors.bottom: parent.bottom
                width: parent.width
                Text {
                    visible: (page.f.empty || "") !== ""
                    anchors.centerIn: parent
                    width: parent.width - 60
                    horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                    text: page.f.empty || ""; color: Theme.muted; font.family: Theme.face; font.pixelSize: 16
                }
                ListView {
                    id: friendList
                    anchors.fill: parent
                    anchors.margins: 10
                    clip: true
                    spacing: 4
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { width: 8; policy: ScrollBar.AsNeeded }
                    model: page.f.friends || []
                    // A header that grows (the requests arrive after the friends) would grow up out of sight: until the player
                    // scrolls the list, it starts at the top.
                    property bool moved: false
                    onMovementStarted: moved = true
                    onModelChanged: if (!moved) Qt.callLater(positionViewAtBeginning)
                    // Above the friends: the friend requests, received ones first, each with what can be done about it.
                    header: Column {
                        width: friendList.width - 10
                        onHeightChanged: if (!friendList.moved) Qt.callLater(friendList.positionViewAtBeginning)
                        readonly property var asked: page.f.requests || []
                        Text { visible: parent.asked.length > 0; x: 12; height: 34; verticalAlignment: Text.AlignVCenter; text: "Friend requests"; color: Theme.muted; font.family: Theme.strong; font.pixelSize: 14 }
                        Repeater {
                            model: parent.asked
                            delegate: Item {
                                id: request
                                required property var modelData
                                readonly property bool received: modelData.kind === "received"
                                width: parent.width
                                height: 72
                                Rectangle { anchors.fill: parent; radius: 14; color: Qt.rgba(0.83, 0.69, 0.22, request.received ? 0.09 : 0.04) }
                                Avatar { id: askerFace; x: 12; anchors.verticalCenter: parent.verticalCenter; source: request.modelData.picture || ""; initial: request.modelData.initial || "?"; tone: "off" }
                                Column {
                                    anchors.left: askerFace.right; anchors.leftMargin: 14
                                    anchors.right: answers.left; anchors.rightMargin: 10
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 2
                                    Text { width: parent.width; elide: Text.ElideRight; text: request.modelData.name; color: request.modelData.known ? Theme.text : Theme.dim; font.family: Theme.strong; font.pixelSize: 17 }
                                    Text { width: parent.width; elide: Text.ElideRight; text: request.modelData.busy ? "Asking PSN…" : request.modelData.line; color: request.received ? Theme.goldSoft : Theme.dim; font.family: Theme.face; font.pixelSize: 14 }
                                }
                                Row {
                                    id: answers
                                    anchors.right: parent.right; anchors.rightMargin: 8
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 6
                                    PillButton { visible: request.received; width: 96; height: 40; tone: "main"; text: "Accept"; enabled: !request.modelData.busy; onClicked: shell.act("friend_accept", request.modelData.id) }
                                    PillButton { visible: request.received; width: 96; height: 40; text: "Decline"; enabled: !request.modelData.busy; onClicked: shell.act("friend_decline", request.modelData.id) }
                                    PillButton { visible: !request.received; width: 112; height: 40; text: "Take back"; enabled: !request.modelData.busy; onClicked: shell.act("friend_cancel", request.modelData.id) }
                                }
                            }
                        }
                        Note { x: 12; width: parent.width - 24; topPadding: 6; bottomPadding: 6; tone: "error"; text: page.f.requestsProblem || "" }
                        Text { visible: parent.asked.length > 0 && (page.f.friends || []).length > 0; x: 12; height: 40; verticalAlignment: Text.AlignBottom; bottomPadding: 6; text: "Friends"; color: Theme.muted; font.family: Theme.strong; font.pixelSize: 14 }
                    }
                    delegate: Item {
                        id: row
                        required property var modelData
                        property bool navigable: enabled
                        function activate() { Theme.keys = true; shell.act("friend_message", row.modelData.id) }
                        width: friendList.width - 10
                        height: 76
                        activeFocusOnTab: true
                        Keys.onReturnPressed: activate()
                        Keys.onEnterPressed: activate()
                        Rectangle { anchors.fill: parent; radius: 14; color: rowArea.containsMouse || row.activeFocus ? Qt.rgba(1, 1, 1, 0.07) : "transparent"; Behavior on color { ColorAnimation { duration: Theme.ms(120) } } }
                        MouseArea { id: rowArea; anchors.fill: parent; hoverEnabled: true }
                        Avatar { id: face; x: 12; anchors.verticalCenter: parent.verticalCenter; source: row.modelData.picture || ""; initial: row.modelData.initial || "?"; tone: row.modelData.tone || "off" }
                        Column {
                            anchors.left: face.right; anchors.leftMargin: 14
                            anchors.right: actions.left; anchors.rightMargin: 10
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2
                            Text { width: parent.width; elide: Text.ElideRight; text: row.modelData.name; color: row.modelData.known ? Theme.text : Theme.dim; font.family: Theme.strong; font.pixelSize: 17 }
                            Text { width: parent.width; elide: Text.ElideRight; text: row.modelData.line; font.family: Theme.face; font.pixelSize: 14
                                color: row.modelData.tone === "playing" || row.modelData.tone === "online" ? Theme.online : Theme.dim }
                        }
                        Row {
                            id: actions
                            anchors.right: parent.right; anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 6
                            // Play this too: the game the friend plays, started on the PS5, or found in the Store when it is not there.
                            GlyphButton {
                                readonly property var too: row.modelData.playToo || null
                                visible: !!too
                                enabled: !!too && too.kind !== "running"
                                glyph: too && too.kind === "store" ? "" : ""
                                lit: !!too && too.kind !== "store"
                                tip: too ? too.tip : ""
                                onClicked: shell.act("friend_play", row.modelData.id)
                            }
                            GlyphButton { glyph: row.modelData.favourite ? "" : ""; lit: row.modelData.favourite; tip: row.modelData.favourite ? "Remove from favourites" : "Add to favourites"; onClicked: shell.act("friend_favourite", row.modelData.id) }
                            GlyphButton { tip: "Compare trophies"; onClicked: shell.act("friend_trophies", row.modelData.id)
                                TrophyCup { anchors.centerIn: parent; width: 18; height: 18; colour: Theme.text } }
                            PillButton { width: 104; height: 42; text: "Message"; onClicked: shell.act("friend_message", row.modelData.id) }
                        }
                        FocusGlow { on: row.activeFocus; radius: 9 }
                    }
                }
            }
        }

        // Right: the messages, the list of conversations or the one that is open.
        Glass {
            id: chat
            frost: page.frost
            follow: page.x + page.opacity
            anchors.left: left.right
            anchors.leftMargin: 24
            anchors.right: parent.right
            height: parent.height
            // A gold edge along the top, brighter while a conversation is open.
            Rectangle {
                x: 28; width: parent.width - 56; height: 2; radius: 1
                opacity: page.thread ? 0.85 : 0.35
                Behavior on opacity { NumberAnimation { duration: Theme.ms(220) } }
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.5; color: Theme.gold }
                    GradientStop { position: 1.0; color: "transparent" }
                }
            }
            Item {
                id: chatHead
                x: 24; y: 18
                width: parent.width - 48
                height: 56
                GlyphButton { id: back; visible: !!page.thread; navigable: visible && enabled; glyph: ""; tip: "All conversations · Esc"; onClicked: shell.act("psn_chat_close", null) }
                Faces { id: headFaces; visible: !!page.thread; anchors.left: back.right; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter; size: 46; people: page.thread ? page.thread.people || [] : [] }
                Column {
                    anchors.left: page.thread ? headFaces.right : parent.left; anchors.leftMargin: page.thread ? 14 : 0
                    anchors.right: headTools.left; anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    Text { width: parent.width; elide: Text.ElideRight; text: page.thread ? page.thread.name : "Messages"; color: Theme.text; font.family: Theme.light; font.pixelSize: page.thread ? 26 : 30 }
                    Text {
                        visible: !!page.thread && text !== ""
                        width: parent.width; elide: Text.ElideRight
                        text: page.thread ? page.thread.about || "" : ""
                        color: page.thread && (page.thread.aboutTone === "online" || page.thread.aboutTone === "playing") ? Theme.online : Theme.dim
                        font.family: Theme.face; font.pixelSize: 13
                    }
                }
                Row {
                    id: headTools
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    spacing: 8
                    GlyphButton {
                        visible: !!page.thread; navigable: visible && enabled; enabled: !page.f.changing
                        lit: !!page.thread && !!page.thread.favourite
                        glyph: lit ? "" : ""; tip: lit ? "A favourite: pinned to the top. Select to unpin" : "Make it a favourite"
                        onClicked: shell.act("psn_chat_favourite", null)
                    }
                    GlyphButton {
                        visible: !!page.thread; navigable: visible && enabled; enabled: !page.f.changing
                        lit: !!page.thread && !!page.thread.muted
                        glyph: lit ? "" : ""; tip: lit ? "Muted: no alerts. Select to hear them again" : "Mute its alerts"
                        onClicked: shell.act("psn_mute", null)
                    }
                    GlyphButton { visible: !!page.thread; navigable: visible && enabled; glyph: ""; tip: "People and options"; onClicked: shell.act("psn_options", null) }
                    PillButton { visible: !page.thread; width: 140; height: 40; tone: "ghost"; text: "New group"; onClicked: shell.act("psn_group_new", null) }
                }
            }
            Rectangle { id: headLine; anchors.top: chatHead.bottom; anchors.topMargin: 12; x: 24; width: parent.width - 48; height: 1; color: Qt.rgba(1, 1, 1, 0.1) }

            // The conversations, favourites first.
            Note {
                id: listNote
                visible: !page.thread && text !== ""
                anchors.top: headLine.bottom; anchors.topMargin: 12
                x: 24; width: parent.width - 48
                text: page.f.chatLine ? page.f.chatLine.text : ""
                tone: page.f.chatLine ? page.f.chatLine.tone : "plain"
            }
            Text {
                visible: !page.thread && (page.f.groups || []).length === 0
                anchors.centerIn: parent
                width: parent.width - 80
                horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                text: "No conversations yet. Select Message beside a friend to start one, or New group to talk to several at once."
                color: Theme.muted; font.family: Theme.face; font.pixelSize: 16
            }
            ListView {
                id: groupList
                visible: !page.thread
                anchors.top: listNote.visible ? listNote.bottom : chatHead.bottom; anchors.topMargin: listNote.visible ? 10 : 26
                anchors.bottom: parent.bottom; anchors.bottomMargin: 14
                x: 12; width: parent.width - 24
                clip: true
                spacing: 4
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { width: 8; policy: ScrollBar.AsNeeded }
                model: page.f.groups || []
                delegate: Item {
                    id: conversation
                    required property var modelData
                    property bool navigable: enabled
                    function activate() { Theme.keys = true; shell.act("psn_chat", conversation.modelData.id) }
                    readonly property bool hot: groupArea.containsMouse || activeFocus
                    width: groupList.width - 10
                    height: 76
                    activeFocusOnTab: true
                    Keys.onReturnPressed: activate()
                    Keys.onEnterPressed: activate()
                    Rectangle {
                        anchors.fill: parent; radius: 16
                        color: conversation.hot ? Qt.rgba(1, 1, 1, 0.075) : conversation.modelData.unread ? Qt.rgba(0.83, 0.69, 0.22, 0.07) : "transparent"
                        border.width: conversation.modelData.unread ? 1 : 0
                        border.color: Qt.rgba(0.83, 0.69, 0.22, 0.28)
                        Behavior on color { ColorAnimation { duration: Theme.ms(120) } }
                    }
                    // A new message: a lit gold edge at the left.
                    Rectangle {
                        visible: conversation.modelData.unread
                        x: 1; width: 3; radius: 1.5
                        height: parent.height - 30; anchors.verticalCenter: parent.verticalCenter
                        color: Theme.gold
                        layer.enabled: visible
                        layer.effect: MultiEffect { shadowEnabled: true; shadowColor: Theme.gold; shadowBlur: 0.7; shadowOpacity: 0.9; blurMax: 12 }
                    }
                    MouseArea { id: groupArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { Theme.keys = false; shell.act("psn_chat", conversation.modelData.id) } }
                    Faces { id: rowFaces; x: 14; anchors.verticalCenter: parent.verticalCenter; size: 48; people: conversation.modelData.faces || []; more: conversation.modelData.more || 0 }
                    Column {
                        anchors.left: rowFaces.right; anchors.leftMargin: 14
                        anchors.right: rowSide.left; anchors.rightMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 3
                        Row {
                            width: parent.width
                            spacing: 6
                            Text { id: rowStar; visible: conversation.modelData.favourite; anchors.verticalCenter: parent.verticalCenter; text: ""; font.family: "Segoe MDL2 Assets"; font.pixelSize: 12; color: Theme.gold }
                            Text {
                                width: Math.min(implicitWidth, parent.width - (rowStar.visible ? rowStar.width + 6 : 0) - (rowMute.visible ? rowMute.width + 6 : 0))
                                elide: Text.ElideRight
                                text: conversation.modelData.name
                                color: Theme.text; font.family: conversation.modelData.unread ? Theme.strong : Theme.face; font.pixelSize: 17
                            }
                            Text { id: rowMute; visible: conversation.modelData.muted; anchors.verticalCenter: parent.verticalCenter; text: ""; font.family: "Segoe MDL2 Assets"; font.pixelSize: 12; color: Theme.dim }
                        }
                        Text { width: parent.width; elide: Text.ElideRight; text: conversation.modelData.last || " "; color: conversation.modelData.unread ? Theme.text : Theme.dim; font.family: Theme.face; font.pixelSize: 14 }
                    }
                    Column {
                        id: rowSide
                        anchors.right: parent.right; anchors.rightMargin: 14
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 8
                        Text { anchors.right: parent.right; text: conversation.modelData.when; color: conversation.modelData.unread ? Theme.goldSoft : Theme.dim; font.family: Theme.face; font.pixelSize: 13 }
                        // The new-message dot breathes while the page is moving.
                        Rectangle {
                            anchors.right: parent.right
                            width: 10; height: 10; radius: 5
                            color: Theme.gold
                            opacity: conversation.modelData.unread ? 1 : 0
                            layer.enabled: conversation.modelData.unread
                            layer.effect: MultiEffect { shadowEnabled: true; shadowColor: Theme.gold; shadowBlur: 0.8; shadowOpacity: 1; blurMax: 16 }
                            SequentialAnimation on scale {
                                running: conversation.modelData.unread && Theme.motion
                                loops: Animation.Infinite
                                NumberAnimation { to: 1.3; duration: 900; easing.type: Easing.InOutSine }
                                NumberAnimation { to: 1.0; duration: 900; easing.type: Easing.InOutSine }
                            }
                        }
                    }
                    FocusGlow { on: conversation.activeFocus; radius: 11 }
                }
            }

            // The open conversation: the newest message at the bottom, over the box to write in.
            Text {
                visible: !!page.thread && page.thread.loading
                anchors.centerIn: parent
                text: "Loading the conversation…"; color: Theme.muted; font.family: Theme.face; font.pixelSize: 16
            }
            ListView {
                id: messageList
                visible: !!page.thread
                anchors.top: chatHead.bottom; anchors.topMargin: 26
                anchors.bottom: outbox.top; anchors.bottomMargin: 12
                x: 20; width: parent.width - 40
                clip: true
                spacing: 6
                boundsBehavior: Flickable.StopAtBounds
                // Only the player moving the list (dragging, the wheel, the scroll bar) says whether it stays at the newest message: pictures
                // above that finish loading move the list by themselves and must not make it stop following.
                ScrollBar.vertical: ScrollBar { width: 8; policy: ScrollBar.AsNeeded; onPressedChanged: messageList.following = !pressed && messageList.atYEnd }
                onMovementStarted: following = false
                onMovementEnded: following = atYEnd
                // The page is put again whenever something on it changes (a picture arriving, the times every half minute): the messages
                // are made again only when they changed, the view stays at the newest message while it was there, else where the player
                // scrolled to, and the message the keys or the controller were on keeps the focus. A conversation opens at its end.
                readonly property var rows: page.thread ? page.thread.messages : []
                property bool following: true
                property string shownThread: ""
                property string shownRows: ""
                function settle() {
                    var opened = page.thread ? page.thread.id : ""
                    if (opened !== shownThread) { shownThread = opened; following = true; shownRows = "" }
                    var text = JSON.stringify(rows)
                    if (text === shownRows) return
                    shownRows = text
                    var at = contentY, view = messageList, keep = page.heldMessage
                    model = rows
                    Qt.callLater(function() {
                        if (view.following) view.positionViewAtEnd(); else view.contentY = at
                        if (keep !== "") view.refocus(keep)
                    })
                }
                function refocus(key) {
                    for (var i = 0; i < rows.length; i++) {
                        if (rows[i].id !== key) continue
                        var item = itemAtIndex(i)
                        if (item && item.visible) item.focusBubble()
                        return
                    }
                }
                onRowsChanged: settle()
                Component.onCompleted: settle()
                onContentHeightChanged: if (following && !moving) Qt.callLater(positionViewAtEnd)
                onHeightChanged: if (following && !moving) Qt.callLater(positionViewAtEnd)
                delegate: FocusScope {
                    id: message
                    required property var modelData
                    readonly property string kind: modelData.kind || "text"
                    readonly property bool note: kind === "note"
                    readonly property bool mine: !!modelData.mine
                    readonly property bool pictured: kind === "picture" || kind === "gif" || kind === "sticker"
                    readonly property bool recorded: kind === "voice" || kind === "video"
                    readonly property bool shown: pictured && modelData.state === "ready"
                    readonly property bool picking: (page.f.picking || "") !== "" && page.f.picking === modelData.id
                    // Under the pointer or in the keys' focus, the message shows what can be done to it.
                    readonly property bool engaged: !note && !modelData.busy && (hover.hovered || activeFocus || picking)
                    readonly property real most: width * 0.78
                    readonly property var reactions: modelData.reactions || []
                    property real trayRoom: picking ? tray.height + 10 : 0
                    Behavior on trayRoom { NumberAnimation { duration: Theme.ms(180); easing.type: Easing.OutCubic } }
                    function focusBubble() { bubble.forceActiveFocus() }
                    width: messageList.width - 10
                    height: note ? groupNote.implicitHeight + 14 : bubble.y + bubble.height + (reactionRow.visible ? reactionRow.height + 6 : 0) + trayRoom + 2
                    onActiveFocusChanged: {
                        if (activeFocus) page.heldMessage = modelData.id
                        else if (page.heldMessage === modelData.id) page.heldMessage = ""
                    }
                    HoverHandler { id: hover }
                    // The group's own words (made, someone added, a message deleted): in the middle, no bubble, nobody's.
                    Text {
                        id: groupNote
                        visible: message.note
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 7
                        width: Math.min(implicitWidth, parent.width - 40)
                        horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap; textFormat: Text.PlainText
                        text: message.modelData.text + (message.modelData.when ? "  ·  " + message.modelData.when : "")
                        color: Theme.dim; font.family: Theme.face; font.pixelSize: 13; font.italic: true
                    }
                    Text { id: who; visible: !message.note && message.modelData.first && !message.mine; text: message.modelData.who; color: Theme.dim; font.family: Theme.face; font.pixelSize: 13; x: 14 }
                    Rectangle {
                        id: bubble
                        visible: !message.note
                        // Enter or the controller's button: a picture opens whole, a voice message plays, words open the reactions.
                        property bool navigable: visible && enabled
                        function activate() {
                            Theme.keys = true
                            if (message.shown) shell.act("psn_picture_open", message.modelData.id)
                            else if (message.recorded) shell.act("psn_media", message.modelData.id)
                            else if (message.modelData.canReact) shell.act("psn_react_open", message.modelData.id)
                        }
                        activeFocusOnTab: visible
                        Keys.onReturnPressed: activate()
                        Keys.onEnterPressed: activate()
                        y: who.visible ? who.height + 4 : 0
                        width: Math.min(message.most, Math.max(content.implicitWidth, stamp.implicitWidth) + 28)
                        height: content.implicitHeight + stamp.implicitHeight + 22
                        anchors.right: message.mine ? parent.right : undefined
                        radius: 18
                        opacity: message.modelData.busy ? 0.5 : 1
                        Behavior on opacity { NumberAnimation { duration: Theme.ms(160) } }
                        // A sticker stands on its own, as in the PlayStation App.
                        readonly property bool bare: message.kind === "sticker" && message.shown
                        color: bare ? "transparent" : message.mine ? Qt.rgba(0.83, 0.69, 0.22, message.engaged ? 0.32 : 0.26) : Qt.rgba(1, 1, 1, message.engaged ? 0.12 : 0.09)
                        border.width: bare ? 0 : 1
                        border.color: message.mine ? (message.engaged ? Theme.gold : Qt.rgba(0.83, 0.69, 0.22, 0.5)) : Qt.rgba(1, 1, 1, message.engaged ? 0.26 : 0.12)
                        Behavior on color { ColorAnimation { duration: Theme.ms(140) } }
                        Behavior on border.color { ColorAnimation { duration: Theme.ms(140) } }
                        layer.enabled: message.engaged && !bare
                        layer.effect: MultiEffect { shadowEnabled: true; shadowColor: message.mine ? Theme.gold : "#000000"; shadowOpacity: message.mine ? 0.4 : 0.6; shadowBlur: 0.7; shadowVerticalOffset: message.mine ? 0 : 3; blurMax: 22 }
                        // Light from above, as on the glass panels.
                        Rectangle {
                            visible: !bubble.bare
                            anchors.fill: parent; radius: parent.radius
                            gradient: Gradient {
                                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.08) }
                                GradientStop { position: 0.55; color: Qt.rgba(1, 1, 1, 0.0) }
                            }
                        }
                        Column {
                            id: content
                            x: 14; y: 10
                            spacing: 8
                            // A picture, GIF or sticker, as large as the bubble allows: selected, it opens whole in Windows' viewer.
                            Item {
                                id: shot
                                visible: message.shown
                                readonly property var picture: message.kind === "gif" ? moving : still
                                readonly property real side: message.kind === "sticker" ? 160 : Math.min(320, message.most - 28)
                                readonly property real fit: Math.min(1, side / Math.max(1, picture.implicitWidth), side / Math.max(1, picture.implicitHeight))
                                width: visible ? Math.max(24, picture.implicitWidth * fit) : 0
                                height: visible ? Math.max(24, picture.implicitHeight * fit) : 0
                                Image {
                                    id: still
                                    visible: message.kind !== "gif"
                                    anchors.fill: parent
                                    source: message.kind !== "gif" && message.shown ? message.modelData.image : ""
                                    sourceSize.width: 640
                                    asynchronous: true
                                    fillMode: Image.PreserveAspectFit
                                    smooth: true; mipmap: true
                                }
                                AnimatedImage {
                                    id: moving
                                    visible: message.kind === "gif"
                                    anchors.fill: parent
                                    source: message.kind === "gif" && message.shown ? message.modelData.image : ""
                                    fillMode: Image.PreserveAspectFit
                                    playing: visible && Theme.motion
                                    smooth: true
                                }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: { Theme.keys = false; shell.act("psn_picture_open", message.modelData.id) } }
                            }
                            // A voice message or video: played here (a voice message) or opened in Windows' player (a video).
                            Row {
                                visible: message.recorded
                                spacing: 12
                                PillButton {
                                    width: 112; height: 40
                                    tone: message.modelData.state === "playing" ? "main" : "plain"
                                    text: message.modelData.state === "getting" ? "Getting…" : message.modelData.state === "playing" ? "Stop" : message.kind === "voice" ? "Play" : "Open"
                                    enabled: message.modelData.state !== "getting"
                                    onClicked: shell.act("psn_media", message.modelData.id)
                                }
                                Text { anchors.verticalCenter: parent.verticalCenter; text: message.modelData.text; color: Theme.muted; font.family: Theme.face; font.pixelSize: 15 }
                            }
                            // Words: a message's own, the words under a picture, or why a picture is not there (smaller, muted).
                            Text {
                                id: words
                                visible: !message.recorded && text !== ""
                                width: Math.min(implicitWidth, message.most - 28)
                                text: message.modelData.text
                                wrapMode: Text.Wrap; textFormat: Text.PlainText
                                color: message.pictured && !message.shown ? Theme.muted : Theme.text
                                font.family: Theme.face; font.pixelSize: message.pictured && !message.shown ? 14 : 16
                            }
                        }
                        Text {
                            id: stamp
                            anchors.right: parent.right; anchors.rightMargin: 14
                            anchors.top: content.bottom; anchors.topMargin: 3
                            text: message.modelData.busy ? "Telling PSN…" : message.modelData.when
                            color: message.modelData.busy ? Theme.goldSoft : Theme.dim
                            font.family: Theme.face; font.pixelSize: 11
                        }
                    }
                    Item { x: bubble.x; y: bubble.y; width: bubble.width; height: bubble.height; visible: bubble.visible; FocusGlow { on: bubble.activeFocus; radius: 13 } }
                    // What can be done to the message, beside it (over its top corner when the message is wide): react, copy, save, delete
                    // for everyone (the player's own, for 10 minutes), take it off this PC.
                    Rectangle {
                        id: strip
                        readonly property bool beside: message.width - bubble.width - 14 >= width
                        visible: opacity > 0
                        opacity: message.engaged ? 1 : 0
                        Behavior on opacity { NumberAnimation { duration: Theme.ms(140) } }
                        z: 3
                        width: tools.implicitWidth + 12
                        height: tools.implicitHeight + 10
                        radius: height / 2
                        x: message.mine ? (beside ? bubble.x - width - 10 : bubble.x + 10) : (beside ? bubble.x + bubble.width + 10 : bubble.x + bubble.width - width - 10)
                        y: beside ? bubble.y + Math.max(0, (Math.min(bubble.height, 64) - height) / 2) : Math.max(0, bubble.y - height / 2)
                        color: Qt.rgba(0.06, 0.065, 0.09, 0.94)
                        border.width: 1; border.color: Qt.rgba(0.83, 0.69, 0.22, 0.42)
                        transform: Translate { x: message.engaged ? 0 : message.mine ? 8 : -8; Behavior on x { NumberAnimation { duration: Theme.ms(160); easing.type: Easing.OutCubic } } }
                        Row {
                            id: tools
                            anchors.centerIn: parent
                            spacing: 4
                            GlyphButton { u: 0.76; visible: !!message.modelData.canReact; navigable: strip.visible && visible && enabled; enabled: !page.f.changing; lit: message.picking; glyph: ""; tip: "React"; onClicked: shell.act("psn_react_open", message.modelData.id) }
                            GlyphButton { u: 0.76; visible: !!message.modelData.canCopy; navigable: strip.visible && visible && enabled; glyph: ""; tip: message.kind === "text" ? "Copy the words" : "Copy the picture"; onClicked: shell.act("psn_copy", message.modelData.id) }
                            GlyphButton { u: 0.76; visible: !!message.modelData.canSave; navigable: strip.visible && visible && enabled; glyph: ""; tip: "Save the picture"; onClicked: page.savePicture(message.modelData) }
                            GlyphButton { u: 0.76; visible: !!message.modelData.canDelete; navigable: strip.visible && visible && enabled; enabled: !page.f.changing; danger: true; glyph: ""; tip: message.modelData.deleteTip || "Delete for everyone"; onClicked: shell.act("psn_delete", message.modelData.id) }
                            GlyphButton { u: 0.76; visible: !!message.modelData.canHide; navigable: strip.visible && visible && enabled; glyph: ""; tip: "Remove from this PC"; onClicked: shell.act("psn_hide", message.modelData.id) }
                        }
                    }
                    // The reactions on it, the most given first; the player's own glows gold. Selecting one gives it, or takes yours back.
                    Flow {
                        id: reactionRow
                        visible: message.reactions.length > 0
                        y: bubble.y + bubble.height + 6
                        x: message.mine ? parent.width - width : 6
                        width: Math.min(message.most, implicitWidth)
                        spacing: 6
                        layoutDirection: message.mine ? Qt.RightToLeft : Qt.LeftToRight
                        Repeater {
                            model: message.reactions
                            delegate: Rectangle {
                                id: given
                                required property var modelData
                                readonly property bool hot: givenArea.containsMouse
                                width: givenRow.implicitWidth + 20; height: 30; radius: 15
                                color: modelData.mine ? Qt.rgba(0.83, 0.69, 0.22, hot ? 0.36 : 0.24) : Qt.rgba(1, 1, 1, hot ? 0.15 : 0.08)
                                border.width: 1
                                border.color: modelData.mine ? Theme.gold : Qt.rgba(1, 1, 1, hot ? 0.3 : 0.14)
                                scale: givenArea.pressed ? 0.92 : hot ? 1.08 : 1
                                Behavior on scale { NumberAnimation { duration: Theme.ms(160); easing.type: Easing.OutBack } }
                                Behavior on color { ColorAnimation { duration: Theme.ms(120) } }
                                layer.enabled: modelData.mine
                                layer.effect: MultiEffect { shadowEnabled: true; shadowColor: Theme.gold; shadowOpacity: 0.45; shadowBlur: 0.6; blurMax: 14 }
                                Row {
                                    id: givenRow
                                    anchors.centerIn: parent
                                    spacing: 5
                                    Text { visible: given.modelData.emoji !== ""; anchors.verticalCenter: parent.verticalCenter; text: given.modelData.emoji; font.family: "Segoe UI Emoji"; font.pixelSize: 17 }
                                    Image { visible: given.modelData.emoji === ""; anchors.verticalCenter: parent.verticalCenter; width: 20; height: 20; source: given.modelData.emoji === "" ? given.modelData.picture : ""; sourceSize: Qt.size(40, 40); fillMode: Image.PreserveAspectFit; asynchronous: true }
                                    Text { visible: given.modelData.count > 1; anchors.verticalCenter: parent.verticalCenter; text: given.modelData.count; color: given.modelData.mine ? Theme.goldSoft : Theme.muted; font.family: Theme.strong; font.pixelSize: 12 }
                                }
                                MouseArea {
                                    id: givenArea
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    enabled: !page.f.changing
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: { Theme.keys = false; shell.act("psn_react", [message.modelData.id, given.modelData.id]) }
                                }
                            }
                        }
                    }
                    // The reactions PSN offers, opened under the message: each one grows under the pointer; the one you gave is lit.
                    Rectangle {
                        id: tray
                        readonly property var kinds: page.thread ? page.thread.reactionKinds || [] : []
                        visible: opacity > 0
                        opacity: message.picking ? 1 : 0
                        scale: message.picking ? 1 : 0.86
                        transformOrigin: message.mine ? Item.TopRight : Item.TopLeft
                        Behavior on opacity { NumberAnimation { duration: Theme.ms(160) } }
                        Behavior on scale { NumberAnimation { duration: Theme.ms(240); easing.type: Easing.OutBack } }
                        z: 4
                        y: (reactionRow.visible ? reactionRow.y + reactionRow.height : bubble.y + bubble.height) + 8
                        x: message.mine ? parent.width - width : 0
                        width: Math.min(parent.width, trayRow.implicitWidth + 20)
                        height: 58
                        radius: 29
                        color: Qt.rgba(0.06, 0.065, 0.09, 0.96)
                        border.width: 1; border.color: Qt.rgba(0.83, 0.69, 0.22, 0.55)
                        layer.enabled: visible
                        layer.effect: MultiEffect { shadowEnabled: true; shadowColor: Theme.gold; shadowOpacity: 0.3; shadowBlur: 0.9; blurMax: 26 }
                        Row {
                            id: trayRow
                            anchors.centerIn: parent
                            spacing: 2
                            Repeater {
                                model: tray.kinds
                                delegate: Item {
                                    id: kind
                                    required property var modelData
                                    required property int index
                                    readonly property bool given: message.reactions.some(function(r) { return r.mine && r.id === kind.modelData.id })
                                    readonly property bool hot: kindArea.containsMouse || activeFocus
                                    property bool navigable: tray.visible && message.picking
                                    function activate() { Theme.keys = true; shell.act("psn_react", [message.modelData.id, kind.modelData.id]) }
                                    // Each one pops in after the one before it.
                                    property real pop: message.picking ? 1 : 0
                                    Behavior on pop { SequentialAnimation { PauseAnimation { duration: Theme.ms(kind.index * 22) } NumberAnimation { duration: Theme.ms(220); easing.type: Easing.OutBack } } }
                                    width: 46; height: 46
                                    activeFocusOnTab: navigable
                                    Keys.onReturnPressed: activate()
                                    Keys.onEnterPressed: activate()
                                    Rectangle {
                                        anchors.centerIn: parent
                                        width: 42; height: 42; radius: 21
                                        color: kind.given ? Qt.rgba(0.83, 0.69, 0.22, 0.3) : kind.hot ? Qt.rgba(1, 1, 1, 0.12) : "transparent"
                                        border.width: kind.given || kind.activeFocus ? 1.5 : 0
                                        border.color: Theme.gold
                                        Behavior on color { ColorAnimation { duration: Theme.ms(120) } }
                                    }
                                    Item {
                                        anchors.centerIn: parent
                                        width: 30; height: 30
                                        scale: kind.pop * (kind.hot ? 1.38 : 1)
                                        Behavior on scale { enabled: kind.pop === 1; NumberAnimation { duration: Theme.ms(170); easing.type: Easing.OutBack } }
                                        Text { visible: kind.modelData.emoji !== ""; anchors.centerIn: parent; text: kind.modelData.emoji; font.family: "Segoe UI Emoji"; font.pixelSize: 24 }
                                        Image { visible: kind.modelData.emoji === ""; anchors.fill: parent; source: kind.modelData.emoji === "" ? kind.modelData.picture : ""; sourceSize: Qt.size(60, 60); fillMode: Image.PreserveAspectFit; asynchronous: true }
                                    }
                                    MouseArea { id: kindArea; anchors.fill: parent; hoverEnabled: true; enabled: !page.f.changing; cursorShape: Qt.PointingHandCursor; onClicked: { Theme.keys = false; shell.act("psn_react", [message.modelData.id, kind.modelData.id]) } }
                                }
                            }
                            Text {
                                visible: tray.kinds.length === 0
                                anchors.verticalCenter: parent.verticalCenter
                                leftPadding: 10; rightPadding: 6
                                text: page.thread && page.thread.reactionsReady ? "PSN offers no reactions right now." : "Getting the reactions from PSN…"
                                color: Theme.muted; font.family: Theme.face; font.pixelSize: 14
                            }
                            GlyphButton { u: 0.7; navigable: tray.visible && message.picking; glyph: ""; tip: "Close · Esc"; onClicked: shell.act("psn_react_close", null) }
                        }
                    }
                }
            }
            // Above the box to write in: what came of the last change or picture sent, and the picture waiting to go (Esc takes it off).
            Column {
                id: outbox
                visible: !!page.thread
                anchors.bottom: writer.top; anchors.bottomMargin: waiting.visible || sendNote.visible || chatNote.visible ? 10 : 0
                x: 20; width: parent.width - 40
                spacing: 8
                Note { id: chatNote; text: page.thread && page.thread.chatLine ? page.thread.chatLine.text : ""; tone: page.thread && page.thread.chatLine ? page.thread.chatLine.tone : "plain" }
                Note { id: sendNote; text: page.thread && page.thread.sendLine ? page.thread.sendLine.text : ""; tone: page.thread && page.thread.sendLine ? page.thread.sendLine.tone : "plain" }
                Rectangle {
                    id: waiting
                    visible: !!page.f.outgoing
                    width: parent.width; height: visible ? 84 : 0
                    radius: 14
                    color: Qt.rgba(1, 1, 1, 0.06)
                    border.width: 1; border.color: Qt.rgba(0.83, 0.69, 0.22, 0.45)
                    Image {
                        id: waitingShot
                        x: 10; anchors.verticalCenter: parent.verticalCenter
                        width: 112; height: 64
                        fillMode: Image.PreserveAspectFit
                        source: (page.f.outgoing || {}).image || ""
                        sourceSize.height: 128
                        asynchronous: true
                    }
                    Column {
                        anchors.left: waitingShot.right; anchors.leftMargin: 14
                        anchors.right: takeOff.left; anchors.rightMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2
                        Text { width: parent.width; elide: Text.ElideMiddle; text: (page.f.outgoing || {}).name || ""; color: Theme.text; font.family: Theme.strong; font.pixelSize: 15 }
                        Text { width: parent.width; wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight
                            text: waitingShot.status === Image.Error ? "PlayBridge cannot show this file. It may not be a picture." : "Select Send. Words you write go under it."
                            color: waitingShot.status === Image.Error ? Theme.alert : Theme.muted; font.family: Theme.face; font.pixelSize: 13 }
                    }
                    GlyphButton { id: takeOff; anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter; navigable: visible && enabled; glyph: ""; tip: "Take the picture off · Esc"; onClicked: shell.act("psn_picture_clear", null) }
                }
            }
            Row {
                id: writer
                visible: !!page.thread
                anchors.bottom: parent.bottom; anchors.bottomMargin: 18
                x: 20; width: parent.width - 40
                spacing: 10
                GlyphButton { id: pick; anchors.verticalCenter: parent.verticalCenter; navigable: visible && enabled; glyph: ""; tip: "Send a picture · Ctrl+V pastes one"; onClicked: pictureDialog.open() }
                Field {
                    id: draft
                    width: parent.width - send.width - pick.width - 20
                    height: 48
                    maximumLength: 2000
                    placeholderText: page.f.outgoing ? "Words under the picture (you can leave this empty)…" : "Write to " + (page.thread ? page.thread.name : "") + "…"
                    onEntered: send.activate()
                    // While you write, the others see that you are typing (told to PSN every few seconds at most).
                    onTextChanged: if (text.trim() !== "") shell.act("psn_typing", null)
                    // A copied picture (a screenshot, say) pasted here waits above, ready to send.
                    Keys.onPressed: function(event) {
                        if (event.matches(StandardKey.Paste) && shell.clipboardPicture()) { shell.act("psn_picture_paste", null); event.accepted = true }
                    }
                }
                PillButton {
                    id: send
                    width: 108; height: 48; tone: "main"
                    text: page.f.sending ? "Sending…" : "Send"
                    enabled: !page.f.sending && (draft.text.trim() !== "" || !!page.f.outgoing)
                    onClicked: { messageList.following = true; shell.act("psn_send", draft.text); draft.text = "" }
                }
            }
            // A picture dragged in from Explorer onto the open conversation waits above the box to write in.
            DropArea {
                anchors.fill: parent
                enabled: !!page.thread
                onEntered: function(drag) { if (drag.hasUrls) drag.accept(Qt.CopyAction); else drag.accepted = false }
                onDropped: function(drop) {
                    if (!drop.hasUrls) return
                    shell.act("psn_picture_drop", drop.urls.map(function(url) { return url.toString() }))
                    drop.accept(Qt.CopyAction)
                }
            }
            FileDialog {
                id: pictureDialog
                title: "Choose a picture to send"
                nameFilters: ["Pictures (*.png *.jpg *.jpeg *.webp *.bmp *.gif)", "All files (*)"]
                onAccepted: shell.act("psn_picture_file", selectedFile.toString())
            }
            // A picture of the conversation saved where the player chooses, as it came from PSN.
            FileDialog {
                id: saveDialog
                property string message: ""
                title: "Save the picture"
                fileMode: FileDialog.SaveFile
                nameFilters: ["Pictures (*.png *.jpg *.jpeg *.gif)", "All files (*)"]
                onAccepted: shell.act("psn_picture_save", [message, selectedFile.toString()])
            }
        }
    }
    // The add-friend card: an online ID typed exactly, PSN's answer, and the player found with what can be done. Esc closes it.
    Item {
        id: finder
        visible: page.finderOpen
        anchors.fill: parent
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; onWheel: function(wheel) { wheel.accepted = true } }
        Glass {
            id: finderCard
            frost: page.frost
            follow: page.x + page.opacity + finderColumn.implicitHeight
            anchors.horizontalCenter: parent.horizontalCenter
            y: Math.max(page.topInset + 40, (parent.height - height) / 2 - 40)
            width: Math.min(620, parent.width - 2 * page.side)
            height: finderColumn.implicitHeight + 64
            Column {
                id: finderColumn
                x: 32; y: 30
                width: parent.width - 64
                spacing: 14
                Item {
                    width: parent.width
                    height: Math.max(finderTitle.implicitHeight, 42)
                    Text { id: finderTitle; anchors.verticalCenter: parent.verticalCenter; text: "Add a friend"; color: Theme.text; font.family: Theme.light; font.pixelSize: 32 }
                    GlyphButton { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; navigable: visible; glyph: ""; tip: "Close · Esc"; onClicked: shell.act("friend_find_close", null) }
                }
                Note { text: "Type their online ID exactly as their PSN profile shows it. They get your request on their PlayStation and in the PlayStation App." }
                Row {
                    width: parent.width
                    spacing: 10
                    Field {
                        id: findField
                        width: parent.width - findButton.width - 10
                        height: 48
                        maximumLength: 16
                        placeholderText: "Online ID"
                        inputMethodHints: Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
                        onEntered: findButton.activate()
                    }
                    PillButton {
                        id: findButton
                        width: 120; height: 48; tone: "main"
                        text: page.find.state === "asking" ? "Looking…" : "Find"
                        enabled: page.find.state !== "asking" && findField.text.trim() !== ""
                        onClicked: shell.act("friend_find", findField.text)
                    }
                }
                Note { text: page.find.state === "asking" ? "Looking for " + page.find.asked + " on PSN…" : page.find.text || ""; tone: page.find.tone || "plain" }
                // The player found: who they are, where they stand with you, and the buttons for it.
                Rectangle {
                    id: found
                    readonly property var who: page.find.person || null
                    visible: !!who && page.find.state !== "asking"
                    width: parent.width
                    height: visible ? foundColumn.implicitHeight + 28 : 0
                    radius: 16
                    color: Qt.rgba(1, 1, 1, 0.06)
                    border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.1)
                    Column {
                        id: foundColumn
                        x: 16; y: 14
                        width: parent.width - 32
                        spacing: 12
                        Row {
                            width: parent.width
                            spacing: 14
                            Avatar { id: foundFace; anchors.verticalCenter: parent.verticalCenter; source: (found.who || {}).picture || ""; initial: (found.who || {}).initial || "?"; tone: "off" }
                            Column {
                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width - foundFace.width - 14
                                spacing: 2
                                Text { width: parent.width; elide: Text.ElideRight; text: (found.who || {}).name || ""; color: Theme.text; font.family: Theme.strong; font.pixelSize: 19 }
                                Text { width: parent.width; elide: Text.ElideRight; text: (found.who || {}).busy ? "Asking PSN…" : (found.who || {}).line || ""; color: Theme.muted; font.family: Theme.face; font.pixelSize: 14 }
                            }
                        }
                        Row {
                            visible: ((found.who || {}).actions || []).length > 0
                            spacing: 8
                            Repeater {
                                model: (found.who || {}).actions || []
                                delegate: PillButton {
                                    required property var modelData
                                    height: 44
                                    tone: modelData.tone
                                    text: modelData.label
                                    enabled: !(found.who || {}).busy
                                    onClicked: shell.act("friend_" + modelData.kind, found.who.id)
                                }
                            }
                        }
                        Note { text: (page.find.line || {}).text || ""; tone: (page.find.line || {}).tone || "plain" }
                    }
                }
            }
        }
    }

    // The open conversation's options: favourite and mute, its name, who is in it, adding people and leaving. Esc or a click beside it closes it.
    Item {
        id: options
        readonly property bool open: page.card === "options" && !!page.thread
        readonly property var t: page.thread || ({})
        property var chosen: ({})
        readonly property var picked: Object.keys(chosen)
        function choose(key) { var next = {}; for (var k in chosen) next[k] = true; if (next[key]) delete next[key]; else next[key] = true; chosen = next }
        anchors.fill: parent
        visible: opacity > 0
        opacity: open ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.ms(160) } }
        onOpenChanged: if (open) {
            chosen = ({}); renameField.text = t.named ? t.name : ""
            Qt.callLater(function() { favouriteTile.forceActiveFocus() })
        }
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; onClicked: shell.act("psn_card_close", null); onWheel: function(wheel) { wheel.accepted = true } }
        Glass {
            id: optionsCard
            frost: page.frost
            follow: page.x + page.opacity + optionsView.contentY + optionsColumn.implicitHeight
            anchors.horizontalCenter: parent.horizontalCenter
            y: Math.max(page.topInset + 30, (parent.height - height) / 2)
            width: Math.min(700, parent.width - 2 * page.side)
            height: Math.min(optionsColumn.implicitHeight + 60, parent.height - page.topInset - 60)
            scale: options.open ? 1 : 0.95
            Behavior on scale { NumberAnimation { duration: Theme.ms(220); easing.type: Easing.OutCubic } }
            MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons }
            CardEdge {}
            Flickable {
                id: optionsView
                anchors.fill: parent
                anchors.topMargin: 28; anchors.bottomMargin: 28
                contentHeight: optionsColumn.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { width: 8; policy: ScrollBar.AsNeeded }
                Column {
                    id: optionsColumn
                    x: 32
                    width: optionsCard.width - 64
                    spacing: 18
                    Item {
                        width: parent.width
                        height: 58
                        Faces { id: optionsFaces; anchors.verticalCenter: parent.verticalCenter; size: 54; people: options.t.people || [] }
                        Column {
                            anchors.left: optionsFaces.right; anchors.leftMargin: 16
                            anchors.right: optionsClose.left; anchors.rightMargin: 12
                            anchors.verticalCenter: parent.verticalCenter
                            Text { width: parent.width; elide: Text.ElideRight; text: options.t.name || ""; color: Theme.text; font.family: Theme.light; font.pixelSize: 30 }
                            Text { width: parent.width; elide: Text.ElideRight; text: options.t.kind === "group" ? "Group conversation · " + ((options.t.people || []).length + 1) + " people" : "Conversation of two"; color: Theme.dim; font.family: Theme.face; font.pixelSize: 13 }
                        }
                        GlyphButton { id: optionsClose; anchors.right: parent.right; navigable: visible && enabled; glyph: ""; tip: "Close · Esc"; onClicked: shell.act("psn_card_close", null) }
                    }
                    Row {
                        width: parent.width
                        spacing: 12
                        Tile {
                            id: favouriteTile
                            width: (parent.width - 12) / 2
                            on: !!options.t.favourite
                            enabled: !page.f.changing
                            glyph: on ? "" : ""
                            label: "Favourite"
                            detail: on ? "Pinned to the top of your list" : "Pin it to the top of your list"
                            onClicked: shell.act("psn_chat_favourite", null)
                        }
                        Tile {
                            width: (parent.width - 12) / 2
                            on: !!options.t.muted
                            enabled: !page.f.changing
                            glyph: on ? "" : ""
                            label: on ? "Muted" : "Alerts on"
                            detail: on ? "No alerts for its new messages" : "Alerts tell you of new messages"
                            onClicked: shell.act("psn_mute", null)
                        }
                    }
                    Column {
                        visible: !!options.t.canRename
                        width: parent.width
                        spacing: 10
                        Heading { text: "Group name" }
                        Row {
                            width: parent.width
                            spacing: 10
                            Field {
                                id: renameField
                                width: parent.width - renameButton.width - 10
                                height: 46
                                maximumLength: 64
                                placeholderText: options.t.name || "Name the group"
                                onEntered: renameButton.activate()
                            }
                            PillButton {
                                id: renameButton
                                width: 124; height: 46
                                text: "Rename"
                                enabled: !page.f.changing && renameField.text.trim() !== "" && renameField.text.trim() !== options.t.name
                                onClicked: shell.act("psn_rename", renameField.text)
                            }
                        }
                    }
                    Column {
                        width: parent.width
                        spacing: 6
                        Heading { text: "People · " + ((options.t.people || []).length + 1) }
                        Repeater {
                            model: options.t.people || []
                            delegate: Item {
                                id: member
                                required property var modelData
                                width: optionsColumn.width
                                height: 62
                                Rectangle { anchors.fill: parent; radius: 14; color: memberHover.hovered ? Qt.rgba(1, 1, 1, 0.06) : "transparent" }
                                HoverHandler { id: memberHover }
                                Avatar { id: memberFace; x: 8; width: 44; height: 44; anchors.verticalCenter: parent.verticalCenter; source: member.modelData.picture || ""; initial: member.modelData.initial || "?"; tone: member.modelData.tone || "off" }
                                Column {
                                    anchors.left: memberFace.right; anchors.leftMargin: 14
                                    anchors.right: takeOut.left; anchors.rightMargin: 10
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 1
                                    Text { width: parent.width; elide: Text.ElideRight; text: member.modelData.name; color: Theme.text; font.family: Theme.strong; font.pixelSize: 16 }
                                    Text { visible: text !== ""; width: parent.width; elide: Text.ElideRight; text: member.modelData.line || ""; color: member.modelData.tone === "online" || member.modelData.tone === "playing" ? Theme.online : Theme.dim; font.family: Theme.face; font.pixelSize: 13 }
                                }
                                PillButton { id: takeOut; visible: !!options.t.canRemove; anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter; width: 112; height: 38; tone: "ghost"; text: "Take out"; enabled: !page.f.changing; onClicked: shell.act("psn_member_remove", member.modelData.id) }
                            }
                        }
                        Text { x: 8; text: "And you."; color: Theme.dim; font.family: Theme.face; font.pixelSize: 13 }
                    }
                    Column {
                        width: parent.width
                        spacing: 10
                        Heading { text: "Add people" }
                        Note { text: options.t.kind === "group" ? "Choose friends to add. They see the whole conversation from now on." : "Adding someone starts a new group with all of you. This conversation of two stays as it is." }
                        Flow {
                            width: parent.width
                            spacing: 8
                            Repeater {
                                model: options.t.invitable || []
                                delegate: PersonChip {
                                    required property var modelData
                                    person: modelData
                                    chosen: !!options.chosen[modelData.id]
                                    onClicked: options.choose(modelData.id)
                                }
                            }
                        }
                        Note { visible: (options.t.invitable || []).length === 0; text: "All your friends are in this conversation already." }
                        PillButton {
                            visible: (options.t.invitable || []).length > 0
                            width: 160; height: 44; tone: "main"
                            text: options.picked.length > 0 ? "Add " + options.picked.length : "Add"
                            enabled: options.picked.length > 0 && !page.f.changing
                            onClicked: { shell.act("psn_invite", options.picked); options.chosen = ({}) }
                        }
                    }
                    PillButton { visible: !!options.t.canLeave; width: 170; height: 44; tone: "danger"; text: "Leave group"; enabled: !page.f.changing; onClicked: shell.act("psn_leave", null) }
                    Note { text: options.t.chatLine ? options.t.chatLine.text : ""; tone: options.t.chatLine ? options.t.chatLine.tone : "plain" }
                }
            }
        }
    }

    // A new group of friends (two or more), named or not. It opens once PSN has made it.
    Item {
        id: maker
        readonly property bool open: page.card === "new"
        property var chosen: ({})
        readonly property var picked: Object.keys(chosen)
        function choose(key) { var next = {}; for (var k in chosen) next[k] = true; if (next[key]) delete next[key]; else next[key] = true; chosen = next }
        anchors.fill: parent
        visible: opacity > 0
        opacity: open ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.ms(160) } }
        onOpenChanged: if (open) { chosen = ({}); groupName.text = ""; Qt.callLater(function() { groupName.forceActiveFocus() }) }
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; onClicked: shell.act("psn_card_close", null); onWheel: function(wheel) { wheel.accepted = true } }
        Glass {
            id: makerCard
            frost: page.frost
            follow: page.x + page.opacity + makerView.contentY + makerColumn.implicitHeight
            anchors.horizontalCenter: parent.horizontalCenter
            y: Math.max(page.topInset + 30, (parent.height - height) / 2)
            width: Math.min(700, parent.width - 2 * page.side)
            height: Math.min(makerColumn.implicitHeight + 60, parent.height - page.topInset - 60)
            scale: maker.open ? 1 : 0.95
            Behavior on scale { NumberAnimation { duration: Theme.ms(220); easing.type: Easing.OutCubic } }
            MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons }
            CardEdge {}
            Flickable {
                id: makerView
                anchors.fill: parent
                anchors.topMargin: 28; anchors.bottomMargin: 28
                contentHeight: makerColumn.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { width: 8; policy: ScrollBar.AsNeeded }
                Column {
                    id: makerColumn
                    x: 32
                    width: makerCard.width - 64
                    spacing: 16
                    Item {
                        width: parent.width
                        height: 54
                        Rectangle {
                            id: makerBadge
                            width: 54; height: 54; radius: 27
                            anchors.verticalCenter: parent.verticalCenter
                            color: Qt.rgba(0.83, 0.69, 0.22, 0.18)
                            border.width: 1; border.color: Theme.gold
                            layer.enabled: true
                            layer.effect: MultiEffect { shadowEnabled: true; shadowColor: Theme.gold; shadowOpacity: 0.45; shadowBlur: 0.8; blurMax: 22 }
                            Text { anchors.centerIn: parent; text: ""; font.family: "Segoe MDL2 Assets"; font.pixelSize: 24; color: Theme.goldSoft }
                        }
                        Text { anchors.left: makerBadge.right; anchors.leftMargin: 16; anchors.verticalCenter: parent.verticalCenter; text: "New group"; color: Theme.text; font.family: Theme.light; font.pixelSize: 32 }
                        GlyphButton { anchors.right: parent.right; navigable: visible && enabled; glyph: ""; tip: "Close · Esc"; onClicked: shell.act("psn_card_close", null) }
                    }
                    Note { text: "Choose two friends or more. The group shows on PSN, in the PlayStation App and on their PlayStation, and anyone in it can write to everyone." }
                    Field { id: groupName; width: parent.width; height: 48; maximumLength: 64; placeholderText: "Group name (you can leave this empty)"; onEntered: create.activate() }
                    Heading { text: "Friends" + (maker.picked.length > 0 ? " · " + maker.picked.length + " chosen" : "") }
                    Flow {
                        width: parent.width
                        spacing: 8
                        Repeater {
                            model: page.f.everyone || []
                            delegate: PersonChip {
                                required property var modelData
                                person: modelData
                                chosen: !!maker.chosen[modelData.id]
                                onClicked: maker.choose(modelData.id)
                            }
                        }
                    }
                    Note { visible: (page.f.everyone || []).length === 0; text: "You have no friends on PSN to make a group with yet. Select Add friend to find someone." }
                    Row {
                        spacing: 14
                        PillButton {
                            id: create
                            width: 180; height: 46; tone: "main"
                            text: page.f.changing ? "Making it…" : "Create group"
                            enabled: maker.picked.length >= 2 && !page.f.changing
                            onClicked: shell.act("psn_group_create", [maker.picked, groupName.text])
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: maker.picked.length === 1 ? "Choose one more friend." : ""
                            color: Theme.dim; font.family: Theme.face; font.pixelSize: 14
                        }
                    }
                    Note { text: page.f.chatLine ? page.f.chatLine.text : ""; tone: page.f.chatLine ? page.f.chatLine.tone : "plain" }
                }
            }
        }
    }

    // The faces of a conversation: one round picture for one person, two overlapping for a group (with how many more there are).
    component Faces: Item {
        id: faces
        property var people: []
        property int more: 0
        property real size: 46
        readonly property bool several: people.length > 1
        width: several ? size * 1.42 : size
        height: size
        Avatar {
            width: faces.several ? faces.size * 0.76 : faces.size; height: width
            source: (faces.people[0] || {}).picture || ""
            initial: faces.people.length > 0 ? (faces.people[0].initial || "?") : ""
            tone: faces.several ? "off" : (faces.people[0] || {}).tone || "off"
        }
        Rectangle {
            visible: faces.several
            x: faces.width - width; y: faces.height - height
            width: faces.size * 0.76 + 4; height: width; radius: width / 2
            color: "#15171C"
            Avatar { anchors.centerIn: parent; width: faces.size * 0.76; height: width; source: (faces.people[1] || {}).picture || ""; initial: (faces.people[1] || {}).initial || "?"; tone: "off" }
        }
        Rectangle {
            visible: faces.more > 0
            x: faces.width - width + 4; y: -2
            height: 20; width: Math.max(20, moreText.implicitWidth + 10); radius: 10
            color: Theme.gold
            Text { id: moreText; anchors.centerIn: parent; text: "+" + faces.more; color: Theme.ink; font.family: Theme.strong; font.pixelSize: 11 }
        }
    }

    // A gold rule over a card's top edge, as over the Messages panel.
    component CardEdge: Rectangle {
        x: 32; width: parent.width - 64; height: 2; radius: 1
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: "transparent" }
            GradientStop { position: 0.5; color: Theme.gold }
            GradientStop { position: 1.0; color: "transparent" }
        }
    }

    // A section's title in a card: small capitals after a short gold line.
    component Heading: Row {
        property alias text: headingText.text
        spacing: 10
        Rectangle { width: 18; height: 2; radius: 1; color: Theme.gold; anchors.verticalCenter: parent.verticalCenter }
        Text { id: headingText; color: Theme.muted; font.family: Theme.strong; font.pixelSize: 13; font.capitalization: Font.AllUppercase; font.letterSpacing: 1.4 }
    }

    // A switch as a large tile: gold and glowing while it is on, lifted under the pointer.
    component Tile: Item {
        id: tile
        property string glyph: ""
        property string label: ""
        property string detail: ""
        property bool on: false
        property bool navigable: visible && enabled
        signal clicked()
        function activate() { if (enabled) { Theme.keys = true; clicked() } }
        readonly property bool hot: tileArea.containsMouse && enabled
        implicitHeight: 84
        activeFocusOnTab: true
        opacity: enabled ? 1 : 0.5
        Keys.onReturnPressed: activate()
        Keys.onEnterPressed: activate()
        Keys.onSpacePressed: activate()
        Rectangle {
            anchors.fill: parent
            radius: 18
            border.width: 1
            border.color: tile.on ? Theme.gold : Qt.rgba(1, 1, 1, tile.hot ? 0.26 : 0.12)
            gradient: Gradient {
                GradientStop { position: 0.0; color: tile.on ? Qt.rgba(0.83, 0.69, 0.22, tile.hot ? 0.36 : 0.27) : Qt.rgba(1, 1, 1, tile.hot ? 0.12 : 0.075) }
                GradientStop { position: 1.0; color: tile.on ? Qt.rgba(0.83, 0.69, 0.22, 0.08) : Qt.rgba(1, 1, 1, 0.025) }
            }
            transform: Translate { y: tile.hot && !tileArea.pressed ? -2 : 0; Behavior on y { NumberAnimation { duration: Theme.ms(140); easing.type: Easing.OutCubic } } }
            scale: tileArea.pressed ? 0.97 : 1
            Behavior on scale { NumberAnimation { duration: Theme.ms(90) } }
            layer.enabled: tile.on
            layer.effect: MultiEffect { shadowEnabled: true; shadowColor: Theme.gold; shadowOpacity: tile.hot ? 0.5 : 0.3; shadowBlur: 0.8; blurMax: 28 }
            Text { id: tileGlyph; x: 20; anchors.verticalCenter: parent.verticalCenter; text: tile.glyph; font.family: "Segoe MDL2 Assets"; font.pixelSize: 24; color: tile.on ? Theme.goldSoft : Theme.text }
            Column {
                anchors.left: tileGlyph.right; anchors.leftMargin: 16
                anchors.right: parent.right; anchors.rightMargin: 14
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2
                Text { width: parent.width; elide: Text.ElideRight; text: tile.label; color: Theme.text; font.family: Theme.strong; font.pixelSize: 16 }
                Text { width: parent.width; elide: Text.ElideRight; text: tile.detail; color: tile.on ? Theme.goldSoft : Theme.dim; font.family: Theme.face; font.pixelSize: 13 }
            }
        }
        MouseArea { id: tileArea; anchors.fill: parent; hoverEnabled: true; cursorShape: tile.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor; onClicked: { Theme.keys = false; if (tile.enabled) tile.clicked() } }
        FocusGlow { on: tile.activeFocus; radius: 13 }
    }

    // A friend to choose: their picture and name, and a gold tick once chosen.
    component PersonChip: Item {
        id: chip
        property var person: ({})
        property bool chosen: false
        property bool navigable: visible && enabled
        signal clicked()
        function activate() { if (enabled) { Theme.keys = true; clicked() } }
        readonly property bool hot: chipArea.containsMouse
        width: chipRow.implicitWidth + 22
        height: 48
        activeFocusOnTab: true
        Keys.onReturnPressed: activate()
        Keys.onEnterPressed: activate()
        Keys.onSpacePressed: activate()
        Rectangle {
            anchors.fill: parent
            radius: height / 2
            color: chip.chosen ? Qt.rgba(0.83, 0.69, 0.22, chip.hot ? 0.32 : 0.22) : Qt.rgba(1, 1, 1, chip.hot ? 0.12 : 0.06)
            border.width: 1
            border.color: chip.chosen ? Theme.gold : Qt.rgba(1, 1, 1, chip.hot ? 0.28 : 0.12)
            Behavior on color { ColorAnimation { duration: Theme.ms(120) } }
            scale: chipArea.pressed ? 0.96 : 1
            Behavior on scale { NumberAnimation { duration: Theme.ms(90) } }
        }
        Row {
            id: chipRow
            x: 6
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10
            Avatar { width: 36; height: 36; anchors.verticalCenter: parent.verticalCenter; source: chip.person.picture || ""; initial: chip.person.initial || "?"; tone: chip.person.tone || "off"; ring: "#1D1B14" }
            Text { anchors.verticalCenter: parent.verticalCenter; text: chip.person.name || ""; color: Theme.text; font.family: chip.chosen ? Theme.strong : Theme.face; font.pixelSize: 15 }
            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: 22; height: 22; radius: 11
                color: chip.chosen ? Theme.gold : "transparent"
                border.width: chip.chosen ? 0 : 1.5
                border.color: Qt.rgba(1, 1, 1, 0.35)
                scale: chip.chosen ? 1 : 0.86
                Behavior on scale { NumberAnimation { duration: Theme.ms(200); easing.type: Easing.OutBack } }
                Behavior on color { ColorAnimation { duration: Theme.ms(120) } }
                Text { anchors.centerIn: parent; visible: chip.chosen; text: ""; font.family: "Segoe MDL2 Assets"; font.pixelSize: 12; color: Theme.ink }
            }
        }
        MouseArea { id: chipArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { Theme.keys = false; chip.clicked() } }
        FocusGlow { on: chip.activeFocus; radius: chip.height / 2 - 5 }
    }
}
