import QtQuick
import QtQuick.Effects

// A frosted panel: the window's picture, blurred once in Main, shows through it, under a dark tint, a rim lit from above and a soft shadow.
// follow: anything that moves the panel without changing its own x or y, such as a scroll, so the frost moves with it.
Item {
    id: glass
    property Item frost: null
    property real radius: 18
    property var follow: 0
    property color tint: Theme.glassTint
    property color rim: Theme.glassRim
    property bool shadow: true
    property real shine: 0.07

    RectangularShadow {
        anchors.fill: parent
        visible: glass.shadow
        radius: glass.radius
        blur: 30
        spread: 0
        offset.y: 10
        color: Qt.rgba(0, 0, 0, 0.55)
    }
    ShaderEffectSource {
        id: region
        anchors.fill: parent
        visible: false
        sourceItem: glass.frost
        hideSource: true
        live: true
        sourceRect: {
            glass.follow; glass.x; glass.y; glass.width; glass.height
            if (!glass.frost) return Qt.rect(0, 0, 0, 0)
            var p = glass.mapToItem(glass.frost, 0, 0)
            return Qt.rect(p.x, p.y, glass.width, glass.height)
        }
    }
    Rectangle {
        id: mask
        anchors.fill: parent
        radius: glass.radius
        visible: false
        layer.enabled: true
    }
    MultiEffect {
        anchors.fill: parent
        visible: glass.frost !== null
        source: region
        maskEnabled: true
        maskSource: mask
    }
    Rectangle {
        anchors.fill: parent
        radius: glass.radius
        color: glass.tint
        border.width: 1
        border.color: glass.rim
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, glass.shine) }
            GradientStop { position: 0.28; color: Qt.rgba(glass.tint.r, glass.tint.g, glass.tint.b, glass.tint.a) }
            GradientStop { position: 1.0; color: Qt.rgba(glass.tint.r * 0.8, glass.tint.g * 0.8, glass.tint.b * 0.8, Math.min(1, glass.tint.a + 0.08)) }
        }
    }
}
