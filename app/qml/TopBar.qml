import QtQuick
import QtQuick.Window
import QtQuick.Effects

// The bar over every page: the tabs, with a gold mark that slides between them, the console's state, the clock and the page buttons.
Item {
    id: bar
    property var strip: shell.top
    property real u: 1
    property Item powerButton: power
    implicitHeight: 76 * u

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
        spacing: 12 * bar.u
        Image { source: Theme.icons ? Theme.icons + "playbridge.png" : ""; width: Math.round(30 * bar.u); height: width; sourceSize: Qt.size(Math.ceil(width * Screen.devicePixelRatio), Math.ceil(height * Screen.devicePixelRatio)); smooth: true; anchors.verticalCenter: parent.verticalCenter }
        Item { width: 18 * bar.u; height: 1 }
        Repeater {
            id: tabs
            model: [{ key: "games", label: "Games" }, { key: "live", label: "Live" }, { key: "media", label: "Media" }]
            delegate: Item {
                id: tab
                required property var modelData
                readonly property bool chosen: (bar.strip.tab || "") === modelData.key
                width: label.implicitWidth + 28 * bar.u
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
                MouseArea { id: area; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { Theme.keys = false; shell.act("tab", tab.modelData.key) } }
            }
        }
    }
    Row {
        anchors.right: parent.right
        anchors.rightMargin: 34 * bar.u
        anchors.verticalCenter: parent.verticalCenter
        spacing: 10 * bar.u
        Rectangle {
            id: status
            height: 38 * bar.u
            width: statusRow.implicitWidth + 30 * bar.u
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
                Text { text: bar.strip.status || "Not connected"; color: Theme.text; font.family: Theme.face; font.pixelSize: 15 * bar.u; anchors.verticalCenter: parent.verticalCenter }
                Icon { visible: !!bar.strip.pad; name: "controller"; width: 18 * bar.u; height: width; anchors.verticalCenter: parent.verticalCenter; color: Theme.muted }
            }
        }
        Text { text: bar.strip.clock || ""; color: Theme.text; font.family: Theme.light; font.pixelSize: 21 * bar.u; anchors.verticalCenter: parent.verticalCenter; leftPadding: 8 * bar.u; rightPadding: 8 * bar.u }
        GlyphButton { glyph: ""; tip: "Search"; u: bar.u; onClicked: shell.act("tab", "search") }
        GlyphButton { glyph: ""; tip: "Settings · Ctrl+,"; u: bar.u; lit: (bar.strip.selected || "") === "settings"; onClicked: shell.act("tab", "settings") }
        GlyphButton { glyph: shell.fullscreen ? "" : ""; tip: shell.page === "live" ? "Full screen · F11" : "Gaming Mode · Ctrl+G"; u: bar.u; onClicked: shell.act("tab", "fullscreen") }
        GlyphButton { id: power; glyph: ""; tip: "Power"; u: bar.u; onClicked: shell.act("tab", "power") }
    }
}
