import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtCore as QtCore
import "components" as UI

ApplicationWindow {
    id: window
    width: startupWidth
    height: startupHeight
    minimumWidth: 1180
    minimumHeight: 720
    visible: true
    title: "GaussianOS · Visual System Prototype"
    color: theme.canvas

    property string currentPage: "workspace"
    property string currentProject: "Atrium Capture"
    property string managedProject: currentProject
    property string purgeProject: ""
    property bool leftOpen: true
    property bool inspectorOpen: true
    property bool running: false
    property int mockProgress: 64
    property string globalNotice: ""
    property bool horizontalSplitDragging: false
    property bool splitSnapping: false
    property string themeMode: useSavedSettings ? prototypeSettings.themeMode : startupTheme
    property string interfaceSize: useSavedSettings ? prototypeSettings.interfaceSize : "standard"
    property string typographyWeight: useSavedSettings ? prototypeSettings.typographyWeight : "balanced"
    property bool sidebarWidthCustomized: useSavedSettings && prototypeSettings.sidebarPaneWidth >= theme.density.sidebarMinWidth
    property bool inspectorWidthCustomized: useSavedSettings && prototypeSettings.inspectorPaneWidth >= theme.density.inspectorMinWidth
    property bool activityLogHeightCustomized: useSavedSettings && prototypeSettings.activityLogHeight >= theme.density.activityLogCollapsedHeight
    property real customSidebarPaneWidth: sidebarWidthCustomized ? prototypeSettings.sidebarPaneWidth : theme.density.sidebarWidth
    property real customInspectorPaneWidth: inspectorWidthCustomized ? prototypeSettings.inspectorPaneWidth : theme.density.inspectorWidth
    property real customActivityLogHeight: activityLogHeightCustomized ? prototypeSettings.activityLogHeight : theme.density.activityLogHeight
    readonly property real effectiveSidebarPaneWidth: sidebarWidthCustomized ? customSidebarPaneWidth : theme.density.sidebarWidth
    readonly property real effectiveInspectorPaneWidth: inspectorWidthCustomized ? customInspectorPaneWidth : theme.density.inspectorWidth
    readonly property real effectiveActivityLogHeight: activityLogHeightCustomized ? customActivityLogHeight : theme.density.activityLogHeight
    property var librarySelection: ({
        "id":"atrium","name":"Atrium Capture","status":"Ready","group":"active",
        "date":"24 Jul 2026, 14:32","size":"6.2 GiB",
        "location":"D:\\GaussianOS\\Projects\\atrium",
        "profile":"Balanced","source":"Video · 2,448 frames"
    })
    readonly property alias themeTokens: theme
    readonly property alias typeTokens: type

    QtCore.Settings {
        id: prototypeSettings
        category: "appearance-v3"
        property string themeMode: "light"
        property string interfaceSize: "standard"
        property string typographyWeight: "balanced"
        property bool reduceMotion: false
        property real sidebarPaneWidth: -1
        property real inspectorPaneWidth: -1
        property real activityLogHeight: -1
    }

    Motion { id: motionTokens; reducedMotion: useSavedSettings ? prototypeSettings.reduceMotion : false }
    Density { id: densityTokens; mode: window.interfaceSize }
    Theme { id: theme; mode: window.themeMode; motion: motionTokens; density: densityTokens }
    Typography { id: type; densityMode: densityTokens.mode; weightPreset: window.typographyWeight }

    function showNotice(message) {
        globalNotice = message
        noticeTimer.restart()
    }

    function setThemeMode(value) {
        appearanceTransition.restart()
        window.themeMode = value
        if (useSavedSettings)
            prototypeSettings.themeMode = value
    }

    function setInterfaceSize(value) {
        appearanceTransition.restart()
        motionTokens.densityChanging = true
        window.interfaceSize = value
        if (useSavedSettings)
            prototypeSettings.interfaceSize = value
        densityChangeTimer.restart()
    }

    function setTypographyWeight(value) {
        appearanceTransition.restart()
        window.typographyWeight = value
        if (useSavedSettings)
            prototypeSettings.typographyWeight = value
    }

    function persistSplitSizes() {
        if (!useSavedSettings)
            return
        prototypeSettings.sidebarPaneWidth = sidebarWidthCustomized ? customSidebarPaneWidth : -1
        prototypeSettings.inspectorPaneWidth = inspectorWidthCustomized ? customInspectorPaneWidth : -1
        prototypeSettings.activityLogHeight = activityLogHeightCustomized ? customActivityLogHeight : -1
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

    Timer {
        id: progressTimer
        interval: 850
        repeat: true
        running: window.running
        onTriggered: {
            mockProgress += 3
            if (mockProgress >= 100) {
                mockProgress = 100
                window.running = false
                window.showNotice("Mock pipeline completed · no backend was called")
            }
        }
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
                    onClicked: importDialog.open()
                }
                UI.ToolbarButton {
                    theme: window.themeTokens; type: window.typeTokens
                    text: window.width >= 1510 ? "Import images" : ""
                    iconName: "images"
                    quiet: true
                    compact: true
                    onClicked: showNotice("Mock action · image-folder picker")
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
                    enabled: !running
                    onClicked: {
                        running = true
                        mockProgress = 1
                        showNotice("Mock action · pipeline simulation started")
                    }
                }
                UI.ToolbarButton {
                    theme: window.themeTokens; type: window.typeTokens
                    text: "Cancel"
                    iconName: "stop"
                    compact: true
                    enabled: running
                    onClicked: {
                        running = false
                        showNotice("Mock action · simulation cancelled")
                    }
                }
                UI.ToolbarButton {
                    theme: window.themeTokens; type: window.typeTokens
                    text: "Export"
                    iconName: "export"
                    compact: true
                    onClicked: showNotice("Mock action · export options")
                }

                Item { Layout.fillWidth: true }

                UI.StatusBadge {
                    theme: window.themeTokens
                    type: window.typeTokens
                    text: running ? "TRAINING " + mockProgress + "%" : "READY"
                    status: running ? "running" : "success"
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
                currentProject: window.currentProject
                onPageSelected: function(page) { window.currentPage = page }
                onProjectSelected: function(project) {
                    window.currentProject = project
                    window.currentPage = "workspace"
                }
                onManageProject: function(project) {
                    managedProject = project
                    manageName.text = project
                    manageDialog.open()
                }
                onNewProject: newProjectDialog.open()
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
                    activityLogHeight: window.effectiveActivityLogHeight
                    enabled: window.currentPage === "workspace"
                    opacity: window.currentPage === "workspace" ? 1 : 0
                    x: window.currentPage === "workspace" ? 0 : -theme.motion.pageTravel
                    scale: window.currentPage === "workspace" ? 1 : theme.motion.pageScale
                    z: window.currentPage === "workspace" ? 2 : 1
                    onNoticeChanged: if (notice.length > 0) noticeTimer.restart()
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
                    enabled: window.currentPage === "library"
                    opacity: window.currentPage === "library" ? 1 : 0
                    x: window.currentPage === "library" ? 0 : theme.motion.pageTravel
                    scale: window.currentPage === "library" ? 1 : theme.motion.pageScale
                    z: window.currentPage === "library" ? 2 : 1
                    onProjectSelected: function(project) {
                        window.librarySelection = project
                    }
                    onActionRequested: function(message) {
                        showNotice(message)
                    }
                    onRenameRequested: function(project) {
                        managedProject = project.name
                        manageName.text = project.name
                        manageDialog.open()
                    }
                    onPurgeRequested: function(project) {
                        window.librarySelection = project
                        purgeProject = project.name
                        purgeConfirm.text = ""
                        purgeDialog.open()
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
                        running: window.running
                        progress: window.mockProgress
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
                        onActionRequested: function(message) { showNotice(message) }
                        onRenameRequested: function(project) {
                            managedProject = project.name
                            manageName.text = project.name
                            manageDialog.open()
                        }
                        onPurgeRequested: function(project) {
                            purgeProject = project.name
                            purgeConfirm.text = ""
                            purgeDialog.open()
                        }
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
                    text: "Prototype mode · static mock data · backend disconnected"
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
                theme: window.themeTokens
                type: window.typeTokens
                Layout.fillWidth: true
                text: "D:\\GaussianOS\\Projects"
            }
            UI.ToolbarButton {
                theme: window.themeTokens; type: window.typeTokens
                text: "Browse"
                iconName: "folder"
                onClicked: showNotice("Mock action · library picker")
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
                onClicked: {
                    currentProject = newProjectName.text.trim()
                    newProjectDialog.close()
                    showNotice("Mock project created · " + currentProject)
                }
            }
        }
    }

    UI.Dialog {
        id: manageDialog
        theme: window.themeTokens
        type: window.typeTokens
        title: "Manage project"
        subtitle: managedProject + " · lifecycle and isolated workspace controls"
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
                onClicked: showNotice("Mock action · project renamed")
            }
        }
        UI.Divider { theme: window.themeTokens; Layout.fillWidth: true; Layout.topMargin: 2 }
        UI.SectionHeader { theme: window.themeTokens; type: window.typeTokens; Layout.fillWidth: true; title: "Independent copy" }
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            UI.ToolbarButton {
                theme: window.themeTokens; type: window.typeTokens
                Layout.fillWidth: true
                text: "Inputs & settings"
                iconName: "copy"
                onClicked: showNotice("Mock action · duplicate inputs and settings")
            }
            UI.ToolbarButton {
                theme: window.themeTokens; type: window.typeTokens
                Layout.fillWidth: true
                text: "Complete project"
                iconName: "copy"
                onClicked: showNotice("Mock action · duplicate complete project")
            }
        }
        UI.SectionHeader { theme: window.themeTokens; type: window.typeTokens; Layout.fillWidth: true; title: "Selective cleanup" }
        GridLayout {
            Layout.fillWidth: true
            columns: 2
            rowSpacing: 8
            columnSpacing: 8
            Repeater {
                model: ["Reconstruction", "Training", "Viewer / timeline", "Exports"]
                UI.ToolbarButton {
                    required property string modelData
                    theme: window.themeTokens
                    type: window.typeTokens
                    Layout.fillWidth: true
                    text: modelData
                    iconName: "delete"
                    onClicked: showNotice("Mock cleanup · " + modelData)
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
                onClicked: showNotice("Mock action · archived project")
            }
            UI.ToolbarButton {
                theme: window.themeTokens; type: window.typeTokens
                text: "Move to trash"
                iconName: "trash"
                danger: true
                onClicked: {
                    manageDialog.close()
                    showNotice("Mock action · moved project to Trash")
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
        theme: window.themeTokens
        type: window.typeTokens
        title: "Import video"
        subtitle: "Choose a workflow after static preflight. No file will be read in this prototype."
        dialogWidth: 540

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
                    Text { text: "courtyard_walkthrough.mp4"; color: theme.ink; font.family: type.family; font.pixelSize: type.labelSize; font.weight: type.semibold }
                    Text { text: "3840 × 2160 · 30 FPS · 01:21"; color: theme.inkSecondary; font.family: type.family; font.pixelSize: type.microSize }
                }
                UI.StatusBadge { theme: window.themeTokens; type: window.typeTokens; text: "PREFLIGHT READY"; status: "success" }
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
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: { importDialog.close(); showNotice("Mock import · Easy mode selected") } }
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
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: { importDialog.close(); showNotice("Mock import · Pro mode selected") } }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            UI.ToolbarButton { theme: window.themeTokens; type: window.typeTokens; text: "Cancel"; onClicked: importDialog.close() }
        }
    }

    UI.Dialog {
        id: settingsDialog
        objectName: "settingsDialog"
        theme: window.themeTokens
        type: window.typeTokens
        title: "Settings"
        subtitle: "Prototype appearance and workspace preferences."
        dialogWidth: 500

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
                    prototypeSettings.reduceMotion = checked
            }
        }
        UI.AppCheckBox {
            theme: window.themeTokens
            type: window.typeTokens
            text: "Restore last project at startup"
            checked: true
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
                showNotice("Mock action · workspace layout reset")
            }
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
        subtitle: "This permanently removes “" + purgeProject + "” and its isolated workspace."
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
            placeholderText: purgeProject
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
                enabled: purgeConfirm.text === purgeProject
                onClicked: {
                    purgeDialog.close()
                    showNotice("Mock action · permanently deleted " + purgeProject)
                }
            }
        }
    }
}
