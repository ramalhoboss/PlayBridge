import QtQuick
import QtQuick.Window
import QtQuick.Effects
import QtQuick.Controls.Basic

// The bar over every page: the tabs, with a gold mark that slides between them, the console's state, the clock and the page buttons.
Item {
    id: bar
    property var strip: shell.top
    property real u: 1
    property Item powerButton: power
    property Item psnButton: psnChip
    readonly property var me: strip.psn || ({})
    implicitHeight: 76 * u
    // What the right-hand row shows beside the tabs. As the window narrows it gives way in this order: the player's name and line (the
    // picture stays), the console's words (its dot stays), then the clock. Widths come from the words themselves, never from the row.
    readonly property real gap: 10 * u
    readonly property real spare: width - (brand.x + brand.width) - 24 * u - (34 * u + (shell.fullscreen || shell.mini ? 0 : (shell.frame.buttons || 0)))
        - 4 * 42 * u - (psnChip.visible ? 42 * u + gap : 0) - 4 * gap - 38 * u
    readonly property real statusWords: statusText.implicitWidth + 10 * u + (bar.strip.pad ? 28 * u : 0) + 30 * u - 38 * u + 9 * u
    readonly property real clockWidth: clockText.implicitWidth + gap
    readonly property bool showClock: spare >= clockWidth
    readonly property bool showStatusWords: spare >= clockWidth + statusWords
    readonly property bool showMe: spare >= clockWidth + statusWords + words.implicitWidth + 28 * u
    // The tabs close up when even the fewest things on the right would not fit beside them at their usual spacing (a narrow window).
    readonly property real labels: { var sum = 0; for (var i = 0; i < tabs.count; i++) { var tab = tabs.itemAt(i); if (tab) sum += tab.labelWidth } return sum }
    readonly property real rightLeast: 4 * 42 * u + (psnChip.visible ? 42 * u + gap : 0) + 4 * gap + 38 * u + 34 * u + (shell.fullscreen || shell.mini ? 0 : (shell.frame.buttons || 0))
    readonly property bool tight: brand.x + 48 * u + labels + tabs.count * 28 * u + (tabs.count + 1) * 12 * u + 24 * u + rightLeast > width

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.rgba(0, 0, 0, 0.72) }
            GradientStop { position: 1; color: Qt.rgba(0, 0, 0, 0) }
        }
    }
    Row {
        id: brand
        x: 40 * bar.u
        anchors.verticalCenter: parent.verticalCenter
        spacing: (bar.tight ? 4 : 12) * bar.u
        Image { source: Theme.icons ? Theme.icons + "playbridge.png" : ""; width: Math.round(30 * bar.u); height: width; sourceSize: Qt.size(Math.ceil(width * Screen.devicePixelRatio), Math.ceil(height * Screen.devicePixelRatio)); smooth: true; anchors.verticalCenter: parent.verticalCenter }
        Item { width: 18 * bar.u; height: 1 }
        Repeater {
            id: tabs
            model: [{ key: "games", label: "Games" }, { key: "live", label: "Live" }, { key: "media", label: "Media" }, { key: "friends", label: "Friends" }, { key: "trophies", label: "Trophies" }, { key: "stats", label: "Stats" }, { key: "files", label: "Files" }]
            delegate: Item {
                id: tab
                required property var modelData
                readonly property bool chosen: (bar.strip.tab || "") === modelData.key
                readonly property real labelWidth: label.implicitWidth
                width: label.implicitWidth + (bar.tight ? 12 : 28) * bar.u
                height: 44 * bar.u
                anchors.verticalCenter: parent.verticalCenter
                Text {
                    id: label
                    anchors.centerIn: parent
                    text: tab.modelData.label
                    color: tab.chosen ? Theme.text : area.containsMouse ? Theme.text : Theme.muted
                    font.family: tab.chosen ? Theme.strong : Theme.face
                    font.pixelSize: 19 * bar.u
                    Behavior on color { ColorAnimation { duration: Theme.ms(140) } }
                }
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.horizontalCenter: parent.horizontalCenter
                    height: 3 * bar.u
                    radius: height / 2
                    width: tab.chosen ? label.implicitWidth : 0
                    color: Theme.gold
                    Behavior on width { NumberAnimation { duration: Theme.ms(220); easing.type: Easing.OutCubic } }
                    layer.enabled: tab.chosen
                    layer.effect: MultiEffect { shadowEnabled: true; shadowColor: Theme.gold; shadowBlur: 0.6; shadowOpacity: 0.8; shadowVerticalOffset: 0; blurMax: 16 }
                }
                // New PSN messages: a gold dot beside Friends.
                Rectangle {
                    visible: tab.modelData.key === "friends" && (bar.strip.unread || 0) > 0
                    width: 8 * bar.u; height: width; radius: width / 2
                    color: Theme.gold
                    anchors.left: label.right; anchors.leftMargin: 3 * bar.u
                    anchors.top: label.top; anchors.topMargin: 2 * bar.u
                }
                MouseArea { id: area; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { Theme.keys = false; shell.act("tab", tab.modelData.key) } }
            }
        }
    }
    Row {
        anchors.right: parent.right
        // Clear of the window's own buttons in the top right corner while it has them.
        anchors.rightMargin: 34 * bar.u + (shell.fullscreen || shell.mini ? 0 : (shell.frame.buttons || 0))
        anchors.verticalCenter: parent.verticalCenter
        spacing: 10 * bar.u
        Rectangle {
            id: status
            visible: bar.spare >= 0
            height: 38 * bar.u
            width: bar.showStatusWords ? statusRow.implicitWidth + 30 * bar.u : height
            radius: height / 2
            anchors.verticalCenter: parent.verticalCenter
            color: Qt.rgba(1, 1, 1, 0.07)
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, 0.12)
            Row {
                id: statusRow
                anchors.centerIn: parent
                spacing: 10 * bar.u
                Rectangle {
                    id: dot
                    width: 9 * bar.u; height: width; radius: width / 2
                    anchors.verticalCenter: parent.verticalCenter
                    readonly property string state: (bar.strip.info || {}).state || "offline"
                    color: state === "online" ? Theme.online : state === "connecting" ? Theme.gold : Theme.dim
                    SequentialAnimation on opacity {
                        // Not over a game: an endless animation makes Qt redraw the window every frame.
                        running: dot.state === "connecting" && Theme.motion && shell.page !== "live"
                        loops: Animation.Infinite
                        alwaysRunToEnd: true
                        NumberAnimation { to: 0.25; duration: 650; easing.type: Easing.InOutSine }
                        NumberAnimation { to: 1; duration: 650; easing.type: Easing.InOutSine }
                    }
                }
                Text { id: statusText; visible: bar.showStatusWords; text: bar.strip.status || "Not connected"; color: Theme.text; font.family: Theme.face; font.pixelSize: 15 * bar.u; anchors.verticalCenter: parent.verticalCenter }
                Icon { visible: !!bar.strip.pad && bar.showStatusWords; name: "controller"; width: 18 * bar.u; height: width; anchors.verticalCenter: parent.verticalCenter; color: Theme.muted }
            }
        }
        Text { id: clockText; visible: bar.showClock; text: bar.strip.clock || ""; color: Theme.text; font.family: Theme.light; font.pixelSize: 21 * bar.u; anchors.verticalCenter: parent.verticalCenter; leftPadding: 8 * bar.u; rightPadding: 8 * bar.u }
        GlyphButton { id: searchButton; glyph: ""; tip: "Search"; u: bar.u; onClicked: shell.act("tab", "search") }
        GlyphButton { glyph: ""; tip: "Settings · Ctrl+,"; u: bar.u; lit: (bar.strip.selected || "") === "settings"; onClicked: shell.act("tab", "settings") }
        GlyphButton { glyph: shell.fullscreen ? "" : ""; tip: shell.page === "live" ? "Full screen · F11" : "Gaming Mode · Ctrl+G"; u: bar.u; onClicked: shell.act("tab", "fullscreen") }
        // The player: picture, name and how they stand on PSN. The name and line show when the bar has room for them beside the tabs.
        Rectangle {
            id: psnChip
            readonly property real side: 42 * bar.u
            readonly property bool roomy: bar.showMe
            visible: !!bar.me.state
            height: side
            width: roomy ? side + words.implicitWidth + 28 * bar.u : side
            radius: height / 2
            anchors.verticalCenter: parent.verticalCenter
            color: chipArea.containsMouse ? Qt.rgba(1, 1, 1, 0.16) : Qt.rgba(1, 1, 1, 0.07)
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, chipArea.containsMouse ? 0.4 : 0.12)
            Avatar {
                x: 3 * bar.u; y: 3 * bar.u
                width: psnChip.side - 6 * bar.u; height: width
                source: bar.me.picture || ""
                initial: bar.me.initial || ""
                tone: bar.me.tone || "off"
                ring: "#1B1D22"
            }
            Column {
                id: words
                visible: psnChip.roomy
                x: psnChip.side + 10 * bar.u
                anchors.verticalCenter: parent.verticalCenter
                spacing: 0
                Text { width: Math.min(implicitWidth, 200 * bar.u); elide: Text.ElideRight; text: bar.me.name || ""; color: Theme.text; font.family: Theme.strong; font.pixelSize: 16 * bar.u }
                // Online is green, playing too (a player in a game is online); offline and signed out stay grey.
                Text { width: Math.min(implicitWidth, 200 * bar.u); elide: Text.ElideRight; text: bar.me.line || ""; font.family: Theme.face; font.pixelSize: 13 * bar.u
                    color: bar.me.tone === "playing" || bar.me.tone === "online" ? Theme.online : Theme.muted }
            }
            MouseArea { id: chipArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { Theme.keys = false; shell.act("tab", "psn") } }
            ToolTip {
                visible: chipArea.containsMouse && !psnChip.roomy
                delay: 500
                popupType: Popup.Window
                y: psnChip.height + 8
                contentItem: Text { text: (bar.me.name || "PSN") + "  ·  " + (bar.me.line || ""); color: Theme.text; font.family: Theme.face; font.pixelSize: 12 }
                background: Rectangle { color: Theme.raised; radius: 6; border.color: Theme.line }
            }
        }
        GlyphButton { id: power; glyph: ""; tip: "Power"; u: bar.u; onClicked: shell.act("tab", "power") }
    }
}
