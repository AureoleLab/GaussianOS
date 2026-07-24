import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    required property var theme
    required property var type
    property string currentPage: "workspace"
    property string currentProject: "Atrium Capture"
    signal pageSelected(string page)
    signal projectSelected(string project)
    signal manageProject(string project)
    signal newProject()

    color: theme.chrome

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: theme.density.sidePadding
        anchors.rightMargin: theme.density.sidePadding
        anchors.topMargin: theme.density.panelPadding
        anchors.bottomMargin: theme.density.sidePadding
        spacing: 3

        AppTextField {
            theme: root.theme
            type: root.type
            Layout.fillWidth: true
            placeholderText: "Search projects"
            leftPadding: 32
            background: Rectangle {
                radius: theme.radiusControl
                color: root.theme.surfaceSunken
                border.width: parent.activeFocus ? 2 : 0
                border.color: theme.focus
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

        SidebarItem {
            theme: root.theme
            type: root.type
            Layout.fillWidth: true
            text: "Atrium Capture"
            detail: "CURRENT · READY"
            iconName: "project"
            selected: root.currentPage === "workspace" && root.currentProject === text
            onClicked: {
                root.currentProject = text
                root.projectSelected(text)
            }
            onManageClicked: root.manageProject(text)
        }
        SidebarItem {
            theme: root.theme
            type: root.type
            Layout.fillWidth: true
            text: "Turbine Housing"
            detail: "FAVORITE · TRAINING 64%"
            iconName: "folder"
            status: "warning"
            selected: root.currentPage === "workspace" && root.currentProject === text
            onClicked: {
                root.currentProject = text
                root.projectSelected(text)
            }
            onManageClicked: root.manageProject(text)
        }
        SidebarItem {
            theme: root.theme
            type: root.type
            Layout.fillWidth: true
            text: "Workshop Scan"
            detail: "RECENT · ARCHIVED"
            iconName: "archive"
            selected: root.currentPage === "workspace" && root.currentProject === text
            onClicked: {
                root.currentProject = text
                root.projectSelected(text)
            }
            onManageClicked: root.manageProject(text)
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
        SidebarItem {
            theme: root.theme
            type: root.type
            Layout.fillWidth: true
            text: "atrium_final.ply"
            iconName: "viewer"
        }
        SidebarItem {
            theme: root.theme
            type: root.type
            Layout.fillWidth: true
            text: "camera_path.json"
            iconName: "camera"
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
                        text: "D:\\GaussianOS\\Projects"
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
                }
            }
        }
    }
}
