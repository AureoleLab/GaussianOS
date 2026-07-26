import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    required property var theme
    required property var type
    property var project: ({})
    property bool running: project.status === "running"
    property int progress: Math.round(Number(project.progress || 0) * 100)
    readonly property var sampling: project.sampling || ({})
    signal profileRequested(string profile)
    signal samplingRequested(string mode, int requested, real intervalValue,
                             string intervalUnit, int inFrame, int outFrame)
    signal analyzeRequested()
    signal openProjectDirectoryRequested()
    signal openLibraryDirectoryRequested()
    signal openRunDirectoryRequested()
    signal openInputsDirectoryRequested()
    signal openArtifactsDirectoryRequested()
    signal openExportsDirectoryRequested()

    function profileIndex() {
        return Math.max(0, ["preview", "balanced", "quality"].indexOf(project.profile || "balanced"))
    }
    function samplingIndex() {
        return Math.max(0, ["auto", "target_count", "interval", "all_frames"].indexOf(sampling.mode || "auto"))
    }
    function stageState(name) {
        return (project.stages || {})[name] || {"status": "pending"}
    }
    function statusColor(status) {
        if (status === "succeeded") return theme.success
        if (status === "running") return theme.accent
        if (status === "failed") return theme.error
        if (status === "interrupted" || status === "fallback_required") return theme.warning
        return theme.inkTertiary
    }

    color: theme.chrome

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: parent.width
            spacing: 0

            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 16
                Layout.rightMargin: 16
                Layout.topMargin: 14
                Layout.bottomMargin: 12
                Text {
                    Layout.fillWidth: true
                    text: "Inspector"
                    color: theme.ink
                    font.family: type.family
                    font.pixelSize: type.headingSize
                    font.weight: type.semibold
                }
                StatusBadge {
                    theme: root.theme
                    type: root.type
                    text: String(root.project.status || "NO PROJECT").toUpperCase()
                    status: root.running ? "running"
                        : root.project.status === "failed" ? "error"
                        : root.project.project_id ? "success" : "neutral"
                }
            }

            Divider { theme: root.theme; Layout.fillWidth: true }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 16
                spacing: 8
                SectionHeader { theme: root.theme; type: root.type; Layout.fillWidth: true; title: "Files" }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    ToolbarButton {
                        theme: root.theme; type: root.type
                        Layout.fillWidth: true
                        text: "Project folder"
                        compact: true
                        enabled: !!root.project.project_id
                        onClicked: root.openProjectDirectoryRequested()
                    }
                    ToolbarButton {
                        theme: root.theme; type: root.type
                        Layout.fillWidth: true
                        text: "Library"
                        compact: true
                        enabled: !!root.project.library_path
                        onClicked: root.openLibraryDirectoryRequested()
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    ToolbarButton {
                        theme: root.theme; type: root.type
                        Layout.fillWidth: true
                        text: "Current run"
                        compact: true
                        enabled: !!root.project.run_id
                        onClicked: root.openRunDirectoryRequested()
                    }
                    ToolbarButton {
                        theme: root.theme; type: root.type
                        Layout.fillWidth: true
                        text: "Input frames"
                        compact: true
                        enabled: !!root.project.run_id
                        onClicked: root.openInputsDirectoryRequested()
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    ToolbarButton {
                        theme: root.theme; type: root.type
                        Layout.fillWidth: true
                        text: "Artifacts"
                        compact: true
                        enabled: !!root.project.run_id
                        onClicked: root.openArtifactsDirectoryRequested()
                    }
                    ToolbarButton {
                        theme: root.theme; type: root.type
                        Layout.fillWidth: true
                        text: "Exports"
                        compact: true
                        enabled: !!root.project.run_id
                        onClicked: root.openExportsDirectoryRequested()
                    }
                }
                Text {
                    visible: root.project.active_run_status === "stale"
                    Layout.fillWidth: true
                    text: "The saved active run is stale; its run directory is missing."
                    color: theme.warning
                    font.family: type.family
                    font.pixelSize: type.microSize
                    wrapMode: Text.Wrap
                }
            }

            Divider { theme: root.theme; Layout.fillWidth: true }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 16
                spacing: 9
                SectionHeader { theme: root.theme; type: root.type; Layout.fillWidth: true; title: "Reconstruction profile" }
                ComboField {
                    id: profileField
                    theme: root.theme
                    type: root.type
                    Layout.fillWidth: true
                    model: ["Preview", "Balanced", "Quality"]
                    currentIndex: root.profileIndex()
                    enabled: !!root.project.project_id && !root.running
                    onActivated: root.profileRequested(["preview", "balanced", "quality"][currentIndex])
                }
                Text {
                    Layout.fillWidth: true
                    text: root.project.project_id
                        ? "Profile is persisted in the active project JSON."
                        : "Open or create a project to configure reconstruction."
                    color: theme.inkSecondary
                    font.family: type.family
                    font.pixelSize: type.microSize
                    lineHeight: type.bodyLine
                    wrapMode: Text.Wrap
                }
            }

            Divider { theme: root.theme; Layout.fillWidth: true }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 16
                spacing: 9
                SectionHeader { theme: root.theme; type: root.type; Layout.fillWidth: true; title: "Frame sampling" }
                ComboField {
                    id: samplingField
                    theme: root.theme
                    type: root.type
                    Layout.fillWidth: true
                    model: ["Auto", "Target count", "Interval", "All frames"]
                    currentIndex: root.samplingIndex()
                    enabled: root.project.input_kind === "video" && !root.running
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    AppTextField {
                        id: requestedField
                        theme: root.theme; type: root.type
                        Layout.fillWidth: true
                        placeholderText: "Target"
                        text: String(root.sampling.requested_frame_count || 120)
                    }
                    AppTextField {
                        id: intervalField
                        theme: root.theme; type: root.type
                        Layout.fillWidth: true
                        placeholderText: "Interval"
                        text: String(root.sampling.interval_value || 1)
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    ToolbarButton {
                        theme: root.theme; type: root.type
                        Layout.fillWidth: true
                        text: "Apply"
                        compact: true
                        enabled: root.project.input_kind === "video" && !root.running
                        onClicked: root.samplingRequested(
                            ["auto", "target_count", "interval", "all_frames"][samplingField.currentIndex],
                            Math.max(1, parseInt(requestedField.text) || 1),
                            Math.max(0.001, parseFloat(intervalField.text) || 1),
                            "seconds",
                            Number(root.sampling.in_frame || 0),
                            Number(root.sampling.out_frame || Math.max(0, Number(root.sampling.source_total_frames || 1) - 1))
                        )
                    }
                    ToolbarButton {
                        theme: root.theme; type: root.type
                        Layout.fillWidth: true
                        text: "Reanalyze"
                        iconName: "refresh"
                        primary: true
                        compact: true
                        enabled: root.project.input_kind === "video" && !root.running
                        onClicked: root.analyzeRequested()
                    }
                }
                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    rowSpacing: 7
                    columnSpacing: 10
                    Repeater {
                        model: [
                            ["Source", Number(root.sampling.source_total_frames || 0) + " frames"],
                            ["Selected", Number(root.sampling.selected_frame_count || 0) + " frames"],
                            ["COLMAP input", Number(root.sampling.colmap_input_frame_count || 0) + " frames"],
                            ["Analysis", String(root.sampling.analysis_status || "not started")]
                        ]
                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.columnSpan: 2
                            Text { Layout.fillWidth: true; text: modelData[0]; color: theme.inkSecondary; font.family: type.family; font.pixelSize: type.microSize }
                            Text { text: modelData[1]; color: theme.ink; font.family: type.family; font.pixelSize: type.microSize; font.weight: type.medium }
                        }
                    }
                }
            }

            Divider { theme: root.theme; Layout.fillWidth: true }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 16
                spacing: 8
                SectionHeader { theme: root.theme; type: root.type; Layout.fillWidth: true; title: "Quality & status" }
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        text: root.project.current_stage
                            ? "Stage · " + root.project.current_stage
                            : root.project.project_id ? "Ready to reconstruct" : "No active project"
                        color: theme.ink
                        font.family: type.family
                        font.pixelSize: type.labelSize
                        font.weight: type.medium
                    }
                    Text {
                        text: root.progress + "%"
                        color: root.running ? theme.accent : theme.inkTertiary
                        font.family: type.family
                        font.pixelSize: type.labelSize
                        font.weight: type.semibold
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 4
                    radius: theme.radiusProgress
                    color: theme.surfaceSunken
                    Rectangle {
                        width: parent.width * Math.max(0, Math.min(1, root.progress / 100))
                        height: parent.height
                        radius: parent.radius
                        color: theme.accent
                        Behavior on width { NumberAnimation { duration: theme.motion.stateDuration; easing.type: Easing.OutCubic } }
                    }
                }
            }

            Divider { theme: root.theme; Layout.fillWidth: true }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 16
                spacing: 5
                SectionHeader { theme: root.theme; type: root.type; Layout.fillWidth: true; title: "Pipeline stages" }
                Repeater {
                    model: [
                        ["ingest", "Ingest"], ["colmap", "COLMAP"],
                        ["fallback", "Fallback"], ["train", "Train"],
                        ["validate", "Validate"], ["export", "Export"]
                    ]
                    delegate: Rectangle {
                        required property var modelData
                        readonly property var state: root.stageState(modelData[0])
                        Layout.fillWidth: true
                        implicitHeight: 34
                        radius: theme.radiusItem
                        color: state.status === "running" ? theme.accentSoft : "transparent"
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 6
                            AppIcon {
                                name: state.status === "succeeded" ? "check"
                                    : state.status === "running" ? "activity" : "chevron-right"
                                size: theme.density.iconMicro
                                color: root.statusColor(state.status)
                            }
                            Text {
                                Layout.fillWidth: true
                                text: modelData[1]
                                color: theme.ink
                                font.family: type.family
                                font.pixelSize: type.labelSize
                                font.weight: state.status === "running" ? type.semibold : type.medium
                            }
                            Text {
                                text: String(state.status || "pending").toUpperCase()
                                color: root.statusColor(state.status)
                                font.family: type.family
                                font.pixelSize: type.microSize
                                font.weight: type.semibold
                            }
                        }
                    }
                }
            }
        }
    }
}
