import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtWebEngine
import QtMultimedia

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

    property var current: JSON.parse(backend ? (backend.currentJson || "{}") : "{}")
    property var sampling: current.sampling || ({})
    property var importDraft: JSON.parse(backend ? (backend.importJson || "{}") : "{}")
    property var draftSampling: importDraft.sampling || ({})
    property bool easyPending: false
    property bool acceptanceProPending: false
    property string timelineFilter: "All"
    property real timelineScale: 1.0
    property int viewerPlayhead: 0
    property string timelineMessage: ""
    property string timelinePreviewSource: ""
    readonly property var viewerTimelineModel: {
        var rows = sampling.timeline || []
        if (timelineFilter === "Selected") return rows.filter(function(x) { return x.selection_status === "selected" || x.status === "selected" })
        if (timelineFilter === "Rejected") return rows.filter(function(x) { return x.selection_status === "rejected" || x.status === "rejected" })
        if (timelineFilter === "Candidate") return rows.filter(function(x) { return !!x.candidate })
        if (timelineFilter === "Registered") return rows.filter(function(x) { return x.registration_status === "registered" })
        if (timelineFilter === "Unregistered") return rows.filter(function(x) { return x.registration_status === "unregistered" })
        return rows
    }
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
        if (status === "stale") return "#c38bdb"
        return "#687587"
    }
    function stageState(name) { return (current.stages || {})[name] || {"status":"pending"} }
    function samplingModeId(index) { return ["auto", "target_count", "interval", "all_frames"][index] }
    function samplingModeIndex(mode) { return Math.max(0, ["auto", "target_count", "interval", "all_frames"].indexOf(mode || "auto")) }
    function fileUrl(path) { return path ? "file:///" + path.replace(/\\/g, "/") : "" }
    function beginVideo(path) { backend.beginVideoImport(path); modeDialog.open() }
    function openProAcceptance(path) { acceptanceProPending = true; backend.beginVideoImport(path) }
    function applyProDraft() {
        backend.configureVideoImport(samplingModeId(proSamplingMode.currentIndex), proTarget.value,
            proInterval.value, proIntervalUnit.currentText, proIn.value, proOut.value, proProfile.currentText)
    }
    function activateViewerFrame(position) {
        var rows = viewerTimelineModel
        if (!rows.length) return
        viewerPlayhead = Math.max(0, Math.min(rows.length - 1, position))
        var frame = rows[viewerPlayhead]
        timelinePreviewSource = fileUrl(frame.extracted_image_path || frame.thumbnail_path)
        viewerTimeline.positionViewAtIndex(viewerPlayhead, ListView.Contain)
        if (frame.registration_status === "registered" && frame.colmap_image_id !== null && !sampling.camera_mapping_stale) {
            timelineMessage = ""
            viewer.runJavaScript("viewerCamera.setCamera(" + Number(frame.colmap_image_id) + ")")
        } else {
            timelineMessage = frame.selection_status === "selected" || frame.status === "selected" ? "No reconstructed camera" : (frame.reason || "Rejected frame · no reconstructed camera")
        }
    }

    Connections {
        target: backend
        function onChanged() { current = JSON.parse(backend.currentJson || "{}"); viewerPlayhead = 0 }
        function onImportChanged() {
            importDraft = JSON.parse(backend.importJson || "{}")
            if (easyPending && importDraft.status === "ready" && (importDraft.sampling || {}).analysis_status === "complete") {
                easyPending = false
                easyDialog.close()
                backend.generateVideoImport()
            }
            if (acceptanceProPending && importDraft.status === "ready") {
                acceptanceProPending = false
                proDialog.open()
                proSamplingMode.currentIndex = 1
                proTarget.value = Math.min(60, draftSampling.source_total_frames)
                proIn.value = 0
                proOut.value = draftSampling.source_total_frames - 1
                applyProDraft()
                proPlayer.play()
                acceptancePauseTimer.start()
            }
        }
        function onAcceptanceRequested() {
            if (backend.acceptanceCameraTimeline) {
                timelineFilter = "Registered"
                viewerFilter.currentIndex = 4
                viewerPlayhead = 0
                Qt.callLater(function() {
                    activateViewerFrame(0)
                    viewerPlayback.start()
                    viewer.runJavaScript("JSON.stringify(viewerCamera.state())", function(result) { backend.viewerAcceptanceResult(result) })
                })
            } else {
                viewer.runJavaScript("var before=acceptance.snapshot(); acceptance.orbit(0.03,-0.01); acceptance.pan(0.005,-0.003); acceptance.zoom(0.98); acceptance.walk(0.005); acceptance.motionTest(1800); JSON.stringify({before:before,after:acceptance.snapshot()})", function(result) { backend.viewerAcceptanceResult(result) })
            }
        }
    }
    Timer { id: viewerPlayback; interval: 650; repeat: true; onTriggered: { if (viewerPlayhead + 1 >= viewerTimelineModel.length) stop(); else activateViewerFrame(viewerPlayhead + 1) } }
    Timer { id: acceptancePauseTimer; interval: 700; repeat: false; onTriggered: { proPlayer.position = 1000; proPlayer.pause() } }
    FileDialog {
        id: inputPicker; title: "Import video"
        nameFilters: ["Video files (*.mp4 *.mov *.mkv *.avi *.webm)", "All files (*)"]
        onAccepted: beginVideo(selectedFile.toLocalFile())
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
        id: modeDialog; title: "Import video"; modal: true; width: 520
        closePolicy: Popup.NoAutoClose
        contentItem: ColumnLayout {
            spacing: 14
            Label { Layout.fillWidth: true; wrapMode: Text.Wrap; color: muted; text: importDraft.status === "preflight" ? "Reading real video metadata…" : (importDraft.error || "Choose the workflow. Preflight has not created a project or job.") }
            RowLayout {
                Layout.fillWidth: true
                Button { text: "Easy Mode"; Layout.fillWidth: true; enabled: importDraft.status === "ready"; onClicked: { modeDialog.close(); easyDialog.open() } }
                Button { text: "Pro Mode"; Layout.fillWidth: true; enabled: importDraft.status === "ready"; onClicked: { modeDialog.close(); proDialog.open(); proPlayer.play() } }
                Button { text: "Cancel"; onClicked: { backend.cancelVideoImport(); modeDialog.close() } }
            }
        }
    }
    Dialog {
        id: easyDialog; title: "Easy Mode"; modal: true; width: 600
        closePolicy: Popup.NoAutoClose
        contentItem: ColumnLayout {
            spacing: 12
            Label { text: "Choose one quality target"; font.pixelSize: 18; font.bold: true }
            Label { Layout.fillWidth: true; wrapMode: Text.Wrap; color: muted; text: easyPending ? "Analyzing and selecting keyframes. The pipeline will start automatically." : "Everything else uses the existing automatic sampling logic." }
            RowLayout {
                enabled: !easyPending; Layout.fillWidth: true
                Repeater {
                    model: ["preview", "balanced", "quality"]
                    Button { required property string modelData; text: modelData.charAt(0).toUpperCase() + modelData.slice(1); Layout.fillWidth: true; onClicked: { easyPending = true; backend.configureVideoImport("auto", 0, 1, "seconds", 0, draftSampling.source_total_frames - 1, modelData) } }
                }
            }
            ProgressBar { Layout.fillWidth: true; indeterminate: easyPending }
            Button { text: "Cancel"; Layout.alignment: Qt.AlignRight; onClicked: { easyPending = false; backend.cancelVideoImport(); easyDialog.close() } }
        }
    }
    Dialog {
        id: proDialog; title: "Pro Mode · Video Import"; modal: true; width: Math.min(window.width - 50, 1240); height: Math.min(window.height - 70, 800)
        closePolicy: Popup.NoAutoClose
        MediaPlayer { id: proPlayer; source: fileUrl(importDraft.source); videoOutput: proVideo }
        contentItem: RowLayout {
            spacing: 12
            ColumnLayout {
                Layout.fillWidth: true; Layout.fillHeight: true
                Rectangle {
                    Layout.fillWidth: true; Layout.fillHeight: true; color: "#080b10"; border.color: line
                    VideoOutput { id: proVideo; anchors.fill: parent; fillMode: VideoOutput.PreserveAspectFit }
                    Label { anchors.centerIn: parent; visible: proPlayer.mediaStatus === MediaPlayer.LoadingMedia; text: "Loading preview…" }
                }
                RowLayout {
                    Layout.fillWidth: true
                    ToolButton { text: proPlayer.playbackState === MediaPlayer.PlayingState ? "Pause" : "Play"; onClicked: proPlayer.playbackState === MediaPlayer.PlayingState ? proPlayer.pause() : proPlayer.play() }
                    ToolButton { text: "Prev"; onClicked: proPlayer.position = Math.max(proIn.value * 1000 / draftSampling.fps, proPlayer.position - 1000 / draftSampling.fps) }
                    ToolButton { text: "Next"; onClicked: proPlayer.position = Math.min(proOut.value * 1000 / draftSampling.fps, proPlayer.position + 1000 / draftSampling.fps) }
                    Slider { Layout.fillWidth: true; from: 0; to: Math.max(1, proPlayer.duration); value: proPlayer.position; onMoved: proPlayer.position = value }
                    Label { text: Math.min(Math.max(0, (draftSampling.source_total_frames || 1) - 1), Math.round(proPlayer.position / 1000 * (draftSampling.fps || 0))) + " / " + (draftSampling.source_total_frames || "—") }
                }
                ListView {
                    id: proTimeline; Layout.fillWidth: true; Layout.preferredHeight: 112; orientation: ListView.Horizontal; spacing: 6; clip: true
                    model: draftSampling.timeline || []
                    delegate: Rectangle {
                        required property var modelData; width: 104; height: 104; color: "#11151b"; radius: 4
                        border.width: 2; border.color: modelData.status === "selected" ? "#54c88a" : modelData.candidate ? "#e5ad55" : "#596474"
                        Image { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; height: 72; source: fileUrl(modelData.thumbnail_path); fillMode: Image.PreserveAspectCrop; asynchronous: true }
                        Label { anchors.bottom: parent.bottom; width: parent.width; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 10; text: "#" + modelData.index + " · " + Number(modelData.timestamp_seconds).toFixed(2) + "s"; color: modelData.status === "selected" ? "#54c88a" : muted }
                        MouseArea { id: proThumbMouse; anchors.fill: parent; hoverEnabled: true; onClicked: proPlayer.position = modelData.timestamp_seconds * 1000 }
                        ToolTip.visible: proThumbMouse.containsMouse; ToolTip.text: modelData.reason || modelData.status
                    }
                }
            }
            Rectangle {
                Layout.preferredWidth: 290; Layout.fillHeight: true; color: panel; border.color: line
                ScrollView { anchors.fill: parent; contentWidth: availableWidth
                    ColumnLayout { width: parent.width; spacing: 10
                        Label { text: "SAMPLING"; color: muted; font.bold: true; Layout.margins: 12 }
                        ComboBox { id: proProfile; Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; model: ["preview", "balanced", "quality"]; currentIndex: 1 }
                        ComboBox { id: proSamplingMode; Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; model: ["Auto", "Target Count", "Interval", "All Frames"]; currentIndex: samplingModeIndex(draftSampling.sampling_mode) }
                        RowLayout { Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; visible: proSamplingMode.currentIndex === 1
                            Label { text: "Requested"; Layout.fillWidth: true; color: muted }
                            SpinBox { id: proTarget; from: 1; to: Math.max(1, (proOut.value - proIn.value + 1)); value: Math.min(to, draftSampling.requested_frame_count || 1); editable: true }
                        }
                        RowLayout { Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; visible: proSamplingMode.currentIndex === 2
                            SpinBox { id: proInterval; from: 1; to: 600; value: 1; editable: true; Layout.fillWidth: true }
                            ComboBox { id: proIntervalUnit; model: ["frames", "seconds"]; Layout.fillWidth: true }
                        }
                        RowLayout { Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12
                            Label { text: "In"; color: muted } SpinBox { id: proIn; from: 0; to: Math.max(0, proOut.value); value: draftSampling.in_frame || 0; editable: true; Layout.fillWidth: true }
                        }
                        RowLayout { Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12
                            Label { text: "Out"; color: muted } SpinBox { id: proOut; from: proIn.value; to: Math.max(0, (draftSampling.source_total_frames || 1) - 1); value: draftSampling.out_frame === undefined ? to : draftSampling.out_frame; editable: true; Layout.fillWidth: true }
                        }
                        Button { text: importDraft.status === "analyzing" ? "Analyzing…" : "Analyze"; enabled: importDraft.status !== "analyzing"; Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; onClicked: applyProDraft() }
                        GridLayout { columns: 2; Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; rowSpacing: 5
                            Label { text: "Source"; color: muted } Label { text: (draftSampling.source_total_frames || "—") + " frames"; Layout.alignment: Qt.AlignRight }
                            Label { text: "Trimmed"; color: muted } Label { text: draftSampling.trimmed_frame_count || "—"; Layout.alignment: Qt.AlignRight }
                            Label { text: "Candidates"; color: muted } Label { text: draftSampling.candidate_frame_count || draftSampling.estimated_candidate_count || "—"; Layout.alignment: Qt.AlignRight }
                            Label { text: "Requested"; color: muted } Label { text: draftSampling.requested_frame_count || "—"; Layout.alignment: Qt.AlignRight }
                            Label { text: "Selected"; color: muted } Label { text: draftSampling.selected_frame_count || "—"; Layout.alignment: Qt.AlignRight }
                            Label { text: "Estimate"; color: muted } Label { text: (draftSampling.estimated_minutes || "—") + " min"; Layout.alignment: Qt.AlignRight }
                            Label { text: "VRAM"; color: muted } Label { text: (draftSampling.estimated_vram_gib || "—") + " GiB"; Layout.alignment: Qt.AlignRight }
                        }
                        Label { Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; wrapMode: Text.Wrap; color: importDraft.error ? "#ef6b73" : muted; text: importDraft.error || draftSampling.advisory || "Preflight ready" }
                        Item { Layout.fillHeight: true }
                        RowLayout { Layout.fillWidth: true; Layout.margins: 12
                            Button { text: "Cancel"; onClicked: { proPlayer.stop(); backend.cancelVideoImport(); proDialog.close() } }
                            Button { text: "Generate"; highlighted: true; Layout.fillWidth: true; enabled: draftSampling.analysis_status === "complete" && importDraft.status === "ready"; onClicked: { proPlayer.stop(); proDialog.close(); backend.generateVideoImport() } }
                        }
                    }
                }
            }
        }
    }
    Dialog {
        id: settingsDialog; title: "Settings"; modal: true; standardButtons: Dialog.Close; width: 500
        contentItem: Label { width: 460; text: "Runtime paths are discovered from the locked P2 environment.\nRenderer: Qt WebEngine · WebGL2"; padding: 18 }
    }

    DropArea {
        id: globalVideoDrop; anchors.fill: parent; z: 1000
        keys: ["text/uri-list"]
        onDropped: function(drop) {
            if (drop.hasUrls && drop.urls.length > 0) {
                var path = drop.urls[0].toLocalFile()
                if (/\.(mp4|mov|mkv|avi|webm)$/i.test(path)) {
                    drop.acceptProposedAction()
                    beginVideo(path)
                }
            }
        }
        Rectangle {
            anchors.fill: parent; visible: globalVideoDrop.containsDrag
            color: "#172b48e8"; border.width: 3; border.color: accent
            Label { anchors.centerIn: parent; text: "DROP VIDEO\nEasy or Pro import"; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 28; font.bold: true; color: "white" }
        }
    }

    header: Rectangle {
        height: 54; color: "#1c222b"; border.color: line
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14; spacing: 7
            Label { text: "GF"; font.bold: true; font.pixelSize: 17; color: accent }
            Label { text: "Gaussian Factory"; font.bold: true; font.pixelSize: 15; Layout.rightMargin: 14 }
            ToolButton { text: "New Project"; onClicked: projectDialog.open() }
            ToolButton { text: "Import Video"; onClicked: inputPicker.open() }
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
                ColumnLayout {
                    anchors.fill: parent; spacing: 0
                    Rectangle {
                        Layout.fillWidth: true; Layout.fillHeight: true; color: "#0f1319"
                        WebEngineView { id: viewer; objectName: "gaussianViewer"; anchors.fill: parent; url: backend ? backend.viewerUrl : "about:blank"; focus: true; onTitleChanged: { if (backend) backend.viewerPageTitle(title) } }
                        Column {
                            anchors.centerIn: parent; spacing: 10; visible: !backend || backend.viewerUrl === "about:blank"
                            Label { anchors.horizontalCenter: parent.horizontalCenter; text: current.project_id ? "3D VIEWER" : "NO PROJECT SELECTED"; font.pixelSize: 19; font.bold: true; color: "#cad3df" }
                            Label { width: 440; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap; color: muted; text: backend ? backend.viewerStatus : "" }
                            Button { anchors.horizontalCenter: parent.horizontalCenter; visible: stageState("validate").status === "succeeded"; text: "Reload Viewer"; onClicked: backend.loadViewer() }
                        }
                        Rectangle {
                            anchors.fill: parent; visible: timelineMessage !== ""; color: "#0d1117ed"
                            ColumnLayout { anchors.centerIn: parent; width: Math.min(parent.width - 60, 720); height: Math.min(parent.height - 50, 480)
                                Image { Layout.fillWidth: true; Layout.fillHeight: true; source: timelinePreviewSource; fillMode: Image.PreserveAspectFit; asynchronous: true }
                                Label { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; text: timelineMessage; color: "#e5ad55"; font.pixelSize: 16; font.bold: true }
                            }
                        }
                        Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 27; color: "#141921e8"
                            Label { anchors.fill: parent; anchors.leftMargin: 9; verticalAlignment: Text.AlignVCenter; color: muted; elide: Text.ElideRight; text: backend ? backend.viewerStatus : "" }
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true; Layout.preferredHeight: current.input_kind === "video" ? 190 : 0
                        visible: current.input_kind === "video"; color: "#151a22"; border.color: line
                        ColumnLayout { anchors.fill: parent; anchors.margins: 7; spacing: 5
                            RowLayout { Layout.fillWidth: true
                                Label { text: "KEYFRAME CAMERA TIMELINE"; font.bold: true; font.pixelSize: 11 }
                                Label { text: "In #" + (sampling.in_frame || 0) + " · Out #" + (sampling.out_frame === undefined ? "—" : sampling.out_frame); color: muted }
                                ToolButton { text: "Prev"; enabled: viewerTimelineModel.length > 0; onClicked: activateViewerFrame(viewerPlayhead - 1) }
                                ToolButton { text: viewerPlayback.running ? "Pause" : "Play"; enabled: viewerTimelineModel.length > 0; onClicked: viewerPlayback.running ? viewerPlayback.stop() : viewerPlayback.start() }
                                ToolButton { text: "Next"; enabled: viewerTimelineModel.length > 0; onClicked: activateViewerFrame(viewerPlayhead + 1) }
                                Button { text: "Camera View"; enabled: viewerTimelineModel.length > 0 && !sampling.camera_mapping_stale; onClicked: activateViewerFrame(viewerPlayhead) }
                                Button { text: "Free View"; enabled: backend && backend.viewerUrl !== "about:blank"; onClicked: { timelineMessage = ""; viewer.runJavaScript("viewerCamera.setFreeView()") } }
                                Item { Layout.fillWidth: true }
                                ComboBox { id: viewerFilter; model: ["All", "Selected", "Rejected", "Candidate", "Registered", "Unregistered"]; onActivated: { timelineFilter = currentText; viewerPlayhead = 0 } }
                                Label { text: "Zoom"; color: muted }
                                Slider { from: 0.7; to: 1.7; value: 1.0; Layout.preferredWidth: 100; onMoved: timelineScale = value }
                            }
                            ListView {
                                id: viewerTimeline; Layout.fillWidth: true; Layout.fillHeight: true; orientation: ListView.Horizontal
                                model: viewerTimelineModel; spacing: 6; clip: true; boundsBehavior: Flickable.StopAtBounds
                                delegate: Rectangle {
                                    required property var modelData; required property int index
                                    width: 110 * timelineScale; height: viewerTimeline.height; radius: 4; color: "#10151c"
                                    border.width: index === viewerPlayhead ? 3 : 2
                                    border.color: index === viewerPlayhead ? accent : modelData.registration_status === "registered" ? "#54c88a" : modelData.selection_status === "selected" || modelData.status === "selected" ? "#e5ad55" : modelData.candidate ? "#7289b5" : "#596474"
                                    Rectangle { anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter; width: 2; color: accent; visible: index === viewerPlayhead; z: 2 }
                                    Image { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; height: parent.height - 40; source: fileUrl(modelData.extracted_image_path || modelData.thumbnail_path); fillMode: Image.PreserveAspectCrop; asynchronous: true }
                                    Column { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 39
                                        Label { width: parent.width; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 9; text: "#" + (modelData.source_frame_index === undefined ? modelData.index : modelData.source_frame_index) + " · " + Number(modelData.timestamp_seconds).toFixed(2) + "s" }
                                        Label { width: parent.width; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 9; color: modelData.registration_status === "registered" ? "#54c88a" : muted; text: (modelData.selection_status || modelData.status || "frame") + (modelData.candidate ? " · candidate" : "") + (modelData.registration_status && modelData.registration_status !== "not_applicable" ? " · " + modelData.registration_status : "") }
                                    }
                                    MouseArea { id: viewerThumbMouse; anchors.fill: parent; hoverEnabled: true; onClicked: activateViewerFrame(index) }
                                    ToolTip.visible: viewerThumbMouse.containsMouse; ToolTip.text: modelData.reason || (modelData.registration_status === "unregistered" ? "No reconstructed camera" : modelData.registration_status || modelData.status)
                                }
                                Label { anchors.centerIn: parent; visible: viewerTimeline.count === 0; text: sampling.camera_mapping_stale ? "Timeline is stale · regenerate to rebuild cameras" : "No frames match this filter"; color: muted }
                            }
                        }
                    }
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
                        Label { Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; wrapMode: Text.Wrap; color: muted; text: (mode.currentText === "preview" ? "Fast iteration · 1,000 steps" : mode.currentText === "quality" ? "Maximum quality · 7,000 steps" : "Recommended balance · 3,000 steps") + (sampling.profile_label === "Custom" ? " · Custom frames" : " · Auto frames") }
                        Rectangle { Layout.fillWidth: true; height: 1; color: line; visible: current.input_kind === "video" }
                        Label { text: "FRAME SAMPLING"; color: muted; font.bold: true; font.pixelSize: 11; Layout.leftMargin: 12; visible: current.input_kind === "video" }
                        ComboBox {
                            id: samplingMode; Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12
                            model: ["Auto", "Target Count", "Interval", "All Frames"]
                            currentIndex: samplingModeIndex(sampling.sampling_mode)
                            enabled: current.status !== "running"; visible: current.input_kind === "video"
                        }
                        RowLayout {
                            Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; visible: current.input_kind === "video" && samplingMode.currentIndex === 1
                            Label { text: "Final frames"; color: muted; Layout.fillWidth: true }
                            SpinBox { id: targetFrames; from: 1; to: Math.max(1, sampling.trimmed_frame_count || sampling.source_total_frames || 1); value: Math.min(to, sampling.requested_frame_count || 1); editable: true }
                            Label { text: "/ " + (sampling.trimmed_frame_count || sampling.source_total_frames || 0); color: muted }
                        }
                        RowLayout {
                            Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; visible: current.input_kind === "video" && samplingMode.currentIndex === 2
                            Label { text: "Every"; color: muted }
                            SpinBox { id: intervalValue; from: 1; to: 600; value: Math.max(1, Math.round(sampling.interval_value || 1)); editable: true; Layout.preferredWidth: 90 }
                            ComboBox { id: intervalUnit; model: ["frames", "seconds"]; currentIndex: Math.max(0, model.indexOf(sampling.interval_unit || "seconds")); Layout.fillWidth: true }
                        }
                        RowLayout {
                            Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; visible: current.input_kind === "video"
                            Label { text: "In"; color: muted }
                            SpinBox { id: persistedIn; from: 0; to: Math.max(0, persistedOut.value); value: sampling.in_frame || 0; editable: true; Layout.fillWidth: true }
                            Label { text: "Out"; color: muted }
                            SpinBox { id: persistedOut; from: persistedIn.value; to: Math.max(0, (sampling.source_total_frames || 1) - 1); value: sampling.out_frame === undefined ? to : sampling.out_frame; editable: true; Layout.fillWidth: true }
                        }
                        RowLayout {
                            Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; visible: current.input_kind === "video"
                            Button {
                                text: "Apply"; enabled: current.status !== "running"
                                onClicked: backend.setSampling(samplingModeId(samplingMode.currentIndex), targetFrames.value, intervalValue.value, intervalUnit.currentText, persistedIn.value, persistedOut.value)
                            }
                            Button {
                                text: sampling.analysis_status === "analyzing" ? "Analyzing…" : "Reanalyze"; Layout.fillWidth: true
                                enabled: current.status !== "running" && sampling.analysis_status !== "analyzing"
                                onClicked: {
                                    backend.setSampling(samplingModeId(samplingMode.currentIndex), targetFrames.value, intervalValue.value, intervalUnit.currentText, persistedIn.value, persistedOut.value)
                                    backend.analyzeSampling()
                                }
                            }
                        }
                        GridLayout {
                            columns: 2; columnSpacing: 10; rowSpacing: 5; Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; visible: current.input_kind === "video"
                            Label { text: "Source"; color: muted } Label { text: (sampling.source_total_frames || 0) + " frames"; Layout.alignment: Qt.AlignRight }
                            Label { text: "Duration / FPS"; color: muted } Label { text: Number(sampling.duration_seconds || 0).toFixed(2) + " s · " + Number(sampling.fps || 0).toFixed(2); Layout.alignment: Qt.AlignRight }
                            Label { text: "Resolution"; color: muted } Label { text: (sampling.width || 0) + " × " + (sampling.height || 0); Layout.alignment: Qt.AlignRight }
                            Label { text: "Candidates"; color: muted } Label { text: sampling.candidate_frame_count || sampling.estimated_candidate_count || "—"; Layout.alignment: Qt.AlignRight }
                            Label { text: "Requested / selected"; color: muted } Label { text: (sampling.requested_frame_count || 0) + " / " + (sampling.selected_frame_count || 0); color: sampling.selected_frame_count && sampling.selected_frame_count < sampling.requested_frame_count ? "#e5ad55" : "#dce3ec"; Layout.alignment: Qt.AlignRight }
                            Label { text: sampling.colmap_input_frame_count ? "Sent to COLMAP" : "Ready for COLMAP"; color: muted } Label { text: sampling.colmap_input_frame_count || sampling.selected_frame_count || 0; color: accent; font.bold: true; Layout.alignment: Qt.AlignRight }
                        }
                        Label { Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; wrapMode: Text.Wrap; color: sampling.warnings && sampling.warnings.length ? "#e5ad55" : muted; visible: current.input_kind === "video"; text: sampling.warnings && sampling.warnings.length ? sampling.warnings.join("\n") : (sampling.advisory || "Import a video to estimate frame cost.") }
                        Label { Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12; color: muted; visible: current.input_kind === "video"; text: "Estimate: " + (sampling.estimated_minutes || "—") + " min · " + (sampling.estimated_vram_gib || "—") + " GiB VRAM" }
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
