import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs

// The Files page: the PS5's folders through the FTP server a homebrew payload runs on it, on a sheet of glass over PlayBridge's picture.
// A click picks a file or folder, a double click or Enter opens a folder or shows a text file or picture; the bar under the list copies,
// renames and deletes what is picked. Files and folders dragged from Windows onto the page are sent into the folder on show.
FocusScope {
    id: page
    property real u: 1
    property real topInset: 0
    property Item frost: null
    property var f: shell.files || ({})
    readonly property var look: f.preview || null
    readonly property real side: Math.max(48, 64 * u)
    // "" or "folder" or "rename": the name field under the list.
    property string naming: ""

    function startNaming(kind) {
        page.naming = kind
        nameField.text = kind === "rename" ? (page.f.selected || "") : ""
        Qt.callLater(function() { nameField.activate() })
    }
    function finishNaming() {
        var text = nameField.text.trim()
        if (text !== "") {
            if (page.naming === "folder") shell.act("files_mkdir", text)
            else if (page.naming === "rename") shell.act("files_rename", [page.f.selected || "", text])
        }
        page.naming = ""
    }
    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Backspace && !nameField.activeFocus && !page.look) { shell.act("files_up", null); event.accepted = true }
    }

    Column {
        id: head
        x: page.side
        y: page.topInset + 24
        width: page.width - 2 * page.side
        spacing: 6
        Row {
            width: parent.width
            spacing: 14
            Text { id: title; text: "PS5 files"; color: Theme.text; font.family: Theme.light; font.pixelSize: 44 }
            Text { anchors.baseline: title.baseline; text: page.f.server || ""; color: Theme.dim; font.family: Theme.face; font.pixelSize: 14 }
        }
        Text {
            width: parent.width; wrapMode: Text.WordWrap; color: Theme.muted; font.family: Theme.face; font.pixelSize: 15
            text: "Through the FTP server your homebrew menu runs on the PS5. Copies to this PC go to Downloads\\PS5 and never replace a file there."
        }
    }

    // Places, and sending files from this PC into the folder on show.
    Row {
        id: places
        x: page.side
        anchors.top: head.bottom
        anchors.topMargin: 16
        spacing: 8
        Repeater {
            model: page.f.places || []
            delegate: PillButton {
                required property var modelData
                width: Math.max(88, implicitWidth); height: 40; tone: "ghost"; text: modelData.label
                selected: (page.f.path || "/") === modelData.path
                onClicked: shell.act("files_go", modelData.path)
            }
        }
    }
    Row {
        anchors.right: parent.right
        anchors.rightMargin: page.side
        anchors.verticalCenter: places.verticalCenter
        spacing: 8
        PillButton { width: 150; height: 40; text: "Send files here"; enabled: !!page.f.ready && !page.f.busy; onClicked: sendDialog.open() }
        PillButton { width: 130; height: 40; text: "New folder"; enabled: !!page.f.ready; onClicked: page.startNaming("folder") }
    }

    Glass {
        id: sheet
        frost: page.frost
        follow: page.x + page.opacity + list.contentY
        x: page.side
        anchors.top: places.bottom
        anchors.topMargin: 16
        anchors.bottom: foot.top
        anchors.bottomMargin: 14
        width: page.width - 2 * page.side
        radius: 20

        // Where it stands: up, the path in pieces, and read again.
        Row {
            id: crumbs
            x: 16; y: 12
            width: parent.width - 32
            height: 44
            spacing: 6
            GlyphButton { glyph: ""; tip: "Up · Backspace"; u: 1; enabled: !!page.f.canUp; opacity: enabled ? 1 : 0.35; onClicked: shell.act("files_up", null) }
            Item { width: 4; height: 1 }
            Repeater {
                model: page.f.crumbs || []
                delegate: Row {
                    required property var modelData
                    required property int index
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 6
                    Text { visible: index > 0; text: "›"; color: Theme.dim; font.family: Theme.face; font.pixelSize: 17 }
                    Text {
                        text: modelData.label
                        color: crumbArea.containsMouse ? Theme.goldSoft : index === (page.f.crumbs || []).length - 1 ? Theme.text : Theme.muted
                        font.family: index === (page.f.crumbs || []).length - 1 ? Theme.strong : Theme.face; font.pixelSize: 17
                        MouseArea { id: crumbArea; anchors.fill: parent; anchors.margins: -4; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: shell.act("files_go", modelData.path) }
                    }
                }
            }
        }
        GlyphButton { anchors.right: parent.right; anchors.rightMargin: 16; y: 13; anchors.verticalCenter: undefined; glyph: ""; tip: "Read again"; u: 1; onClicked: shell.act("files_refresh", null) }
        Rectangle { x: 16; y: 64; width: parent.width - 32; height: 1; color: Theme.glassRim }

        Text {
            visible: (page.f.empty || "") !== ""
            anchors.centerIn: parent
            width: parent.width - 80
            horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
            text: page.f.empty || ""; color: Theme.muted; font.family: Theme.face; font.pixelSize: 16
        }
        PillButton {
            visible: !page.f.ready && !page.f.loading
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.verticalCenter; anchors.topMargin: 50
            width: 200; height: 46; tone: "main"; text: "Try again"
            onClicked: shell.act("files_refresh", null)
        }
        ListView {
            id: list
            x: 10; y: 72
            width: parent.width - 20
            height: parent.height - y - 10
            clip: true
            spacing: 2
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { width: 8; policy: ScrollBar.AsNeeded }
            model: page.f.entries || []
            delegate: Item {
                id: row
                required property var modelData
                property bool navigable: true
                function activate() { Theme.keys = true; shell.act("files_open", row.modelData.name) }
                width: list.width - 10
                height: 48
                activeFocusOnTab: true
                onActiveFocusChanged: if (activeFocus) shell.act("files_select", row.modelData.name)
                Keys.onReturnPressed: activate()
                Keys.onEnterPressed: activate()
                Rectangle {
                    anchors.fill: parent; radius: 12
                    color: row.modelData.selected ? Qt.rgba(0.83, 0.69, 0.22, 0.16) : rowArea.containsMouse || row.activeFocus ? Qt.rgba(1, 1, 1, 0.07) : "transparent"
                    border.width: row.modelData.selected ? 1 : 0; border.color: Qt.rgba(0.83, 0.69, 0.22, 0.55)
                    Behavior on color { ColorAnimation { duration: Theme.ms(110) } }
                }
                MouseArea {
                    id: rowArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: { Theme.keys = false; shell.act("files_select", row.modelData.name) }
                    onDoubleClicked: { Theme.keys = false; shell.act("files_open", row.modelData.name) }
                }
                Text {
                    id: mark
                    x: 14; anchors.verticalCenter: parent.verticalCenter
                    text: row.modelData.link ? "" : row.modelData.folder ? "" : ""
                    color: row.modelData.folder ? Theme.goldSoft : Theme.muted
                    font.family: "Segoe MDL2 Assets"; font.pixelSize: 18
                }
                Text {
                    anchors.left: mark.right; anchors.leftMargin: 14
                    anchors.right: sizeText.left; anchors.rightMargin: 16
                    anchors.verticalCenter: parent.verticalCenter
                    elide: Text.ElideMiddle
                    text: row.modelData.name; color: Theme.text; font.family: Theme.face; font.pixelSize: 16
                }
                Text { id: sizeText; anchors.right: whenText.left; anchors.rightMargin: 24; anchors.verticalCenter: parent.verticalCenter; width: 90; horizontalAlignment: Text.AlignRight
                    text: row.modelData.size; color: Theme.muted; font.family: Theme.face; font.pixelSize: 14 }
                Text { id: whenText; anchors.right: parent.right; anchors.rightMargin: 16; anchors.verticalCenter: parent.verticalCenter; width: 160; horizontalAlignment: Text.AlignRight
                    text: row.modelData.when; color: Theme.dim; font.family: Theme.face; font.pixelSize: 13 }
                FocusGlow { on: row.activeFocus && Theme.keys; radius: 12 }
            }
        }
    }

    // What is picked and what can be done with it, or the copy that runs, and the last thing that happened.
    Column {
        id: foot
        x: page.side
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 26
        width: page.width - 2 * page.side
        spacing: 10
        Row {
            visible: page.naming !== ""
            width: parent.width
            spacing: 8
            Field {
                id: nameField
                width: parent.width - 236
                placeholderText: page.naming === "folder" ? "Name of the new folder" : "New name"
                onEntered: page.finishNaming()
                Keys.onEscapePressed: page.naming = ""
            }
            PillButton { width: 110; height: 46; tone: "main"; text: page.naming === "folder" ? "Make" : "Rename"; onClicked: page.finishNaming() }
            PillButton { width: 110; height: 46; text: "Cancel"; onClicked: page.naming = "" }
        }
        Row {
            visible: !!page.f.busy
            width: parent.width
            spacing: 14
            Column {
                width: parent.width - 124
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6
                Text { text: page.f.busyText || ""; color: Theme.text; font.family: Theme.face; font.pixelSize: 15 }
                Rectangle {
                    width: parent.width; height: 6; radius: 3; color: Qt.rgba(1, 1, 1, 0.12)
                    Rectangle { width: parent.width * Math.max(0, Math.min(1, page.f.share || 0)); height: parent.height; radius: 3; color: Theme.gold
                        Behavior on width { NumberAnimation { duration: Theme.ms(200) } } }
                }
            }
            PillButton { width: 110; height: 42; text: "Stop"; onClicked: shell.act("files_stop", null) }
        }
        Row {
            visible: !page.f.busy && page.naming === "" && (page.f.selected || "") !== ""
            spacing: 8
            Text { anchors.verticalCenter: parent.verticalCenter; width: Math.min(420, implicitWidth); elide: Text.ElideMiddle; text: page.f.selected || ""; color: Theme.goldSoft; font.family: Theme.strong; font.pixelSize: 16; rightPadding: 8 }
            PillButton { visible: !!page.f.selectedFolder; width: 100; height: 42; text: "Open"; onClicked: shell.act("files_open", page.f.selected) }
            PillButton { visible: !!page.f.selectedPreview && !page.look; width: 110; height: 42; text: "Preview"; onClicked: shell.act("files_preview", page.f.selected) }
            PillButton { width: 150; height: 42; tone: "main"; text: "Copy to this PC"; onClicked: shell.act("files_get", page.f.selected) }
            PillButton { width: 110; height: 42; text: "Rename"; onClicked: page.startNaming("rename") }
            PillButton { width: 100; height: 42; tone: "danger"; text: "Delete"; onClicked: shell.act("files_remove", page.f.selected) }
        }
        Row {
            visible: ((page.f.line || {}).text || "") !== ""
            spacing: 12
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: (page.f.line || {}).text || ""
                color: (page.f.line || {}).tone === "error" ? Theme.alert : (page.f.line || {}).tone === "news" ? Theme.goldSoft : Theme.muted
                font.family: Theme.face; font.pixelSize: 15
            }
            PillButton { visible: !!page.f.saved && (page.f.line || {}).tone === "news"; width: 150; height: 38; tone: "ghost"; text: "Show on this PC"; onClicked: shell.act("files_show", null) }
        }
    }

    // A look at a text file or a picture, over the list, without copying it. Esc or Close puts the list back.
    Rectangle {
        id: lookSheet
        visible: !!page.look
        x: sheet.x; y: sheet.y; width: sheet.width; height: sheet.height
        radius: 20
        color: "#0B0C10"
        border.width: 1; border.color: Theme.glassRim
        MouseArea { anchors.fill: parent }
        Row {
            id: lookHead
            x: 22; y: 16
            width: parent.width - 44
            height: 44
            spacing: 14
            Text { anchors.verticalCenter: parent.verticalCenter; width: Math.min(implicitWidth, parent.width - 420); elide: Text.ElideMiddle; text: page.look ? page.look.name : ""; color: Theme.text; font.family: Theme.strong; font.pixelSize: 19 }
            Text { anchors.verticalCenter: parent.verticalCenter; text: page.look ? page.look.size + (page.look.cut ? "  ·  the first 256 KB" : "") : ""; color: Theme.dim; font.family: Theme.face; font.pixelSize: 14 }
        }
        Row {
            anchors.right: parent.right; anchors.rightMargin: 22
            anchors.verticalCenter: lookHead.verticalCenter
            spacing: 8
            PillButton { width: 150; height: 40; tone: "main"; text: "Copy to this PC"; enabled: !page.f.busy; onClicked: shell.act("files_get", page.look ? page.look.name : "") }
            PillButton { width: 100; height: 40; text: "Close"; onClicked: shell.act("files_preview_close", null) }
        }
        Rectangle { x: 16; y: 70; width: parent.width - 32; height: 1; color: Theme.glassRim }
        Text {
            visible: !!page.look && (page.look.loading || page.look.why !== "")
            anchors.centerIn: parent
            width: parent.width - 120
            horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
            text: page.look ? (page.look.loading ? "Reading " + page.look.name + " from the PS5…" : page.look.why) : ""
            color: page.look && !page.look.loading ? Theme.alert : Theme.muted
            font.family: Theme.face; font.pixelSize: 16
        }
        ScrollView {
            id: textView
            visible: !!page.look && !page.look.loading && page.look.text !== ""
            x: 16; y: 80
            width: parent.width - 32; height: parent.height - y - 14
            clip: true
            TextArea {
                readOnly: true
                selectByMouse: true
                text: page.look ? page.look.text : ""
                color: Theme.text
                selectionColor: Qt.rgba(0.83, 0.69, 0.22, 0.45)
                font.family: "Consolas"; font.pixelSize: 14
                wrapMode: TextEdit.NoWrap
                background: null
            }
        }
        Image {
            id: lookImage
            visible: !!page.look && !page.look.loading && page.look.image !== ""
            x: 24; y: 86
            width: parent.width - 48; height: parent.height - y - 24
            source: page.look ? page.look.image : ""
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            cache: false
            smooth: true; mipmap: true
        }
        Text {
            visible: lookImage.visible && lookImage.status === Image.Error
            anchors.centerIn: parent
            text: "PlayBridge could not draw this picture. Copy it to this PC to open it."
            color: Theme.alert
            font.family: Theme.face; font.pixelSize: 16
        }
    }

    // Files and folders dragged from Windows: sent into the folder on show when they are let go over the page.
    DropArea {
        id: dropArea
        anchors.fill: parent
        onEntered: function(drag) {
            if (drag.hasUrls && !!page.f.ready && !page.f.busy) drag.accept(Qt.CopyAction)
            else drag.accepted = false
        }
        onDropped: function(drop) {
            if (!drop.hasUrls || !page.f.ready || page.f.busy) return
            shell.act("files_put", drop.urls.map(function(url) { return url.toString() }))
            drop.accept(Qt.CopyAction)
        }
    }
    Rectangle {
        visible: dropArea.containsDrag
        x: sheet.x; y: sheet.y; width: sheet.width; height: sheet.height
        radius: 20
        color: Qt.rgba(0.83, 0.69, 0.22, 0.12)
        border.width: 2; border.color: Theme.gold
        Column {
            anchors.centerIn: parent
            spacing: 12
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "\uE898"; font.family: "Segoe MDL2 Assets"; font.pixelSize: 46; color: Theme.gold }
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Drop to send to " + (page.f.path || "/") + " on your PS5"; color: Theme.text; font.family: Theme.light; font.pixelSize: 28 }
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Files and whole folders. PlayBridge asks before it replaces anything there."; color: Theme.muted; font.family: Theme.face; font.pixelSize: 15 }
        }
    }

    FileDialog {
        id: sendDialog
        title: "Send files to the PS5"
        fileMode: FileDialog.OpenFiles
        onAccepted: shell.act("files_put", selectedFiles.map(function(url) { return url.toString() }))
    }
}
