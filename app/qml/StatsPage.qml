import QtQuick
import QtQuick.Controls.Basic

// The Stats page: your play this week, each game, and a year in numbers, as glass panels over PlayBridge's picture.
FocusScope {
    id: page
    property real u: 1
    property real topInset: 0
    property Item frost: null
    property var s: shell.stats || ({})
    readonly property real side: Math.max(48, 64 * u)

    component Tile: Glass {
        id: tile
        property string label: ""
        property string value: ""
        property string note: ""
        frost: page.frost
        follow: flick.contentY + page.x + page.opacity
        height: 132
        Column {
            x: 22; anchors.verticalCenter: parent.verticalCenter
            width: parent.width - 44
            spacing: 4
            Text { text: tile.label; color: Theme.muted; font.family: Theme.face; font.pixelSize: 14 }
            Text { text: tile.value; color: Theme.text; font.family: Theme.light; font.pixelSize: 38 }
            Text { width: parent.width; elide: Text.ElideRight; text: tile.note; color: Theme.dim; font.family: Theme.face; font.pixelSize: 13 }
        }
    }

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
            Column {
                spacing: 6
                width: parent.width
                Text { text: "Your play"; color: Theme.text; font.family: Theme.light; font.pixelSize: 44 }
                Text { width: parent.width; wrapMode: Text.WordWrap; color: Theme.muted; font.family: Theme.face; font.pixelSize: 16
                    text: (page.s.playing ? "Playing " + page.s.playing + " for " + page.s.playingText + " now. " : "") + "Counted by PlayBridge while it is connected to your PS5; the console's own total for each game stands beside it." }
            }
            // Nothing counted yet: what will appear here.
            Glass {
                visible: !!page.s.empty
                frost: page.frost
                follow: flick.contentY + page.x + page.opacity
                width: parent.width
                height: 220
                Column {
                    anchors.centerIn: parent
                    spacing: 12
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Your stats start with your next game"; color: Theme.text; font.family: Theme.light; font.pixelSize: 30 }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; horizontalAlignment: Text.AlignHCenter; color: Theme.muted; font.family: Theme.face; font.pixelSize: 16
                        text: "Play with PlayBridge connected, and your hours, sessions and trophies\nfor each day, each game and each year appear here." }
                }
            }
            Row {
                visible: !page.s.empty
                width: parent.width
                spacing: 18
                readonly property real tileWidth: (width - 3 * spacing) / 4
                Tile { width: parent.tileWidth; label: "Last 7 days"; value: page.s.weekText || "0 h"; note: (page.s.weekSessions || 0) + " sessions" }
                Tile { width: parent.tileWidth; label: "Trophies"; value: String(page.s.weekTrophies || 0); note: "In the last 7 days" }
                Tile { width: parent.tileWidth; label: "Days in a row"; value: String(page.s.streak || 0); note: (page.s.streak || 0) > 1 ? "Keep it going" : "Play today to start a streak" }
                Tile { width: parent.tileWidth; label: "Games"; value: String((page.s.games || []).length); note: "Played with PlayBridge" }
            }
            // The week, a bar for each day.
            Glass {
                visible: !page.s.empty
                frost: page.frost
                follow: flick.contentY + page.x + page.opacity
                width: parent.width
                height: 270
                Text { x: 24; y: 18; text: "This week"; color: Theme.text; font.family: Theme.strong; font.pixelSize: 18 }
                Row {
                    id: bars
                    x: 24; y: 58
                    width: parent.width - 48
                    height: parent.height - 82
                    spacing: 14
                    Repeater {
                        model: page.s.week || []
                        delegate: Item {
                            required property var modelData
                            width: (bars.width - 6 * bars.spacing) / 7
                            height: bars.height
                            Text { anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: bar.top; anchors.bottomMargin: 6; text: modelData.text; color: Theme.muted; font.family: Theme.face; font.pixelSize: 13 }
                            Rectangle {
                                id: bar
                                anchors.bottom: day.top; anchors.bottomMargin: 8
                                width: parent.width; radius: 8
                                height: Math.max(4, (parent.height - 50) * modelData.share)
                                color: modelData.label === "Today" ? Theme.gold : Qt.rgba(0.83, 0.69, 0.22, 0.55)
                                Behavior on height { NumberAnimation { duration: Theme.ms(300); easing.type: Easing.OutCubic } }
                            }
                            Text { id: day; anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; text: modelData.label; color: modelData.label === "Today" ? Theme.text : Theme.dim; font.family: Theme.face; font.pixelSize: 14 }
                        }
                    }
                }
            }
            Row {
                visible: !page.s.empty
                width: parent.width
                spacing: 22
                // Each game.
                Glass {
                    frost: page.frost
                    follow: flick.contentY + page.x + page.opacity
                    width: (parent.width - parent.spacing) * 0.58
                    height: Math.max(year.height, gameColumn.implicitHeight + 40)
                    Column {
                        id: gameColumn
                        x: 24; y: 20
                        width: parent.width - 48
                        spacing: 14
                        Text { text: "Your games"; color: Theme.text; font.family: Theme.strong; font.pixelSize: 18 }
                        Repeater {
                            model: page.s.games || []
                            delegate: Column {
                                required property var modelData
                                width: gameColumn.width
                                spacing: 5
                                Item {
                                    width: parent.width; height: 22
                                    Text { anchors.left: parent.left; anchors.right: total.left; anchors.rightMargin: 12; elide: Text.ElideRight; text: modelData.name; color: Theme.text; font.family: Theme.face; font.pixelSize: 16 }
                                    Text { id: total; anchors.right: parent.right; text: modelData.text; color: Theme.goldSoft; font.family: Theme.strong; font.pixelSize: 16 }
                                }
                                Rectangle { width: parent.width; height: 5; radius: 3; color: Qt.rgba(1, 1, 1, 0.08)
                                    Rectangle { width: parent.width * modelData.share; height: parent.height; radius: 3; color: Theme.gold } }
                                Text {
                                    width: parent.width; elide: Text.ElideRight; color: Theme.dim; font.family: Theme.face; font.pixelSize: 13
                                    text: modelData.sessions + (modelData.sessions === 1 ? " session" : " sessions") + "  ·  about " + modelData.average + " each  ·  longest " + modelData.longest
                                        + (modelData.console ? "  ·  " + modelData.console + " on the console" : "") + (modelData.trophies ? "  ·  " + modelData.trophies + " trophies" : "")
                                }
                            }
                        }
                    }
                }
                // A year in numbers.
                Glass {
                    id: year
                    property var info: page.s.year || ({})
                    frost: page.frost
                    follow: flick.contentY + page.x + page.opacity
                    width: (parent.width - parent.spacing) * 0.42
                    height: yearColumn.implicitHeight + 40
                    Column {
                        id: yearColumn
                        x: 24; y: 20
                        width: parent.width - 48
                        spacing: 12
                        Item {
                            width: parent.width; height: 34
                            Text { anchors.verticalCenter: parent.verticalCenter; text: (year.info.year || "") + (year.info.soFar ? " so far" : ""); color: Theme.text; font.family: Theme.strong; font.pixelSize: 18 }
                            Row {
                                anchors.right: parent.right
                                spacing: 6
                                Repeater {
                                    model: (page.s.years || []).length > 1 ? page.s.years : []
                                    delegate: PillButton { required property var modelData; text: String(modelData); tone: "ghost"; width: 74; height: 34; fontSize: 13; selected: modelData === year.info.year; onClicked: shell.act("stats_year", modelData) }
                                }
                            }
                        }
                        Text { text: year.info.hours || "0 h"; color: Theme.gold; font.family: Theme.light; font.pixelSize: 52 }
                        Text { width: parent.width; wrapMode: Text.WordWrap; color: Theme.muted; font.family: Theme.face; font.pixelSize: 15
                            text: (year.info.days || 0) + " days with play, " + (year.info.sessions || 0) + " sessions, " + (year.info.games || 0) + " games and " + (year.info.trophies || 0) + " trophies." }
                        Text { visible: !!year.info.month; width: parent.width; wrapMode: Text.WordWrap; color: Theme.muted; font.family: Theme.face; font.pixelSize: 15; text: "Your busiest month was " + (year.info.month || "") + "." }
                        Text { visible: !!year.info.longest; width: parent.width; wrapMode: Text.WordWrap; color: Theme.muted; font.family: Theme.face; font.pixelSize: 15
                            text: year.info.longest ? "Longest session: " + year.info.longest.text + " of " + year.info.longest.name + ", on " + year.info.longest.when + "." : "" }
                        Item { width: 1; height: 4 }
                        Text { text: "Most played"; color: Theme.text; font.family: Theme.strong; font.pixelSize: 15 }
                        Repeater {
                            model: year.info.top || []
                            delegate: Row {
                                required property var modelData
                                required property int index
                                width: yearColumn.width
                                spacing: 10
                                Text { width: 22; text: (index + 1) + "."; color: Theme.dim; font.family: Theme.face; font.pixelSize: 15 }
                                Text { width: parent.width - 22 - 70 - 20; elide: Text.ElideRight; text: modelData.name; color: Theme.text; font.family: Theme.face; font.pixelSize: 15 }
                                Text { width: 70; horizontalAlignment: Text.AlignRight; text: modelData.text; color: Theme.goldSoft; font.family: Theme.face; font.pixelSize: 15 }
                            }
                        }
                    }
                }
            }
        }
    }
}
