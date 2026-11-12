import QtQuick
import QtQuick.Window
import QtQuick.Effects

// The Games page: the focused game's art fills the window behind (drawn in Main), the row of games at the top under the bar,
// the focused one large, lit gold, tilting to the pointer, and under the row the focused game's name, buttons and cards.
FocusScope {
    id: page
    property real u: 1
    property real topInset: 0
    property Item frost: null
    property var shelf: shell.shelf
    property real follow: 0
    property alias moreButton: more
    property point pointer: Qt.point(0, 0)
    // The size the covers are read at: twice the focused tile on this screen, settled after a resize so a drag does not reread them all.
    property int coverPixels: 504
    function wantedCover() { return Math.max(64, Math.round(252 * page.u) * 2 * Screen.devicePixelRatio) }
    onUChanged: coverSettle.restart()
    Timer { id: coverSettle; interval: 300; onTriggered: page.coverPixels = page.wantedCover() }
    Component.onCompleted: page.coverPixels = page.wantedCover()

    // The arrows, Enter and typing. Everything goes to the shelf, which answers with sounds and a new view.
    Keys.onPressed: function(event) {
        Theme.keys = true
        var k = event.key
        if (k === Qt.Key_Left) shell.act("nav", "left")
        else if (k === Qt.Key_Right) shell.act("nav", "right")
        else if (k === Qt.Key_Up) shell.act("nav", "up")
        else if (k === Qt.Key_Down) shell.act("nav", "down")
        else if (k === Qt.Key_Return || k === Qt.Key_Enter) shell.act("nav", "accept")
        else if (k === Qt.Key_PageUp) shell.act("nav", "previous")
        else if (k === Qt.Key_PageDown) shell.act("nav", "next")
        else if (k === Qt.Key_Backspace) shell.act("erase", null)
        else if (event.text.length === 1 && event.text >= " " && !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier))) shell.act("type", event.text)
        else return
        event.accepted = true
    }

    HoverHandler { id: hover; onPointChanged: page.pointer = Qt.point(point.position.x / Math.max(1, page.width) * 2 - 1, point.position.y / Math.max(1, page.height) * 2 - 1) }
    WheelHandler { onWheel: function(event) { shell.act("move", event.angleDelta.y < 0 || event.angleDelta.x < 0 ? 1 : -1) } }

    // Shade where the words sit, so a bright picture never washes them out.
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: Qt.rgba(0, 0, 0, 0.82) }
            GradientStop { position: 0.42; color: Qt.rgba(0, 0, 0, 0.45) }
            GradientStop { position: 0.75; color: Qt.rgba(0, 0, 0, 0.0) }
        }
    }
    Rectangle {
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        height: parent.height * 0.55
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(0, 0, 0, 0) }
            GradientStop { position: 0.55; color: Qt.rgba(0, 0, 0, 0.55) }
            GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, 0.92) }
        }
    }

    // The focused game.
    Column {
        id: info
        x: 96 * page.u
        // Under the row; the cards step aside when they would reach the words and keys at the bottom.
        readonly property real floor: page.height - 100 * page.u
        y: row.y + row.height + 6 * page.u
        width: Math.min(980 * page.u, page.width - 200 * page.u)
        spacing: 14 * page.u
        property string shownTitle: page.shelf.title || ""
        onShownTitleChanged: arrive.restart()
        ParallelAnimation {
            id: arrive
            NumberAnimation { target: info; property: "opacity"; from: 0.2; to: 1; duration: Theme.ms(380); easing.type: Easing.OutCubic }
            NumberAnimation { target: shift; property: "x"; from: -26 * page.u; to: 0; duration: Theme.ms(420); easing.type: Easing.OutCubic }
        }
        transform: Translate { id: shift }
        Text {
            text: (page.shelf.kind || "").toUpperCase()
            visible: text !== ""
            color: Theme.goldSoft
            font.family: Theme.strong
            font.pixelSize: 17 * page.u
            font.letterSpacing: 3 * page.u
        }
        TextMetrics { id: nameWidth; font.family: Theme.light; font.pixelSize: 74 * page.u; text: page.shelf.name || "Your games" }
        Text {
            width: parent.width
            text: page.shelf.name || "Your games"
            color: Theme.text
            font.family: Theme.light
            // A long name drops to a smaller size and takes two lines at most.
            font.pixelSize: (nameWidth.advanceWidth > width ? 54 : 74) * page.u
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
            lineHeight: 0.95
            layer.enabled: true
            layer.effect: MultiEffect { shadowEnabled: true; shadowColor: "black"; shadowOpacity: 0.7; shadowBlur: 0.6; shadowVerticalOffset: 3 }
        }
        Text {
            text: page.shelf.line || ""
            color: Theme.muted
            font.family: Theme.face
            font.pixelSize: 21 * page.u
        }
        Item { width: 1; height: 10 * page.u }
        Row {
            spacing: 16 * page.u
            PillButton {
                id: play
                visible: (page.shelf.action || "") !== ""
                text: page.shelf.action || ""
                icon: ""
                tone: "main"
                fontSize: 22 * page.u
                height: 64 * page.u
                width: Math.max(220 * page.u, implicitWidth + 30 * page.u)
                navigable: false
                onClicked: shell.act("choose", null)
                // Only while the page shows: an endless animation makes Qt redraw the window every frame, over the game too.
                SequentialAnimation on scale {
                    running: Theme.motion && page.visible && (page.shelf.action === "Play" || page.shelf.action === "Resume")
                    loops: Animation.Infinite
                    NumberAnimation { to: 1.03; duration: 1100; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 1.0; duration: 1100; easing.type: Easing.InOutSine }
                }
            }
            PillButton {
                id: more
                visible: !!page.shelf.more
                text: "•••"
                fontSize: 20 * page.u
                height: 64 * page.u
                width: height
                navigable: false
                onClicked: shell.act("more", null)
            }
        }
        Item { id: cardsGap; width: 1; height: 18 * page.u }
        Item {
            id: cardsHolder
            width: cardsRow.width
            height: roomy ? cardsRow.height : 0
            // Measured from the gap above: a Column leaves an item of no height where it was, so its own y could be stale and keep the cards away.
            readonly property bool roomy: info.y + cardsGap.y + cardsGap.height + info.spacing + cardsRow.height <= info.floor
            Row {
                id: cardsRow
                visible: cardsHolder.roomy
                spacing: 18 * page.u
                Repeater {
                    model: page.shelf.cards || []
                    delegate: Glass {
                        required property var modelData
                        frost: page.frost
                        follow: page.follow
                        width: 290 * page.u
                        height: 128 * page.u
                        radius: 18 * page.u
                        Column {
                            anchors.fill: parent
                            anchors.margins: 20 * page.u
                            spacing: 4 * page.u
                            Text { text: modelData.title; color: Theme.muted; font.family: Theme.face; font.pixelSize: 15 * page.u }
                            Text { text: modelData.value; color: Theme.text; font.family: Theme.light; font.pixelSize: 32 * page.u; elide: Text.ElideRight; width: parent.width }
                            Text { text: modelData.note; color: Theme.dim; font.family: Theme.face; font.pixelSize: 14 * page.u; elide: Text.ElideRight; width: parent.width }
                        }
                    }
                }
                // The stream as it is now, only while the console is online.
                Glass {
                    readonly property var live: (page.shelf.info || {})
                    visible: live.state === "online"
                    frost: page.frost
                    follow: page.follow
                    width: 290 * page.u
                    height: 128 * page.u
                    radius: 18 * page.u
                    Column {
                        anchors.fill: parent
                        anchors.margins: 20 * page.u
                        spacing: 4 * page.u
                        Text { text: "Live"; color: Theme.muted; font.family: Theme.face; font.pixelSize: 15 * page.u }
                        Text {
                            text: parent.parent.live.fps !== undefined && parent.parent.live.fps !== null ? parent.parent.live.fps + " fps" : "Ready"
                            color: Theme.text; font.family: Theme.light; font.pixelSize: 32 * page.u
                        }
                        Text {
                            readonly property var live: parent.parent.live
                            text: [live.picture || "", live.bitrate || "", live.cpu ? "CPU " + live.cpu + "°C" : "", live.soc ? "SoC " + live.soc + "°C" : ""].filter(function(s) { return s !== "" }).join("  ·  ") || "Picture when you play"
                            color: Theme.dim; font.family: Theme.face; font.pixelSize: 14 * page.u; elide: Text.ElideRight; width: parent.width
                        }
                    }
                }
            }
        }
    }

    // The shelf's name and the search, just under the bar and over the row.
    Row {
        id: shelfLine
        x: 96 * page.u
        y: Math.round(page.topInset + 12 * page.u)
        spacing: 18 * page.u
        Item {
            width: shelfName.implicitWidth + 44 * page.u
            height: 40 * page.u
            Rectangle { anchors.fill: parent; radius: height / 2; color: shelfArea.containsMouse ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.07); border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.14) }
            Text { id: shelfName; anchors.centerIn: parent; text: (page.shelf.shelfName || "All games") + "   ▾"; color: Theme.text; font.family: Theme.face; font.pixelSize: 17 * page.u }
            MouseArea { id: shelfArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { Theme.keys = false; shelves.current = Math.max(0, (page.shelf.shelves || []).map(function(s) { return s.key }).indexOf(page.shelf.shelf)); shelves.open() } }
            GlassMenu {
                id: shelves
                y: parent.height + 8
                items: page.shelf.shelves || []
                menuWidth: 240
                onChosen: function(index) { shelves.close(); shell.act("shelf", page.shelf.shelves[index].key) }
            }
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: (page.shelf.count || 0) + ((page.shelf.count || 0) === 1 ? " game" : " games")
            color: Theme.dim; font.family: Theme.face; font.pixelSize: 16 * page.u
        }
        Rectangle {
            visible: !!page.shelf.searching || (page.shelf.text || "") !== ""
            anchors.verticalCenter: parent.verticalCenter
            height: 40 * page.u
            width: Math.max(260 * page.u, searchText.implicitWidth + 70 * page.u)
            radius: height / 2
            color: Qt.rgba(0, 0, 0, 0.45)
            border.width: 1.5
            border.color: Theme.gold
            Text { x: 16 * page.u; anchors.verticalCenter: parent.verticalCenter; text: ""; font.family: "Segoe MDL2 Assets"; font.pixelSize: 14 * page.u; color: Theme.goldSoft }
            Text {
                id: searchText
                x: 42 * page.u
                anchors.verticalCenter: parent.verticalCenter
                text: (page.shelf.text || "") === "" ? "Type a game's name" : page.shelf.text
                color: (page.shelf.text || "") === "" ? Theme.dim : Theme.text
                font.family: Theme.face; font.pixelSize: 17 * page.u
            }
            Rectangle {
                id: cursor
                width: 2; height: 20 * page.u; color: Theme.goldSoft
                anchors.verticalCenter: parent.verticalCenter
                x: searchText.x + ((page.shelf.text || "") === "" ? 0 : searchText.implicitWidth + 2)
                SequentialAnimation on opacity { loops: Animation.Infinite; running: cursor.visible; NumberAnimation { to: 0; duration: 500 } NumberAnimation { to: 1; duration: 500 } }
            }
        }
    }

    // The row of games.
    ListView {
        id: row
        x: 0
        width: page.width
        // The focused tile with its glow, and the short fade under it.
        height: 318 * page.u
        y: Math.round(shelfLine.y + shelfLine.height + 8 * page.u)
        orientation: ListView.Horizontal
        spacing: Math.round(22 * page.u)
        model: gameModel
        clip: false
        interactive: false
        cacheBuffer: 1400 * page.u
        highlightRangeMode: ListView.StrictlyEnforceRange
        preferredHighlightBegin: Math.round(96 * page.u)
        preferredHighlightEnd: Math.round(96 * page.u) + Math.round(252 * page.u)
        highlightMoveDuration: Theme.ms(260)
        highlightMoveVelocity: -1
        highlightFollowsCurrentItem: true
        currentIndex: 0
        readonly property int wanted: page.shelf.focus || 0
        onWantedChanged: if (currentIndex !== wanted && wanted < count) currentIndex = wanted
        onCountChanged: if (wanted < count) { currentIndex = wanted; positionViewAtIndex(wanted, ListView.Beginning) }
        Connections { target: gameModel; function onModelReset() { if (row.wanted < row.count) { row.currentIndex = row.wanted; row.positionViewAtIndex(row.wanted, ListView.Beginning) } } }
        delegate: Item {
            id: tile
            required property int index
            required property string title
            required property string name
            required property string cover
            readonly property bool chosen: ListView.isCurrentItem
            readonly property bool running: title === (page.shelf.running || "")
            // Whole pixels at rest: a picture placed between two pixels is drawn blurred.
            width: Math.round((chosen ? 252 : 156) * page.u)
            height: row.height
            Behavior on width { enabled: Theme.motion; NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
            readonly property real side: width
            // Only the focused tile turns in 3D, towards the mouse (anywhere on the page, more over the tile itself) or the right
            // stick; the others stay flat.
            readonly property bool hovered: tileArea.containsMouse
            readonly property var look: shell.parallax.x !== 0 || shell.parallax.y !== 0 ? shell.parallax : page.pointer
            property real lean: chosen && Theme.motion ? Math.max(-1, Math.min(1, hovered ? tileArea.mouseX / Math.max(1, width) * 2 - 1 : look.x * 0.75)) : 0
            property real nod: chosen && Theme.motion ? Math.max(-1, Math.min(1, hovered ? tileArea.mouseY / Math.max(1, card.height) * 2 - 1 : look.y * 0.6)) : 0
            Behavior on lean { SmoothedAnimation { velocity: 4 } }
            Behavior on nod { SmoothedAnimation { velocity: 4 } }
            readonly property real yaw: chosen ? lean * 15 : 0
            readonly property real pitch: chosen ? -nod * 11 : 0
            Item {
                id: card
                width: tile.side
                height: tile.side
                anchors.top: parent.top
                anchors.topMargin: Math.round(12 * page.u)
                // A shorter eye distance than Qt's 1024 px makes the turn read as depth rather than a squeeze.
                transform: [
                    Rotation { origin.x: card.width / 2; origin.y: card.height / 2; axis { x: 0; y: 1; z: 0 } angle: tile.yaw; distanceToPlane: 620 * page.u },
                    Rotation { origin.x: card.width / 2; origin.y: card.height / 2; axis { x: 1; y: 0; z: 0 } angle: tile.pitch; distanceToPlane: 620 * page.u }
                ]
                // The shadow falls away from the side that turns towards you, so the tile seems to stand off the page.
                RectangularShadow {
                    anchors.fill: parent
                    radius: 16 * page.u
                    blur: tile.chosen ? 46 * page.u : 22 * page.u
                    offset.x: tile.yaw * 1.1 * page.u
                    offset.y: (tile.chosen ? 18 : 8) * page.u - tile.pitch * 1.1 * page.u
                    color: Qt.rgba(0, 0, 0, tile.chosen ? 0.75 : 0.6)
                }
                // A soft gold light behind the focused tile, no ring round it; it leans a little with the tile.
                RectangularShadow {
                    id: glow
                    anchors.fill: parent
                    radius: 16 * page.u
                    blur: 34 * page.u
                    spread: 3 * page.u
                    offset.x: tile.yaw * 0.35 * page.u
                    offset.y: 4 * page.u - tile.pitch * 0.35 * page.u
                    color: Theme.gold
                    opacity: tile.chosen ? 0.5 : 0
                    visible: opacity > 0.01
                    Behavior on opacity { NumberAnimation { duration: Theme.ms(220) } }
                }
                // The cover with its rounded corners. The focused one is drawn at twice its size and filtered down,
                // so it stays sharp while it turns; the cover file is read at that size, never stretched up.
                Image {
                    id: art
                    anchors.fill: parent
                    source: tile.cover
                    sourceSize: Qt.size(page.coverPixels, page.coverPixels)
                    asynchronous: true
                    retainWhileLoading: true
                    cache: true
                    smooth: true
                    mipmap: true
                    fillMode: Image.PreserveAspectCrop
                }
                readonly property size texture: Qt.size(Math.ceil(width * 2 * Screen.devicePixelRatio), Math.ceil(height * 2 * Screen.devicePixelRatio))
                // The picture stays a shown item that the source hides from the page, Qt's own way, so it is always drawn again when it changes.
                ShaderEffectSource { id: artSource; anchors.fill: parent; sourceItem: art; hideSource: true; textureSize: card.texture; mipmap: true; smooth: true; visible: false }
                Rectangle { id: mask; anchors.fill: parent; radius: 16 * page.u; visible: false; layer.enabled: true; layer.smooth: true; layer.textureSize: card.texture }
                Rectangle { anchors.fill: parent; radius: 16 * page.u; color: Theme.raised; visible: art.status !== Image.Ready
                    Text { anchors.centerIn: parent; width: parent.width - 20; text: tile.name; color: Theme.muted; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter; font.family: Theme.face; font.pixelSize: 15 * page.u }
                }
                MultiEffect {
                    id: face
                    anchors.fill: parent
                    visible: art.status === Image.Ready
                    source: artSource
                    maskEnabled: true
                    maskSource: mask
                    brightness: tile.chosen ? 0 : -0.06
                }
                // Light across the top of the focused tile, stronger on the side it turns to.
                Rectangle {
                    anchors.fill: parent
                    radius: 16 * page.u
                    visible: tile.chosen
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, Math.max(0, 0.08 + tile.lean * 0.04)) }
                        GradientStop { position: 0.35; color: Qt.rgba(1, 1, 1, 0.0) }
                    }
                }
                // A sheen that sweeps across as the tile turns, the way light runs over a glossy case; gone when it faces you.
                Rectangle {
                    id: sheen
                    anchors.fill: parent
                    radius: 16 * page.u
                    readonly property real at: Math.max(0.12, Math.min(0.88, 0.5 + tile.yaw / 30))
                    opacity: tile.chosen && Theme.motion ? Math.min(1, Math.abs(tile.yaw) / 10) : 0
                    visible: opacity > 0.02
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0) }
                        GradientStop { position: Math.max(0.01, sheen.at - 0.12); color: Qt.rgba(1, 1, 1, 0) }
                        GradientStop { position: sheen.at; color: Qt.rgba(1, 1, 1, 0.13) }
                        GradientStop { position: Math.min(0.99, sheen.at + 0.12); color: Qt.rgba(1, 1, 1, 0) }
                        GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0) }
                    }
                }
                Rectangle {
                    visible: tile.running
                    anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 10 * page.u
                    height: 26 * page.u; width: openText.implicitWidth + 20 * page.u; radius: height / 2
                    color: Theme.gold
                    Text { id: openText; anchors.centerIn: parent; text: "OPEN"; color: Theme.ink; font.family: Theme.strong; font.pixelSize: 12 * page.u; font.letterSpacing: 1.5 }
                }
                MouseArea {
                    id: tileArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: { Theme.keys = false; shell.act("go", tile.index) }
                }
            }
            // Under the focused tile only, a faint blur of its colours on the floor, gone within a short way; the others stand on nothing.
            ShaderEffectSource {
                id: mirror
                width: card.width
                height: card.height * 0.2
                anchors.top: card.bottom
                anchors.topMargin: 4 * page.u
                visible: false
                sourceItem: face
                sourceRect: Qt.rect(0, card.height * 0.8, card.width, card.height * 0.2)
                live: tile.chosen
                textureMirroring: ShaderEffectSource.MirrorVertically
            }
            Rectangle {
                id: fade
                anchors.fill: mirror
                visible: false
                layer.enabled: true
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 1) }
                    GradientStop { position: 0.75; color: Qt.rgba(1, 1, 1, 0) }
                }
            }
            MultiEffect {
                anchors.fill: mirror
                source: mirror
                opacity: tile.chosen ? 0.2 : 0
                visible: opacity > 0
                // It turns with the tile above it.
                transform: Rotation { origin.x: mirror.width / 2; origin.y: -card.height / 2; axis { x: 0; y: 1; z: 0 } angle: tile.yaw }
                Behavior on opacity { NumberAnimation { duration: Theme.ms(240) } }
                maskEnabled: true
                maskSource: fade
                maskThresholdMin: 0.0
                maskSpreadAtMin: 1.0
                blurEnabled: true
                blur: 1.0
                blurMax: 32
            }
        }
    }

    // Words at the bottom: what the console is doing, or the latest news, and the keys or buttons.
    Text {
        x: 96 * page.u
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 44 * page.u
        width: page.width * 0.5
        elide: Text.ElideRight
        text: page.shelf.notice || page.shelf.status || ""
        color: page.shelf.notice ? Theme.goldSoft : Theme.muted
        font.family: Theme.face
        font.pixelSize: 17 * page.u
    }
    Row {
        anchors.right: parent.right
        anchors.rightMargin: 72 * page.u
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 40 * page.u
        spacing: 26 * page.u
        Repeater {
            model: (shell.top.pad ? page.shelf.padHints : page.shelf.hints) || []
            delegate: Row {
                required property var modelData
                spacing: 9 * page.u
                Rectangle {
                    readonly property var glyphs: ({ cross: "✕", circle: "○", square: "□", triangle: "△" })
                    readonly property var colours: ({ cross: "#8FB4FF", circle: "#FF8F9A", square: "#F5A3E0", triangle: "#7CE0C3" })
                    height: 30 * page.u
                    width: Math.max(height, keyText.implicitWidth + 18 * page.u)
                    radius: glyphs[modelData.key] ? height / 2 : 7 * page.u
                    color: Qt.rgba(1, 1, 1, 0.1)
                    border.width: 1
                    border.color: Qt.rgba(1, 1, 1, 0.22)
                    Text { id: keyText; anchors.centerIn: parent; text: parent.glyphs[modelData.key] || modelData.key; color: parent.colours[modelData.key] || Theme.text; font.family: Theme.face; font.pixelSize: 14 * page.u }
                }
                Text { text: modelData.text; color: Theme.muted; font.family: Theme.face; font.pixelSize: 15 * page.u; anchors.verticalCenter: parent.verticalCenter }
            }
        }
    }
}
