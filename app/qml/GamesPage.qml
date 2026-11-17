import QtQuick
import QtQuick.Window
import QtQuick.Effects
import PlayBridge.Classic

// The Games page as 1.5.x drew it. The classic drawing makes the page, bar, row, cards and menus included, as a clear picture shown one
// picture pixel to one screen pixel, and this page sends it the pointer, the clicks, the wheel and the keys. Under it the game's art,
// sharp and a little larger than the page, leans with the pointer or the right stick; the glass shows a frosted copy that moves with it.
FocusScope {
    id: page
    property real u: 1
    property real topInset: 0
    property Item frost: null
    property real follow: 0
    // Read by the window's menu and backdrop, which this page draws itself.
    property alias moreButton: moreAnchor
    // Where the pointer is, from -1 to 1 across and down the page.
    property point pointer: Qt.point(0, 0)
    Item { id: moreAnchor }

    readonly property real ratio: Screen.devicePixelRatio
    // The stick leans the art while it is pushed, the pointer otherwise. Without animations the art stays still.
    readonly property bool stick: shell.parallax.x !== 0 || shell.parallax.y !== 0
    readonly property real leanX: !Theme.motion ? 0 : stick ? shell.parallax.x : pointer.x
    readonly property real leanY: !Theme.motion ? 0 : stick ? shell.parallax.y : pointer.y
    property real driftX: -leanX * width * 0.035
    property real driftY: -leanY * height * 0.03
    Behavior on driftX { enabled: Theme.motion; SmoothedAnimation { velocity: 220 } }
    Behavior on driftY { enabled: Theme.motion; SmoothedAnimation { velocity: 180 } }
    // On whole screen pixels, so the art is never resampled and stays as sharp as its file.
    function snap(value) { return Math.round(value * ratio) / ratio }

    // The arrows, Enter and typing. Everything goes to the shelf, which answers with sounds and a new picture.
    Keys.onPressed: function(event) {
        var k = event.key
        // Ctrl+1, 2 and 3: the row, the grid and the list.
        if ((event.modifiers & Qt.ControlModifier) && k >= Qt.Key_1 && k <= Qt.Key_3) { shell.act("games_view", ["row", "grid", "list"][k - Qt.Key_1]); event.accepted = true; return }
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

    // The art or its frost, at its picture's own size.
    component Picture: ClassicArt {
        width: implicitWidth
        height: implicitHeight
    }
    // One of the two slots of the art. A new game's art comes in over the last one, which stays whole under it until it has, and only
    // then fades away, out of sight under the new.
    component Slot: Picture {
        property Item other: null
        x: page.snap((page.width - width) / 2 + page.driftX)
        y: page.snap((page.height - height) / 2 + page.driftY)
        z: shown ? 1 : 0
        opacity: shown || (other !== null && other.shown && other.opacity < 1) ? 1 : 0
        Behavior on opacity { enabled: Theme.motion; NumberAnimation { duration: Theme.ms(280); easing.type: Easing.InOutQuad } }
    }

    Rectangle { anchors.fill: parent; color: "black" }
    Item {
        anchors.fill: parent
        clip: true
        Slot { id: artA; role: "art"; slot: 0; other: artB }
        Slot { id: artB; role: "art"; slot: 1; other: artA }
        // Appearance › Colour › Backdrop: the game's art darker behind the tiles.
        Rectangle { anchors.fill: parent; z: 2; color: "black"; opacity: Theme.shade }
    }
    // The frosted art, moving with the art, and the shapes of the glass it shows through.
    Item {
        id: frostView
        anchors.fill: parent
        visible: false
        layer.enabled: true
        Picture { role: "frost"; slot: 0; x: artA.x; y: artA.y; opacity: artA.opacity; z: artA.z }
        Picture { role: "frost"; slot: 1; x: artB.x; y: artB.y; opacity: artB.opacity; z: artB.z }
    }
    Item {
        id: glassShape
        anchors.fill: parent
        visible: false
        layer.enabled: true
        Repeater {
            model: frame.glass
            Rectangle {
                x: modelData.x
                y: modelData.y
                width: modelData.w
                height: modelData.h
                radius: modelData.r
                color: "white"
                antialiasing: true
            }
        }
    }
    MultiEffect {
        anchors.fill: parent
        source: frostView
        visible: frame.glass.length > 0
        maskEnabled: true
        maskSource: glassShape
        maskThresholdMin: 0.5
        maskSpreadAtMin: 1.0
        autoPaddingEnabled: false
    }

    ClassicFrame {
        id: frame
        anchors.fill: parent
        function report() { if (width > 0 && height > 0) shell.act("classic_size", [width, height, page.ratio]) }
        onWidthChanged: report()
        onHeightChanged: report()
        Connections { target: page; function onRatioChanged() { frame.report() } }
        Component.onCompleted: report()
    }
    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        cursorShape: shell.classic.hand ? Qt.PointingHandCursor : Qt.ArrowCursor
        onPositionChanged: function(mouse) {
            page.pointer = Qt.point(mouse.x / Math.max(1, width) * 2 - 1, mouse.y / Math.max(1, height) * 2 - 1)
            shell.act("classic_pointer", [mouse.x, mouse.y])
        }
        onExited: { page.pointer = Qt.point(0, 0); shell.act("classic_pointer", null) }
        onPressed: function(mouse) {
            // The empty top of a window without a title bar is left to Windows, which moves the window from there.
            if (mouse.y < (shell.frame.top || 0) && !shell.classic.hand && !shell.fullscreen && !shell.mini) { mouse.accepted = false; return }
            page.forceActiveFocus()
        }
        onReleased: function(mouse) { shell.act("classic_release", [mouse.x, mouse.y]) }
        onWheel: function(wheel) { shell.act("move", wheel.angleDelta.y > 0 ? -1 : 1) }
    }
}
