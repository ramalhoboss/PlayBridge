import QtQuick
import QtQuick.Window
import QtQuick.Effects
import QtQuick.Controls.Basic

// PlayBridge's window in Qt Quick. Python (qt_shell.py) owns everything that happens; this file draws it:
// the picture behind the pages, with parallax, blurred once for every glass panel, the pages with their transitions,
// the top bar, the menus and dialogs, and the keys and the controller's moves on Settings and Media.
Window {
    id: root
    // Placed once by qt_shell.py when it opens, then left to Windows: a position bound to the size would push a maximized or
    // full-screen window down from the top of the screen every time its size changed.
    width: 1540
    height: 920
    minimumWidth: 900
    minimumHeight: 620
    visible: false
    color: "black"
    title: "PlayBridge"

    readonly property real u: Math.max(0.6, Math.min(width / 1920, height / 1080))
    readonly property string page: shell.page
    readonly property bool bare: page === "live" && (shell.fullscreen || shell.mini)
    readonly property real topInset: topBar.visible ? topBar.height : 0

    Binding { target: Theme; property: "motion"; value: !!shell.look.animations }
    Binding { target: Theme; property: "icons"; value: shell.look.icons || "" }

    // The picture behind every page but the live view: the focused game's art on Games, PlayBridge's own elsewhere.
    Item {
        id: backdrop
        anchors.fill: parent
        visible: root.page !== "live"
        // A texture of its own, which the frost below reads without hiding the picture.
        layer.enabled: true
        readonly property bool games: root.page === "games"
        readonly property real px: shell.parallax.x !== 0 ? shell.parallax.x : gamesPage.pointer.x
        readonly property real py: shell.parallax.y !== 0 ? shell.parallax.y : gamesPage.pointer.y
        Rectangle { anchors.fill: parent; color: "#06070A" }
        Image {
            anchors.fill: parent
            source: shell.look.backdrop || ""
            fillMode: Image.PreserveAspectCrop
            opacity: backdrop.games ? 0 : 1
            Behavior on opacity { NumberAnimation { duration: Theme.ms(500) } }
        }
        Item {
            id: hero
            anchors.fill: parent
            opacity: backdrop.games ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.ms(500) } }
            readonly property string wanted: shell.shelf.art || shell.shelf.cover || ""
            readonly property bool soft: !shell.shelf.art
            // Two pictures: the new one loads behind and fades in over the old once it is ready.
            property int front: 0
            onWantedChanged: {
                var back = front === 0 ? heroB : heroA
                if (back.source.toString() === wanted && back.status === Image.Ready) { front = front === 0 ? 1 : 0; return }
                back.soft = soft
                back.source = wanted
            }
            // Bigger than the window, so it can lean with the pointer or the right stick without showing an edge.
            Item {
                id: lean
                width: parent.width * 1.1
                height: parent.height * 1.1
                x: -parent.width * 0.05 - backdrop.px * parent.width * 0.035
                y: -parent.height * 0.05 - backdrop.py * parent.height * 0.03
                Behavior on x { enabled: Theme.motion; SmoothedAnimation { velocity: 220 } }
                Behavior on y { enabled: Theme.motion; SmoothedAnimation { velocity: 180 } }
                // A slow drift, as if the camera breathed.
                SequentialAnimation on scale {
                    running: Theme.motion && backdrop.games && backdrop.visible
                    loops: Animation.Infinite
                    NumberAnimation { from: 1.0; to: 1.05; duration: 24000; easing.type: Easing.InOutSine }
                    NumberAnimation { from: 1.05; to: 1.0; duration: 24000; easing.type: Easing.InOutSine }
                }
                HeroPicture { id: heroA; shown: hero.front === 0; onArrived: if (source.toString() === hero.wanted) hero.front = 0 }
                HeroPicture { id: heroB; shown: hero.front === 1; onArrived: if (source.toString() === hero.wanted) hero.front = 1 }
            }
        }
    }
    // The same picture, blurred, for the glass. Drawn under the picture itself, so only the glass panels show it.
    MultiEffect {
        id: frostLayer
        anchors.fill: backdrop
        z: -1
        source: backdrop
        visible: backdrop.visible
        blurEnabled: true
        blur: 1.0
        blurMax: 64
        saturation: 0.1
        autoPaddingEnabled: false
    }

    // The pages. The one shown fades and settles in; the others step back and fade away.
    component PageHolder: Item {
        id: holder
        property string name
        readonly property bool on: root.page === name
        anchors.fill: parent
        opacity: on ? 1 : 0
        visible: opacity > 0.001
        scale: on ? 1 : 0.985
        Behavior on opacity { NumberAnimation { duration: Theme.ms(260); easing.type: Easing.OutCubic } }
        Behavior on scale { NumberAnimation { duration: Theme.ms(320); easing.type: Easing.OutCubic } }
    }
    Item {
        id: pages
        anchors.fill: parent
        PageHolder {
            name: "games"
            GamesPage {
                id: gamesPage
                anchors.fill: parent
                anchors.topMargin: 0
                u: root.u
                topInset: root.topInset
                frost: frostLayer
                follow: parent.opacity + parent.scale
            }
        }
        PageHolder {
            name: "media"
            MediaPage {
                id: mediaPage
                anchors.fill: parent
                u: root.u
                topInset: root.topInset
                frost: frostLayer
                Keys.onPressed: function(event) { root.keyMove(event) }
            }
        }
        PageHolder {
            name: "settings"
            SettingsPage {
                id: settingsPage
                anchors.fill: parent
                u: root.u
                topInset: root.topInset
                frost: frostLayer
                Keys.onPressed: function(event) { root.keyMove(event) }
            }
        }
        Item {
            id: liveHolder
            anchors.fill: parent
            readonly property bool on: root.page === "live"
            opacity: on ? 1 : 0
            visible: opacity > 0.001
            Behavior on opacity { NumberAnimation { duration: Theme.ms(220) } }
            LivePage {
                id: livePage
                anchors.fill: parent
                u: root.u
                topInset: root.topInset
                settled: liveHolder.opacity === 1
                Keys.onPressed: function(event) { root.keyMove(event) }
            }
        }
    }

    TopBar {
        id: topBar
        anchors.left: parent.left
        anchors.right: parent.right
        u: Math.max(0.75, root.u)
        visible: !root.bare
    }
    // The line at the bottom on Media and Settings, as on the live view.
    Text {
        visible: root.page === "media" || root.page === "settings"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 10
        anchors.leftMargin: 22
        elide: Text.ElideRight
        text: shell.message.text || ""
        color: shell.message.tone === "error" ? "#FFAAA5" : Theme.tone(shell.message.tone)
        font.family: Theme.face
        font.pixelSize: 12
    }

    // The power menu and the game's menu. Python keeps which row is chosen, so the keys, the controller and the mouse agree.
    GlassMenu {
        id: menu
        readonly property var shelfMenu: root.page === "games" ? (shell.shelf.menu || null) : null
        readonly property var active: (shell.popup && shell.popup.items) ? shell.popup : shelfMenu
        readonly property bool fromMore: !!active && active.kind === "more"
        parent: fromMore ? gamesPage.moreButton : topBar.powerButton
        x: fromMore ? 0 : (parent ? parent.width - width : 0)
        y: parent ? parent.height + 10 : 0
        menuWidth: 300
        items: active ? active.items : []
        current: active ? active.selected : 0
        onActiveChanged: if (active) open(); else close()
        onChosen: function(index) { shell.act("menu_choose", index) }
        onKeyed: function(event) { shell.act("nav", event) }
        onClosed: if (active) shell.act("menu_close", null)
    }
    ConfirmDialog { id: dialog }
    ConsoleCaptures {
        id: captures
        readonly property bool wanted: !!shell.consoleCaptures.open
        onWantedChanged: if (wanted) open(); else close()
    }

    // Keys that do the same on every page.
    Shortcut { sequence: "F11"; onActivated: shell.act("key", "f11") }
    Shortcut { sequence: "Ctrl+I"; onActivated: shell.act("key", "session") }
    Shortcut { sequence: "Ctrl+L"; onActivated: shell.act("key", "media") }
    Shortcut { sequence: "Ctrl+,"; onActivated: shell.act("key", "settings") }
    Shortcut { sequence: "F8"; onActivated: shell.act("key", "screenshot") }
    Shortcut { sequence: "F9"; onActivated: shell.act("key", "record") }
    Shortcut { sequence: "F10"; onActivated: shell.act("key", "replay") }
    Shortcut { sequence: "F7"; onActivated: shell.act("key", "mic") }
    Shortcut { sequence: "F6"; onActivated: shell.act("key", "f6") }
    Shortcut { sequence: "Ctrl+G"; onActivated: shell.act("key", "gaming") }
    Shortcut { sequence: "Ctrl+M"; onActivated: shell.act("key", "mini") }
    Shortcut { sequence: "Ctrl+B"; onActivated: shell.act("key", "live") }
    Shortcut {
        sequence: "Escape"
        onActivated: {
            // In a text field, Escape only leaves it.
            var item = root.activeFocusItem
            if (item && item.cursorPosition !== undefined) { root.pageItem().forceActiveFocus(); return }
            shell.act("key", "escape")
        }
    }

    function pageItem() { return page === "games" ? gamesPage : page === "media" ? mediaPage : page === "settings" ? settingsPage : livePage }
    onPageChanged: {
        settingsRail = false; settingsPage.railFocus = ""
        Qt.callLater(function() { root.pageItem().forceActiveFocus() })
    }
    Component.onCompleted: pageItem().forceActiveFocus()

    // Moving the focus by direction, for the arrows and the controller: the nearest control that way, a little to either side.
    property bool settingsRail: false
    function navigables(item, out) {
        if (!item || !item.visible || item.opacity === 0) return out
        if (item.navigable === true && item.width > 0 && item.height > 0) out.push(item)
        for (var i = 0; i < item.children.length; i++) navigables(item.children[i], out)
        return out
    }
    function focused() {
        var item = root.activeFocusItem
        while (item && item.navigable !== true) item = item.parent
        return item
    }
    function reveal(item) {
        var view = item.parent
        while (view && view.contentY === undefined) view = view.parent
        if (!view || !view.contentItem) return
        var top = item.mapToItem(view.contentItem, 0, 0).y, bottom = top + item.height
        if (top < view.contentY + 24) view.contentY = Math.max(0, top - 48)
        else if (bottom > view.contentY + view.height - 24) view.contentY = Math.min(Math.max(0, view.contentHeight - view.height), bottom - view.height + 48)
    }
    function moveFocus(area, direction) {
        var items = navigables(area, [])
        if (items.length === 0) return false
        var current = focused()
        if (!current || items.indexOf(current) < 0) {
            // Nothing in focus yet: the first control in reading order, the left column before the right one.
            var first = null, firstScore = 1e12
            for (var k = 0; k < items.length; k++) {
                var at = items[k].mapToItem(null, 0, 0)
                if (at.y + at.x / 2 < firstScore) { first = items[k]; firstScore = at.y + at.x / 2 }
            }
            first.forceActiveFocus(); reveal(first); return true
        }
        // Only what lies past the focused control's edge counts. What shares its row (or its column, going up and down) comes first,
        // the nearest of those; anything else only when nothing does, so a wide button never jumps to a field above it.
        var across = direction === "left" || direction === "right"
        var sign = direction === "right" || direction === "down" ? 1 : -1
        function span(item) {
            var p = item.mapToItem(null, 0, 0)
            return across ? { lead: p.x, end: p.x + item.width, low: p.y, high: p.y + item.height }
                          : { lead: p.y, end: p.y + item.height, low: p.x, high: p.x + item.width }
        }
        var from = span(current), middle = (from.low + from.high) / 2
        var best = null, score = 1e12
        for (var i = 0; i < items.length; i++) {
            var item = items[i]
            if (item === current) continue
            var to = span(item)
            var centre = (to.lead + to.end) / 2
            if (sign > 0 ? centre <= from.end - 4 : centre >= from.lead + 4) continue
            var gap = Math.max(0, sign > 0 ? to.lead - from.end : from.lead - to.end)
            var shared = Math.min(from.high, to.high) - Math.max(from.low, to.low) > 4
            var side = Math.abs((to.low + to.high) / 2 - middle)
            var value = (shared ? 0 : 1e6) + gap + side * (shared ? 0.25 : 2.5)
            if (value < score) { score = value; best = item }
        }
        if (!best) return false
        best.forceActiveFocus(); reveal(best); return true
    }
    function activateFocused() {
        var item = focused()
        if (item && item.activate) item.activate()
    }
    // One move from the arrows or the controller on Settings, Media or the PS5's captures. On Settings, going left past the panels
    // reaches the sections at the left, where up and down change the section and right goes back into it.
    function move(event) {
        Theme.keys = true
        if (Theme.openChoice && Theme.openChoice.answer(event)) return
        var area = captures.opened ? captures.contentItem : pageItem()
        if (page === "settings" && settingsRail && !captures.opened) {
            var keys = (shell.settings.sections || []).map(function(s) { return s.key })
            var at = Math.max(0, keys.indexOf(shell.settings.section))
            if (event === "up" || event === "down") {
                var next = keys[(at + (event === "down" ? 1 : keys.length - 1)) % keys.length]
                shell.act("section", next); settingsPage.railFocus = next; shell.act("cue", "move")
            } else if (event === "right" || event === "accept") {
                settingsRail = false; settingsPage.railFocus = ""
                Qt.callLater(function() { moveFocus(settingsPage, "down") })
            }
            return
        }
        if (event === "accept") { activateFocused(); return }
        if (["up", "down", "left", "right"].indexOf(event) < 0) return
        if (!moveFocus(area, event) && page === "settings" && event === "left" && !captures.opened) {
            var left = focused()
            if (left) left.focus = false
            settingsRail = true; settingsPage.railFocus = shell.settings.section; root.pageItem().forceActiveFocus()
        }
    }
    function keyMove(event) {
        var names = {}
        names[Qt.Key_Up] = "up"; names[Qt.Key_Down] = "down"; names[Qt.Key_Left] = "left"; names[Qt.Key_Right] = "right"
        if (names[event.key] === undefined) {
            if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && settingsRail) { move("accept"); event.accepted = true }
            return
        }
        if (page === "live") return
        move(names[event.key]); event.accepted = true
    }
    Connections { target: shell; function onNavigate(event) { root.move(event) } }
    // A click hands the window back to the mouse: the ring goes.
    TapHandler { acceptedButtons: Qt.LeftButton; gesturePolicy: TapHandler.DragThreshold; onTapped: Theme.keys = false }
}
