import QtQuick

// A trophy cup in its grade's colour (platinum, gold, silver, bronze), drawn rather than taken from a font. colour, when set, wins.
Canvas {
    id: cup
    property string grade: "bronze"
    property bool lit: true
    property color colour: "transparent"
    readonly property color ink: colour.a > 0 ? colour : grade === "platinum" ? "#B0C8E8" : grade === "gold" ? "#E0B85A" : grade === "silver" ? "#C4C6CE" : grade === "bronze" ? "#C88050" : "#969696"
    width: 20; height: 20
    onInkChanged: requestPaint()
    onLitChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        var c = getContext("2d"), w = width, h = height
        c.reset()
        c.globalAlpha = lit ? 1 : 0.35
        c.fillStyle = ink
        c.strokeStyle = ink
        c.beginPath(); c.moveTo(w * 0.24, h * 0.1); c.lineTo(w * 0.76, h * 0.1)
        c.quadraticCurveTo(w * 0.78, h * 0.56, w * 0.5, h * 0.6); c.quadraticCurveTo(w * 0.22, h * 0.56, w * 0.24, h * 0.1); c.fill()
        c.lineWidth = Math.max(1.2, w * 0.08)
        c.beginPath(); c.arc(w * 0.24, h * 0.26, w * 0.13, Math.PI * 0.5, Math.PI * 1.5); c.stroke()
        c.beginPath(); c.arc(w * 0.76, h * 0.26, w * 0.13, -Math.PI * 0.5, Math.PI * 0.5); c.stroke()
        c.fillRect(w * 0.45, h * 0.58, w * 0.1, h * 0.2)
        c.fillRect(w * 0.28, h * 0.78, w * 0.44, h * 0.12)
    }
}
