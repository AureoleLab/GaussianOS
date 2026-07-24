import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtCore as QtCore
import "components" as UI
import "design" as Design

ApplicationWindow {
    id: window
    width: startupWidth
    height: startupHeight
    minimumWidth: 1180
    minimumHeight: 720
    visible: true
    title: "GaussianOS · ModernUI"
    color: theme.canvas

    property string currentPage: "workspace"
    property var projects: []
    property var trashProjects: []
    property var current: ({})
    property var importDraft: ({})
    property var settingsState: ({})
    property var runtimeState: ({})
    property var librarySelection: ({})
    property var managedProject: ({})
    property var purgeTarget: ({})
    property string currentProject: current.name || "No project selected"
    property string currentProjectId: current.project_id || ""
    property bool leftOpen: true
    property bool inspectorOpen: true
    property bool running: current.status === "running"
    property int progress: Math.round(Number(current.progress || 0) * 100)
    property string globalNotice: ""
    property string selectedVideoPath: ""
    property string pendingVideoMode: ""
    property bool horizontalSplitDragging: false
    property bool splitSnapping: false
    property string themeMode: useSavedSettings ? modernSettings.themeMode : startupTheme
    property string interfaceSize: useSavedSettings ? modernSettings.interfaceSize : "standard"
    property string typographyWeight: useSavedSettings ? modernSettings.typographyWeight : "balanced"
    property bool sidebarWidthCustomized: useSavedSettings && modernSettings.sidebarPaneWidth >= theme.density.sidebarMinWidth
    property bool inspectorWidthCustomized: useSavedSettings && modernSettings.inspectorPaneWidth >= theme.density.inspectorMinWidth
    property bool activityLogHeightCustomized: useSavedSettings && modernSettings.activityLogHeight >= theme.density.activityLogCollapsedHeight
    property real customSidebarPaneWidth: sidebarWidthCustomized ? modernSettings.sidebarPaneWidth : theme.density.sidebarWidth
    property real customInspectorPaneWidth: inspectorWidthCustomized ? modernSettings.inspectorPaneWidth : theme.density.inspectorWidth
    property real customActivityLogHeight: activityLogHeightCustomized ? modernSettings.activityLogHeight : theme.density.activityLogHeight
    readonly property real effectiveSidebarPaneWidth: sidebarWidthCustomized ? customSidebarPaneWidth : theme.density.sidebarWidth
    readonly property real effectiveInspectorPaneWidth: inspectorWidthCustomized ? customInspectorPaneWidth : theme.density.inspectorWidth
    readonly property real effectiveActivityLogHeight: activityLogHeightCustomized ? customActivityLogHeight : theme.density.activityLogHeight
    readonly property var libraryProjects: {
        var result = []
        for (var index = 0; index < projects.length; ++index)
            result.push(presentProject(projects[index], projects[index].archived ? "archived" : "active"))
        for (var trashIndex = 0; trashIndex < trashProjects.length; ++trashIndex)
            result.push(presentProject(trashProjects[trashIndex], "trash"))
        return result
    }
    readonly property alias themeTokens: theme
    readonly property alias typeTokens: type

    QtCore.Settings {
        id: modernSettings
        category: "modern-ui-v1"
        property string themeMode: "light"
        property string interfaceSize: "standard"
        property string typographyWeight: "balanced"
        property bool reduceMotion: false
        property bool restoreLastProject: false
        property string lastProjectId: ""
        property real sidebarPaneWidth: -1
        property real inspectorPaneWidth: -1
        property real activityLogHeight: -1
    }

    Design.Motion { id: motionTokens; reducedMotion: useSavedSettings ? modernSettings.reduceMotion : false }
    Design.Density { id: densityTokens; mode: window.interfaceSize }
    Design.Theme { id: theme; mode: window.themeMode; motion: motionTokens; density: densityTokens }
    Design.Typography { id: type; densityMode: densityTokens.mode; weightPreset: window.typographyWeight }

    function showNotice(message) {
        globalNotice = message
        noticeTimer.restart()
    }

    function parseJson(value, fallback) {
        try { return JSON.parse(value || "") } catch (error) { return fallback }
    }

    function formatBytes(value) {
        var bytes = Math.max(0, Number(value || 0))
        if (bytes === 0) return "—"
        if (bytes < 1024) return Math.round(bytes) + " B"
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KiB"
        if (bytes < 1024 * 1024 * 1024) return (bytes / 1048576).toFixed(1) + " MiB"
        return (bytes / 1073741824).toFixed(2) + " GiB"
    }

    function presentProject(project, group) {
        var sampling = project.sampling || ({})
        var inputCount = Number(sampling.source_total_frames || 0)
        return {
            "id": String(project.project_id || ""),
            "project_id": String(project.project_id || ""),
            "name": String(project.name || "Untitled"),
            "status": group === "trash" ? "Trash"
                : group === "archived" ? "Archived"
                : String(project.status || "Idle"),
            "group": group,
            "date": String(project.updated_at || project.deleted_at || project.archived_at || "—"),
            "size": formatBytes(project.estimated_bytes || 0),
            "location": String(project.root || project.internal_workspace || ""),
            "profile": String(project.profile || "—"),
            "source": project.input_kind
                ? String(project.input_kind) + (inputCount ? " · " + inputCount + " frames" : "")
                : "No input",
            "raw": project
        }
    }

    function refreshBackend() {
        projects = parseJson(backend.projectsJson, [])
        trashProjects = parseJson(backend.trashJson, [])
        current = parseJson(backend.currentJson, {})
        if (current.project_id)
            modernSettings.lastProjectId = current.project_id
        importDraft = parseJson(backend.importJson, {})
        settingsState = parseJson(backend.settingsJson, {})
        runtimeState = parseJson(backend.runtimeJson, {})
        if (librarySelection.project_id) {
            for (var index = 0; index < libraryProjects.length; ++index) {
                if (libraryProjects[index].project_id === librarySelection.project_id) {
                    librarySelection = libraryProjects[index]
                    return
                }
            }
        }
        librarySelection = libraryProjects.length > 0 ? libraryProjects[0] : ({})
    }

    function openProject(project) {
        if (!project || !project.project_id || project.group === "trash")
            return
        if (project.group === "archived") {
            showNotice("Restore archived projects before opening them")
            return
        }
        currentPage = "workspace"
        backend.selectProject(project.project_id)
    }

    function manage(project) {
        if (!project || !project.project_id)
            return
        managedProject = project
        manageName.text = project.name || ""
        duplicateName.text = (project.name || "Project") + " Copy"
        manageDialog.open()
    }

    function requestPurge(project) {
        purgeTarget = project
        purgeConfirm.text = ""
        purgeDialog.open()
    }

    function localPathFromUrl(value) {
        if (value && typeof value.toLocalFile === "function") return value.toLocalFile()
        var text = value && typeof value.toString === "function" ? value.toString() : String(value || "")
        if (/^file:\/\/\//i.test(text)) text = text.substring(8)
        else if (/^file:\/\//i.test(text)) text = "//" + text.substring(7)
        try { return decodeURIComponent(text) } catch (error) { return text }
    }

    function beginVideo(path) {
        selectedVideoPath = path
        pendingVideoMode = ""
        backend.beginVideoImport(path)
        importDialog.open()
    }

    function openProAcceptance(path) {
        beginVideo(path)
    }

    function setThemeMode(value) {
        appearanceTransition.restart()
        window.themeMode = value
        if (useSavedSettings)
            modernSettings.themeMode = value
    }

    function setInterfaceSize(value) {
        appearanceTransition.restart()
        motionTokens.densityChanging = true
        window.interfaceSize = value
        if (useSavedSettings)
            modernSettings.interfaceSize = value
        densityChangeTimer.restart()
    }

    function setTypographyWeight(value) {
        appearanceTransition.restart()
        window.typographyWeight = value
        if (useSavedSettings)
            modernSettings.typographyWeight = value
    }

    function persistSplitSizes() {
        if (!useSavedSettings)
            return
        modernSettings.sidebarPaneWidth = sidebarWidthCustomized ? customSidebarPaneWidth : -1
        modernSettings.inspectorPaneWidth = inspectorWidthCustomized ? customInspectorPaneWidth : -1
        modernSettings.activityLogHeight = activityLogHeightCustomized ? customActivityLogHeight : -1
    }

    function resetSidebarWidth() {
        sidebarWidthCustomized = false
        customSidebarPaneWidth = theme.density.sidebarWidth
        persistSplitSizes()
    }

    function resetInspectorWidth() {
        inspectorWidthCustomized = false
        customInspectorPaneWidth = theme.density.inspectorWidth
        persistSplitSizes()
    }

    function resetActivityLogHeight() {
        activityLogHeightCustomized = false
        customActivityLogHeight = theme.density.activityLogHeight
        persistSplitSizes()
    }

    Timer {
        id: noticeTimer
        interval: 3200
        onTriggered: globalNotice = ""
    }

    Timer {
        id: densityChangeTimer
        interval: motionTokens.densityDuration + 40
        onTriggered: motionTokens.densityChanging = false
    }

    Timer {
        id: splitSnapTimer
        interval: motionTokens.splitSnapDuration + 20
        onTriggered: window.splitSnapping = false
    }

    SequentialAnimation {
        id: appearanceTransition
        NumberAnimation {
            target: appLayout
            property: "opacity"
            to: motionTokens.reducedMotion ? 1 : 0.88
            duration: motionTokens.reducedMotion ? 1 : 60
            easing.type: Easing.InCubic
        }
        NumberAnimation {
            target: appLayout
            property: "opacity"
            to: 1
            duration: motionTokens.reducedMotion ? 1 : 100
            easing.type: Easing.OutCubic
        }
    }

    Connections {
        target: backend
        function onChanged() { window.refreshBackend() }
        function onImportChanged() { window.refreshBackend() }
        function onSettingsChanged() { window.refreshBackend() }
        function onViewerUrlChanged() { window.refreshBackend() }
        function onViewerStatusChanged() { window.refreshBackend() }
        function onAcceptanceRequested() {
            viewerPane.runAcceptance(backend.acceptanceCameraTimeline)
        }
    }

    Component.onCompleted: {
        refreshBackend()
        if (modernSettings.restoreLastProject && modernSettings.lastProjectId)
            Qt.callLater(function() { backend.selectProject(modernSettings.lastProjectId) })
    }

    Shortcut { sequence: "Ctrl+N"; onActivated: newProjectDialog.open() }
    Shortcut { sequence: "Ctrl+1"; onActivated: setThemeMode("light") }
    Shortcut { sequence: "Ctrl+2"; onActivated: setThemeMode("dark") }
    Shortcut { sequence: "Ctrl+,"; onActivated: settingsDialog.open() }

    ColumnLayout {
        id: appLayout
        anchors.fill: parent
        spacing: 0

        Rectangle {
            id: topbar
            Layout.fillWidth: true
            Layout.preferredHeight: theme.density.toolbarHeight
            color: theme.chrome
            Behavior on Layout.preferredHeight {
                NumberAnimation { duration: theme.motion.densityDuration; easing.type: Easing.OutCubic }
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: theme.density.sidePadding
                anchors.rightMargin: theme.density.sidePadding
                spacing: theme.density.itemGap

                UI.BrandGlyph {
                    color: theme.accent
                    size: theme.density.iconBrand
                    Layout.rightMargin: 2
                }
                Text {
                    visible: window.width >= 1320
                    text: "GaussianOS"
                    color: theme.ink
                    font.family: type.family
                    font.pixelSize: type.headingSize
                    font.weight: type.semibold
                    Layout.rightMargin: 12
                }
                UI.ToolbarButton {
                    theme: window.themeTokens; type: window.typeTokens
                    text: window.width >= 1440 ? "New project" : ""
                    iconName: "add"
                    quiet: true
                    compact: true
                    onClicked: newProjectDialog.open()
                }
                UI.ToolbarButton {
                    theme: window.themeTokens; type: window.typeTokens
                    text: window.width >= 1440 ? "Import video" : ""
                    iconName: "video"
                    quiet: true
                    compact: true
                    onClicked: videoPicker.open()
                }
                UI.ToolbarButton {
                    theme: window.themeTokens; type: window.typeTokens
                    text: window.width >= 1510 ? "Import images" : ""
                    iconName: "images"
                    quiet: true
                    compact: true
                    enabled: !!window.currentProjectId && !window.running
                    onClicked: imageFolderPicker.open()
                }

                UI.Divider {
                    theme: window.themeTokens
                    vertical: true
                    Layout.leftMargin: 6
                    Layout.rightMargin: 6
                }

                UI.ToolbarButton {
                    theme: window.themeTokens; type: window.typeTokens
                    text: running ? "Running" : "Run"
                    iconName: "play"
                    primary: true
                    compact: true
                    enabled: !!window.currentProjectId && !running
                    onClicked: backend.start()
                }
                UI.ToolbarButton {
                    theme: window.themeTokens; type: window.typeTokens
                    text: "Cancel"
                    iconName: "stop"
                    compact: true
                    enabled: running
                    onClicked: backend.cancel()
                }
                UI.ToolbarButton {
                    theme: window.themeTokens; type: window.typeTokens
                    text: "Export"
                    iconName: "export"
                    compact: true
                    enabled: !!window.currentProjectId
                    onClicked: backend.openExportFolder()
                }

                Item { Layout.fillWidth: true }

                UI.StatusBadge {
                    theme: window.themeTokens
                    type: window.typeTokens
                    text: running ? "RUNNING " + progress + "%"
                        : String(current.status || "NO PROJECT").toUpperCase()
                    status: running ? "running"
                        : current.status === "failed" ? "error"
                        : currentProjectId ? "success" : "neutral"
                }
                Text {
                    visible: window.width >= 1380
                    text: currentProject
                    color: theme.inkSecondary
                    font.family: type.family
                    font.pixelSize: type.microSize
                    font.weight: type.medium
                    Layout.leftMargin: 3
                    Layout.rightMargin: 5
                }

                UI.Divider { theme: window.themeTokens; vertical: true; Layout.leftMargin: 3; Layout.rightMargin: 3 }

                UI.IconButton {
                    theme: window.themeTokens; type: window.typeTokens
                    iconName: "sidebar"
                    toolTip: leftOpen ? "Hide sidebar" : "Show sidebar"
                    selected: leftOpen
                    prominent: true
                    toggle: true
                    onClicked: leftOpen = !leftOpen
                }
                UI.IconButton {
                    theme: window.themeTokens; type: window.typeTokens
                    iconName: "inspector"
                    toolTip: inspectorOpen ? "Hide inspector" : "Show inspector"
                    selected: inspectorOpen
                    prominent: true
                    toggle: true
                    onClicked: inspectorOpen = !inspectorOpen
                }
                UI.IconButton {
                    theme: window.themeTokens; type: window.typeTokens
                    iconName: theme.dark ? "sun" : "moon"
                    toolTip: theme.dark ? "Use light theme" : "Use dark theme"
                    prominent: true
                    onClicked: setThemeMode(theme.dark ? "light" : "dark")
                }
                UI.IconButton {
                    theme: window.themeTokens; type: window.typeTokens
                    iconName: "settings"
                    toolTip: "Settings"
                    prominent: true
                    onClicked: settingsDialog.open()
                }
            }
        }

        UI.Divider { theme: window.themeTokens; Layout.fillWidth: true }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            UI.Sidebar {
                id: sidebar
                objectName: "sidebarPane"
                Layout.preferredWidth: leftOpen ? window.effectiveSidebarPaneWidth : 0
                Layout.minimumWidth: leftOpen ? theme.density.sidebarMinWidth : 0
                Layout.maximumWidth: leftOpen ? theme.density.sidebarMaxWidth : 0
                Layout.fillHeight: true
                opacity: leftOpen ? 1 : 0
                enabled: leftOpen
                clip: true
                theme: window.themeTokens
                type: window.typeTokens
                currentPage: window.currentPage
                currentProjectId: window.currentProjectId
                projects: window.projects.filter(function(project) { return !project.archived })
                artifacts: window.current.artifacts || []
                libraryPath: window.projects.length > 0
                    ? String(window.projects[0].library_root || "")
                    : "No projects yet"
                onPageSelected: function(page) { window.currentPage = page }
                onProjectSelected: function(project) { window.openProject(window.presentProject(project, "active")) }
                onManageProject: function(project) { window.manage(window.presentProject(project, "active")) }
                onNewProject: newProjectDialog.open()
                onOpenLibrary: backend.openProjectsFolder()
                transform: Translate {
                    x: leftOpen ? 0 : -theme.motion.paneTravel
                    Behavior on x {
                        NumberAnimation {
                            duration: theme.motion.adaptivePaneDuration
                            easing.type: Easing.BezierSpline
                            easing.bezierCurve: theme.motion.standardCurve
                        }
                    }
                }
                Behavior on Layout.preferredWidth {
                    enabled: !window.horizontalSplitDragging
                    NumberAnimation {
                        duration: window.splitSnapping
                            ? theme.motion.splitSnapDuration : theme.motion.adaptivePaneDuration
                        easing.type: Easing.BezierSpline
                        easing.bezierCurve: theme.motion.navigationCurve
                    }
                }
                Behavior on opacity {
                    NumberAnimation { duration: theme.motion.adaptivePaneDuration; easing.type: Easing.OutCubic }
                }
            }

            UI.PaneSplitHandle {
                id: sidebarSplitHandle
                objectName: "sidebarSplitHandle"
                property real dragStart: 0
                theme: window.themeTokens
                orientation: Qt.Horizontal
                interactive: window.leftOpen
                Layout.preferredWidth: leftOpen ? theme.density.splitHandleExtent : 0
                Layout.fillHeight: true
                opacity: leftOpen ? 1 : 0
                onDragStarted: {
                    dragStart = sidebar.width
                    window.horizontalSplitDragging = true
                }
                onDragMoved: function(delta) {
                    window.sidebarWidthCustomized = true
                    window.customSidebarPaneWidth = Math.max(
                        theme.density.sidebarMinWidth,
                        Math.min(theme.density.sidebarMaxWidth, dragStart + delta)
                    )
                }
                onDragFinished: {
                    if (!window.horizontalSplitDragging)
                        return
                    window.horizontalSplitDragging = false
                    window.splitSnapping = true
                    window.customSidebarPaneWidth = Math.round(window.customSidebarPaneWidth / 2) * 2
                    window.sidebarWidthCustomized = true
                    window.persistSplitSizes()
                    splitSnapTimer.restart()
                }
                onResetRequested: {
                    window.splitSnapping = true
                    window.resetSidebarWidth()
                    splitSnapTimer.restart()
                }
                Behavior on opacity {
                    NumberAnimation { duration: theme.motion.adaptivePaneDuration; easing.type: Easing.OutCubic }
                }
            }

            Item {
                id: pageHost
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: theme.density.viewerMinWidth
                clip: true

                UI.ViewerPane {
                    id: viewerPane
                    objectName: "workspacePage"
                    width: parent.width
                    height: parent.height
                    y: 0
                    theme: window.themeTokens
                    type: window.typeTokens
                    projectName: window.currentProject
                    running: window.running
                    notice: window.globalNotice
                    viewerUrl: backend.viewerUrl
                    viewerStatus: backend.viewerStatus
                    logText: backend.logText
                    timeline: (window.current.sampling || {}).timeline || []
                    activityLogHeight: window.effectiveActivityLogHeight
                    enabled: window.currentPage === "workspace"
                    opacity: window.currentPage === "workspace" ? 1 : 0
                    x: window.currentPage === "workspace" ? 0 : -theme.motion.pageTravel
                    scale: window.currentPage === "workspace" ? 1 : theme.motion.pageScale
                    z: window.currentPage === "workspace" ? 2 : 1
                    onNoticeChanged: if (notice.length > 0) noticeTimer.restart()
                    onRunRequested: backend.start()
                    onCancelRequested: backend.cancel()
                    onLoadViewerRequested: backend.loadViewer()
                    onExportRequested: backend.openExportFolder()
                    onViewerTitleChanged: function(title) { backend.viewerPageTitle(title) }
                    onAcceptanceResult: function(result) { backend.viewerAcceptanceResult(result) }
                    onLogHeightAdjusted: function(value, reset) {
                        if (reset) {
                            window.splitSnapping = true
                            window.resetActivityLogHeight()
                            splitSnapTimer.restart()
                            return
                        }
                        window.activityLogHeightCustomized = true
                        window.customActivityLogHeight = value
                        window.persistSplitSizes()
                    }
                    Behavior on opacity {
                        NumberAnimation {
                            duration: theme.motion.pageTransitionDuration
                            easing.type: Easing.BezierSpline
                            easing.bezierCurve: theme.motion.navigationCurve
                        }
                    }
                    Behavior on x {
                        NumberAnimation {
                            duration: theme.motion.pageTransitionDuration
                            easing.type: Easing.BezierSpline
                            easing.bezierCurve: theme.motion.navigationCurve
                        }
                    }
                    Behavior on scale {
                        NumberAnimation {
                            duration: theme.motion.pageTransitionDuration
                            easing.type: Easing.BezierSpline
                            easing.bezierCurve: theme.motion.navigationCurve
                        }
                    }
                }

                UI.ProjectLibrary {
                    id: projectLibrary
                    objectName: "libraryPage"
                    width: parent.width
                    height: parent.height
                    y: 0
                    theme: window.themeTokens
                    type: window.typeTokens
                    projects: window.libraryProjects
                    selectedProjectId: window.librarySelection.project_id || ""
                    enabled: window.currentPage === "library"
                    opacity: window.currentPage === "library" ? 1 : 0
                    x: window.currentPage === "library" ? 0 : theme.motion.pageTravel
                    scale: window.currentPage === "library" ? 1 : theme.motion.pageScale
                    z: window.currentPage === "library" ? 2 : 1
                    onProjectSelected: function(project) {
                        window.librarySelection = project
                    }
                    onOpenLibraryRequested: backend.openProjectsFolder()
                    onOpenFolderRequested: function(project) { backend.openProjectFolder(project.project_id) }
                    onRenameRequested: function(project) { window.manage(project) }
                    onDuplicateRequested: function(project) { window.manage(project) }
                    onArchiveRequested: function(project, archived) {
                        backend.setProjectArchived(project.project_id, archived)
                    }
                    onRestoreRequested: function(project) { backend.restoreProject(project.project_id) }
                    onPurgeRequested: function(project) { window.requestPurge(project) }
                    Behavior on opacity {
                        NumberAnimation {
                            duration: theme.motion.pageTransitionDuration
                            easing.type: Easing.BezierSpline
                            easing.bezierCurve: theme.motion.navigationCurve
                        }
                    }
                    Behavior on x {
                        NumberAnimation {
                            duration: theme.motion.pageTransitionDuration
                            easing.type: Easing.BezierSpline
                            easing.bezierCurve: theme.motion.navigationCurve
                        }
                    }
                    Behavior on scale {
                        NumberAnimation {
                            duration: theme.motion.pageTransitionDuration
                            easing.type: Easing.BezierSpline
                            easing.bezierCurve: theme.motion.navigationCurve
                        }
                    }
                }
            }

            UI.PaneSplitHandle {
                id: inspectorSplitHandle
                objectName: "inspectorSplitHandle"
                property real dragStart: 0
                theme: window.themeTokens
                orientation: Qt.Horizontal
                interactive: window.inspectorOpen
                Layout.preferredWidth: inspectorOpen ? theme.density.splitHandleExtent : 0
                Layout.fillHeight: true
                opacity: inspectorOpen ? 1 : 0
                onDragStarted: {
                    dragStart = inspectorPane.width
                    window.horizontalSplitDragging = true
                }
                onDragMoved: function(delta) {
                    window.inspectorWidthCustomized = true
                    window.customInspectorPaneWidth = Math.max(
                        theme.density.inspectorMinWidth,
                        Math.min(theme.density.inspectorMaxWidth, dragStart - delta)
                    )
                }
                onDragFinished: {
                    if (!window.horizontalSplitDragging)
                        return
                    window.horizontalSplitDragging = false
                    window.splitSnapping = true
                    window.customInspectorPaneWidth = Math.round(window.customInspectorPaneWidth / 2) * 2
                    window.inspectorWidthCustomized = true
                    window.persistSplitSizes()
                    splitSnapTimer.restart()
                }
                onResetRequested: {
                    window.splitSnapping = true
                    window.resetInspectorWidth()
                    splitSnapTimer.restart()
                }
                Behavior on opacity {
                    NumberAnimation { duration: theme.motion.adaptivePaneDuration; easing.type: Easing.OutCubic }
                }
            }

            Rectangle {
                id: inspectorPane
                objectName: "inspectorPane"
                property bool paneOpen: inspectorOpen
                Layout.preferredWidth: paneOpen ? window.effectiveInspectorPaneWidth : 0
                Layout.minimumWidth: paneOpen ? theme.density.inspectorMinWidth : 0
                Layout.maximumWidth: paneOpen ? theme.density.inspectorMaxWidth : 0
                Layout.fillHeight: true
                opacity: paneOpen ? 1 : 0
                enabled: paneOpen
                clip: true
                color: theme.chrome
                Item {
                    anchors.fill: parent
                    UI.Inspector {
                        id: workspaceInspector
                        objectName: "workspaceInspectorContent"
                        width: parent.width
                        height: parent.height
                        y: 0
                        theme: window.themeTokens
                        type: window.typeTokens
                        project: window.current
                        onProfileRequested: function(profile) { backend.setProfile(profile) }
                        onSamplingRequested: function(mode, requested, intervalValue, intervalUnit, inFrame, outFrame) {
                            backend.setSampling(mode, requested, intervalValue, intervalUnit, inFrame, outFrame)
                        }
                        onAnalyzeRequested: backend.analyzeSampling()
                        enabled: window.currentPage === "workspace"
                        opacity: window.currentPage === "workspace" ? 1 : 0
                        x: window.currentPage === "workspace" ? 0 : -theme.motion.inspectorTravel
                        Behavior on opacity {
                            SequentialAnimation {
                                PauseAnimation { duration: theme.motion.inspectorDelay }
                                NumberAnimation {
                                    duration: theme.motion.inspectorTransitionDuration
                                    easing.type: Easing.BezierSpline
                                    easing.bezierCurve: theme.motion.navigationCurve
                                }
                            }
                        }
                        Behavior on x {
                            NumberAnimation {
                                duration: theme.motion.inspectorTransitionDuration
                                easing.type: Easing.BezierSpline
                                easing.bezierCurve: theme.motion.navigationCurve
                            }
                        }
                    }
                    UI.ProjectDetailsInspector {
                        id: libraryInspector
                        objectName: "libraryInspectorContent"
                        width: parent.width
                        height: parent.height
                        y: 0
                        theme: window.themeTokens
                        type: window.typeTokens
                        project: window.librarySelection
                        enabled: window.currentPage === "library"
                        opacity: window.currentPage === "library" ? 1 : 0
                        x: window.currentPage === "library" ? 0 : theme.motion.inspectorTravel
                        onOpenProjectRequested: function(project) { window.openProject(project) }
                        onOpenFolderRequested: function(project) { backend.openProjectFolder(project.project_id) }
                        onRenameRequested: function(project) { window.manage(project) }
                        onDuplicateRequested: function(project) { window.manage(project) }
                        onArchiveRequested: function(project, archived) {
                            backend.setProjectArchived(project.project_id, archived)
                        }
                        onRestoreRequested: function(project) { backend.restoreProject(project.project_id) }
                        onPurgeRequested: function(project) { window.requestPurge(project) }
                        Behavior on opacity {
                            SequentialAnimation {
                                PauseAnimation { duration: theme.motion.inspectorDelay }
                                NumberAnimation {
                                    duration: theme.motion.inspectorTransitionDuration
                                    easing.type: Easing.BezierSpline
                                    easing.bezierCurve: theme.motion.navigationCurve
                                }
                            }
                        }
                        Behavior on x {
                            NumberAnimation {
                                duration: theme.motion.inspectorTransitionDuration
                                easing.type: Easing.BezierSpline
                                easing.bezierCurve: theme.motion.navigationCurve
                            }
                        }
                    }
                }
                transform: Translate {
                    x: inspectorPane.paneOpen ? 0 : theme.motion.paneTravel
                    Behavior on x {
                        NumberAnimation {
                            duration: theme.motion.adaptivePaneDuration
                            easing.type: Easing.BezierSpline
                            easing.bezierCurve: theme.motion.standardCurve
                        }
                    }
                }
                Behavior on Layout.preferredWidth {
                    enabled: !window.horizontalSplitDragging
                    NumberAnimation {
                        duration: window.splitSnapping
                            ? theme.motion.splitSnapDuration : theme.motion.adaptivePaneDuration
                        easing.type: Easing.BezierSpline
                        easing.bezierCurve: theme.motion.navigationCurve
                    }
                }
                Behavior on opacity {
                    NumberAnimation { duration: theme.motion.adaptivePaneDuration; easing.type: Easing.OutCubic }
                }
            }
        }

        UI.Divider { theme: window.themeTokens; Layout.fillWidth: true }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: theme.density.statusbarHeight
            color: theme.chrome
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: theme.density.sidePadding
                anchors.rightMargin: theme.density.sidePadding
                spacing: theme.density.itemGap
                UI.AppIcon { name: "check"; size: theme.density.iconMicro; color: theme.success }
                Text {
                    Layout.fillWidth: true
                    text: "ModernUI · shared production backend · "
                        + (runtimeState.status === "ok" ? "runtime ready" : "runtime attention")
                    color: theme.inkTertiary
                    font.family: type.family
                    font.pixelSize: type.microSize
                }
                Text {
                    text: "Qt 6 · " + (theme.dark ? "Dark" : "Light") + " · DPI aware"
                    color: theme.inkTertiary
                    font.family: type.family
                    font.pixelSize: type.microSize
                }
            }
        }
    }

    FileDialog {
        id: videoPicker
        title: "Import video"
        nameFilters: ["Video files (*.mp4 *.mov *.mkv *.avi *.webm)", "All files (*)"]
        onAccepted: window.beginVideo(window.localPathFromUrl(selectedFile))
    }
    FolderDialog {
        id: imageFolderPicker
        title: "Import image folder"
        onAccepted: backend.importInput(window.localPathFromUrl(selectedFolder))
    }
    FolderDialog {
        id: projectFolderPicker
        title: "Choose project workspace"
        onAccepted: newProjectRoot.text = window.localPathFromUrl(selectedFolder)
    }

    UI.Dialog {
        id: newProjectDialog
        objectName: "newProjectDialog"
        theme: window.themeTokens
        type: window.typeTokens
        title: "New project"
        subtitle: "Create an isolated workspace for a new reconstruction."
        dialogWidth: 520

        Text {
            text: "PROJECT NAME"
            color: theme.inkTertiary
            font.family: type.family
            font.pixelSize: type.microSize
            font.weight: type.semibold
            font.letterSpacing: 0.8
        }
        UI.AppTextField {
            id: newProjectName
            theme: window.themeTokens
            type: window.typeTokens
            Layout.fillWidth: true
            placeholderText: "My reconstruction"
        }
        Text {
            text: "PROJECT LIBRARY"
            color: theme.inkTertiary
            font.family: type.family
            font.pixelSize: type.microSize
            font.weight: type.semibold
            font.letterSpacing: 0.8
            Layout.topMargin: 2
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            UI.AppTextField {
                id: newProjectRoot
                theme: window.themeTokens
                type: window.typeTokens
                Layout.fillWidth: true
                placeholderText: "Choose an empty workspace directory"
            }
            UI.ToolbarButton {
                theme: window.themeTokens; type: window.typeTokens
                text: "Browse"
                iconName: "folder"
                onClicked: projectFolderPicker.open()
            }
        }
        UI.Panel {
            theme: window.themeTokens
            Layout.fillWidth: true
            implicitHeight: 62
            color: theme.surfaceSunken
            border.width: 0
            RowLayout {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 10
                UI.AppIcon { name: "info"; size: theme.density.iconDefault; color: theme.inkSecondary }
                Text {
                    Layout.fillWidth: true
                    text: "Projects in one library remain physically isolated by project ID."
                    color: theme.inkSecondary
                    font.family: type.family
                    font.pixelSize: type.microSize
                    lineHeight: type.bodyLine
                    wrapMode: Text.Wrap
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 4
            Item { Layout.fillWidth: true }
            UI.ToolbarButton {
                theme: window.themeTokens; type: window.typeTokens
                text: "Cancel"
                onClicked: newProjectDialog.close()
            }
            UI.ToolbarButton {
                theme: window.themeTokens; type: window.typeTokens
                text: "Create project"
                iconName: "add"
                primary: true
                enabled: newProjectName.text.trim().length > 0
                    && newProjectRoot.text.trim().length > 0
                onClicked: {
                    backend.createProject(
                        newProjectName.text.trim(),
                        newProjectRoot.text.trim()
                    )
                    newProjectDialog.close()
                    showNotice("Project creation requested")
                }
            }
        }
    }

    UI.Dialog {
        id: manageDialog
        theme: window.themeTokens
        type: window.typeTokens
        title: "Manage project"
        subtitle: (managedProject.name || "Project") + " · lifecycle and isolated workspace controls"
        dialogWidth: 560

        Text {
            text: "DISPLAY NAME"
            color: theme.inkTertiary
            font.family: type.family
            font.pixelSize: type.microSize
            font.weight: type.semibold
            font.letterSpacing: 0.8
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            UI.AppTextField { id: manageName; theme: window.themeTokens; type: window.typeTokens; Layout.fillWidth: true }
            UI.ToolbarButton {
                theme: window.themeTokens; type: window.typeTokens
                text: "Rename"
                iconName: "rename"
                enabled: manageName.text.trim().length > 0
                onClicked: {
                    backend.renameProject(managedProject.project_id, manageName.text.trim())
                    managedProject.name = manageName.text.trim()
                }
            }
        }
        UI.Divider { theme: window.themeTokens; Layout.fillWidth: true; Layout.topMargin: 2 }
        UI.SectionHeader { theme: window.themeTokens; type: window.typeTokens; Layout.fillWidth: true; title: "Independent copy" }
        UI.AppTextField {
            id: duplicateName
            theme: window.themeTokens
            type: window.typeTokens
            Layout.fillWidth: true
            placeholderText: "Copy name"
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            UI.ToolbarButton {
                theme: window.themeTokens; type: window.typeTokens
                Layout.fillWidth: true
                text: "Inputs & settings"
                iconName: "copy"
                enabled: duplicateName.text.trim().length > 0
                onClicked: backend.duplicateProject(
                    managedProject.project_id, duplicateName.text.trim(), "inputs"
                )
            }
            UI.ToolbarButton {
                theme: window.themeTokens; type: window.typeTokens
                Layout.fillWidth: true
                text: "Complete project"
                iconName: "copy"
                enabled: duplicateName.text.trim().length > 0
                onClicked: backend.duplicateProject(
                    managedProject.project_id, duplicateName.text.trim(), "complete"
                )
            }
        }
        UI.SectionHeader { theme: window.themeTokens; type: window.typeTokens; Layout.fillWidth: true; title: "Selective cleanup" }
        GridLayout {
            Layout.fillWidth: true
            columns: 2
            rowSpacing: 8
            columnSpacing: 8
            Repeater {
                model: [
                    {"label": "Reconstruction", "id": "reconstruction"},
                    {"label": "Training", "id": "training"},
                    {"label": "Viewer / timeline", "id": "viewer"},
                    {"label": "Exports", "id": "exports"}
                ]
                UI.ToolbarButton {
                    required property var modelData
                    theme: window.themeTokens
                    type: window.typeTokens
                    Layout.fillWidth: true
                    text: modelData.label
                    iconName: "delete"
                    enabled: managedProject.group !== "trash"
                    onClicked: backend.cleanupProject(
                        managedProject.project_id, modelData.id
                    )
                }
            }
        }
        UI.Divider { theme: window.themeTokens; Layout.fillWidth: true; Layout.topMargin: 2 }
        RowLayout {
            Layout.fillWidth: true
            UI.ToolbarButton {
                theme: window.themeTokens; type: window.typeTokens
                text: "Archive"
                iconName: "archive"
                visible: managedProject.group !== "trash"
                onClicked: {
                    backend.setProjectArchived(
                        managedProject.project_id,
                        managedProject.group !== "archived"
                    )
                    manageDialog.close()
                }
            }
            UI.ToolbarButton {
                theme: window.themeTokens; type: window.typeTokens
                text: "Move to trash"
                iconName: "trash"
                danger: true
                visible: managedProject.group !== "trash"
                onClicked: {
                    backend.deleteProject(managedProject.project_id)
                    manageDialog.close()
                }
            }
            Item { Layout.fillWidth: true }
            UI.ToolbarButton {
                theme: window.themeTokens; type: window.typeTokens
                text: "Done"
                primary: true
                onClicked: manageDialog.close()
            }
        }
    }

    UI.Dialog {
        id: importDialog
        readonly property var sampling: window.importDraft.sampling || ({})
        theme: window.themeTokens
        type: window.typeTokens
        title: "Import video"
        subtitle: "Real ffprobe preflight, frame analysis, and isolated project commit."
        dialogWidth: 600

        UI.Panel {
            theme: window.themeTokens
            Layout.fillWidth: true
            implicitHeight: 72
            color: theme.surfaceSunken
            border.width: 0
            RowLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 12
                UI.AppIcon { name: "video"; size: theme.density.iconMajor; color: theme.accent }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        text: String(window.importDraft.source || window.selectedVideoPath).replace(/\\/g, "/").split("/").pop()
                        color: theme.ink; font.family: type.family
                        font.pixelSize: type.labelSize; font.weight: type.semibold
                        elide: Text.ElideMiddle
                    }
                    Text {
                        text: Number(importDialog.sampling.width || 0) + " × "
                            + Number(importDialog.sampling.height || 0) + " · "
                            + Number(importDialog.sampling.fps || 0).toFixed(2) + " FPS · "
                            + Number(importDialog.sampling.source_total_frames || 0) + " frames"
                        color: theme.inkSecondary; font.family: type.family
                        font.pixelSize: type.microSize
                    }
                }
                UI.StatusBadge {
                    theme: window.themeTokens; type: window.typeTokens
                    text: String(window.importDraft.status || "preflight").toUpperCase()
                    status: window.importDraft.status === "failed" ? "error"
                        : window.importDraft.status === "ready" ? "success" : "running"
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            UI.Panel {
                theme: window.themeTokens
                Layout.fillWidth: true
                implicitHeight: 132
                raised: true
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 6
                    UI.AppIcon { name: "play"; size: theme.density.iconDefault; color: theme.inkSecondary }
                    Text { text: "Easy mode"; color: theme.ink; font.family: type.family; font.pixelSize: type.headingSize; font.weight: type.semibold }
                    Text { Layout.fillWidth: true; text: "Automatic sampling and recommended reconstruction profile."; color: theme.inkSecondary; font.family: type.family; font.pixelSize: type.microSize; lineHeight: type.bodyLine; wrapMode: Text.Wrap }
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    enabled: window.importDraft.status === "ready"
                    onClicked: {
                        window.pendingVideoMode = "easy"
                        backend.configureVideoImport(
                            "auto", 1, 1.0, "seconds", 0,
                            Math.max(0, Number(importDialog.sampling.source_total_frames || 1) - 1),
                            "balanced"
                        )
                    }
                }
            }
            UI.Panel {
                theme: window.themeTokens
                Layout.fillWidth: true
                implicitHeight: 132
                color: theme.accentSoft
                border.color: theme.accent
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 6
                    UI.AppIcon { name: "sliders"; size: theme.density.iconDefault; color: theme.accent }
                    Text { text: "Pro mode"; color: theme.ink; font.family: type.family; font.pixelSize: type.headingSize; font.weight: type.semibold }
                    Text { Layout.fillWidth: true; text: "Trim, sampling, preview and analysis controls before generation."; color: theme.inkSecondary; font.family: type.family; font.pixelSize: type.microSize; lineHeight: type.bodyLine; wrapMode: Text.Wrap }
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    enabled: window.importDraft.status === "ready"
                    onClicked: window.pendingVideoMode = "pro"
                }
            }
        }

        GridLayout {
            visible: window.pendingVideoMode === "pro"
            Layout.fillWidth: true
            columns: 2
            rowSpacing: 8
            columnSpacing: 8
            UI.ComboField {
                id: importSamplingMode
                theme: window.themeTokens; type: window.typeTokens
                Layout.fillWidth: true
                model: ["Auto", "Target count", "Interval", "All frames"]
                currentIndex: 1
            }
            UI.ComboField {
                id: importProfile
                theme: window.themeTokens; type: window.typeTokens
                Layout.fillWidth: true
                model: ["preview", "balanced", "quality"]
                currentIndex: 1
            }
            UI.AppTextField {
                id: importRequested
                theme: window.themeTokens; type: window.typeTokens
                Layout.fillWidth: true
                placeholderText: "Target frame count"
                text: "120"
            }
            UI.AppTextField {
                id: importInterval
                theme: window.themeTokens; type: window.typeTokens
                Layout.fillWidth: true
                placeholderText: "Interval seconds"
                text: "1.0"
            }
            UI.AppTextField {
                id: importInFrame
                theme: window.themeTokens; type: window.typeTokens
                Layout.fillWidth: true
                placeholderText: "In frame"
                text: "0"
            }
            UI.AppTextField {
                id: importOutFrame
                theme: window.themeTokens; type: window.typeTokens
                Layout.fillWidth: true
                placeholderText: "Out frame"
                text: String(Math.max(0, Number(importDialog.sampling.source_total_frames || 1) - 1))
            }
        }
        Text {
            visible: !!window.importDraft.error
            Layout.fillWidth: true
            text: window.importDraft.error || ""
            color: theme.error
            font.family: type.family
            font.pixelSize: type.microSize
            wrapMode: Text.Wrap
        }
        Text {
            visible: (importDialog.sampling.analysis_status || "") === "complete"
            Layout.fillWidth: true
            text: "Analysis complete · "
                + Number(importDialog.sampling.selected_frame_count || 0)
                + " frames selected"
            color: theme.success
            font.family: type.family
            font.pixelSize: type.microSize
        }
        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            UI.ToolbarButton {
                visible: window.pendingVideoMode === "pro"
                theme: window.themeTokens; type: window.typeTokens
                text: "Analyze"
                iconName: "refresh"
                onClicked: backend.configureVideoImport(
                    ["auto", "target_count", "interval", "all_frames"][importSamplingMode.currentIndex],
                    Math.max(1, parseInt(importRequested.text) || 1),
                    Math.max(0.001, parseFloat(importInterval.text) || 1),
                    "seconds",
                    Math.max(0, parseInt(importInFrame.text) || 0),
                    Math.max(0, parseInt(importOutFrame.text) || 0),
                    importProfile.currentText
                )
            }
            UI.ToolbarButton {
                theme: window.themeTokens; type: window.typeTokens
                text: "Cancel"
                onClicked: {
                    backend.cancelVideoImport()
                    importDialog.close()
                }
            }
            UI.ToolbarButton {
                theme: window.themeTokens; type: window.typeTokens
                text: "Generate"
                iconName: "play"
                primary: true
                enabled: (importDialog.sampling.analysis_status || "") === "complete"
                onClicked: {
                    backend.generateVideoImport()
                    importDialog.close()
                }
            }
        }
    }

    UI.Dialog {
        id: settingsDialog
        objectName: "settingsDialog"
        theme: window.themeTokens
        type: window.typeTokens
        title: "Settings"
        subtitle: "Appearance, workspace persistence, and startup shell."
        dialogWidth: 540

        UI.SectionHeader { theme: window.themeTokens; type: window.typeTokens; Layout.fillWidth: true; title: "Appearance" }
        RowLayout {
            Layout.fillWidth: true
            spacing: densityTokens.itemGap
            Repeater {
                model: [
                    {"id": "light", "label": "Light", "icon": "sun"},
                    {"id": "dark", "label": "Dark", "icon": "moon"},
                    {"id": "system", "label": "Follow system", "icon": "system"}
                ]
                delegate: UI.ToolbarButton {
                    required property var modelData
                    theme: window.themeTokens; type: window.typeTokens
                    Layout.fillWidth: true
                    text: modelData.label
                    iconName: modelData.icon
                    selected: window.themeMode === modelData.id
                    onClicked: setThemeMode(modelData.id)
                }
            }
        }
        UI.SectionHeader { theme: window.themeTokens; type: window.typeTokens; Layout.fillWidth: true; title: "Interface size" }
        RowLayout {
            Layout.fillWidth: true
            spacing: densityTokens.itemGap
            Repeater {
                model: [
                    {"id": "compact", "label": "Compact"},
                    {"id": "standard", "label": "Standard"},
                    {"id": "comfortable", "label": "Comfortable"}
                ]
                delegate: UI.ToolbarButton {
                    required property var modelData
                    theme: window.themeTokens; type: window.typeTokens
                    Layout.fillWidth: true
                    text: modelData.label
                    selected: window.interfaceSize === modelData.id
                    onClicked: setInterfaceSize(modelData.id)
                }
            }
        }
        UI.SectionHeader { theme: window.themeTokens; type: window.typeTokens; Layout.fillWidth: true; title: "Typography weight" }
        RowLayout {
            Layout.fillWidth: true
            spacing: densityTokens.itemGap
            Repeater {
                model: [
                    {"id": "light", "label": "Light"},
                    {"id": "balanced", "label": "Balanced"},
                    {"id": "strong", "label": "Strong"}
                ]
                delegate: UI.ToolbarButton {
                    required property var modelData
                    theme: window.themeTokens; type: window.typeTokens
                    Layout.fillWidth: true
                    text: modelData.label
                    selected: window.typographyWeight === modelData.id
                    onClicked: setTypographyWeight(modelData.id)
                }
            }
        }
        UI.SectionHeader { theme: window.themeTokens; type: window.typeTokens; Layout.fillWidth: true; title: "Motion & startup" }
        UI.AppCheckBox {
            theme: window.themeTokens
            type: window.typeTokens
            text: "Reduce motion"
            checked: motionTokens.reducedMotion
            onToggled: {
                motionTokens.reducedMotion = checked
                if (useSavedSettings)
                    modernSettings.reduceMotion = checked
            }
        }
        UI.AppCheckBox {
            theme: window.themeTokens
            type: window.typeTokens
            text: "Restore last project at startup"
            checked: modernSettings.restoreLastProject
            onToggled: modernSettings.restoreLastProject = checked
        }
        UI.ToolbarButton {
            theme: window.themeTokens; type: window.typeTokens
            Layout.fillWidth: true
            text: "Reset workspace layout"
            iconName: "refresh"
            onClicked: {
                leftOpen = true
                inspectorOpen = true
                resetSidebarWidth()
                resetInspectorWidth()
                resetActivityLogHeight()
                showNotice("ModernUI workspace layout reset")
            }
        }
        UI.SectionHeader {
            theme: window.themeTokens; type: window.typeTokens
            Layout.fillWidth: true
            title: "Interface shell · restart required"
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: densityTokens.itemGap
            Repeater {
                model: [
                    {"id": "modern", "label": "Modern"},
                    {"id": "classic", "label": "Classic"}
                ]
                delegate: UI.ToolbarButton {
                    required property var modelData
                    theme: window.themeTokens; type: window.typeTokens
                    Layout.fillWidth: true
                    text: modelData.label
                    selected: window.settingsState.preferred_ui === modelData.id
                    onClicked: backend.setPreferredUi(modelData.id)
                }
            }
        }
        Text {
            Layout.fillWidth: true
            text: window.settingsState.restart_required
                ? "Restart GaussianOS to activate "
                    + String(window.settingsState.preferred_ui || "modern") + " UI."
                : "Active shell: " + String(window.settingsState.active_ui || "modern")
            color: window.settingsState.restart_required ? theme.warning : theme.inkTertiary
            font.family: type.family
            font.pixelSize: type.microSize
            wrapMode: Text.Wrap
        }
        UI.SectionHeader {
            theme: window.themeTokens; type: window.typeTokens
            Layout.fillWidth: true
            title: "Runtime doctor"
        }
        Text {
            Layout.fillWidth: true
            text: window.runtimeState.status === "ok"
                ? "Runtime doctor: OK"
                : (window.runtimeState.messages || []).join("\n")
            color: window.runtimeState.status === "ok" ? theme.success : theme.warning
            font.family: type.monoFamily
            font.pixelSize: type.microSize
            wrapMode: Text.Wrap
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 4
            Text {
                Layout.fillWidth: true
                text: "Ctrl+1 Light · Ctrl+2 Dark · Ctrl+, Settings"
                color: theme.inkTertiary
                font.family: type.family
                font.pixelSize: type.microSize
            }
            UI.ToolbarButton {
                theme: window.themeTokens; type: window.typeTokens
                text: "Done"
                primary: true
                onClicked: settingsDialog.close()
            }
        }
    }

    UI.Dialog {
        id: purgeDialog
        theme: window.themeTokens
        type: window.typeTokens
        title: "Delete project forever?"
        subtitle: "This permanently removes “" + (purgeTarget.name || "Project") + "” and its isolated workspace."
        dialogWidth: 480

        UI.Panel {
            theme: window.themeTokens
            Layout.fillWidth: true
            implicitHeight: 66
            color: theme.surfaceSunken
            border.color: theme.lineStrong
            RowLayout {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 10
                UI.AppIcon { name: "warning"; size: theme.density.iconMajor; color: theme.ink }
                Text {
                    Layout.fillWidth: true
                    text: "This action cannot be undone. Type the project name to confirm."
                    color: theme.inkSecondary
                    font.family: type.family
                    font.pixelSize: type.labelSize
                    lineHeight: type.bodyLine
                    wrapMode: Text.Wrap
                }
            }
        }
        UI.AppTextField {
            id: purgeConfirm
            theme: window.themeTokens
            type: window.typeTokens
            Layout.fillWidth: true
            placeholderText: purgeTarget.name || ""
        }
        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            UI.ToolbarButton { theme: window.themeTokens; type: window.typeTokens; text: "Cancel"; onClicked: purgeDialog.close() }
            UI.ToolbarButton {
                theme: window.themeTokens; type: window.typeTokens
                text: "Delete forever"
                iconName: "delete"
                danger: true
                enabled: purgeConfirm.text === (purgeTarget.name || "")
                onClicked: {
                    backend.purgeProject(purgeTarget.project_id)
                    purgeDialog.close()
                    showNotice("Permanent delete requested for " + purgeTarget.name)
                }
            }
        }
    }
}
