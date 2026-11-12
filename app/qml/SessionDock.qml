import QtQuick
import QtQuick.Shapes
import QtQuick.Controls.Basic
import QtQuick.Dialogs

// The session panel beside the picture: frames per second, the source, the console with its actions, what arrives and a minute of it.
Rectangle {
    id: dock
    property var d: shell.dock
    property real u: 1
    color: "#08090C"
    border.width: 0
    Rectangle { width: 1; height: parent.height; color: Qt.rgba(1, 1, 1, 0.08) }

    Flickable {
        anchors.fill: parent
        anchors.margins: 14
        contentHeight: column.height + 20
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { width: 6; policy: ScrollBar.AsNeeded }
        Column {
            id: column
            width: parent.width
            spacing: 12
            Text { text: "Session"; color: Theme.text; font.family: Theme.light; font.pixelSize: 24; topPadding: 4 }
            Rectangle {
                width: parent.width; height: 230; radius: 16
                color: Theme.card; border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.07)
                Item {
                    id: ring
                    width: 124; height: 124
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: 16
                    readonly property real share: dock.d.fps === undefined || dock.d.fps === null ? 0 : Math.min(1, dock.d.fps / 60)
                    Shape {
                        anchors.fill: parent
                        preferredRendererType: Shape.CurveRenderer
                        ShapePath {
                            strokeColor: Qt.rgba(1, 1, 1, 0.1); strokeWidth: 9; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                            PathAngleArc { centerX: 62; centerY: 62; radiusX: 54; radiusY: 54; startAngle: 135; sweepAngle: 270 }
                        }
                        ShapePath {
                            strokeColor: Theme.gold; strokeWidth: 9; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                            PathAngleArc { centerX: 62; centerY: 62; radiusX: 54; radiusY: 54; startAngle: 135; sweepAngle: Math.max(0.1, 270 * ring.share); Behavior on sweepAngle { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } } }
                        }
                    }
                    Text { anchors.centerIn: parent; anchors.verticalCenterOffset: -6; text: dock.d.fps === undefined || dock.d.fps === null ? "—" : dock.d.fps; color: Theme.text; font.family: Theme.light; font.pixelSize: 36 }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; y: 80; text: "FPS"; color: Theme.muted; font.family: Theme.face; font.pixelSize: 12; font.letterSpacing: 2 }
                }
                Column {
                    anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                    anchors.margins: 16
                    spacing: 6
                    Repeater {
                        model: [["Source", dock.d.source || "—"], ["PC pipeline", dock.d.latency || "—"]]
                        delegate: Item {
                            required property var modelData
                            width: parent.width; height: 20
                            Text { text: modelData[0]; color: Theme.muted; font.family: Theme.face; font.pixelSize: 13 }
                            Text { anchors.right: parent.right; text: modelData[1]; color: Theme.text; font.family: Theme.strong; font.pixelSize: 13 }
                        }
                    }
                }
            }
            Rectangle {
                width: parent.width; height: consoleColumn.height + 28; radius: 16
                color: Theme.card; border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.07)
                Column {
                    id: consoleColumn
                    x: 14; y: 14; width: parent.width - 28
                    spacing: 6
                    Text { text: "Console"; color: Theme.muted; font.family: Theme.face; font.pixelSize: 13 }
                    Text { width: parent.width; text: dock.d.game || "Not connected"; color: Theme.text; font.family: Theme.light; font.pixelSize: 18; wrapMode: Text.WordWrap }
                    Text { width: parent.width; text: dock.d.readings || ""; visible: text !== ""; color: Theme.muted; font.family: Theme.face; font.pixelSize: 12; wrapMode: Text.WordWrap }
                    Grid {
                        width: parent.width
                        columns: 2
                        spacing: 6
                        topPadding: 4
                        Repeater {
                            model: [["Close game", "close"], ["Soft reset", "soft_reset"], ["Rest mode", "rest"], ["Reboot", "reboot"], ["Turn off", "off"], ["Recovery", "recovery"]]
                            delegate: PillButton {
                                required property var modelData
                                width: (consoleColumn.width - 6) / 2
                                height: 32
                                fontSize: 12
                                text: modelData[0]
                                onClicked: shell.act("power", modelData[1])
                            }
                        }
                    }
                }
            }
            Text { text: "Received  ·  " + (dock.d.rate || "—"); color: Theme.text; font.family: Theme.face; font.pixelSize: 13; topPadding: 6 }
            Canvas {
                id: graph
                width: parent.width; height: 70
                property var values: dock.d.history || []
                onValuesChanged: requestPaint()
                onPaint: {
                    var c = getContext("2d"); c.reset()
                    var w = width, h = 64
                    c.strokeStyle = "#2A2A2A"; c.lineWidth = 1
                    ;[8, 32, 58].forEach(function(y) { c.beginPath(); c.moveTo(0, y); c.lineTo(w, y); c.stroke() })
                    var v = values, top = 1
                    for (var i = 0; i < v.length; i++) if (v[i] > top) top = v[i]
                    top *= 1.15
                    var grad = c.createLinearGradient(0, 0, 0, h)
                    grad.addColorStop(0, "rgba(212,175,55,0.35)"); grad.addColorStop(1, "rgba(212,175,55,0)")
                    var started = false, first = 0, last = 0
                    c.beginPath()
                    for (var j = 0; j < v.length; j++) {
                        var x = w * (60 - v.length + j) / 59
                        if (v[j] < 0) continue
                        var y = 58 - v[j] / top * 50
                        if (!started) { c.moveTo(x, y); started = true; first = x } else c.lineTo(x, y)
                        last = x
                    }
                    if (started) {
                        c.strokeStyle = "#D4AF37"; c.lineWidth = 2; c.stroke()
                        c.lineTo(last, 58); c.lineTo(first, 58); c.closePath(); c.fillStyle = grad; c.fill()
                    }
                }
            }
            Text { text: "Last 60 seconds · media payload"; color: Theme.muted; font.family: Theme.face; font.pixelSize: 12 }
            Column {
                topPadding: 10
                spacing: 3
                Repeater { model: dock.d.details || []; delegate: Text { required property string modelData; text: modelData; color: Theme.muted; font.family: Theme.face; font.pixelSize: 12 } }
            }
            PillButton { width: parent.width; height: 38; fontSize: 13; text: "Export diagnostics"; onClicked: exportDialog.open() }
        }
    }
    FileDialog {
        id: exportDialog
        title: "Export diagnostics"
        fileMode: FileDialog.SaveFile
        nameFilters: ["ZIP archive (*.zip)"]
        defaultSuffix: "zip"
        onAccepted: shell.act("export", selectedFile.toString())
    }
}
