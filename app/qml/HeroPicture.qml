import QtQuick
import QtQuick.Effects

// One of the two pictures behind the Games page. A game with no art of its own shows its cover, far out of focus.
Image {
    id: picture
    property bool shown: false
    property bool soft: false
    signal arrived()
    anchors.fill: parent
    fillMode: Image.PreserveAspectCrop
    verticalAlignment: Image.AlignTop
    asynchronous: true
    cache: false
    smooth: true
    // Read whole: the art is drawn about 1.1 to 1.2 times the window, so a copy read at screen size and stretched up
    // looks soft, and asking for more than the file holds only enlarges it in the decoder.
    opacity: shown ? 1 : 0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: Theme.ms(650); easing.type: Easing.InOutQuad } }
    onStatusChanged: if (status === Image.Ready) arrived()
    layer.enabled: soft
    layer.effect: MultiEffect { blurEnabled: true; blur: 1.0; blurMax: 48; brightness: -0.25 }
}
