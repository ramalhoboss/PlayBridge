pragma Singleton
import QtQuick

// PlayBridge's colours and type, the same as the Tk window's, and whether the gold focus ring is wanted (keys or controller in use).
QtObject {
    readonly property color bg: "#000000"
    readonly property color card: "#141414"
    readonly property color raised: "#232323"
    readonly property color line: "#2A2A2A"
    readonly property color gold: "#D4AF37"
    readonly property color goldSoft: "#EBD48E"
    readonly property color goldHover: "#E2C25A"
    readonly property color ink: "#101010"
    readonly property color text: "#FFFFFF"
    readonly property color muted: "#BDBDBD"
    readonly property color dim: "#8C8C8C"
    readonly property color alert: "#FF9C9C"
    readonly property color danger: "#FF5A64"
    readonly property color online: "#5BE38C"
    readonly property color glassTint: Qt.rgba(0.055, 0.06, 0.085, 0.58)
    readonly property color glassRim: Qt.rgba(1, 1, 1, 0.12)
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
}
