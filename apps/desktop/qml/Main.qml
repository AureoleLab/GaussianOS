import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.LocalStorage
import QtWebEngine
import QtMultimedia

ApplicationWindow {
    id: window
    visible: true
    width: 1680
    height: 945
    minimumWidth: 1180
    minimumHeight: 720
    title: "Gaussian Factory"
    color: theme.background

    property string themeMode: "light"
    DesignTokens { id: theme; mode: window.themeMode }

    palette.window: theme.background
    palette.windowText: theme.text
    palette.base: theme.surfaceSunken
    palette.alternateBase: theme.surfaceRaised
    palette.text: theme.text
    palette.button: theme.control
    palette.buttonText: theme.text
    palette.highlight: theme.accent
    palette.highlightedText: "#ffffff"
    font.family: theme.uiFont
    font.pixelSize: theme.typeBody

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
    property bool logsOpen: true
    property bool viewerLogsOpen: false
    property bool projectsExpanded: true
    property bool layoutReady: false
    property bool leftPaneOpen: true
    property bool rightPaneOpen: true
    property bool timelineOpen: true
    property bool proInspectorOpen: true
    property real leftPaneSize: 252
    property real rightPaneSize: 318
    property real projectPaneSize: 238
    property real viewerTimelineSize: 196
    property real welcomeLogSize: 138
    property real proInspectorSize: 370
    property real proTimelineSize: 196
    readonly property bool viewerActive: backend && backend.viewerUrl !== "about:blank"
    readonly property bool viewerLoading: backend && String(backend.viewerStatus || "").toLowerCase().indexOf("loading") >= 0
    readonly property string route: proDialog.opened ? "pro" : viewerActive ? "viewer" : "home"
    readonly property var viewerTimelineModel: {
        var rows = sampling.timeline || []
        if (timelineFilter === "Selected") return rows.filter(function(x) { return x.selection_status === "selected" || x.status === "selected" })
        if (timelineFilter === "Rejected") return rows.filter(function(x) { return x.selection_status === "rejected" || x.status === "rejected" })
        if (timelineFilter === "Candidate") return rows.filter(function(x) { return !!x.candidate })
        if (timelineFilter === "Registered") return rows.filter(function(x) { return x.registration_status === "registered" })
        if (timelineFilter === "Unregistered") return rows.filter(function(x) { return x.registration_status === "unregistered" })
        return rows
    }

    function statusColor(status) {
        if (status === "succeeded") return theme.success
        if (status === "skipped") return theme.textTertiary
        if (status === "running") return theme.accent
        if (status === "failed") return theme.error
        if (status === "interrupted" || status === "fallback_required") return theme.warning
        if (status === "stale") return "#b985d4"
        return theme.textDisabled
    }
    function stageState(name) { return (current.stages || {})[name] || {"status":"pending"} }
    function samplingModeId(index) { return ["auto", "target_count", "interval", "all_frames"][index] }
    function samplingModeIndex(mode) { return Math.max(0, ["auto", "target_count", "interval", "all_frames"].indexOf(mode || "auto")) }
    function fileUrl(path) { return path ? "file:///" + path.replace(/\\/g, "/") : "" }
    function localPathFromUrl(value) {
        if (value && typeof value.toLocalFile === "function") return value.toLocalFile()
        var text = value && typeof value.toString === "function" ? value.toString() : String(value || "")
        if (/^file:\/\/\//i.test(text)) text = text.substring(8)
        else if (/^file:\/\//i.test(text)) text = "//" + text.substring(7)
        try { return decodeURIComponent(text) } catch (error) { return text }
    }
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
    function frameLabel(value) { return value === undefined || value === null ? "—" : value }

    function clampLayout(value, minimum, maximum) { return Math.max(minimum, Math.min(maximum, Number(value))) }
    function defaultLayout() {
        leftPaneOpen = true
        rightPaneOpen = true
        timelineOpen = true
        proInspectorOpen = true
        leftPaneSize = 252
        rightPaneSize = 318
        projectPaneSize = 238
        viewerTimelineSize = 196
        welcomeLogSize = 138
        proInspectorSize = 370
        proTimelineSize = 196
    }
    function layoutDatabase() {
        return LocalStorage.openDatabaseSync("GaussianFactoryUILayout", "1.0", "QML workspace layout", 65536)
    }
    function applyLayoutState(state) {
        if (!state) return
        if (state.themeMode === "light" || state.themeMode === "dark" || state.themeMode === "system") themeMode = state.themeMode
        leftPaneOpen = state.leftPaneOpen !== false
        rightPaneOpen = state.rightPaneOpen !== false
        timelineOpen = state.timelineOpen !== false
        proInspectorOpen = state.proInspectorOpen !== false
        leftPaneSize = clampLayout(state.leftPaneSize || 252, 214, 420)
        rightPaneSize = clampLayout(state.rightPaneSize || 318, 276, 480)
        projectPaneSize = clampLayout(state.projectPaneSize || 238, 116, 440)
        viewerTimelineSize = clampLayout(state.viewerTimelineSize || 196, 132, 360)
        welcomeLogSize = clampLayout(state.welcomeLogSize || 138, 92, 300)
        proInspectorSize = clampLayout(state.proInspectorSize || 370, 310, 520)
        proTimelineSize = clampLayout(state.proTimelineSize || 196, 132, 360)
    }
    function loadLayout() {
        try {
            var db = layoutDatabase()
            db.transaction(function(tx) {
                tx.executeSql("CREATE TABLE IF NOT EXISTS layout_state (id INTEGER PRIMARY KEY, value TEXT)")
                var rows = tx.executeSql("SELECT value FROM layout_state WHERE id = 1")
                if (rows.rows.length) applyLayoutState(JSON.parse(rows.rows.item(0).value))
            })
        } catch (error) {
            console.warn("Could not restore workspace layout:", error)
        }
        layoutReady = true
    }
    function saveLayout() {
        if (!layoutReady) return
        var state = {
            "themeMode": themeMode,
            "leftPaneOpen": leftPaneOpen,
            "rightPaneOpen": rightPaneOpen,
            "timelineOpen": timelineOpen,
            "proInspectorOpen": proInspectorOpen,
            "leftPaneSize": leftPaneSize,
            "rightPaneSize": rightPaneSize,
            "projectPaneSize": projectPaneSize,
            "viewerTimelineSize": viewerTimelineSize,
            "welcomeLogSize": welcomeLogSize,
            "proInspectorSize": proInspectorSize,
            "proTimelineSize": proTimelineSize
        }
        try {
            var db = layoutDatabase()
            db.transaction(function(tx) {
                tx.executeSql("CREATE TABLE IF NOT EXISTS layout_state (id INTEGER PRIMARY KEY, value TEXT)")
                tx.executeSql("INSERT OR REPLACE INTO layout_state (id, value) VALUES (1, ?)", [JSON.stringify(state)])
            })
        } catch (error) {
            console.warn("Could not save workspace layout:", error)
        }
    }
    function queueLayoutSave() { if (layoutReady) layoutSaveTimer.restart() }
    function resetLayout() {
        layoutReady = false
        defaultLayout()
        Qt.callLater(function() { layoutReady = true; saveLayout() })
    }
    onThemeModeChanged: queueLayoutSave()

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

    Timer { id: viewerPlayback; interval: 650; repeat: true; onTriggered: viewerPlayhead + 1 >= viewerTimelineModel.length ? stop() : activateViewerFrame(viewerPlayhead + 1) }
    Timer { id: acceptancePauseTimer; interval: 700; repeat: false; onTriggered: { proPlayer.position = 1000; proPlayer.pause() } }
    Timer { id: layoutSaveTimer; interval: 420; repeat: false; onTriggered: saveLayout() }
    Component.onCompleted: Qt.callLater(loadLayout)
    onClosing: saveLayout()
    Shortcut { sequence: "Ctrl+1"; onActivated: window.themeMode = "light" }
    Shortcut { sequence: "Ctrl+2"; onActivated: window.themeMode = "dark" }
    Shortcut { sequence: "Ctrl+3"; onActivated: window.themeMode = "system" }

    FileDialog {
        id: inputPicker
        title: "Import video"
        nameFilters: ["Video files (*.mp4 *.mov *.mkv *.avi *.webm)", "All files (*)"]
        onAccepted: beginVideo(localPathFromUrl(selectedFile))
    }
    FolderDialog { id: folderPicker; title: "Import image folder"; onAccepted: backend.importInput(localPathFromUrl(selectedFolder)) }

    Dialog {
        id: projectDialog
        title: "New project"
        modal: true
        anchors.centerIn: parent
        width: 510
        padding: 0
        background: GfPanel { tokens: theme; raised: true }
        enter: Transition { ParallelAnimation { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: theme.motionNormal } NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: theme.motionSlow; easing.type: Easing.OutCubic } } }
        exit: Transition { ParallelAnimation { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: theme.motionFast } NumberAnimation { property: "scale"; from: 1; to: 0.98; duration: theme.motionFast } } }
        contentItem: ColumnLayout {
            spacing: theme.space12
            Item { Layout.fillWidth: true; Layout.preferredHeight: 12 }
            Text { text: "Create a new project"; color: theme.text; font.pixelSize: 18; font.weight: Font.DemiBold; Layout.leftMargin: 22 }
            Text { text: "Choose a name and a working folder for generated files."; color: theme.textSecondary; font.pixelSize: theme.typeBody; Layout.leftMargin: 22 }
            Text { text: "PROJECT NAME"; color: theme.textSecondary; font.pixelSize: theme.typeCaption; font.weight: Font.DemiBold; Layout.leftMargin: 22; Layout.topMargin: 8 }
            GfTextField { id: projectName; tokens: theme; placeholderText: "My reconstruction"; Layout.fillWidth: true; Layout.leftMargin: 22; Layout.rightMargin: 22 }
            Text { text: "WORKING FOLDER"; color: theme.textSecondary; font.pixelSize: theme.typeCaption; font.weight: Font.DemiBold; Layout.leftMargin: 22 }
            GfTextField { id: projectRoot; tokens: theme; placeholderText: "D:/Projects/my-scan"; Layout.fillWidth: true; Layout.leftMargin: 22; Layout.rightMargin: 22 }
            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: theme.divider; Layout.topMargin: 10 }
            RowLayout {
                Layout.fillWidth: true; Layout.leftMargin: 22; Layout.rightMargin: 22; Layout.bottomMargin: 18
                Item { Layout.fillWidth: true }
                GfButton { tokens: theme; text: "Cancel"; onClicked: projectDialog.reject() }
                GfButton { tokens: theme; text: "Create Project"; primary: true; enabled: projectName.text.trim() !== "" && projectRoot.text.trim() !== ""; onClicked: { backend.createProject(projectName.text, projectRoot.text); projectDialog.accept() } }
            }
        }
    }

    Dialog {
        id: modeDialog
        title: "Import video"
        modal: true
        anchors.centerIn: parent
        width: 540
        closePolicy: Popup.NoAutoClose
        padding: 0
        background: GfPanel { tokens: theme; raised: true }
        enter: Transition { ParallelAnimation { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: theme.motionNormal } NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: theme.motionSlow; easing.type: Easing.OutCubic } } }
        exit: Transition { ParallelAnimation { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: theme.motionFast } NumberAnimation { property: "scale"; from: 1; to: 0.98; duration: theme.motionFast } } }
        contentItem: ColumnLayout {
            spacing: theme.space16
            Item { Layout.fillWidth: true; Layout.preferredHeight: 10 }
            Text { text: "Choose an import workflow"; color: theme.text; font.pixelSize: 18; font.weight: Font.DemiBold; Layout.leftMargin: 22 }
            Text {
                Layout.fillWidth: true; Layout.leftMargin: 22; Layout.rightMargin: 22
                wrapMode: Text.Wrap; color: importDraft.error ? theme.error : theme.textSecondary
                text: importDraft.status === "preflight" ? "Reading video metadata…" : (importDraft.error || "Preflight is complete. No project or pipeline job has been created yet.")
            }
            GfProgressBar { tokens: theme; Layout.fillWidth: true; Layout.leftMargin: 22; Layout.rightMargin: 22; indeterminate: importDraft.status === "preflight"; visible: indeterminate }
            RowLayout {
                Layout.fillWidth: true; Layout.leftMargin: 22; Layout.rightMargin: 22
                GfButton { tokens: theme; text: "Easy Mode"; Layout.fillWidth: true; enabled: importDraft.status === "ready"; onClicked: { modeDialog.close(); easyDialog.open() } }
                GfButton { tokens: theme; text: "Pro Mode"; primary: true; Layout.fillWidth: true; enabled: importDraft.status === "ready"; onClicked: { modeDialog.close(); proDialog.open(); proPlayer.play() } }
            }
            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: theme.divider }
            RowLayout { Layout.fillWidth: true; Layout.leftMargin: 22; Layout.rightMargin: 22; Layout.bottomMargin: 18
                Item { Layout.fillWidth: true }
                GfButton { tokens: theme; text: "Cancel"; onClicked: { backend.cancelVideoImport(); modeDialog.close() } }
            }
        }
    }

    Dialog {
        id: easyDialog
        title: "Easy Mode"
        modal: true
        anchors.centerIn: parent
        width: 620
        closePolicy: Popup.NoAutoClose
        padding: 0
        background: GfPanel { tokens: theme; raised: true }
        enter: Transition { ParallelAnimation { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: theme.motionNormal } NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: theme.motionSlow; easing.type: Easing.OutCubic } } }
        exit: Transition { ParallelAnimation { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: theme.motionFast } NumberAnimation { property: "scale"; from: 1; to: 0.98; duration: theme.motionFast } } }
        contentItem: ColumnLayout {
            spacing: theme.space16
            Item { Layout.fillWidth: true; Layout.preferredHeight: 8 }
            Text { text: "Choose one quality target"; font.pixelSize: 18; font.weight: Font.DemiBold; color: theme.text; Layout.leftMargin: 22 }
            Text { Layout.fillWidth: true; Layout.leftMargin: 22; Layout.rightMargin: 22; wrapMode: Text.Wrap; color: theme.textSecondary; text: easyPending ? "Analyzing and selecting keyframes. The pipeline will start automatically." : "Gaussian Factory will configure sampling and reconstruction automatically." }
            RowLayout {
                enabled: !easyPending; Layout.fillWidth: true; Layout.leftMargin: 22; Layout.rightMargin: 22
                Repeater {
                    model: ["preview", "balanced", "quality"]
                    GfButton { required property string modelData; tokens: theme; text: modelData.charAt(0).toUpperCase() + modelData.slice(1); primary: modelData === "balanced"; Layout.fillWidth: true; onClicked: { easyPending = true; backend.configureVideoImport("auto", 0, 1, "seconds", 0, draftSampling.source_total_frames - 1, modelData) } }
                }
            }
            GfProgressBar { tokens: theme; Layout.fillWidth: true; Layout.leftMargin: 22; Layout.rightMargin: 22; indeterminate: easyPending; visible: easyPending }
            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: theme.divider }
            RowLayout { Layout.fillWidth: true; Layout.leftMargin: 22; Layout.rightMargin: 22; Layout.bottomMargin: 18
                Item { Layout.fillWidth: true }
                GfButton { tokens: theme; text: "Cancel"; onClicked: { easyPending = false; backend.cancelVideoImport(); easyDialog.close() } }
            }
        }
    }

    Dialog {
        id: settingsDialog
        title: "Settings"
        modal: true
        anchors.centerIn: parent
        width: 520
        padding: 0
        background: GfPanel { tokens: theme; raised: true }
        enter: Transition { ParallelAnimation { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: theme.motionNormal } NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: theme.motionSlow; easing.type: Easing.OutCubic } } }
        exit: Transition { ParallelAnimation { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: theme.motionFast } NumberAnimation { property: "scale"; from: 1; to: 0.98; duration: theme.motionFast } } }
        contentItem: ColumnLayout {
            spacing: theme.space16
            Item { Layout.fillWidth: true; Layout.preferredHeight: 10 }
            Text { text: "Appearance"; color: theme.text; font.pixelSize: 18; font.weight: Font.DemiBold; Layout.leftMargin: 22 }
            Text { text: "THEME"; color: theme.textSecondary; font.pixelSize: theme.typeCaption; font.weight: Font.DemiBold; Layout.leftMargin: 22 }
            RowLayout {
                Layout.fillWidth: true; Layout.leftMargin: 22; Layout.rightMargin: 22
                Repeater {
                    model: [{"id":"light","label":"Light"},{"id":"dark","label":"Dark"},{"id":"system","label":"Follow System"}]
                    GfButton { required property var modelData; tokens: theme; text: modelData.label; primary: window.themeMode === modelData.id; Layout.fillWidth: true; onClicked: window.themeMode = modelData.id }
                }
            }
            Text { Layout.fillWidth: true; Layout.leftMargin: 22; Layout.rightMargin: 22; wrapMode: Text.Wrap; color: theme.textSecondary; text: "Theme changes apply globally to the workspace, Pro Mode, Viewer, timeline, dialogs and every control. Shortcuts: Ctrl+1 / Ctrl+2 / Ctrl+3." }
            GfButton { tokens: theme; text: "Reset Workspace Layout"; Layout.leftMargin: 22; Layout.rightMargin: 22; Layout.fillWidth: true; onClicked: resetLayout() }
            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: theme.divider }
            Text { text: "Runtime paths are discovered from the locked P2 environment.\nRenderer: Qt WebEngine · WebGL2"; color: theme.textSecondary; Layout.leftMargin: 22; lineHeight: 1.45 }
            RowLayout { Layout.fillWidth: true; Layout.leftMargin: 22; Layout.rightMargin: 22; Layout.bottomMargin: 18
                Item { Layout.fillWidth: true }
                GfButton { tokens: theme; text: "Done"; primary: true; onClicked: settingsDialog.close() }
            }
        }
    }

    Popup {
        id: proDialog
        parent: Overlay.overlay
        x: 0; y: 0
        width: window.width; height: window.height
        modal: true
        focus: true
        padding: 0
        closePolicy: Popup.NoAutoClose
        background: Rectangle { color: theme.background }
        enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: theme.motionNormal } }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: theme.motionFast } }
        MediaPlayer { id: proPlayer; source: fileUrl(importDraft.source); videoOutput: proVideo }

        contentItem: ColumnLayout {
            spacing: 0
            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: theme.toolbarHeight; color: theme.surface; border.color: theme.divider
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 20; anchors.rightMargin: 18; spacing: 10
                    Text { text: "GF"; color: theme.accent; font.pixelSize: 16; font.weight: Font.Bold }
                    Text { text: "Gaussian Factory"; color: theme.text; font.pixelSize: 15; font.weight: Font.DemiBold; Layout.rightMargin: 12 }
                    GfButton { tokens: theme; text: "New Project"; quiet: true; onClicked: { proPlayer.pause(); proDialog.close(); projectDialog.open() } }
                    Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 22; color: theme.divider }
                    Text { text: "Import Video"; color: theme.accent; font.pixelSize: theme.typeBody; font.weight: Font.Medium; Layout.leftMargin: 8; Layout.rightMargin: 8 }
                    Text { text: "Import Images"; color: theme.textSecondary; font.pixelSize: theme.typeBody }
                    Item { Layout.fillWidth: true }
                    GfButton { tokens: theme; text: "Run"; primary: true; enabled: false; Layout.preferredWidth: 92 }
                    GfButton { tokens: theme; text: "Cancel"; enabled: false; Layout.preferredWidth: 92 }
                    GfButton { tokens: theme; text: "Export"; enabled: false; Layout.preferredWidth: 92 }
                    Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 22; color: theme.divider; Layout.leftMargin: 8; Layout.rightMargin: 4 }
                    GfButton { tokens: theme; text: proInspectorOpen ? "Hide Inspector" : "Show Inspector"; quiet: true; compact: true; toolTip: "Toggle Sampling and Analysis"; onClicked: { proInspectorOpen = !proInspectorOpen; queueLayoutSave() } }
                    GfButton { tokens: theme; text: theme.dark ? "☀" : "☾"; quiet: true; compact: true; ToolTip.visible: hovered; ToolTip.text: "Toggle theme"; onClicked: window.themeMode = theme.dark ? "light" : "dark" }
                }
            }
            SplitView {
                id: proWorkspaceSplit
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.margins: 20; Layout.topMargin: 14
                orientation: Qt.Horizontal
                handle: GfSplitHandle { tokens: theme; splitOrientation: Qt.Horizontal; onResetRequested: { proInspectorSize = 370; queueLayoutSave() } }
                SplitView {
                    id: proVerticalSplit
                    SplitView.fillWidth: true; SplitView.fillHeight: true; SplitView.minimumWidth: 620
                    orientation: Qt.Vertical
                    handle: GfSplitHandle { tokens: theme; splitOrientation: Qt.Vertical; onResetRequested: { proTimelineSize = 196; queueLayoutSave() } }
                    ColumnLayout {
                        SplitView.fillWidth: true; SplitView.fillHeight: true; SplitView.minimumHeight: 360; spacing: 10
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "Pro Mode"; color: theme.accent; font.pixelSize: 15; font.weight: Font.DemiBold }
                        Text { text: "·  Video Import"; color: theme.textSecondary; font.pixelSize: 15 }
                    }
                    GfPanel {
                        tokens: theme; sunken: true; Layout.fillWidth: true; Layout.fillHeight: true; radius: theme.radiusMedium
                        VideoOutput { id: proVideo; anchors.fill: parent; anchors.margins: 16; fillMode: VideoOutput.PreserveAspectFit }
                        GfSkeleton { tokens: theme; anchors.fill: parent; anchors.margins: 16; visible: proPlayer.mediaStatus === MediaPlayer.LoadingMedia; running: visible }
                        Column { anchors.centerIn: parent; spacing: 10; visible: proPlayer.mediaStatus === MediaPlayer.LoadingMedia
                            Text { text: "◌"; color: theme.accent; font.pixelSize: 26; anchors.horizontalCenter: parent.horizontalCenter; RotationAnimator on rotation { from: 0; to: 360; loops: Animation.Infinite; duration: 900 } }
                            Text { text: "Loading preview…"; color: theme.textSecondary }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true; Layout.leftMargin: 10; Layout.rightMargin: 10; spacing: 12
                        GfButton { tokens: theme; text: proPlayer.playbackState === MediaPlayer.PlayingState ? "Ⅱ" : "▶"; quiet: true; compact: true; onClicked: proPlayer.playbackState === MediaPlayer.PlayingState ? proPlayer.pause() : proPlayer.play() }
                        GfButton { tokens: theme; text: "|◀"; quiet: true; compact: true; onClicked: proPlayer.position = Math.max(proIn.value * 1000 / Math.max(1, draftSampling.fps), proPlayer.position - 1000 / Math.max(1, draftSampling.fps)) }
                        GfButton { tokens: theme; text: "▶|"; quiet: true; compact: true; onClicked: proPlayer.position = Math.min(proOut.value * 1000 / Math.max(1, draftSampling.fps), proPlayer.position + 1000 / Math.max(1, draftSampling.fps)) }
                        Text { text: Qt.formatTime(new Date(proPlayer.position), "mm:ss:zzz"); color: theme.textSecondary; font.pixelSize: theme.typeSmall }
                        Slider { Layout.fillWidth: true; from: 0; to: Math.max(1, proPlayer.duration); value: proPlayer.position; onMoved: proPlayer.position = value }
                        Text { text: Qt.formatTime(new Date(proPlayer.duration), "mm:ss:zzz"); color: theme.textSecondary; font.pixelSize: theme.typeSmall }
                        Text { text: "▣"; color: theme.textSecondary; font.pixelSize: 18 }
                    }
                    }
                    GfPanel {
                        tokens: theme
                        SplitView.fillWidth: true; SplitView.preferredHeight: proTimelineSize
                        SplitView.minimumHeight: 132; SplitView.maximumHeight: 360
                        radius: theme.radiusMedium
                        onHeightChanged: if (layoutReady && height >= 132) { proTimelineSize = height; queueLayoutSave() }
                        Behavior on SplitView.preferredHeight { NumberAnimation { duration: theme.motionSlow; easing.type: Easing.OutCubic } }
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 12; spacing: 8
                            RowLayout {
                                Layout.fillWidth: true
                                Text { text: "KEYFRAME TIMELINE"; color: theme.text; font.pixelSize: theme.typeSmall; font.weight: Font.DemiBold }
                                Rectangle { Layout.preferredWidth: 17; Layout.preferredHeight: 17; radius: 9; color: "transparent"; border.color: theme.border
                                    Text { anchors.centerIn: parent; text: "?"; color: theme.textSecondary; font.pixelSize: 10 }
                                }
                                Text { text: (draftSampling.source_total_frames || 0) + " frames · " + (draftSampling.estimated_minutes || "—") + " min"; color: theme.textSecondary; font.pixelSize: theme.typeSmall }
                                Item { Layout.fillWidth: true }
                                GfComboBox { tokens: theme; model: ["All Frames", "Selected", "Candidates"]; Layout.preferredWidth: 145; Layout.preferredHeight: theme.compactHeight }
                                Text { text: "Zoom"; color: theme.textSecondary; font.pixelSize: theme.typeSmall }
                                Slider { Layout.preferredWidth: 90; from: 0.8; to: 1.5; value: 1.0 }
                            }
                            ListView {
                                id: proTimeline; Layout.fillWidth: true; Layout.fillHeight: true; orientation: ListView.Horizontal; spacing: 6; clip: true; boundsBehavior: Flickable.StopAtBounds
                                model: draftSampling.timeline || []
                                delegate: Rectangle {
                                    required property var modelData
                                    width: 108; height: proTimeline.height; color: theme.surfaceSunken; radius: theme.radiusSmall
                                    border.width: modelData.status === "selected" ? 2 : 1
                                    border.color: modelData.status === "selected" ? theme.accent : modelData.candidate ? theme.success : theme.border
                                    Image { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 3; height: parent.height - 42; source: fileUrl(modelData.thumbnail_path); fillMode: Image.PreserveAspectCrop; asynchronous: true }
                                    Column { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 38; spacing: 1
                                        Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: "#" + modelData.index; color: modelData.status === "selected" ? theme.accent : theme.textSecondary; font.pixelSize: 10; font.weight: Font.Medium }
                                        Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: "00:" + Number(modelData.timestamp_seconds).toFixed(2); color: theme.textSecondary; font.pixelSize: 10 }
                                    }
                                    Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 3; color: modelData.status === "selected" ? theme.accent : modelData.candidate ? theme.success : theme.textTertiary; radius: 2 }
                                    MouseArea { id: proThumbMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: proPlayer.position = modelData.timestamp_seconds * 1000 }
                                    GfToolTip { tokens: theme; tipText: modelData.reason || modelData.status || ""; requested: proThumbMouse.containsMouse && tipText !== "not_applicable" }
                                }
                                Row {
                                    anchors.fill: parent; spacing: 6; visible: proTimeline.count === 0 && importDraft.status === "analyzing"
                                    Repeater { model: 8; GfSkeleton { required property int index; tokens: theme; width: 108; height: parent.height; running: parent.visible } }
                                }
                                Text { anchors.centerIn: parent; visible: proTimeline.count === 0 && importDraft.status !== "analyzing"; text: "Analyze to populate the keyframe timeline"; color: theme.textTertiary }
                            }
                        }
                    }
                }
                GfPanel {
                    tokens: theme
                    SplitView.preferredWidth: proInspectorOpen ? proInspectorSize : 0
                    SplitView.minimumWidth: proInspectorOpen ? 310 : 0
                    SplitView.maximumWidth: 520
                    SplitView.fillHeight: true
                    opacity: proInspectorOpen ? 1 : 0; enabled: proInspectorOpen; clip: true; radius: theme.radiusMedium
                    onWidthChanged: if (layoutReady && proInspectorOpen && width >= 310) { proInspectorSize = width; queueLayoutSave() }
                    Behavior on SplitView.preferredWidth { NumberAnimation { duration: theme.motionSlow; easing.type: Easing.OutCubic } }
                    Behavior on opacity { NumberAnimation { duration: theme.motionNormal } }
                    ScrollView {
                        anchors.fill: parent; contentWidth: availableWidth; clip: true
                        ColumnLayout {
                            width: parent.width; spacing: 11
                            Text { text: "SAMPLING & ANALYSIS"; color: theme.textSecondary; font.pixelSize: theme.typeLabel; font.weight: Font.DemiBold; Layout.topMargin: 18; Layout.leftMargin: 18 }
                            GfComboBox { id: proProfile; tokens: theme; Layout.fillWidth: true; Layout.leftMargin: 18; Layout.rightMargin: 18; model: ["preview", "balanced", "quality"]; currentIndex: 1 }
                            GfComboBox { id: proSamplingMode; tokens: theme; Layout.fillWidth: true; Layout.leftMargin: 18; Layout.rightMargin: 18; model: ["Auto", "Target Count", "Interval", "All Frames"]; currentIndex: samplingModeIndex(draftSampling.sampling_mode) }
                            RowLayout { Layout.fillWidth: true; Layout.leftMargin: 18; Layout.rightMargin: 18; visible: proSamplingMode.currentIndex === 1
                                Text { text: "Requested"; color: theme.textSecondary; Layout.fillWidth: true }
                                GfSpinBox { id: proTarget; tokens: theme; from: 1; to: Math.max(1, proOut.value - proIn.value + 1); value: Math.min(to, draftSampling.requested_frame_count || 1); Layout.preferredWidth: 150 }
                            }
                            RowLayout { Layout.fillWidth: true; Layout.leftMargin: 18; Layout.rightMargin: 18; visible: proSamplingMode.currentIndex === 2
                                GfSpinBox { id: proInterval; tokens: theme; from: 1; to: 600; value: 1; Layout.fillWidth: true }
                                GfComboBox { id: proIntervalUnit; tokens: theme; model: ["frames", "seconds"]; Layout.fillWidth: true }
                            }
                            RowLayout { Layout.fillWidth: true; Layout.leftMargin: 18; Layout.rightMargin: 18
                                Text { text: "In"; color: theme.textSecondary; Layout.preferredWidth: 34 }
                                GfSpinBox { id: proIn; tokens: theme; from: 0; to: Math.max(0, proOut.value); value: draftSampling.in_frame || 0; Layout.fillWidth: true }
                            }
                            RowLayout { Layout.fillWidth: true; Layout.leftMargin: 18; Layout.rightMargin: 18
                                Text { text: "Out"; color: theme.textSecondary; Layout.preferredWidth: 34 }
                                GfSpinBox { id: proOut; tokens: theme; from: proIn.value; to: Math.max(0, (draftSampling.source_total_frames || 1) - 1); value: draftSampling.out_frame === undefined ? to : draftSampling.out_frame; Layout.fillWidth: true }
                            }
                            GfButton { tokens: theme; text: importDraft.status === "analyzing" ? "Analyzing…" : "Analyze"; primary: true; loading: importDraft.status === "analyzing"; enabled: importDraft.status !== "analyzing"; Layout.fillWidth: true; Layout.leftMargin: 18; Layout.rightMargin: 18; onClicked: applyProDraft() }
                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: theme.divider; Layout.topMargin: 8 }
                            GridLayout {
                                columns: 2; Layout.fillWidth: true; Layout.leftMargin: 18; Layout.rightMargin: 18; rowSpacing: 10
                                Text { text: "Source"; color: theme.textSecondary } Text { text: frameLabel(draftSampling.source_total_frames) + " frames"; color: theme.text; Layout.alignment: Qt.AlignRight }
                                Text { text: "Trimmed"; color: theme.textSecondary } Text { text: frameLabel(draftSampling.trimmed_frame_count); color: theme.text; Layout.alignment: Qt.AlignRight }
                                Text { text: "Candidates"; color: theme.textSecondary } Text { text: frameLabel(draftSampling.candidate_frame_count || draftSampling.estimated_candidate_count); color: theme.text; Layout.alignment: Qt.AlignRight }
                                Text { text: "Requested"; color: theme.textSecondary } Text { text: frameLabel(draftSampling.requested_frame_count); color: theme.text; Layout.alignment: Qt.AlignRight }
                                Text { text: "Selected"; color: theme.textSecondary } Text { text: frameLabel(draftSampling.selected_frame_count); color: theme.text; Layout.alignment: Qt.AlignRight }
                                Text { text: "Estimate"; color: theme.textSecondary } Text { text: frameLabel(draftSampling.estimated_minutes) + " min"; color: theme.text; Layout.alignment: Qt.AlignRight }
                                Text { text: "VRAM"; color: theme.textSecondary } Text { text: frameLabel(draftSampling.estimated_vram_gib) + " GiB"; color: theme.text; Layout.alignment: Qt.AlignRight }
                            }
                            Text { Layout.fillWidth: true; Layout.leftMargin: 18; Layout.rightMargin: 18; Layout.topMargin: 10; wrapMode: Text.Wrap; lineHeight: 1.35; color: importDraft.error ? theme.error : theme.textSecondary; text: importDraft.error || draftSampling.advisory || "Time coverage and quality filtering will be balanced." }
                            Item { Layout.fillHeight: true; Layout.minimumHeight: 10 }
                            RowLayout { Layout.fillWidth: true; Layout.margins: 18
                                GfButton { tokens: theme; text: "Cancel"; Layout.fillWidth: true; onClicked: { proPlayer.stop(); backend.cancelVideoImport(); proDialog.close() } }
                                GfButton { tokens: theme; text: "Generate"; primary: true; Layout.fillWidth: true; enabled: draftSampling.analysis_status === "complete" && importDraft.status === "ready"; onClicked: { proPlayer.stop(); proDialog.close(); backend.generateVideoImport() } }
                            }
                        }
                    }
                }
            }
        }
    }

    DropArea {
        id: globalVideoDrop
        anchors.fill: parent
        z: 1000
        keys: ["text/uri-list"]
        onDropped: function(drop) {
            if (drop.hasUrls && drop.urls.length > 0) {
                var path = localPathFromUrl(drop.urls[0])
                if (/\.(mp4|mov|mkv|avi|webm)$/i.test(path)) { drop.acceptProposedAction(); beginVideo(path) }
            }
        }
        Rectangle {
            anchors.fill: parent; visible: globalVideoDrop.containsDrag; color: theme.dark ? "#111111e8" : "#f7f7f7ed"; border.width: 2; border.color: theme.accent
            Column { anchors.centerIn: parent; spacing: 12
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: "⇩"; color: theme.accent; font.pixelSize: 44 }
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Drop video to import"; color: theme.text; font.pixelSize: 24; font.weight: Font.DemiBold }
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Choose Easy or Pro Mode after preflight"; color: theme.textSecondary; font.pixelSize: 14 }
            }
        }
    }

    header: Rectangle {
        id: appHeader
        height: theme.toolbarHeight
        color: theme.surface
        border.color: theme.divider
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 20; anchors.rightMargin: 16; spacing: 7
            Text { text: "GF"; font.weight: Font.Bold; font.pixelSize: 17; color: theme.accent }
            Text { text: "Gaussian Factory"; font.weight: Font.DemiBold; font.pixelSize: 15; color: theme.text; Layout.rightMargin: 14 }
            GfButton { tokens: theme; text: "New Project"; quiet: true; compact: true; onClicked: projectDialog.open() }
            GfButton { tokens: theme; text: "Import Video"; quiet: true; compact: true; onClicked: inputPicker.open() }
            GfButton { tokens: theme; text: "Import Images"; quiet: true; compact: true; enabled: !!current.project_id; onClicked: folderPicker.open() }
            Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 22; color: theme.divider; Layout.leftMargin: 7; Layout.rightMargin: 7 }
            GfButton { tokens: theme; text: current.status === "interrupted" ? "Resume" : "Run"; iconText: "▶"; primary: true; compact: true; Layout.preferredWidth: 86; enabled: !!current.input_path && current.status !== "running"; onClicked: backend.start() }
            GfButton { tokens: theme; text: "Cancel"; compact: true; Layout.preferredWidth: 88; enabled: current.status === "running"; onClicked: backend.cancel() }
            GfButton { tokens: theme; text: "Export"; iconText: "↑"; compact: true; Layout.preferredWidth: 92; enabled: stageState("export").status === "succeeded"; onClicked: backend.openExportFolder() }
            Item { Layout.fillWidth: true }
            GfStatusDot { tokens: theme; status: current.status || "idle" }
            Text { text: current.name || "Idle"; color: theme.textSecondary; elide: Text.ElideRight; Layout.maximumWidth: 210; font.pixelSize: theme.typeSmall }
            Text { visible: !!current.project_id; text: (current.status || "idle").toUpperCase(); color: statusColor(current.status || "idle"); font.pixelSize: theme.typeCaption; font.weight: Font.DemiBold }
            Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 22; color: theme.divider; Layout.leftMargin: 6; Layout.rightMargin: 5 }
            GfButton { tokens: theme; text: leftPaneOpen ? "Hide Left" : "Show Left"; quiet: true; compact: true; toolTip: "Toggle Projects and Artifacts"; onClicked: { leftPaneOpen = !leftPaneOpen; queueLayoutSave() } }
            GfButton { tokens: theme; text: rightPaneOpen ? "Hide Inspector" : "Show Inspector"; quiet: true; compact: true; toolTip: "Toggle Inspector"; onClicked: { rightPaneOpen = !rightPaneOpen; queueLayoutSave() } }
            GfButton { tokens: theme; text: theme.dark ? "☀" : "☾"; quiet: true; compact: true; onClicked: window.themeMode = theme.dark ? "light" : "dark" }
            GfButton { tokens: theme; text: "⚙  Settings"; quiet: true; compact: true; onClicked: settingsDialog.open() }
        }
    }

    ColumnLayout {
        anchors.fill: parent; spacing: 0
        SplitView {
            id: workspaceSplit
            Layout.fillWidth: true; Layout.fillHeight: true
            orientation: Qt.Horizontal
            handle: GfSplitHandle { tokens: theme; splitOrientation: Qt.Horizontal; onResetRequested: resetLayout() }

            Rectangle {
                id: leftPane
                SplitView.preferredWidth: leftPaneOpen ? leftPaneSize : 0
                SplitView.minimumWidth: leftPaneOpen ? 214 : 0
                SplitView.maximumWidth: 420
                SplitView.fillHeight: true
                opacity: leftPaneOpen ? 1 : 0; enabled: leftPaneOpen; clip: true
                color: theme.surface; border.color: theme.divider
                onWidthChanged: if (layoutReady && leftPaneOpen && width >= 214) { leftPaneSize = width; queueLayoutSave() }
                Behavior on SplitView.preferredWidth { NumberAnimation { duration: theme.motionSlow; easing.type: Easing.OutCubic } }
                Behavior on opacity { NumberAnimation { duration: theme.motionNormal } }
                ColumnLayout {
                    anchors.fill: parent; spacing: 0
                    Text { text: "PROJECTS"; color: theme.textSecondary; font.pixelSize: theme.typeCaption; font.weight: Font.DemiBold; Layout.leftMargin: 18; Layout.topMargin: 18; Layout.bottomMargin: 10 }
                    ListView {
                        id: projectList; Layout.fillWidth: true; Layout.preferredHeight: Math.min(238, Math.max(60, contentHeight)); clip: true; leftMargin: 10; rightMargin: 10; spacing: 3
                        model: JSON.parse(backend ? (backend.projectsJson || "[]") : "[]")
                        delegate: ItemDelegate {
                            required property var modelData
                            width: projectList.width - 20; height: 54; hoverEnabled: true
                            highlighted: modelData.project_id === current.project_id
                            onClicked: backend.selectProject(modelData.project_id)
                            background: Rectangle {
                                radius: theme.radiusMedium
                                color: highlighted ? theme.selectionStrong : hovered ? theme.controlHover : "transparent"
                                border.width: highlighted ? 1 : 0
                                border.color: activeFocus ? theme.accent : theme.border
                                Behavior on color { ColorAnimation { duration: theme.motionFast } }
                                Rectangle { width: 2; height: parent.height - 14; anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; radius: 1; color: theme.accent; visible: highlighted }
                            }
                            contentItem: RowLayout {
                                spacing: 8
                                Rectangle { Layout.preferredWidth: 22; Layout.preferredHeight: 22; radius: 4; color: theme.surfaceSunken; border.color: highlighted ? theme.accent : theme.border
                                    Text { anchors.centerIn: parent; text: "◇"; color: highlighted ? theme.accent : theme.textSecondary; font.pixelSize: 15 }
                                }
                                ColumnLayout { Layout.fillWidth: true; spacing: 2
                                    Text { Layout.fillWidth: true; text: modelData.name; color: theme.text; font.weight: Font.DemiBold; font.pixelSize: theme.typeBody; elide: Text.ElideRight }
                                    Text { text: modelData.status.toUpperCase() + "  ·  " + Math.round((modelData.progress || 0) * 100) + "%"; color: statusColor(modelData.status); font.pixelSize: theme.typeCaption }
                                }
                                Text { text: highlighted ? "›" : ""; color: theme.textSecondary; font.pixelSize: 18 }
                            }
                        }
                        Text { anchors.centerIn: parent; visible: projectList.count === 0; text: "No projects yet"; color: theme.textTertiary; font.pixelSize: theme.typeSmall }
                    }
                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: theme.divider; Layout.topMargin: 12 }
                    Text { text: "ARTIFACTS"; color: theme.textSecondary; font.pixelSize: theme.typeCaption; font.weight: Font.DemiBold; Layout.leftMargin: 18; Layout.topMargin: 16; Layout.bottomMargin: 9 }
                    ListView {
                        id: artifactList; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; leftMargin: 10; rightMargin: 10; spacing: 2
                        model: current.artifacts || []
                        delegate: ItemDelegate {
                            required property string modelData
                            width: artifactList.width - 20; height: 32; hoverEnabled: true
                            contentItem: Text { text: modelData.split(/[\\/]/).pop(); color: theme.textSecondary; font.pixelSize: theme.typeSmall; verticalAlignment: Text.AlignVCenter; elide: Text.ElideMiddle }
                            background: Rectangle { radius: theme.radiusSmall; color: hovered ? theme.controlHover : "transparent" }
                            ToolTip.visible: hovered; ToolTip.text: modelData
                        }
                        Column { anchors.centerIn: parent; width: parent.width - 40; spacing: 12; visible: artifactList.count === 0
                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "◇"; color: theme.textTertiary; font.pixelSize: 30 }
                            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap; color: theme.textTertiary; font.pixelSize: theme.typeSmall; lineHeight: 1.35; text: current.project_id ? "Artifacts will appear here\nas stages complete." : "Create or select a project" }
                        }
                    }
                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: theme.divider; visible: viewerActive }
                    Item {
                        Layout.fillWidth: true; Layout.preferredHeight: viewerActive ? (viewerLogsOpen ? 130 : 38) : 0; visible: viewerActive; clip: true
                        Behavior on Layout.preferredHeight { NumberAnimation { duration: theme.motionNormal } }
                        ColumnLayout { anchors.fill: parent; spacing: 0
                            Item { Layout.fillWidth: true; Layout.preferredHeight: 38
                                RowLayout { anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                                    Text { text: "ACTIVITY LOG"; color: theme.textSecondary; font.pixelSize: theme.typeCaption; font.weight: Font.DemiBold; Layout.fillWidth: true }
                                    Rectangle { Layout.preferredWidth: 16; Layout.preferredHeight: 16; radius: 8; color: theme.accent; visible: backend && backend.logText !== ""
                                        Text { anchors.centerIn: parent; text: "i"; color: "#ffffff"; font.pixelSize: 10; font.weight: Font.Bold }
                                    }
                                    GfButton { tokens: theme; text: viewerLogsOpen ? "⌄" : "›"; quiet: true; compact: true; Layout.preferredWidth: 26; onClicked: viewerLogsOpen = !viewerLogsOpen }
                                }
                            }
                            TextArea { Layout.fillWidth: true; Layout.fillHeight: true; visible: viewerLogsOpen; readOnly: true; text: backend ? backend.logText : ""; wrapMode: TextArea.Wrap; color: theme.textSecondary; font.family: theme.monoFont; font.pixelSize: 9; leftPadding: 12; rightPadding: 8; background: Rectangle { color: theme.surfaceSunken } }
                        }
                    }
                }
            }

            Rectangle {
                id: centerPane
                SplitView.fillWidth: true; SplitView.fillHeight: true; SplitView.minimumWidth: 560; color: theme.background
                SplitView {
                    id: centerVerticalSplit
                    anchors.fill: parent; orientation: Qt.Vertical; anchors.margins: viewerActive ? 10 : 8
                    handle: GfSplitHandle { tokens: theme; splitOrientation: Qt.Vertical; onResetRequested: resetLayout() }

                    Item {
                        SplitView.fillWidth: true; SplitView.fillHeight: true; SplitView.minimumHeight: 360; visible: !viewerActive
                        GfPanel {
                            tokens: theme; anchors.fill: parent; radius: theme.radiusLarge
                            Column {
                                anchors.centerIn: parent; width: Math.min(620, parent.width - 60); spacing: 16
                                Canvas {
                                    width: 250; height: 205; anchors.horizontalCenter: parent.horizontalCenter
                                    onPaint: {
                                        var ctx = getContext("2d"); ctx.reset();
                                        function cube(x,y,s,fill,stroke) {
                                            ctx.beginPath(); ctx.moveTo(x,y-s*.48); ctx.lineTo(x+s*.72,y-s*.08); ctx.lineTo(x,y+s*.34); ctx.lineTo(x-s*.72,y-s*.08); ctx.closePath(); ctx.fillStyle=fill; ctx.fill(); ctx.strokeStyle=stroke; ctx.lineWidth=1; ctx.stroke();
                                            ctx.beginPath(); ctx.moveTo(x-s*.72,y-s*.08); ctx.lineTo(x,y+s*.34); ctx.lineTo(x,y+s*1.18); ctx.lineTo(x-s*.72,y+s*.72); ctx.closePath(); ctx.fillStyle=fill; ctx.fill(); ctx.stroke();
                                            ctx.beginPath(); ctx.moveTo(x+s*.72,y-s*.08); ctx.lineTo(x,y+s*.34); ctx.lineTo(x,y+s*1.18); ctx.lineTo(x+s*.72,y+s*.72); ctx.closePath(); ctx.fillStyle=fill; ctx.fill(); ctx.stroke();
                                        }
                                        var faint = theme.dark ? "rgba(255,255,255,.035)" : "rgba(20,20,20,.018)";
                                        var edge = theme.dark ? "rgba(210,210,210,.24)" : "rgba(70,70,70,.18)";
                                        cube(112,50,62,faint,edge); cube(112,102,62,faint,edge); cube(178,116,36,theme.dark?"rgba(127,149,181,.20)":"rgba(83,107,140,.13)",theme.accent);
                                    }
                                    Connections { target: theme; function onDarkChanged() { parent.requestPaint() } }
                                }
                                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: current.project_id ? "Ready to reconstruct" : "Welcome to Gaussian Factory"; color: theme.text; font.pixelSize: theme.typeHero; font.weight: Font.DemiBold }
                                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap; lineHeight: 1.45; text: current.project_id ? "Import video or images to begin a high-quality 3D Gaussian reconstruction." : "Create a new project or import footage to reconstruct high-quality 3D Gaussian artifacts."; color: theme.textSecondary; font.pixelSize: 14 }
                                Row { anchors.horizontalCenter: parent.horizontalCenter; spacing: 12
                                    GfButton { tokens: theme; text: "New Project"; iconText: "+"; primary: true; implicitWidth: 164; onClicked: projectDialog.open() }
                                    GfButton { tokens: theme; text: "Import Video"; iconText: "▻"; implicitWidth: 164; onClicked: inputPicker.open() }
                                    GfButton { tokens: theme; text: "Import Images"; iconText: "▧"; implicitWidth: 164; enabled: !!current.project_id; onClicked: folderPicker.open() }
                                }
                                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: current.project_id ? "Project ready. Add an input to continue." : "Your projects will appear in the sidebar."; color: theme.textTertiary; font.pixelSize: theme.typeSmall; topPadding: 8 }
                            }
                        }
                    }

                    SplitView {
                        id: viewerVerticalSplit
                        SplitView.fillWidth: true; SplitView.fillHeight: true; visible: viewerActive
                        orientation: Qt.Vertical
                        handle: GfSplitHandle { tokens: theme; splitOrientation: Qt.Vertical; onResetRequested: { viewerTimelineSize = 196; queueLayoutSave() } }
                        GfPanel {
                            tokens: theme; sunken: true; SplitView.fillWidth: true; SplitView.fillHeight: true; SplitView.minimumHeight: 280; radius: theme.radiusMedium; clip: true
                            WebEngineView { id: viewer; objectName: "gaussianViewer"; anchors.fill: parent; anchors.margins: 1; url: backend ? backend.viewerUrl : "about:blank"; focus: true; onTitleChanged: if (backend) backend.viewerPageTitle(title) }
                            GfSkeleton { tokens: theme; anchors.fill: parent; anchors.margins: 1; visible: viewerLoading; running: visible }
                            Column {
                                anchors.centerIn: parent; spacing: 10; visible: viewerLoading
                                Text { anchors.horizontalCenter: parent.horizontalCenter; text: "◌"; color: theme.accent; font.pixelSize: 28; RotationAnimator on rotation { from: 0; to: 360; loops: Animation.Infinite; duration: 900 } }
                                Text { text: "Preparing 3D workspace…"; color: theme.textSecondary; font.pixelSize: theme.typeBody }
                            }
                            Rectangle {
                                anchors.fill: parent; visible: timelineMessage !== ""; color: theme.dark ? "#111111ed" : "#f7f7f7ed"
                                ColumnLayout { anchors.centerIn: parent; width: Math.min(parent.width - 60, 720); height: Math.min(parent.height - 50, 480)
                                    Image { Layout.fillWidth: true; Layout.fillHeight: true; source: timelinePreviewSource; fillMode: Image.PreserveAspectFit; asynchronous: true }
                                    Text { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; text: timelineMessage; color: theme.warning; font.pixelSize: 16; font.weight: Font.DemiBold }
                                }
                            }
                        }
                        GfPanel {
                            tokens: theme
                            SplitView.fillWidth: true
                            SplitView.preferredHeight: current.input_kind === "video" ? (timelineOpen ? viewerTimelineSize : 38) : 0
                            SplitView.minimumHeight: current.input_kind === "video" ? (timelineOpen ? 132 : 38) : 0
                            SplitView.maximumHeight: current.input_kind === "video" ? 360 : 0
                            visible: current.input_kind === "video"; radius: theme.radiusMedium; clip: true
                            onHeightChanged: if (layoutReady && timelineOpen && height >= 132) { viewerTimelineSize = height; queueLayoutSave() }
                            Behavior on SplitView.preferredHeight { NumberAnimation { duration: theme.motionSlow; easing.type: Easing.OutCubic } }
                            ColumnLayout { anchors.fill: parent; anchors.margins: 8; spacing: 6
                                RowLayout { Layout.fillWidth: true
                                    Text { text: "KEYFRAME CAMERA TIMELINE"; color: theme.text; font.pixelSize: theme.typeSmall; font.weight: Font.DemiBold }
                                    Text { text: "In " + (sampling.in_frame || 0) + " · Out " + frameLabel(sampling.out_frame) + "    " + (sampling.source_total_frames || 0) + " frames"; color: theme.textSecondary; font.pixelSize: theme.typeSmall }
                                    GfButton { tokens: theme; text: timelineOpen ? "Collapse" : "Expand"; quiet: true; compact: true; toolTip: "Toggle camera timeline"; onClicked: { timelineOpen = !timelineOpen; queueLayoutSave() } }
                                    GfButton { tokens: theme; text: "Prev"; compact: true; enabled: viewerTimelineModel.length > 0; onClicked: activateViewerFrame(viewerPlayhead - 1) }
                                    GfButton { tokens: theme; text: viewerPlayback.running ? "Pause" : "Play"; compact: true; enabled: viewerTimelineModel.length > 0; onClicked: viewerPlayback.running ? viewerPlayback.stop() : viewerPlayback.start() }
                                    GfButton { tokens: theme; text: "Next"; compact: true; enabled: viewerTimelineModel.length > 0; onClicked: activateViewerFrame(viewerPlayhead + 1) }
                                    Item { Layout.fillWidth: true }
                                    GfComboBox { id: viewerFilter; tokens: theme; model: ["All", "Selected", "Rejected", "Candidate", "Registered", "Unregistered"]; Layout.preferredWidth: 126; Layout.preferredHeight: theme.compactHeight; onActivated: { timelineFilter = currentText; viewerPlayhead = 0 } }
                                    Text { text: "Zoom"; color: theme.textSecondary; font.pixelSize: theme.typeSmall }
                                    Slider { from: 0.7; to: 1.7; value: 1.0; Layout.preferredWidth: 90; onMoved: timelineScale = value }
                                }
                                ListView {
                                    id: viewerTimeline; Layout.fillWidth: true; Layout.fillHeight: true; orientation: ListView.Horizontal; model: viewerTimelineModel; spacing: 6; clip: true; boundsBehavior: Flickable.StopAtBounds
                                    visible: timelineOpen
                                    delegate: Rectangle {
                                        required property var modelData; required property int index
                                        width: 110 * timelineScale; height: viewerTimeline.height; radius: theme.radiusSmall; color: theme.surfaceSunken
                                        border.width: index === viewerPlayhead ? 2 : 1
                                        border.color: index === viewerPlayhead ? theme.accent : modelData.registration_status === "registered" ? theme.success : modelData.selection_status === "selected" || modelData.status === "selected" ? theme.warning : theme.border
                                        Image { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 3; height: parent.height - 40; source: fileUrl(modelData.extracted_image_path || modelData.thumbnail_path); fillMode: Image.PreserveAspectCrop; asynchronous: true }
                                        Column { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 36
                                            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 9; color: index === viewerPlayhead ? theme.accent : theme.text; text: "#" + (modelData.source_frame_index === undefined ? modelData.index : modelData.source_frame_index) + " · " + Number(modelData.timestamp_seconds).toFixed(2) + "s" }
                                            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 9; color: modelData.registration_status === "registered" ? theme.success : theme.textSecondary; text: modelData.registration_status || modelData.selection_status || modelData.status || "frame" }
                                        }
                                        MouseArea { id: viewerThumbMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: activateViewerFrame(index) }
                                        GfToolTip { tokens: theme; tipText: modelData.reason || modelData.registration_status || modelData.status || ""; requested: viewerThumbMouse.containsMouse && tipText !== "not_applicable" }
                                    }
                                    Text { anchors.centerIn: parent; visible: viewerTimeline.count === 0; text: sampling.camera_mapping_stale ? "Timeline is stale · regenerate to rebuild cameras" : "No frames match this filter"; color: theme.textTertiary }
                                }
                            }
                        }
                    }

                    GfPanel {
                        tokens: theme
                        SplitView.fillWidth: true
                        SplitView.preferredHeight: !viewerActive ? (logsOpen ? welcomeLogSize : 36) : 0
                        SplitView.minimumHeight: !viewerActive ? (logsOpen ? 92 : 36) : 0
                        SplitView.maximumHeight: !viewerActive ? 300 : 0
                        visible: !viewerActive; radius: theme.radiusMedium; clip: true
                        onHeightChanged: if (layoutReady && logsOpen && !viewerActive && height >= 92) { welcomeLogSize = height; queueLayoutSave() }
                        Behavior on SplitView.preferredHeight { NumberAnimation { duration: theme.motionSlow; easing.type: Easing.OutCubic } }
                        ColumnLayout { anchors.fill: parent; spacing: 0
                            Item { Layout.fillWidth: true; Layout.preferredHeight: 36
                                RowLayout { anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10
                                    GfButton { tokens: theme; text: logsOpen ? "⌄" : "›"; quiet: true; compact: true; Layout.preferredWidth: 26; onClicked: logsOpen = !logsOpen }
                                    Text { text: "ACTIVITY LOG"; color: theme.textSecondary; font.pixelSize: theme.typeCaption; font.weight: Font.DemiBold }
                                    Item { Layout.fillWidth: true }
                                    Text { text: current.warnings && current.warnings.length ? current.warnings.length + " warning(s)" : "No warnings"; color: current.warnings && current.warnings.length ? theme.warning : theme.textTertiary; font.pixelSize: theme.typeCaption }
                                }
                            }
                            TextArea { Layout.fillWidth: true; Layout.fillHeight: true; visible: logsOpen; readOnly: true; text: backend ? backend.logText : ""; placeholderText: "Activity logs will appear here as processes run."; placeholderTextColor: theme.textTertiary; color: theme.textSecondary; wrapMode: TextArea.Wrap; font.family: theme.monoFont; font.pixelSize: theme.typeSmall; leftPadding: 12; rightPadding: 12; background: Rectangle { color: theme.surface } }
                        }
                    }
                }
            }

            Rectangle {
                id: rightPane
                SplitView.preferredWidth: rightPaneOpen ? rightPaneSize : 0
                SplitView.minimumWidth: rightPaneOpen ? 276 : 0
                SplitView.maximumWidth: 480
                SplitView.fillHeight: true
                opacity: rightPaneOpen ? 1 : 0; enabled: rightPaneOpen; clip: true
                color: theme.surface; border.color: theme.divider
                onWidthChanged: if (layoutReady && rightPaneOpen && width >= 276) { rightPaneSize = width; queueLayoutSave() }
                Behavior on SplitView.preferredWidth { NumberAnimation { duration: theme.motionSlow; easing.type: Easing.OutCubic } }
                Behavior on opacity { NumberAnimation { duration: theme.motionNormal } }
                ScrollView {
                    anchors.fill: parent; contentWidth: availableWidth; clip: true
                    ColumnLayout {
                        width: parent.width; spacing: 8
                        GfPanel {
                            tokens: theme; Layout.fillWidth: true; Layout.leftMargin: 8; Layout.rightMargin: 8; Layout.topMargin: 8; implicitHeight: profileColumn.implicitHeight + 28; radius: theme.radiusMedium
                            ColumnLayout { id: profileColumn; anchors.fill: parent; anchors.margins: 14; spacing: 8
                                RowLayout { Layout.fillWidth: true
                                    Text { text: "RECONSTRUCTION PROFILE"; color: theme.textSecondary; font.pixelSize: theme.typeCaption; font.weight: Font.DemiBold; Layout.fillWidth: true }
                                    Text { text: "?"; color: theme.textTertiary; font.pixelSize: theme.typeSmall }
                                }
                                GfComboBox { id: mode; tokens: theme; Layout.fillWidth: true; model: ["preview", "balanced", "quality"]; currentIndex: Math.max(0, model.indexOf(current.profile || "balanced")); enabled: current.status !== "running"; onActivated: backend.setProfile(currentText) }
                                Text { Layout.fillWidth: true; wrapMode: Text.Wrap; lineHeight: 1.35; color: theme.textSecondary; font.pixelSize: theme.typeSmall; text: (mode.currentText === "preview" ? "Fast iteration · 1,000 steps" : mode.currentText === "quality" ? "Maximum quality · 7,000 steps" : "Recommended balance · 3,000 steps") + (sampling.profile_label === "Custom" ? " · Custom frames" : " · Auto frames") }
                            }
                        }
                        GfPanel {
                            tokens: theme; Layout.fillWidth: true; Layout.leftMargin: 8; Layout.rightMargin: 8; implicitHeight: samplingColumn.implicitHeight + 28; radius: theme.radiusMedium; visible: current.input_kind === "video"
                            ColumnLayout { id: samplingColumn; anchors.fill: parent; anchors.margins: 14; spacing: 8
                                Text { text: "FRAME SAMPLING"; color: theme.textSecondary; font.pixelSize: theme.typeCaption; font.weight: Font.DemiBold }
                                GfComboBox { id: samplingMode; tokens: theme; Layout.fillWidth: true; model: ["Auto", "Target Count", "Interval", "All Frames"]; currentIndex: samplingModeIndex(sampling.sampling_mode); enabled: current.status !== "running" }
                                RowLayout { Layout.fillWidth: true; visible: samplingMode.currentIndex === 1
                                    Text { text: "Final frames"; color: theme.textSecondary; Layout.fillWidth: true }
                                    GfSpinBox { id: targetFrames; tokens: theme; from: 1; to: Math.max(1, sampling.trimmed_frame_count || sampling.source_total_frames || 1); value: Math.min(to, sampling.requested_frame_count || 1); Layout.preferredWidth: 98 }
                                    Text { text: "/ " + (sampling.trimmed_frame_count || sampling.source_total_frames || 0); color: theme.textSecondary }
                                }
                                RowLayout { Layout.fillWidth: true; visible: samplingMode.currentIndex === 2
                                    Text { text: "Every"; color: theme.textSecondary }
                                    GfSpinBox { id: intervalValue; tokens: theme; from: 1; to: 600; value: Math.max(1, Math.round(sampling.interval_value || 1)); Layout.preferredWidth: 82 }
                                    GfComboBox { id: intervalUnit; tokens: theme; model: ["frames", "seconds"]; currentIndex: Math.max(0, model.indexOf(sampling.interval_unit || "seconds")); Layout.fillWidth: true }
                                }
                                RowLayout { Layout.fillWidth: true
                                    Text { text: "In"; color: theme.textSecondary }
                                    GfSpinBox { id: persistedIn; tokens: theme; from: 0; to: Math.max(0, persistedOut.value); value: sampling.in_frame || 0; Layout.fillWidth: true }
                                    Text { text: "Out"; color: theme.textSecondary }
                                    GfSpinBox { id: persistedOut; tokens: theme; from: persistedIn.value; to: Math.max(0, (sampling.source_total_frames || 1) - 1); value: sampling.out_frame === undefined ? to : sampling.out_frame; Layout.fillWidth: true }
                                }
                                RowLayout { Layout.fillWidth: true
                                    GfButton { tokens: theme; text: "Apply"; compact: true; Layout.fillWidth: true; enabled: current.status !== "running"; onClicked: backend.setSampling(samplingModeId(samplingMode.currentIndex), targetFrames.value, intervalValue.value, intervalUnit.currentText, persistedIn.value, persistedOut.value) }
                                    GfButton { tokens: theme; text: sampling.analysis_status === "analyzing" ? "Analyzing…" : "Reanalyze"; compact: true; primary: true; Layout.fillWidth: true; loading: sampling.analysis_status === "analyzing"; enabled: current.status !== "running" && sampling.analysis_status !== "analyzing"; onClicked: { backend.setSampling(samplingModeId(samplingMode.currentIndex), targetFrames.value, intervalValue.value, intervalUnit.currentText, persistedIn.value, persistedOut.value); backend.analyzeSampling() } }
                                }
                                GridLayout { columns: 2; Layout.fillWidth: true; rowSpacing: 5
                                    Text { text: "Source"; color: theme.textSecondary; font.pixelSize: theme.typeSmall } Text { text: (sampling.source_total_frames || 0) + " frames"; color: theme.text; font.pixelSize: theme.typeSmall; Layout.alignment: Qt.AlignRight }
                                    Text { text: "Duration / FPS"; color: theme.textSecondary; font.pixelSize: theme.typeSmall } Text { text: Number(sampling.duration_seconds || 0).toFixed(2) + " s · " + Number(sampling.fps || 0).toFixed(2); color: theme.text; font.pixelSize: theme.typeSmall; Layout.alignment: Qt.AlignRight }
                                    Text { text: "Resolution"; color: theme.textSecondary; font.pixelSize: theme.typeSmall } Text { text: (sampling.width || 0) + " × " + (sampling.height || 0); color: theme.text; font.pixelSize: theme.typeSmall; Layout.alignment: Qt.AlignRight }
                                    Text { text: "Candidates"; color: theme.textSecondary; font.pixelSize: theme.typeSmall } Text { text: frameLabel(sampling.candidate_frame_count || sampling.estimated_candidate_count); color: theme.text; font.pixelSize: theme.typeSmall; Layout.alignment: Qt.AlignRight }
                                    Text { text: "Requested / selected"; color: theme.textSecondary; font.pixelSize: theme.typeSmall } Text { text: (sampling.requested_frame_count || 0) + " / " + (sampling.selected_frame_count || 0); color: theme.text; font.pixelSize: theme.typeSmall; Layout.alignment: Qt.AlignRight }
                                }
                                Text { Layout.fillWidth: true; wrapMode: Text.Wrap; lineHeight: 1.3; color: sampling.warnings && sampling.warnings.length ? theme.warning : theme.textSecondary; font.pixelSize: theme.typeSmall; text: sampling.warnings && sampling.warnings.length ? sampling.warnings.join("\n") : (sampling.advisory || "Time coverage and quality filtering are balanced.") }
                                Text { text: "Estimate · " + frameLabel(sampling.estimated_minutes) + " min · " + frameLabel(sampling.estimated_vram_gib) + " GiB VRAM"; color: theme.textSecondary; font.pixelSize: theme.typeSmall }
                            }
                        }
                        GfPanel {
                            tokens: theme; Layout.fillWidth: true; Layout.leftMargin: 8; Layout.rightMargin: 8; implicitHeight: statusColumn.implicitHeight + 28; radius: theme.radiusMedium
                            ColumnLayout { id: statusColumn; anchors.fill: parent; anchors.margins: 14; spacing: 10
                                Text { text: "QUALITY & STATUS"; color: theme.textSecondary; font.pixelSize: theme.typeCaption; font.weight: Font.DemiBold }
                                GridLayout { columns: 2; Layout.fillWidth: true; rowSpacing: 7
                                    Text { text: "Progress"; color: theme.textSecondary; font.pixelSize: theme.typeSmall } Text { text: Math.round((current.progress || 0) * 100) + "%"; color: theme.text; font.pixelSize: theme.typeSmall; font.weight: Font.DemiBold; Layout.alignment: Qt.AlignRight }
                                    Text { text: "Current stage"; color: theme.textSecondary; font.pixelSize: theme.typeSmall } Text { text: current.current_stage || "—"; color: theme.text; font.pixelSize: theme.typeSmall; Layout.alignment: Qt.AlignRight }
                                    Text { text: "Gaussians"; color: theme.textSecondary; font.pixelSize: theme.typeSmall } Text { text: frameLabel((stageState("validate").metrics || {}).gaussian_count); color: theme.text; font.pixelSize: theme.typeSmall; Layout.alignment: Qt.AlignRight }
                                    Text { text: "Profile"; color: theme.textSecondary; font.pixelSize: theme.typeSmall } Text { text: (current.profile || "balanced").toUpperCase(); color: theme.text; font.pixelSize: theme.typeSmall; font.weight: Font.DemiBold; Layout.alignment: Qt.AlignRight }
                                }
                                GfProgressBar { tokens: theme; Layout.fillWidth: true; value: current.progress || 0; indeterminate: current.status === "running" && !current.progress }
                                GfButton { tokens: theme; text: "Open 3D Viewer"; primary: true; compact: true; Layout.fillWidth: true; visible: stageState("validate").status === "succeeded" && !viewerActive; onClicked: backend.loadViewer() }
                            }
                        }
                        GfPanel {
                            tokens: theme; Layout.fillWidth: true; Layout.leftMargin: 8; Layout.rightMargin: 8; Layout.bottomMargin: 8; implicitHeight: stagesColumn.implicitHeight + 28; radius: theme.radiusMedium
                            ColumnLayout { id: stagesColumn; anchors.fill: parent; anchors.margins: 14; spacing: 7
                                Text { text: "PIPELINE STAGES"; color: theme.textSecondary; font.pixelSize: theme.typeCaption; font.weight: Font.DemiBold; Layout.bottomMargin: 2 }
                                Repeater {
                                    model: ["ingest", "colmap", "fallback", "train", "validate", "export"]
                                    delegate: Rectangle {
                                        required property string modelData
                                        Layout.fillWidth: true; height: 34; radius: theme.radiusSmall
                                        color: current.current_stage === modelData ? theme.selection : theme.surfaceRaised
                                        border.color: current.current_stage === modelData ? theme.accent : theme.borderSubtle
                                        RowLayout { anchors.fill: parent; anchors.leftMargin: 9; anchors.rightMargin: 9
                                            GfStatusDot { tokens: theme; status: stageState(modelData).status }
                                            Text { text: modelData.charAt(0).toUpperCase() + modelData.slice(1); color: theme.text; font.pixelSize: theme.typeSmall; font.weight: current.current_stage === modelData ? Font.DemiBold : Font.Normal; Layout.fillWidth: true }
                                            Text { text: stageState(modelData).status.toUpperCase(); color: statusColor(stageState(modelData).status); font.pixelSize: 9 }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 26; color: theme.surface; border.color: theme.divider
            RowLayout { anchors.fill: parent; anchors.leftMargin: 18; anchors.rightMargin: 18
                Text { text: "Ready."; color: theme.textSecondary; font.pixelSize: theme.typeCaption; Layout.fillWidth: true }
                Text { text: theme.dark ? "Dark" : "Light"; color: theme.textTertiary; font.pixelSize: theme.typeCaption }
            }
        }
    }
}
