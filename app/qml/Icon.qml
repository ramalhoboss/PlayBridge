import QtQuick
import QtQuick.Window
import QtQuick.Effects

// One of the app's white icons, in any colour.
Item {
    id: icon
    property string name: ""
    property color color: Theme.text
    implicitWidth: 20
    implicitHeight: 20
    Image {
        id: picture
        anchors.fill: parent
        source: icon.name && Theme.icons ? Theme.icons + icon.name + ".png" : ""
        // Read at the size it shows, so a small icon is sharp instead of a big one filtered down.
        sourceSize: Qt.size(Math.max(1, Math.ceil(icon.width * Screen.devicePixelRatio)), Math.max(1, Math.ceil(icon.height * Screen.devicePixelRatio)))
        smooth: true
        visible: false
    }
    MultiEffect {
        anchors.fill: parent
        source: picture
        visible: icon.name !== ""
        colorization: 1.0
        colorizationColor: icon.color
        brightness: icon.color.hslLightness < 0.3 ? -0.9 : 0.0
    }
}
