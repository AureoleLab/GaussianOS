import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "projectDetailsInspector"
    required property var theme
    required property var type
    property var project: ({})
    signal openProjectRequested(var project)
    signal openFolderRequested(var project)
    signal openLibraryRequested(var project)
    signal renameRequested(var project)
    signal duplicateRequested(var project)
    signal archiveRequested(var project, bool archived)
    signal restoreRequested(var project)
    signal purgeRequested(var project)

    color: theme.chrome
    onProjectChanged: detailPulse.restart()

    SequentialAnimation {
        id: detailPulse
        NumberAnimation {
            target: detailsContent
            property: "opacity"
            to: theme.motion.reducedMotion ? 1 : 0.35
            duration: theme.motion.reducedMotion ? 1 : 70
            easing.type: Easing.InCubic
        }
        NumberAnimation {
            target: detailsContent
            property: "opacity"
            to: 1
            duration: theme.motion.reducedMotion ? 1 : 110
            easing.type: Easing.OutCubic
        }
    }

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            id: detailsContent
            width: parent.width
            spacing: 0

            RowLayout {
                Layout.fillWidth: true
                Layout.margins: theme.density.panelPadding
                spacing: theme.density.itemGap
                Text {
                    Layout.fillWidth: true
                    text: "Project Details"
                    color: theme.ink
                    font.family: type.family
                    font.pixelSize: type.panelTitleSize
                    font.weight: type.semibold
                }
                StatusBadge {
                    theme: root.theme
                    type: root.type
                    text: root.project.project_id
                        ? (root.project.status || "Ready").toUpperCase()
                        : "NO SELECTION"
                    status: root.project.group === "active" ? "success" : "neutral"
                }
            }

            Divider { theme: root.theme; Layout.fillWidth: true }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: theme.density.panelPadding
                spacing: theme.density.itemGap
                AppIcon {
                    Layout.alignment: Qt.AlignHCenter
                    name: root.project.group === "archived" ? "archive" : "project"
                    size: theme.density.iconBrand
                    color: theme.ink
                }
                Text {
                    Layout.fillWidth: true
                    text: root.project.name || "Project"
                    color: theme.ink
                    font.family: type.family
                    font.pixelSize: type.panelTitleSize
                    font.weight: type.semibold
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideRight
                }
                Text {
                    Layout.fillWidth: true
                    text: root.project.location || ""
                    color: theme.inkTertiary
                    font.family: type.family
                    font.pixelSize: type.metadataSize
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideMiddle
                }
            }

            Divider { theme: root.theme; Layout.fillWidth: true }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: theme.density.panelPadding
                spacing: theme.density.itemGap
                SectionHeader { theme: root.theme; type: root.type; Layout.fillWidth: true; title: "Project information" }
                Repeater {
                    model: [
                        ["Status", root.project.status || "—"],
                        [root.project.group === "trash" ? "Deleted" : "Modified", root.project.date || "—"],
                        ["Size", root.project.size || "—"],
                        ["Source", root.project.source || "—"],
                        ["Profile", root.project.profile || "—"]
                    ]
                    delegate: RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        Text { Layout.fillWidth: true; text: modelData[0]; color: theme.inkSecondary; font.family: type.family; font.pixelSize: type.metadataSize }
                        Text { text: modelData[1]; color: theme.ink; font.family: type.family; font.pixelSize: type.metadataSize; font.weight: type.medium }
                    }
                }
            }

            Divider { theme: root.theme; Layout.fillWidth: true }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: theme.density.panelPadding
                spacing: theme.density.itemGap
                SectionHeader { theme: root.theme; type: root.type; Layout.fillWidth: true; title: "Actions" }
                ToolbarButton {
                    visible: root.project.group === "active"
                    theme: root.theme; type: root.type
                    Layout.fillWidth: true
                    text: "Open project"
                    iconName: "viewer"
                    primary: true
                    onClicked: root.openProjectRequested(root.project)
                }
                ToolbarButton {
                    visible: !!root.project.project_id && root.project.group !== "trash"
                    theme: root.theme; type: root.type
                    Layout.fillWidth: true
                    text: "Open workspace"
                    iconName: "folder"
                    onClicked: root.openFolderRequested(root.project)
                }
                ToolbarButton {
                    visible: !!root.project.library_path && root.project.group !== "trash"
                    theme: root.theme; type: root.type
                    Layout.fillWidth: true
                    text: "Open library"
                    iconName: "library"
                    onClicked: root.openLibraryRequested(root.project)
                }
                RowLayout {
                    visible: !!root.project.project_id
                    Layout.fillWidth: true
                    spacing: theme.density.itemGap
                    ToolbarButton {
                        visible: root.project.group !== "trash"
                        theme: root.theme; type: root.type
                        Layout.fillWidth: true
                        text: "Rename"
                        iconName: "rename"
                        onClicked: root.renameRequested(root.project)
                    }
                    ToolbarButton {
                        visible: root.project.group !== "trash"
                        theme: root.theme; type: root.type
                        Layout.fillWidth: true
                        text: "Duplicate"
                        iconName: "copy"
                        onClicked: root.duplicateRequested(root.project)
                    }
                }
                ToolbarButton {
                    visible: root.project.group === "active"
                    theme: root.theme; type: root.type
                    Layout.fillWidth: true
                    text: "Archive project"
                    iconName: "archive"
                    onClicked: root.archiveRequested(root.project, true)
                }
                ToolbarButton {
                    visible: root.project.group === "archived" || root.project.group === "trash"
                    theme: root.theme; type: root.type
                    Layout.fillWidth: true
                    text: root.project.group === "trash" ? "Restore project" : "Unarchive project"
                    iconName: "restore"
                    onClicked: root.project.group === "trash"
                        ? root.restoreRequested(root.project)
                        : root.archiveRequested(root.project, false)
                }
                ToolbarButton {
                    visible: root.project.group === "trash"
                    theme: root.theme; type: root.type
                    Layout.fillWidth: true
                    text: "Delete forever"
                    iconName: "delete"
                    danger: true
                    onClicked: root.purgeRequested(root.project)
                }
            }

            Item { Layout.fillHeight: true; Layout.minimumHeight: theme.density.panelPadding }
        }
    }
}
