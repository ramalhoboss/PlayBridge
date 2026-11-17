pragma Singleton
import QtQuick

// PlayBridge's colours and type, the same as the Tk window's, and whether the gold focus ring is wanted (keys or controller in use).
QtObject {
    readonly property color bg: "#000000"
    readonly property color card: "#141414"
    readonly property color raised: "#232323"
    readonly property color line: "#2A2A2A"
    // Appearance › Colour: the accent (still called gold here) and how dark the picture behind the pages is. Main.qml sets them.
    property color gold: "#D4AF37"
    property color goldSoft: "#EBD48E"
    property color goldHover: "#E2C25A"
    property real shade: 0
    readonly property color ink: "#101010"
    readonly property color text: "#FFFFFF"
    // Appearance › Text and contrast: text a size or two up, and stronger contrast. Main.qml sets them from the preferences.
    property real textScale: 1
    property bool contrast: false
    readonly property color muted: contrast ? "#E8E8E8" : "#BDBDBD"
    readonly property color dim: contrast ? "#D0D0D0" : "#8C8C8C"
    readonly property color alert: "#FF9C9C"
    readonly property color danger: "#FF5A64"
    readonly property color online: "#5BE38C"
    readonly property color glassTint: contrast ? Qt.rgba(0.015, 0.015, 0.02, 0.92) : Qt.rgba(0.055, 0.06, 0.085, 0.58)
    readonly property color glassRim: contrast ? Qt.rgba(1, 1, 1, 0.6) : Qt.rgba(1, 1, 1, 0.12)
    readonly property string face: "Segoe UI"
    readonly property string light: "Segoe UI Semilight"
    readonly property string strong: "Segoe UI Semibold"
    // True after a key or the controller moved the focus, false after the mouse was used: the ring shows only for the first.
    property bool keys: false
    property bool motion: true
    property string icons: ""
    // The dropdown whose list is open, which takes the controller's moves until it closes.
    property var openChoice: null
    function tone(name) { return name === "error" ? alert : name === "news" ? goldSoft : muted }
    function ms(value) { return motion ? value : 0 }
    function px(size) { return Math.round(size * textScale) }
    // The accent with see-through, for fills, rims and glows; css() is the same for a Canvas.
    function glow(alpha) { return Qt.rgba(gold.r, gold.g, gold.b, alpha) }
    function css(alpha) { return "rgba(" + Math.round(gold.r * 255) + "," + Math.round(gold.g * 255) + "," + Math.round(gold.b * 255) + "," + alpha + ")" }
}
