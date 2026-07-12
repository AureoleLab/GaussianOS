import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtWebEngine

ApplicationWindow {
    id: window
    visible: true
    width: 1540; height: 920
    minimumWidth: 1180; minimumHeight: 720
    title: "Gaussian Factory"
    color: "#151920"
    palette.window: "#151920"
    palette.windowText: "#dce3ec"
    palette.base: "#11151b"
    palette.alternateBase: "#1b2029"
    palette.text: "#dce3ec"
    palette.button: "#252c36"
    palette.buttonText: "#dce3ec"
    palette.highlight: "#3f8cff"
    palette.highlightedText: "#ffffff"

    property var current: JSON.parse(backend.currentJson || "{}")
    property bool logsOpen: true
    readonly property color panel: "#1a1f27"
    readonly property color line: "#303845"
    readonly property color muted: "#98a4b3"
    readonly property color accent: "#4c97ff"

    function statusColor(status) {
        if (status === "succeeded") return "#54c88a"
        if (status === "skipped") return "#8290a2"
        if (status === "running") return "#4c97ff"
        if (status === "failed") return "#ef6b73"
        if (status === "interrupted") return "#e5ad55"
        if (status === "fallback_required") return "#e5ad55"
        return "#687587"
    }
    function stageState(name) { return (current.stages || {})[name] || {"status":"pending"} }

    Connections {
        target: backend
        function onChanged() { current = JSON.parse(backend.currentJson || "{}") }
        function onAcceptanceRequested() {
            viewer.runJavaScript("var before=acceptance.snapshot(); acceptance.orbit(0.03,-0.01); acceptance.pan(0.005,-0.003); acceptance.zoom(0.98); acceptance.walk(0.005); acceptance.motionTest(1800); JSON.stringify({before:before,after:acceptance.snapshot()})", function(result) { backend.viewerAcceptanceResult(result) })
        }
    }
    FileDialog {
        id: inputPicker; title: "Import video"
        nameFilters: ["Video files (*.mp4 *.mov *.mkv *.avi *.webm)", "All files (*)"]
        onAccepted: backend.importInput(selectedFile.toLocalFile())
    }
    FolderDialog { id: folderPicker; title: "Import image folder"; onAccepted: backend.importInput(selectedFolder.toLocalFile()) }
    Dialog {
        id: projectDialog; title: "New project"; modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        contentItem: ColumnLayout {
            implicitWidth: 460
            spacing: 10
            Label { text: "PROJECT NAME"; color: muted; font.pixelSize: 11 }
            TextField { id: projectName; placeholderText: "My reconstruction"; Layout.fillWidth: true }
            Label { text: "WORKING FOLDER"; color: muted; font.pixelSize: 11 }
            TextField { id: projectRoot; placeholderText: "D:/Projects/my-scan"; Layout.fillWidth: true }
        }
        onAccepted: backend.createProject(projectName.text, projectRoot.text)
    }
    Dialog {
        id: settingsDialog; title: "Settings"; modal: true; standardButtons: Dialog.Close; width: 500
        contentItem: Label { width: 460; text: "Runtime paths are discovered from the locked P2 environment.\nRenderer: Qt WebEngine · WebGL2"; padding: 18 }
    }

    header: Rectangle {
        height: 54; color: "#1c222b"; border.color: line
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14; spacing: 7
            Label { text: "GF"; font.bold: true; font.pixelSize: 17; color: accent }
            Label { text: "Gaussian Factory"; font.bold: true; font.pixelSize: 15; Layout.rightMargin: 14 }
            ToolButton { text: "New Project"; onClicked: projectDialog.open() }
            ToolButton { text: "Import Video"; enabled: !!current.project_id; onClicked: inputPicker.open() }
            ToolButton { text: "Import Images"; enabled: !!current.project_id; onClicked: folderPicker.open() }
            Rectangle { width: 1; height: 24; color: line; Layout.leftMargin: 4; Layout.rightMargin: 4 }
            Button { text: current.status === "interrupted" ? "Resume" : "Run"; enabled: !!current.input_path && current.status !== "running"; highlighted: true; onClicked: backend.start() }
            Button { text: "Cancel"; enabled: current.status === "running"; onClicked: backend.cancel() }
            Button { text: "Export"; enabled: stageState("export").status === "succeeded"; onClicked: backend.openExportFolder() }
            Item { Layout.fillWidth: true }
            Label { text: current.name || "No project"; color: muted; elide: Text.ElideRight; Layout.maximumWidth: 260 }
            Rectangle { width: 8; height: 8; radius: 4; color: statusColor(current.status || "idle") }
            Label { text: (current.status || "idle").toUpperCase(); font.bold: true; color: statusColor(current.status || "idle") }
            ToolButton { text: "Settings"; onClicked: settingsDialog.open() }
        }
    }

    ColumnLayout {
        anchors.fill: parent; spacing: 0
        SplitView {
            Layout.fillWidth: true; Layout.fillHeight: true; orientation: Qt.Horizontal
            Rectangle {
                SplitView.preferredWidth: 248; SplitView.minimumWidth: 210; color: panel
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 10; spacing: 8
                    Label { text: "PROJECTS"; color: muted; font.bold: true; font.pixelSize: 11 }
                    ListView {
                        id: projectList; Layout.fillWidth: true; Layout.preferredHeight: 220; clip: true
                        model: JSON.parse(backend ? (backend.projectsJson || "[]") : "[]"); spacing: 3
                        delegate: ItemDelegate {
                            required property var modelData
                            width: projectList.width; height: 48
                            highlighted: modelData.project_id === current.project_id
                            onClicked: backend.selectProject(modelData.project_id)
                            contentItem: Column {
                                spacing: 3
                                Label { width: parent.width; text: modelData.name; font.bold: true; elide: Text.ElideRight }
                                Label { text: modelData.status.toUpperCase() + "  ·  " + Math.round((modelData.progress || 0) * 100) + "%"; color: statusColor(modelData.status); font.pixelSize: 10 }
                            }
                        }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: line }
                    Label { text: "ARTIFACTS"; color: muted; font.bold: true; font.pixelSize: 11 }
                    ListView {
                        id: artifactList; Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        model: current.artifacts || []
                        delegate: ItemDelegate {
                            required property string modelData
                            width: artifactList.width; height: 34
                            text: modelData.split(/[\\/]/).pop(); ToolTip.visible: hovered; ToolTip.text: modelData
                        }
                        Label { anchors.centerIn: parent; width: parent.width - 20; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap; color: muted; visible: artifactList.count === 0; text: current.project_id ? "Artifacts appear here as stages complete" : "Create or select a project" }
                    }
                }
            }

            Rectangle {
                SplitView.fillWidth: true; SplitView.minimumWidth: 560; color: "#0f1319"
                WebEngineView { id: viewer; objectName: "gaussianViewer"; anchors.fill: parent; url: backend ? backend.viewerUrl : "about:blank"; focus: true; onTitleChanged: { if (backend) backend.viewerPageTitle(title) } }
                Column {
                    anchors.centerIn: parent; spacing: 10; visible: !backend || backend.viewerUrl === "about:blank"
                    Label { anchors.horizontalCenter: parent.horizontalCenter; text: current.project_id ? "3D VIEWER" : "NO PROJECT SELECTED"; font.pixelSize: 19; font.bold: true; color: "#cad3df" }
                    Label { width: 440; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap; color: muted; text: backend ? backend.viewerStatus : "" }
                    Button { anchors.horizontalCenter: parent.horizontalCenter; visible: stageState("validate").status === "succeeded"; text: "Reload Viewer"; onClicked: backend.loadViewer() }
                }
                Rectangle {
                    anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                    height: 27; color: "#141921e8"
                    Label { anchors.fill: parent; anchors.leftMargin: 9; verticalAlignment: Text.AlignVCenter; color: muted; elide: Text.ElideRight; text: backend ? backend.viewerStatus : "" }
                }
            }

            Rectangle {
                SplitView.preferredWidth: 286; SplitView.minimumWidth: 250; color: panel
                ScrollView {
                    anchors.fill: parent; contentWidth: availableWidth
                    ColumnLayout {
                        width: parent.width; spacing: 12
                        Label { text: "RECONSTRUCTION PROFILE"; color: muted; font.bold: true; font.pixelSize: 11; Layout.topMargin: 12; Layout.leftMargin: 12 }
                        ComboBox { id: mode; Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; model: ["preview", "balanced", "quality"]; currentIndex: Math.max(0, model.indexOf(current.profile || "balanced")); enabled: current.status !== "running"; onActivated: backend.setProfile(currentText) }
                        Label { Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; wrapMode: Text.Wrap; color: muted; text: mode.currentText === "preview" ? "Fast iteration · 1,000 steps · 3 fps" : mode.currentText === "quality" ? "Maximum quality · 7,000 steps · 15 fps" : "Recommended balance · 3,000 steps · 8 fps" }
                        Rectangle { Layout.fillWidth: true; height: 1; color: line }
                        Label { text: "QUALITY & STATUS"; color: muted; font.bold: true; font.pixelSize: 11; Layout.leftMargin: 12 }
                        GridLayout {
                            columns: 2; columnSpacing: 12; rowSpacing: 8; Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12
                            Label { text: "Progress"; color: muted } Label { text: Math.round((current.progress || 0) * 100) + "%"; font.bold: true; Layout.alignment: Qt.AlignRight }
                            Label { text: "Current stage"; color: muted } Label { text: current.current_stage || "—"; color: accent; Layout.alignment: Qt.AlignRight }
                            Label { text: "Gaussians"; color: muted } Label { text: (stageState("validate").metrics || {}).gaussian_count || "—"; Layout.alignment: Qt.AlignRight }
                            Label { text: "Profile"; color: muted } Label { text: (current.profile || "balanced").toUpperCase(); Layout.alignment: Qt.AlignRight }
                        }
                        ProgressBar { Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; value: current.progress || 0 }
                        Rectangle { Layout.fillWidth: true; height: 1; color: line }
                        Label { text: "STAGES"; color: muted; font.bold: true; font.pixelSize: 11; Layout.leftMargin: 12 }
                        Repeater {
                            model: ["ingest", "colmap", "fallback", "train", "validate", "export"]
                            delegate: Rectangle {
                                required property string modelData
                                Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; height: 38; radius: 4
                                color: current.current_stage === modelData ? "#243650" : "#202630"; border.color: current.current_stage === modelData ? accent : line
                                RowLayout { anchors.fill: parent; anchors.leftMargin: 9; anchors.rightMargin: 9
                                    Rectangle { width: 8; height: 8; radius: 4; color: statusColor(stageState(modelData).status) }
                                    Label { text: modelData.charAt(0).toUpperCase() + modelData.slice(1); font.bold: current.current_stage === modelData; Layout.fillWidth: true }
                                    Label { text: stageState(modelData).status.toUpperCase(); color: statusColor(stageState(modelData).status); font.pixelSize: 10 }
                                }
                            }
                        }
                        Item { height: 10 }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: logsOpen ? 166 : 34; color: "#171c24"; border.color: line
            ColumnLayout { anchors.fill: parent; spacing: 0
                Item { Layout.fillWidth: true; height: 34
                    RowLayout { anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10
                        ToolButton { text: logsOpen ? "▾" : "▸"; onClicked: logsOpen = !logsOpen }
                        Label { text: "ACTIVITY LOG"; font.bold: true; font.pixelSize: 11 }
                        Item { Layout.fillWidth: true }
                        Label { text: current.warnings && current.warnings.length ? current.warnings.length + " warning(s)" : "No warnings"; color: current.warnings && current.warnings.length ? "#e5ad55" : muted }
                    }
                }
                TextArea { Layout.fillWidth: true; Layout.fillHeight: true; visible: logsOpen; readOnly: true; text: backend ? backend.logText : ""; wrapMode: TextArea.Wrap; font.family: "Cascadia Mono"; font.pixelSize: 11; leftPadding: 12; rightPadding: 12; background: Rectangle { color: "#10141a" } }
            }
        }
    }
}
