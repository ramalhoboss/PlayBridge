import QtQuick
import QtQuick.Window
import QtQuick.Effects

// The live view: the picture (a native window of its own, placed over videoArea), the session panel, the footer and the line under it.
// While no picture comes, a slow ambient light and the reason fill the stage.
FocusScope {
    id: page
    property real u: 1
    property real topInset: 0
    readonly property bool bare: shell.fullscreen || shell.mini
    readonly property bool dockShown: !!shell.bar.session && !bare
    property bool settled: true

    Rectangle { anchors.fill: parent; color: "#030304" }

    Item {
        id: stage
        anchors.top: parent.top
        anchors.topMargin: page.bare ? 0 : page.topInset
        anchors.left: parent.left
        anchors.right: page.dockShown ? dock.left : parent.right
        anchors.rightMargin: page.dockShown ? 10 : 0
        anchors.bottom: page.bare ? parent.bottom : footer.top
        anchors.bottomMargin: page.bare ? 0 : 6
        // The top bar grows with the window, which moves the stage down without changing its size, so the picture follows the stage's
        // own place too, not only the area's size.
        onXChanged: videoArea.report()
        onYChanged: videoArea.report()

        Item {
            id: ambient
            anchors.fill: parent
            // Above the video area, whose handlers would otherwise take the clicks meant for Connect while no picture shows.
            z: 1
            visible: opacity > 0
            opacity: shell.stage.waiting ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.ms(400) } }
            clip: true
            Rectangle {
                id: blue
                width: parent.width * 0.7; height: width; radius: width / 2
                color: "#1A3A9A"
                opacity: 0.55
                x: parent.width * 0.45 - width / 2; y: parent.height * 0.25 - height / 2
                SequentialAnimation on x {
                    running: Theme.motion && ambient.visible; loops: Animation.Infinite
                    NumberAnimation { to: ambient.width * 0.62 - blue.width / 2; duration: 9000; easing.type: Easing.InOutSine }
                    NumberAnimation { to: ambient.width * 0.45 - blue.width / 2; duration: 9000; easing.type: Easing.InOutSine }
                }
                layer.enabled: true
                layer.effect: MultiEffect { blurEnabled: true; blur: 1.0; blurMax: 64 }
            }
            Rectangle {
                id: violet
                width: parent.width * 0.5; height: width; radius: width / 2
                color: "#4A1A78"
                opacity: 0.5
                x: parent.width * 0.85 - width / 2; y: parent.height * 0.8 - height / 2
                SequentialAnimation on y {
                    running: Theme.motion && ambient.visible; loops: Animation.Infinite
                    NumberAnimation { to: ambient.height * 0.62 - violet.height / 2; duration: 11000; easing.type: Easing.InOutSine }
                    NumberAnimation { to: ambient.height * 0.8 - violet.height / 2; duration: 11000; easing.type: Easing.InOutSine }
                }
                layer.enabled: true
                layer.effect: MultiEffect { blurEnabled: true; blur: 1.0; blurMax: 64 }
            }
            Rectangle { anchors.fill: parent; color: Qt.rgba(0, 0, 0, 0.35) }
            Column {
                anchors.centerIn: parent
                spacing: 22
                width: Math.min(parent.width - 80, 760)
                Item {
                    width: 84; height: 84
                    anchors.horizontalCenter: parent.horizontalCenter
                    Rectangle {
                        anchors.centerIn: parent
                        width: 84; height: 84; radius: 42
                        color: "transparent"; border.width: 2; border.color: Theme.gold
                        opacity: 0.8
                        SequentialAnimation on scale { running: Theme.motion && ambient.visible; loops: Animation.Infinite; NumberAnimation { from: 0.7; to: 1.25; duration: 1800; easing.type: Easing.OutCubic } }
                        SequentialAnimation on opacity { running: Theme.motion && ambient.visible; loops: Animation.Infinite; NumberAnimation { from: 0.9; to: 0; duration: 1800; easing.type: Easing.OutCubic } }
                    }
                    Image { anchors.centerIn: parent; source: Theme.icons ? Theme.icons + "playbridge.png" : ""; width: 46; height: 46; sourceSize: Qt.size(Math.ceil(width * Screen.devicePixelRatio), Math.ceil(height * Screen.devicePixelRatio)); smooth: true }
                }
                Text {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    text: shell.stage.text || ""
                    color: Theme.text
                    font.family: Theme.light
                    font.pixelSize: 24
                }
                PillButton {
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: !shell.bar.active
                    text: "Connect"
                    icon: "connect"
                    tone: "main"
                    onClicked: shell.act("connect", null)
                }
            }
        }

        // Where the picture goes. The native video window follows this rectangle.
        Item {
            id: videoArea
            objectName: "videoArea"
            anchors.fill: parent
            function report() {
                if (!page.visible) return
                var p = videoArea.mapToItem(null, 0, 0)
                shell.placeVideo(p.x, p.y, videoArea.width, videoArea.height)
            }
            onWidthChanged: report()
            onHeightChanged: report()
            onXChanged: report()
            onYChanged: report()
            Component.onCompleted: report()
            Connections { target: page; function onVisibleChanged() { videoArea.report() } function onSettledChanged() { videoArea.report() } }
            Connections { target: shell; function onFullscreenChanged() { Qt.callLater(videoArea.report) } function onMiniChanged() { Qt.callLater(videoArea.report) } }
            TapHandler { onDoubleTapped: shell.act("video_double", null) }
            HoverHandler { onPointChanged: shell.act("pointer", null) }
        }
    }

    SessionDock {
        id: dock
        visible: page.dockShown
        width: 270
        anchors.top: parent.top
        anchors.topMargin: page.topInset
        anchors.bottom: footer.top
        anchors.right: parent.right
        u: page.u
    }

    // The footer: sound, the capture tools, the session panel and the connection.
    Item {
        id: footer
        visible: !page.bare
        height: page.bare ? 0 : 58
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: message.top
        anchors.leftMargin: 18
        anchors.rightMargin: 18
        Row {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10
            RoundTool { icon: shell.bar.muted ? "muted" : "speaker"; tip: "Mute / unmute"; onClicked: shell.act("mute", null) }
            LuxSlider {
                width: 110
                anchors.verticalCenter: parent.verticalCenter
                from: 0; to: 1
                value: shell.bar.volume !== undefined ? shell.bar.volume : 1
                onMoved: shell.act("volume", value)
            }
            Choice {
                visible: page.width >= 1120
                width: 220
                height: 36
                fontSize: 13
                anchors.verticalCenter: parent.verticalCenter
                model: shell.bar.outputs || []
                value: shell.bar.output || ""
                onPicked: function(value) { shell.act("output", value) }
            }
        }
        Row {
            anchors.centerIn: parent
            spacing: 8
            RoundTool { icon: "camera"; tip: "Screenshot · F8"; onClicked: shell.act("screenshot", null) }
            RoundTool { icon: "record"; iconColor: shell.bar.recording ? Theme.text : "#FF6470"; lit: !!shell.bar.recording; tip: "Start / stop recording · F9"; onClicked: shell.act("record", null) }
            RoundTool { icon: "replay"; tip: "Save the last moments · F10"; onClicked: shell.act("replay", null) }
            RoundTool { icon: "folder"; tip: "Your captures · Ctrl+L"; onClicked: shell.act("page", "media") }
            RoundTool { icon: "mini"; tip: "Small window on top · Ctrl+M"; onClicked: shell.act("mini", null) }
            RoundTool { icon: "live"; iconColor: shell.bar.onAir ? Theme.danger : Theme.text; lit: !!shell.bar.onAir; tip: "Go live · Ctrl+B"; onClicked: shell.act("live", null) }
            PillButton { text: "Session"; height: 42; width: 100; fontSize: 14; selected: !!shell.bar.session; onClicked: shell.act("session", null) }
        }
        Row {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 14
            Text { visible: page.width >= 1300; text: shell.bar.host || ""; color: Theme.muted; font.family: Theme.face; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
            PillButton {
                text: shell.bar.active ? "Disconnect" : "Connect"
                icon: shell.bar.active ? "disconnect" : "connect"
                tone: "main"
                width: 140
                height: 42
                fontSize: 14
                onClicked: shell.act("connect", null)
            }
        }
    }
    Text {
        id: message
        visible: !page.bare
        height: page.bare ? 0 : 26
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: 22
        anchors.rightMargin: 22
        verticalAlignment: Text.AlignTop
        elide: Text.ElideRight
        text: shell.message.text || ""
        color: shell.message.tone === "error" ? "#FFAAA5" : Theme.tone(shell.message.tone)
        font.family: Theme.face
        font.pixelSize: 12
    }
}
