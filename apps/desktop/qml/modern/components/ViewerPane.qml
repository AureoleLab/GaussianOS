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
    readonly property int keyframeCount: {
        var count = 0
        for (var index = 0; index < timeline.length; ++index) {
            if (isKeyframe(timeline[index]))
                count += 1
        }
        return count
    }
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
    function isKeyframe(frame) {
        return !!frame && (frame.selection_status === "selected"
            || frame.status === "selected")
    }
    function sourceFrameIndex(frame, fallback) {
        if (!frame)
            return fallback
        if (frame.source_frame_index !== undefined
                && frame.source_frame_index !== null)
            return Number(frame.source_frame_index)
        if (frame.index !== undefined && frame.index !== null)
            return Number(frame.index)
        return fallback
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
    function timelineMaximumX() {
        return Math.max(0, timelineList.contentWidth - timelineList.width)
    }
    function scrollTimelineBy(delta, smooth) {
        var currentTarget = timelineWheelMotion.running
            ? timelineWheelMotion.to : timelineList.contentX
        var destination = Math.max(0, Math.min(timelineMaximumX(), currentTarget + delta))
        if (!smooth) {
            timelineWheelMotion.stop()
            timelineList.contentX = destination
            return
        }
        timelineWheelMotion.stop()
        timelineWheelMotion.from = timelineList.contentX
        timelineWheelMotion.to = destination
        timelineWheelMotion.start()
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
                visible: opacity > 0.01
                enabled: root.viewerActive
                opacity: root.viewerActive ? 1 : 0
                url: root.viewerUrl
                onTitleChanged: root.viewerTitleChanged(title)
                Behavior on opacity {
                    NumberAnimation {
                        duration: theme.motion.viewerDuration
                        easing.type: Easing.BezierSpline
                        easing.bezierCurve: theme.motion.standardCurve
                    }
                }
            }

            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(440, parent.width - 48)
                spacing: 12
                visible: opacity > 0.01
                enabled: !root.viewerActive
                opacity: root.viewerActive ? 0 : 1
                y: root.viewerActive ? theme.motion.smallTravel : 0
                Behavior on opacity {
                    NumberAnimation {
                        duration: theme.motion.viewerDuration
                        easing.type: Easing.BezierSpline
                        easing.bezierCurve: theme.motion.standardCurve
                    }
                }
                Behavior on y {
                    NumberAnimation {
                        duration: theme.motion.viewerDuration
                        easing.type: Easing.BezierSpline
                        easing.bezierCurve: theme.motion.standardCurve
                    }
                }
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
                id: timelinePanel
                readonly property bool timelineAvailable: root.viewerActive && root.timeline.length > 0
                visible: opacity > 0.01
                enabled: timelineAvailable
                opacity: timelineAvailable ? 0.96 : 0
                y: timelineAvailable ? 0 : theme.motion.smallTravel
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: Math.min(112, parent.height * 0.28)
                color: theme.chrome
                Behavior on opacity {
                    NumberAnimation {
                        duration: theme.motion.viewerDuration
                        easing.type: Easing.BezierSpline
                        easing.bezierCurve: theme.motion.standardCurve
                    }
                }
                Behavior on y {
                    NumberAnimation {
                        duration: theme.motion.viewerDuration
                        easing.type: Easing.BezierSpline
                        easing.bezierCurve: theme.motion.standardCurve
                    }
                }
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
                        Rectangle {
                            visible: root.keyframeCount > 0
                            implicitWidth: keyframeLegend.implicitWidth + 16
                            implicitHeight: 18
                            radius: theme.radiusPill
                            color: theme.accentSoft
                            border.width: theme.hairline
                            border.color: theme.lineStrong
                            Row {
                                id: keyframeLegend
                                anchors.centerIn: parent
                                spacing: 5
                                Rectangle {
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 5
                                    height: 5
                                    radius: 3
                                    color: theme.accent
                                }
                                Text {
                                    text: root.keyframeCount + " keyframes"
                                    color: theme.ink
                                    font.family: type.family
                                    font.pixelSize: type.microSize
                                    font.weight: type.semibold
                                }
                            }
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
                        objectName: "cameraTimeline"
                        readonly property bool overflowing: contentWidth > width + 1
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        orientation: ListView.Horizontal
                        spacing: 6
                        clip: true
                        model: root.timeline
                        boundsBehavior: Flickable.StopAtBounds
                        flickDeceleration: 5000
                        pixelAligned: false
                        delegate: AbstractButton {
                            id: frameButton
                            required property var modelData
                            required property int index
                            readonly property bool keyframe: root.isKeyframe(modelData)
                            readonly property int sourceFrame: root.sourceFrameIndex(
                                modelData, index)
                            objectName: "cameraTimelineFrame-" + sourceFrame
                            width: 92
                            height: Math.max(
                                36,
                                ListView.view.height
                                    - (timelineList.overflowing ? timelineScrollBar.height + 4 : 0)
                            )
                            hoverEnabled: true
                            focusPolicy: Qt.StrongFocus
                            scale: down ? theme.motion.pressScale : 1
                            Accessible.name: keyframe
                                ? "Selected keyframe " + sourceFrame
                                : "Camera frame " + sourceFrame
                            Accessible.role: Accessible.Button
                            onClicked: root.activateFrame(index)
                            background: Rectangle {
                                radius: theme.radiusItem
                                color: root.playhead === index ? theme.selected
                                    : frameButton.keyframe ? theme.accentSoft
                                    : frameButton.down ? theme.controlPressed
                                    : frameButton.hovered ? theme.controlHover
                                    : theme.surface
                                border.width: frameButton.visualFocus
                                    || frameButton.keyframe ? 2
                                    : root.playhead === index ? 1 : 0
                                border.color: frameButton.visualFocus
                                    ? theme.focus
                                    : frameButton.keyframe ? theme.accent
                                    : theme.lineStrong
                                Behavior on color {
                                    ColorAnimation {
                                        duration: theme.motion.hoverDuration
                                        easing.type: Easing.OutCubic
                                    }
                                }
                            }
                            contentItem: Item {
                                clip: true
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
                                    color: frameButton.keyframe ? theme.accent : theme.chrome
                                    opacity: frameButton.keyframe ? 0.96 : 0.88
                                    Text {
                                        anchors.centerIn: parent
                                        text: "#" + frameButton.sourceFrame
                                        color: frameButton.keyframe
                                            ? theme.inkOnAccent : theme.ink
                                        font.family: type.monoFamily
                                        font.pixelSize: type.microSize
                                        font.weight: frameButton.keyframe
                                            ? type.semibold : type.medium
                                    }
                                }
                                Rectangle {
                                    visible: frameButton.keyframe
                                    anchors.left: parent.left
                                    anchors.top: parent.top
                                    anchors.margins: 6
                                    implicitWidth: keyframeLabel.implicitWidth + 12
                                    implicitHeight: 17
                                    radius: theme.radiusPill
                                    color: theme.accent
                                    border.width: theme.hairline
                                    border.color: theme.surface
                                    Text {
                                        id: keyframeLabel
                                        anchors.centerIn: parent
                                        text: "KEY"
                                        color: theme.inkOnAccent
                                        font.family: type.family
                                        font.pixelSize: type.microSize
                                        font.weight: type.semibold
                                    }
                                }
                            }
                            Behavior on scale {
                                NumberAnimation {
                                    duration: theme.motion.pressDuration
                                    easing.type: Easing.BezierSpline
                                    easing.bezierCurve: theme.motion.emphasizedCurve
                                }
                            }
                        }

                        HoverHandler {
                            id: timelineHover
                            acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                        }
                        WheelHandler {
                            id: timelineWheel
                            objectName: "cameraTimelineWheelHandler"
                            target: null
                            acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                            onWheel: function(event) {
                                var pixel = event.pixelDelta.x !== 0
                                    ? event.pixelDelta.x : event.pixelDelta.y
                                var angle = event.angleDelta.x !== 0
                                    ? event.angleDelta.x : event.angleDelta.y
                                if (pixel !== 0)
                                    root.scrollTimelineBy(-pixel, false)
                                else if (angle !== 0)
                                    root.scrollTimelineBy(-angle / 120 * 72, true)
                                event.accepted = true
                            }
                        }

                        ScrollBar.horizontal: ScrollBar {
                            id: timelineScrollBar
                            objectName: "cameraTimelineScrollBar"
                            height: 10
                            policy: ScrollBar.AlwaysOn
                            interactive: true
                            visible: timelineList.overflowing
                            opacity: pressed || hovered || timelineHover.hovered || timelineWheel.active
                                ? 1 : 0.28
                            background: Rectangle {
                                radius: height / 2
                                color: theme.surfaceSunken
                                border.width: parent.visualFocus ? 1 : 0
                                border.color: theme.focus
                            }
                            contentItem: Rectangle {
                                objectName: "cameraTimelineScrollThumb"
                                implicitHeight: 6
                                radius: height / 2
                                color: timelineScrollBar.pressed
                                    ? theme.ink : timelineScrollBar.hovered
                                        ? theme.inkSecondary : theme.inkTertiary
                                Behavior on color {
                                    ColorAnimation {
                                        duration: theme.motion.hoverDuration
                                        easing.type: Easing.OutCubic
                                    }
                                }
                            }
                            Behavior on opacity {
                                NumberAnimation {
                                    duration: theme.motion.hoverDuration
                                    easing.type: Easing.OutCubic
                                }
                            }
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
                Divider {
                    visible: opacity > 0.01
                    opacity: root.logOpen ? 1 : 0
                    theme: root.theme
                    Layout.fillWidth: true
                    Behavior on opacity {
                        NumberAnimation { duration: theme.motion.sectionDuration; easing.type: Easing.OutCubic }
                    }
                }
                ScrollView {
                    visible: opacity > 0.01
                    enabled: root.logOpen
                    opacity: root.logOpen ? 1 : 0
                    y: root.logOpen ? 0 : -theme.motion.smallTravel
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Behavior on opacity {
                        NumberAnimation {
                            duration: theme.motion.sectionDuration
                            easing.type: Easing.BezierSpline
                            easing.bezierCurve: theme.motion.standardCurve
                        }
                    }
                    Behavior on y {
                        NumberAnimation {
                            duration: theme.motion.sectionDuration
                            easing.type: Easing.BezierSpline
                            easing.bezierCurve: theme.motion.standardCurve
                        }
                    }
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

    NumberAnimation {
        id: timelineWheelMotion
        target: timelineList
        property: "contentX"
        duration: theme.motion.timelineScrollDuration
        easing.type: Easing.BezierSpline
        easing.bezierCurve: theme.motion.standardCurve
    }
}
