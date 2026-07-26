import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    required property var theme
    required property var type
    property string currentPage: "workspace"
    property string currentProjectId: ""
    property var projects: []
    property var artifacts: []
    property string libraryPath: ""
    signal pageSelected(string page)
    signal projectSelected(var project)
    signal manageProject(var project)
    signal newProject()
    signal openLibrary()

    color: theme.chrome

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: theme.density.sidePadding
        anchors.rightMargin: theme.density.sidePadding
        anchors.topMargin: theme.density.panelPadding
        anchors.bottomMargin: theme.density.sidePadding
        spacing: 3

        AppTextField {
            id: searchField
            theme: root.theme
            type: root.type
            Layout.fillWidth: true
            placeholderText: "Search projects"
            leftPadding: 32
            background: Rectangle {
                radius: theme.radiusControl
                color: parent.enabled && parent.hovered && !parent.activeFocus
                    ? theme.controlHover : root.theme.surfaceSunken
                border.width: parent.activeFocus ? 2 : 0
                border.color: theme.focus
                Behavior on color {
                    ColorAnimation { duration: theme.motion.hoverDuration; easing.type: Easing.OutCubic }
                }
                AppIcon {
                    anchors.left: parent.left
                    anchors.leftMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    name: "search"
                    size: theme.density.iconDefault
                    color: theme.inkTertiary
                }
            }
        }

        Item { Layout.preferredHeight: 5 }
        SidebarItem {
            theme: root.theme
            type: root.type
            Layout.fillWidth: true
            text: "Workspace"
            iconName: "viewer"
            selected: root.currentPage === "workspace"
            onClicked: root.pageSelected("workspace")
        }
        SidebarItem {
            theme: root.theme
            type: root.type
            Layout.fillWidth: true
            text: "Project Library"
            detail: root.projects.length + " PROJECTS"
            iconName: "library"
            selected: root.currentPage === "library"
            onClicked: root.pageSelected("library")
        }

        SectionHeader {
            theme: root.theme
            type: root.type
            Layout.fillWidth: true
            Layout.topMargin: 10
            title: "Recent projects"
            actionText: "NEW"
            onAction: root.newProject()
        }

        Repeater {
            model: root.projects.filter(function(project) {
                var query = searchField.text.trim().toLowerCase()
                return !query || String(project.name || "").toLowerCase().indexOf(query) >= 0
            }).slice(0, 5)
            delegate: SidebarItem {
                required property var modelData
                theme: root.theme
                type: root.type
                Layout.fillWidth: true
                text: modelData.name
                detail: String(modelData.status || "idle").toUpperCase()
                iconName: modelData.archived ? "archive" : "project"
                status: modelData.status === "running" ? "warning" : ""
                selected: root.currentPage === "workspace"
                    && root.currentProjectId === modelData.project_id
                onClicked: root.projectSelected(modelData)
                onManageClicked: root.manageProject(modelData)
            }
        }

        Divider {
            theme: root.theme
            Layout.fillWidth: true
            Layout.topMargin: 10
            Layout.bottomMargin: 4
        }

        SectionHeader {
            theme: root.theme
            type: root.type
            Layout.fillWidth: true
            title: "Artifacts"
        }
        Repeater {
            model: root.artifacts.slice(0, 4)
            delegate: SidebarItem {
                required property var modelData
                theme: root.theme
                type: root.type
                Layout.fillWidth: true
                text: String(modelData).replace(/\\/g, "/").split("/").pop()
                iconName: String(modelData).toLowerCase().endsWith(".ply")
                    ? "viewer" : "folder"
            }
        }
        Text {
            visible: root.artifacts.length === 0
            Layout.fillWidth: true
            text: root.currentProjectId ? "No committed artifacts" : "Open a project"
            color: theme.inkTertiary
            font.family: type.family
            font.pixelSize: type.microSize
            wrapMode: Text.Wrap
        }

        Item { Layout.fillHeight: true }

        Panel {
            theme: root.theme
            Layout.fillWidth: true
            implicitHeight: 62
            color: theme.surfaceSunken
            border.width: 0
            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 9
                AppIcon { name: "folder"; size: theme.density.iconDefault; color: theme.inkSecondary }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        text: "Project library"
                        color: theme.ink
                        font.family: type.family
                        font.pixelSize: type.microSize
                        font.weight: type.semibold
                    }
                    Text {
                        Layout.fillWidth: true
                        text: root.libraryPath
                        color: theme.inkTertiary
                        font.family: type.family
                        font.pixelSize: type.microSize
                        elide: Text.ElideMiddle
                    }
                }
                IconButton {
                    theme: root.theme
                    type: root.type
                    iconName: "chevron-right"
                    toolTip: "Open project library"
                    onClicked: root.openLibrary()
                }
            }
        }
    }
}
