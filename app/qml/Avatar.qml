import QtQuick
import QtQuick.Window
import QtQuick.Effects

// A round picture of a PSN player, or the first letter of their name while it loads (a plain figure when there is no name either);
// a green dot says they are online (playing is online too). ring is the colour around the dot, the colour of what the picture lies on.
Item {
    id: avatar
    property string source: ""
    property string initial: "?"
    property string tone: "off"
    property color ring: "#15171C"
    width: 52; height: 52
    Rectangle {
        anchors.fill: parent; radius: width / 2; color: Theme.raised; visible: picture.status !== Image.Ready
        Text { visible: avatar.initial !== ""; anchors.centerIn: parent; text: avatar.initial; color: Theme.muted; font.family: Theme.strong; font.pixelSize: avatar.width * 0.42 }
        Item {
            visible: avatar.initial === ""
            anchors.fill: parent
            Rectangle { width: parent.width * 0.3; height: width; radius: width / 2; color: Theme.muted; anchors.horizontalCenter: parent.horizontalCenter; y: parent.height * 0.2 }
            Rectangle { width: parent.width * 0.56; height: parent.height * 0.26; radius: height / 2; color: Theme.muted; anchors.horizontalCenter: parent.horizontalCenter; y: parent.height * 0.56 }
        }
    }
    Image {
        id: picture
        anchors.fill: parent
        source: avatar.source
        sourceSize: Qt.size(Math.ceil(width * Screen.devicePixelRatio), Math.ceil(height * Screen.devicePixelRatio))
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: false
        visible: false
    }
    Rectangle { id: round; anchors.fill: parent; radius: width / 2; visible: false; layer.enabled: true }
    MultiEffect { anchors.fill: parent; source: picture; maskEnabled: true; maskSource: round; visible: picture.status === Image.Ready }
    Rectangle {
        visible: avatar.tone === "online" || avatar.tone === "playing"
        width: avatar.width * 0.3; height: width; radius: width / 2
        anchors.right: parent.right; anchors.bottom: parent.bottom
        color: Theme.online
        border.width: Math.max(2, avatar.width * 0.06); border.color: avatar.ring
    }
}
