import QtQuick

// Explanatory words under a control: muted, wrapped, a size down.
Text {
    property string tone: "plain"
    width: parent ? parent.width : implicitWidth
    wrapMode: Text.WordWrap
    color: Theme.tone(tone)
    font.family: Theme.face
    font.pixelSize: 14
    lineHeight: 1.15
    visible: text !== ""
}
