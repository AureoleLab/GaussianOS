import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    required property var theme
    required property var type
    property var project: ({})
    property bool viewerActive: false
    property var scenePlacement: ({
        "translation": [0, 0, 0],
        "rotation_xyz_degrees": [0, 0, 0],
        "scale_xyz": [1, 1, 1],
        "scale_locked": true
    })
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
    signal scenePlacementRequested(string payload)

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
    function transformVector(name, fallback) {
        var value = scenePlacement ? scenePlacement[name] : null
        return value && value.length === 3 ? value : fallback
    }
    function syncTransformFields() {
        var groups = [
            [locationFields, transformVector("translation", [0, 0, 0])],
            [rotationFields, transformVector("rotation_xyz_degrees", [0, 0, 0])],
            [scaleFields, transformVector("scale_xyz", [1, 1, 1])]
        ]
        for (var group = 0; group < groups.length; ++group)
            for (var axis = 0; axis < 3; ++axis) {
                var item = groups[group][0].itemAt(axis)
                if (item) item.text = String(Number(groups[group][1][axis]))
            }
        scaleLock.checked = !scenePlacement || scenePlacement.scale_locked !== false
    }
    function placementPayload() {
        function values(repeater) {
            return [0, 1, 2].map(function(index) {
                return Number(repeater.itemAt(index).text)
            })
        }
        return JSON.stringify({
            "translation": values(locationFields),
            "rotation_xyz_degrees": values(rotationFields),
            "scale_xyz": values(scaleFields),
            "scale_locked": scaleLock.checked
        })
    }
    function resetPlacement() {
        scenePlacementRequested(JSON.stringify({
            "translation": [0, 0, 0],
            "rotation_xyz_degrees": [0, 0, 0],
            "scale_xyz": [1, 1, 1],
            "scale_locked": true
        }))
    }
    onScenePlacementChanged: Qt.callLater(syncTransformFields)
    Component.onCompleted: Qt.callLater(syncTransformFields)

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
                objectName: "sceneTransformInspector"
                visible: root.viewerActive
                Layout.fillWidth: true
                Layout.margins: 16
                spacing: 7
                SectionHeader { theme: root.theme; type: root.type; Layout.fillWidth: true; title: "Scene Transform · Global" }
                Text {
                    Layout.fillWidth: true
                    text: "Places the Scene Root, Gaussians, point cloud and every camera in the Z-up world."
                    color: theme.inkSecondary
                    font.family: type.family
                    font.pixelSize: type.microSize
                    wrapMode: Text.Wrap
                }
                RowLayout {
                    Layout.fillWidth: true
                    Text { Layout.preferredWidth: 54; text: "Location"; color: theme.inkSecondary; font.family: type.family; font.pixelSize: type.microSize }
                    Repeater {
                        id: locationFields
                        model: ["X", "Y", "Z"]
                        delegate: AppTextField {
                            required property string modelData
                            required property int index
                            objectName: "sceneLocation" + modelData
                            theme: root.theme; type: root.type
                            Layout.fillWidth: true
                            placeholderText: modelData
                            validator: DoubleValidator { notation: DoubleValidator.StandardNotation }
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Text { Layout.preferredWidth: 54; text: "Rotation"; color: theme.inkSecondary; font.family: type.family; font.pixelSize: type.microSize }
                    Repeater {
                        id: rotationFields
                        model: ["X", "Y", "Z"]
                        delegate: AppTextField {
                            required property string modelData
                            required property int index
                            objectName: "sceneRotation" + modelData
                            theme: root.theme; type: root.type
                            Layout.fillWidth: true
                            placeholderText: modelData + "°"
                            validator: DoubleValidator { notation: DoubleValidator.StandardNotation }
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Text { Layout.preferredWidth: 54; text: "Scale"; color: theme.inkSecondary; font.family: type.family; font.pixelSize: type.microSize }
                    Repeater {
                        id: scaleFields
                        model: ["X", "Y", "Z"]
                        delegate: AppTextField {
                            required property string modelData
                            required property int index
                            objectName: "sceneScale" + modelData
                            theme: root.theme; type: root.type
                            Layout.fillWidth: true
                            placeholderText: modelData
                            validator: DoubleValidator { bottom: 0.0001; top: 10000; notation: DoubleValidator.StandardNotation }
                            onEditingFinished: {
                                if (!scaleLock.checked) return
                                for (var axis = 0; axis < 3; ++axis)
                                    scaleFields.itemAt(axis).text = text
                            }
                        }
                    }
                }
                AppCheckBox {
                    id: scaleLock
                    objectName: "sceneScaleLock"
                    theme: root.theme; type: root.type
                    text: "Lock proportional scale"
                    checked: true
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    ToolbarButton {
                        objectName: "sceneTransformReset"
                        theme: root.theme; type: root.type
                        Layout.fillWidth: true
                        text: "Reset"
                        iconName: "refresh"
                        compact: true
                        onClicked: root.resetPlacement()
                    }
                    ToolbarButton {
                        objectName: "sceneTransformApply"
                        theme: root.theme; type: root.type
                        Layout.fillWidth: true
                        text: "Apply"
                        iconName: "check"
                        primary: true
                        compact: true
                        onClicked: root.scenePlacementRequested(root.placementPayload())
                    }
                }
            }

            Divider { visible: root.viewerActive; theme: root.theme; Layout.fillWidth: true }

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
