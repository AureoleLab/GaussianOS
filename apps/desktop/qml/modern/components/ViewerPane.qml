import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtWebEngine

Rectangle {
    id: root
    objectName: "viewerPane"
    required property var theme
    required property var type
    property string projectName: "No project selected"
    property bool logOpen: true
    property bool running: false
    property string notice: ""
    property string viewerUrl: "about:blank"
    property string viewerStatus: "Select a project"
    property string logText: ""
    property var timeline: []
    property real activityLogHeight: theme.density.activityLogHeight
    property real draggedLogHeight: activityLogHeight
    property bool logDragging: false
    property bool logSnapping: false
    property int playhead: -1
    readonly property bool viewerActive: viewerUrl !== "" && viewerUrl !== "about:blank"
    readonly property real maximumLogHeight: Math.max(
        theme.density.activityLogCollapsedHeight,
        Math.min(height * 0.45, height - theme.density.viewerMinHeight)
    )
    readonly property real effectiveLogHeight: logDragging
        ? draggedLogHeight : activityLogHeight

    signal logHeightAdjusted(real value, bool reset)
    signal runRequested()
    signal cancelRequested()
    signal loadViewerRequested()
    signal exportRequested()
    signal viewerTitleChanged(string title)
    signal acceptanceResult(string result)

    function boundedLogHeight(value) {
        return Math.max(
            theme.density.activityLogCollapsedHeight,
            Math.min(maximumLogHeight, value)
        )
    }
    function fileUrl(path) {
        return path ? "file:///" + String(path).replace(/\\/g, "/") : ""
    }
    function activateFrame(index) {
        if (index < 0 || index >= timeline.length)
            return
        playhead = index
        timelineList.positionViewAtIndex(index, ListView.Contain)
        var frame = timeline[index]
        if (frame.registration_status === "registered"
                && frame.colmap_image_id !== undefined
                && frame.colmap_image_id !== null) {
            viewer.runJavaScript("viewerCamera.setCamera(" + Number(frame.colmap_image_id) + ")")
            notice = ""
        } else {
            notice = frame.reason || "No reconstructed camera for this frame"
        }
    }
    function runAcceptance(cameraTimeline) {
        if (!viewerActive) {
            acceptanceResult("Modern viewer is not active")
            return
        }
        if (cameraTimeline && timeline.length > 0) {
            activateFrame(0)
            viewer.runJavaScript(
                "JSON.stringify(viewerCamera.state())",
                function(result) { root.acceptanceResult(result) }
            )
        } else {
            viewer.runJavaScript(
                "var before=acceptance.snapshot(); acceptance.orbit(0.03,-0.01); "
                + "acceptance.pan(0.005,-0.003); acceptance.zoom(0.98); "
                + "acceptance.walk(0.005); acceptance.motionTest(1800); "
                + "JSON.stringify({before:before,after:acceptance.snapshot()})",
                function(result) { root.acceptanceResult(result) }
            )
        }
    }

    color: theme.canvas

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 43
            color: theme.canvas
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 12
                spacing: 9
                AppIcon { name: "viewer"; size: theme.density.iconDefault; color: theme.inkSecondary }
                Text {
                    text: root.projectName
                    color: theme.ink
                    font.family: type.family
                    font.pixelSize: type.labelSize
                    font.weight: type.semibold
                    elide: Text.ElideRight
                    Layout.maximumWidth: 260
                }
                Text {
                    Layout.fillWidth: true
                    text: root.viewerStatus
                    color: theme.inkTertiary
                    font.family: type.family
                    font.pixelSize: type.microSize
                    elide: Text.ElideRight
                }
                StatusBadge {
                    theme: root.theme
                    type: root.type
                    text: root.viewerActive ? "LOADED" : root.running ? "RUNNING" : "EMPTY"
                    status: root.viewerActive ? "success" : root.running ? "running" : "neutral"
                }
                IconButton {
                    theme: root.theme; type: root.type
                    iconName: "camera"
                    toolTip: "Reload validated viewer"
                    prominent: true
                    onClicked: root.loadViewerRequested()
                }
                IconButton {
                    theme: root.theme; type: root.type
                    iconName: "export"
                    toolTip: "Open export folder"
                    prominent: true
                    onClicked: root.exportRequested()
                }
            }
        }

        Divider { theme: root.theme; Layout.fillWidth: true }

        Rectangle {
            id: viewport
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: theme.density.viewerMinHeight
            color: theme.viewer
            clip: true

            Repeater {
                model: root.viewerActive ? 0 : 13
                Rectangle {
                    required property int index
                    x: Math.round(index * viewport.width / 12)
                    width: 1
                    height: viewport.height
                    color: index === 6 ? theme.gridAxis : theme.gridLine
                    opacity: index === 6 ? 0.85 : 0.48
                }
            }
            Repeater {
                model: root.viewerActive ? 0 : 9
                Rectangle {
                    required property int index
                    y: Math.round(index * viewport.height / 8)
                    width: viewport.width
                    height: 1
                    color: index === 4 ? theme.gridAxis : theme.gridLine
                    opacity: index === 4 ? 0.85 : 0.48
                }
            }

            WebEngineView {
                id: viewer
                objectName: "gaussianViewer"
                anchors.fill: parent
                visible: root.viewerActive
                url: root.viewerUrl
                onTitleChanged: root.viewerTitleChanged(title)
            }

            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(440, parent.width - 48)
                spacing: 12
                visible: !root.viewerActive
                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 58
                    Layout.preferredHeight: 58
                    radius: theme.radiusPanel
                    color: root.running ? theme.accent : theme.surface
                    border.width: root.running ? 0 : 1
                    border.color: theme.line
                    AppIcon {
                        anchors.centerIn: parent
                        name: root.running ? "activity" : "viewer"
                        size: theme.density.iconBrand
                        color: root.running ? theme.inkOnAccent : theme.accent
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: root.running ? "Reconstruction in progress"
                        : root.projectName === "No project selected"
                            ? "Open or create a project"
                            : "Viewer is ready"
                    color: theme.ink
                    font.family: type.family
                    font.pixelSize: type.titleSize
                    font.weight: type.semibold
                    horizontalAlignment: Text.AlignHCenter
                }
                Text {
                    Layout.fillWidth: true
                    text: root.viewerStatus
                    color: theme.inkSecondary
                    font.family: type.family
                    font.pixelSize: type.labelSize
                    lineHeight: type.bodyLine
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                }
                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    spacing: 8
                    ToolbarButton {
                        theme: root.theme; type: root.type
                        text: root.running ? "Running" : "Run pipeline"
                        iconName: "play"
                        primary: true
                        enabled: root.projectName !== "No project selected" && !root.running
                        onClicked: root.runRequested()
                    }
                    ToolbarButton {
                        theme: root.theme; type: root.type
                        text: root.running ? "Cancel" : "Load viewer"
                        iconName: root.running ? "stop" : "viewer"
                        enabled: root.projectName !== "No project selected"
                        onClicked: root.running ? root.cancelRequested() : root.loadViewerRequested()
                    }
                }
            }

            Rectangle {
                visible: root.viewerActive && root.timeline.length > 0
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: Math.min(112, parent.height * 0.28)
                color: theme.chrome
                opacity: 0.96
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 5
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: "Camera Timeline · " + root.timeline.length + " frames"
                            color: theme.ink
                            font.family: type.family
                            font.pixelSize: type.microSize
                            font.weight: type.semibold
                        }
                        Text {
                            text: root.playhead >= 0 ? (root.playhead + 1) + " / " + root.timeline.length : ""
                            color: theme.inkTertiary
                            font.family: type.monoFamily
                            font.pixelSize: type.microSize
                        }
                    }
                    ListView {
                        id: timelineList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        orientation: ListView.Horizontal
                        spacing: 6
                        clip: true
                        model: root.timeline
                        delegate: Rectangle {
                            required property var modelData
                            required property int index
                            width: 92
                            height: ListView.view.height
                            radius: theme.radiusItem
                            color: root.playhead === index ? theme.selected : theme.surface
                            border.width: root.playhead === index ? 1 : 0
                            border.color: theme.accent
                            Image {
                                anchors.fill: parent
                                anchors.margins: 3
                                source: root.fileUrl(modelData.thumbnail_path || modelData.extracted_image_path)
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                            }
                            Rectangle {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                height: 18
                                color: theme.chrome
                                opacity: 0.88
                                Text {
                                    anchors.centerIn: parent
                                    text: "#" + (modelData.frame_index === undefined ? index : modelData.frame_index)
                                    color: theme.ink
                                    font.family: type.monoFamily
                                    font.pixelSize: type.microSize
                                }
                            }
                            TapHandler { onTapped: root.activateFrame(index) }
                        }
                    }
                }
            }

            Rectangle {
                visible: root.notice.length > 0 || opacity > 0.01
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: root.timeline.length > 0 ? 120 : 16
                implicitWidth: noticeText.implicitWidth + 30
                implicitHeight: 36
                radius: theme.radiusToast
                color: theme.ink
                opacity: root.notice.length > 0 ? 1 : 0
                Text {
                    id: noticeText
                    anchors.centerIn: parent
                    text: root.notice
                    color: theme.surface
                    font.family: type.family
                    font.pixelSize: type.microSize
                }
                Behavior on opacity { NumberAnimation { duration: theme.motion.toastDuration; easing.type: Easing.OutCubic } }
            }
        }

        PaneSplitHandle {
            id: activitySplitHandle
            objectName: "activitySplitHandle"
            property real dragStart: 0
            theme: root.theme
            orientation: Qt.Vertical
            Layout.fillWidth: true
            Layout.preferredHeight: theme.density.splitHandleExtent
            onDragStarted: {
                dragStart = root.logOpen ? logPanel.height : theme.density.activityLogCollapsedHeight
                root.draggedLogHeight = dragStart
                root.logDragging = true
                root.logOpen = true
            }
            onDragMoved: function(delta) {
                root.draggedLogHeight = root.boundedLogHeight(dragStart - delta)
            }
            onDragFinished: {
                if (!root.logDragging) return
                var snapped = Math.round(root.boundedLogHeight(root.draggedLogHeight) / 2) * 2
                root.logHeightAdjusted(snapped, false)
                root.draggedLogHeight = snapped
                root.logSnapping = true
                root.logDragging = false
                logSnapTimer.restart()
            }
            onResetRequested: {
                root.logSnapping = true
                root.logHeightAdjusted(theme.density.activityLogHeight, true)
                logSnapTimer.restart()
            }
        }

        Rectangle {
            id: logPanel
            objectName: "activityLogPanel"
            Layout.fillWidth: true
            Layout.preferredHeight: root.logOpen
                ? root.boundedLogHeight(root.effectiveLogHeight)
                : theme.density.activityLogCollapsedHeight
            color: theme.surface
            clip: true
            Behavior on Layout.preferredHeight {
                enabled: !root.logDragging
                NumberAnimation {
                    duration: root.logSnapping ? theme.motion.splitSnapDuration : theme.motion.sectionDuration
                    easing.type: Easing.BezierSpline
                    easing.bezierCurve: theme.motion.navigationCurve
                }
            }
            ColumnLayout {
                anchors.fill: parent
                spacing: 0
                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 38
                    Layout.leftMargin: 10
                    Layout.rightMargin: 12
                    IconButton {
                        theme: root.theme; type: root.type
                        iconName: "chevron-down"
                        toolTip: "Toggle Activity Log"
                        rotation: root.logOpen ? 0 : -90
                        onClicked: root.logOpen = !root.logOpen
                    }
                    AppIcon { name: "activity"; size: theme.density.iconDefault; color: theme.inkSecondary }
                    Text {
                        Layout.fillWidth: true
                        text: "Activity Log"
                        color: theme.ink
                        font.family: type.family
                        font.pixelSize: type.labelSize
                        font.weight: type.semibold
                    }
                    Text {
                        text: root.logText ? root.logText.split("\n").length + " events" : "No events"
                        color: theme.inkTertiary
                        font.family: type.family
                        font.pixelSize: type.microSize
                    }
                }
                Divider { visible: root.logOpen; theme: root.theme; Layout.fillWidth: true }
                ScrollView {
                    visible: root.logOpen
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    TextArea {
                        text: root.logText
                        readOnly: true
                        selectByMouse: true
                        color: theme.inkSecondary
                        font.family: type.monoFamily
                        font.pixelSize: type.microSize
                        wrapMode: TextEdit.Wrap
                        background: Rectangle { color: "transparent" }
                    }
                }
            }
        }
    }

    Timer {
        id: logSnapTimer
        interval: theme.motion.splitSnapDuration + 20
        onTriggered: root.logSnapping = false
    }
}
