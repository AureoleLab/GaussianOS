import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "viewerPane"
    required property var theme
    required property var type
    property string projectName: "Atrium Capture"
    property bool logOpen: true
    property bool running: false
    property string notice: ""
    property real activityLogHeight: theme.density.activityLogHeight
    property real draggedLogHeight: activityLogHeight
    property bool logDragging: false
    property bool logSnapping: false
    readonly property real maximumLogHeight: Math.max(
        theme.density.activityLogCollapsedHeight,
        Math.min(height * 0.45, height - theme.density.viewerMinHeight)
    )
    readonly property real effectiveLogHeight: logDragging
        ? draggedLogHeight : activityLogHeight

    signal logHeightAdjusted(real value, bool reset)

    function boundedLogHeight(value) {
        return Math.max(
            theme.density.activityLogCollapsedHeight,
            Math.min(maximumLogHeight, value)
        )
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
                }
                Text {
                    text: "Scene viewer"
                    color: theme.inkTertiary
                    font.family: type.family
                    font.pixelSize: type.microSize
                }
                Item { Layout.fillWidth: true }
                StatusBadge { theme: root.theme; type: root.type; text: "EMPTY"; status: "neutral" }
                IconButton { theme: root.theme; type: root.type; iconName: "grid"; toolTip: "Toggle grid"; selected: true; prominent: true }
                IconButton { theme: root.theme; type: root.type; iconName: "camera"; toolTip: "Camera view"; prominent: true }
                IconButton { theme: root.theme; type: root.type; iconName: "expand"; toolTip: "Fullscreen viewer"; prominent: true }
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
                model: 13
                Rectangle {
                    required property int index
                    x: Math.round(index * viewport.width / 12)
                    y: 0
                    width: 1
                    height: viewport.height
                    color: index === 6 ? theme.gridAxis : theme.gridLine
                    opacity: index === 6 ? 0.85 : 0.48
                }
            }
            Repeater {
                model: 9
                Rectangle {
                    required property int index
                    x: 0
                    y: Math.round(index * viewport.height / 8)
                    width: viewport.width
                    height: 1
                    color: index === 4 ? theme.gridAxis : theme.gridLine
                    opacity: index === 4 ? 0.85 : 0.48
                }
            }

            ColumnLayout {
                id: readyState
                objectName: "viewerReadyState"
                anchors.centerIn: parent
                width: Math.min(430, parent.width - 48)
                spacing: 12
                opacity: root.running ? 0 : 1
                enabled: !root.running
                scale: root.running ? theme.motion.stateScale : 1
                anchors.verticalCenterOffset: root.running ? -theme.motion.smallTravel : 0
                Behavior on anchors.verticalCenterOffset {
                    NumberAnimation {
                        duration: theme.motion.stateDuration
                        easing.type: Easing.BezierSpline
                        easing.bezierCurve: theme.motion.standardCurve
                    }
                }
                Behavior on opacity {
                    NumberAnimation { duration: theme.motion.stateDuration; easing.type: Easing.OutCubic }
                }
                Behavior on scale {
                    NumberAnimation {
                        duration: theme.motion.stateDuration
                        easing.type: Easing.BezierSpline
                        easing.bezierCurve: theme.motion.standardCurve
                    }
                }
                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 58
                    Layout.preferredHeight: 58
                    radius: theme.radiusPanel
                    color: theme.surface
                    border.width: 1
                    border.color: theme.line
                    AppIcon { anchors.centerIn: parent; name: "viewer"; size: theme.density.iconBrand; color: theme.accent }
                }
                Text {
                    Layout.fillWidth: true
                    text: "Viewer is ready"
                    color: theme.ink
                    font.family: type.family
                    font.pixelSize: type.titleSize
                    font.weight: type.semibold
                    horizontalAlignment: Text.AlignHCenter
                }
                Text {
                    Layout.fillWidth: true
                    text: "Run the pipeline or open a validated artifact to inspect the reconstructed scene."
                    color: theme.inkSecondary
                    font.family: type.family
                    font.pixelSize: type.labelSize
                    lineHeight: type.bodyLine
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                }
                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.topMargin: 4
                    spacing: 8
                    ToolbarButton {
                        theme: root.theme; type: root.type
                        text: "Run pipeline"
                        iconName: "play"
                        primary: true
                        onClicked: root.notice = "Mock action · pipeline started from Viewer"
                    }
                    ToolbarButton {
                        theme: root.theme; type: root.type
                        text: "Open artifact"
                        iconName: "folder"
                        onClicked: root.notice = "Mock action · artifact picker"
                    }
                }
            }

            ColumnLayout {
                id: runningState
                objectName: "viewerRunningState"
                anchors.centerIn: parent
                width: Math.min(430, parent.width - 48)
                spacing: 12
                opacity: root.running ? 1 : 0
                enabled: root.running
                scale: root.running ? 1 : theme.motion.stateScale
                anchors.verticalCenterOffset: root.running ? 0 : theme.motion.smallTravel
                Behavior on anchors.verticalCenterOffset {
                    NumberAnimation {
                        duration: theme.motion.stateDuration
                        easing.type: Easing.BezierSpline
                        easing.bezierCurve: theme.motion.standardCurve
                    }
                }
                Behavior on opacity {
                    NumberAnimation { duration: theme.motion.stateDuration; easing.type: Easing.OutCubic }
                }
                Behavior on scale {
                    NumberAnimation {
                        duration: theme.motion.stateDuration
                        easing.type: Easing.BezierSpline
                        easing.bezierCurve: theme.motion.standardCurve
                    }
                }
                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 58
                    Layout.preferredHeight: 58
                    radius: theme.radiusPanel
                    color: theme.accent
                    AppIcon { anchors.centerIn: parent; name: "activity"; size: theme.density.iconMajor; color: theme.inkOnAccent }
                }
                Text {
                    Layout.fillWidth: true
                    text: "Reconstruction in progress"
                    color: theme.ink
                    font.family: type.family
                    font.pixelSize: type.titleSize
                    font.weight: type.semibold
                    horizontalAlignment: Text.AlignHCenter
                }
                Text {
                    Layout.fillWidth: true
                    text: "Pipeline stages update in the Inspector while the viewer remains available."
                    color: theme.inkSecondary
                    font.family: type.family
                    font.pixelSize: type.labelSize
                    lineHeight: type.bodyLine
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                }
                ToolbarButton {
                    Layout.alignment: Qt.AlignHCenter
                    theme: root.theme; type: root.type
                    text: "View pipeline"
                    iconName: "pipeline"
                    onClicked: root.notice = "Mock action · pipeline status focused"
                }
            }

            Behavior on color {
                ColorAnimation { duration: theme.motion.stateDuration; easing.type: Easing.OutCubic }
            }
            Rectangle {
                id: toast
                objectName: "toast"
                visible: root.notice.length > 0 || opacity > 0.01
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 16
                implicitWidth: noticeRow.implicitWidth + 24
                implicitHeight: 36
                radius: theme.radiusToast
                color: theme.ink
                opacity: root.notice.length > 0 ? 1 : 0
                scale: root.notice.length > 0 ? 1 : theme.motion.dialogScale
                transform: Translate {
                    y: root.notice.length > 0 ? 0 : theme.motion.smallTravel
                    Behavior on y {
                        NumberAnimation {
                            duration: theme.motion.toastDuration
                            easing.type: Easing.BezierSpline
                            easing.bezierCurve: theme.motion.emphasizedCurve
                        }
                    }
                }
                RowLayout {
                    id: noticeRow
                    anchors.centerIn: parent
                    spacing: 8
                    AppIcon { name: "info"; size: theme.density.iconMicro; color: theme.surface }
                    Text {
                        text: root.notice
                        color: theme.surface
                        font.family: type.family
                        font.pixelSize: type.microSize
                        font.weight: type.medium
                    }
                    IconButton {
                        theme: root.theme; type: root.type
                        iconName: "close"
                        toolTip: "Dismiss"
                        implicitWidth: 24
                        implicitHeight: 24
                        onClicked: root.notice = ""
                        contentItem: AppIcon { name: "close"; size: theme.density.iconMicro; color: theme.surface }
                    }
                }
                Behavior on opacity {
                    NumberAnimation { duration: theme.motion.toastDuration; easing.type: Easing.OutCubic }
                }
                Behavior on scale {
                    NumberAnimation {
                        duration: theme.motion.toastDuration
                        easing.type: Easing.BezierSpline
                        easing.bezierCurve: theme.motion.emphasizedCurve
                    }
                }
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
                dragStart = root.logOpen
                    ? logPanel.height : theme.density.activityLogCollapsedHeight
                root.draggedLogHeight = dragStart
                root.logDragging = true
                root.logOpen = true
            }
            onDragMoved: function(delta) {
                root.draggedLogHeight = root.boundedLogHeight(dragStart - delta)
            }
            onDragFinished: {
                if (!root.logDragging)
                    return
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
                    duration: root.logSnapping
                        ? theme.motion.splitSnapDuration : theme.motion.sectionDuration
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
                        Behavior on rotation {
                            NumberAnimation {
                                duration: theme.motion.sectionDuration
                                easing.type: Easing.BezierSpline
                                easing.bezierCurve: theme.motion.standardCurve
                            }
                        }
                    }
                    AppIcon { name: "activity"; size: theme.density.iconDefault; color: theme.inkSecondary }
                    Text {
                        text: "Activity Log"
                        color: theme.ink
                        font.family: type.family
                        font.pixelSize: type.labelSize
                        font.weight: type.semibold
                    }
                    Text {
                        text: "3 recent events"
                        color: theme.inkTertiary
                        font.family: type.family
                        font.pixelSize: type.microSize
                    }
                    Item { Layout.fillWidth: true }
                    ToolbarButton {
                        theme: root.theme; type: root.type
                        text: "Clear"
                        quiet: true
                        compact: true
                    }
                }
                Divider {
                    visible: root.logOpen || opacity > 0.01
                    opacity: root.logOpen ? 1 : 0
                    theme: root.theme
                    Layout.fillWidth: true
                    Behavior on opacity {
                        NumberAnimation { duration: theme.motion.sectionDuration; easing.type: Easing.OutCubic }
                    }
                }
                ListView {
                    visible: root.logOpen || opacity > 0.01
                    opacity: root.logOpen ? 1 : 0
                    enabled: root.logOpen
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: [
                        ["14:32:08", "Project loaded", "Atrium Capture is ready for reconstruction."],
                        ["14:31:54", "Sampling analyzed", "184 frames selected from 2,448 source frames."],
                        ["14:31:49", "Video preflight", "3840 × 2160 · 30 FPS · 81.6 seconds."]
                    ]
                    delegate: RowLayout {
                        required property var modelData
                        width: ListView.view.width
                        height: 32
                        spacing: 10
                        Text {
                            Layout.leftMargin: 16
                            Layout.preferredWidth: 60
                            text: modelData[0]
                            color: theme.inkTertiary
                            font.family: type.monoFamily
                            font.pixelSize: type.microSize
                        }
                        AppIcon { name: "check"; size: theme.density.iconMicro; color: theme.success }
                        Text {
                            Layout.preferredWidth: 128
                            text: modelData[1]
                            color: theme.ink
                            font.family: type.family
                            font.pixelSize: type.microSize
                            font.weight: type.semibold
                        }
                        Text {
                            Layout.fillWidth: true
                            Layout.rightMargin: 16
                            text: modelData[2]
                            color: theme.inkSecondary
                            font.family: type.family
                            font.pixelSize: type.microSize
                            elide: Text.ElideRight
                        }
                    }
                    Behavior on opacity {
                        NumberAnimation { duration: theme.motion.sectionDuration; easing.type: Easing.OutCubic }
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
