import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    objectName: "projectLibrary"
    required property var theme
    required property var type
    property string filterMode: "all"
    property string viewMode: "list"
    property string sortMode: "Modified"
    property string searchText: ""
    property string selectedProjectId: "atrium"
    property var projects: [
        {"id":"atrium","name":"Atrium Capture","status":"Ready","group":"active","date":"24 Jul 2026, 14:32","size":"6.2 GiB","location":"D:\\GaussianOS\\Projects\\atrium","favorite":true,"profile":"Balanced","source":"Video · 2,448 frames"},
        {"id":"turbine","name":"Turbine Housing","status":"Training · 64%","group":"active","date":"24 Jul 2026, 12:08","size":"8.7 GiB","location":"D:\\GaussianOS\\Projects\\turbine","favorite":true,"profile":"Quality","source":"Images · 386 files"},
        {"id":"workshop","name":"Workshop Scan","status":"Archived","group":"archived","date":"18 Jun 2026, 09:16","size":"3.9 GiB","location":"D:\\GaussianOS\\Projects\\workshop","favorite":false,"profile":"Preview","source":"Video · 1,806 frames"},
        {"id":"courtyard","name":"Courtyard Test","status":"Trash","group":"trash","date":"24 Jul 2026, 10:18","size":"4.8 GiB","location":"D:\\GaussianOS\\Projects\\.trash\\courtyard","favorite":false,"profile":"Balanced","source":"Video · 1,922 frames"},
        {"id":"valve","name":"Valve Macro","status":"Trash","group":"trash","date":"19 Jul 2026, 16:42","size":"1.3 GiB","location":"D:\\GaussianOS\\Projects\\.trash\\valve","favorite":false,"profile":"Quality","source":"Images · 142 files"}
    ]
    readonly property var visibleProjects: {
        var query = searchText.trim().toLowerCase()
        var filtered = projects.filter(function(project) {
            var groupMatch = filterMode === "all" || project.group === filterMode
            var searchMatch = query.length === 0
                || project.name.toLowerCase().indexOf(query) >= 0
                || project.location.toLowerCase().indexOf(query) >= 0
            return groupMatch && searchMatch
        })
        filtered.sort(function(a, b) {
            if (sortMode === "Name") return a.name.localeCompare(b.name)
            if (sortMode === "Size") return parseFloat(b.size) - parseFloat(a.size)
            return b.date.localeCompare(a.date)
        })
        return filtered
    }

    signal projectSelected(var project)
    signal actionRequested(string message)
    signal renameRequested(var project)
    signal purgeRequested(var project)

    color: theme.canvas

    function choose(project) {
        selectedProjectId = project.id
        projectSelected(project)
    }

    function countFor(group) {
        if (group === "all") return projects.length
        return projects.filter(function(project) { return project.group === group }).length
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: theme.density.pagePadding
        spacing: theme.density.sectionGap

        RowLayout {
            Layout.fillWidth: true
            spacing: theme.density.itemGap
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Text {
                    text: "Project Library"
                    color: theme.ink
                    font.family: type.family
                    font.pixelSize: type.pageTitleSize
                    font.weight: type.semibold
                }
                Text {
                    Layout.fillWidth: true
                    text: "Browse, organize, archive, restore, and inspect every isolated project."
                    color: theme.inkSecondary
                    font.family: type.family
                    font.pixelSize: type.bodySize
                    font.weight: type.regular
                    elide: Text.ElideRight
                }
            }
            StatusBadge {
                visible: root.width >= 700
                theme: root.theme
                type: root.type
                text: root.visibleProjects.length + " PROJECTS"
                status: "neutral"
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: theme.density.itemGap
            AppTextField {
                id: librarySearch
                theme: root.theme
                type: root.type
                Layout.fillWidth: true
                Layout.preferredWidth: theme.density.librarySearchWidth
                Layout.minimumWidth: 120
                Layout.maximumWidth: theme.density.librarySearchWidth
                placeholderText: "Search name or location"
                leftPadding: 34
                onTextChanged: root.searchText = text
                background: Rectangle {
                    radius: theme.radiusControl
                    color: theme.control
                    border.width: parent.activeFocus ? 2 : 1
                    border.color: parent.activeFocus ? theme.focus : theme.line
                    AppIcon {
                        anchors.left: parent.left
                        anchors.leftMargin: 11
                        anchors.verticalCenter: parent.verticalCenter
                        name: "search"
                        size: theme.density.iconDefault
                        color: theme.inkTertiary
                    }
                }
            }
            Text {
                visible: root.width >= 760
                text: "Sort"
                color: theme.inkTertiary
                font.family: type.family
                font.pixelSize: type.metadataSize
            }
            ComboField {
                id: sortField
                theme: root.theme
                type: root.type
                Layout.preferredWidth: theme.density.librarySortWidth
                model: ["Modified", "Name", "Size"]
                onActivated: root.sortMode = currentText
            }
            Divider { visible: root.width >= 760; theme: root.theme; vertical: true }
            IconButton {
                objectName: "listViewToggle"
                theme: root.theme; type: root.type
                iconName: "list"
                toolTip: "List view"
                toggle: true
                selected: root.viewMode === "list"
                onClicked: root.viewMode = "list"
            }
            IconButton {
                objectName: "gridViewToggle"
                theme: root.theme; type: root.type
                iconName: "grid"
                toolTip: "Grid view"
                toggle: true
                selected: root.viewMode === "grid"
                onClicked: root.viewMode = "grid"
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: theme.density.itemGap
            Repeater {
                model: [
                    {"id":"all","label":"All"},
                    {"id":"active","label":"Active"},
                    {"id":"archived","label":"Archived"},
                    {"id":"trash","label":"Trash"}
                ]
                delegate: ToolbarButton {
                    required property var modelData
                    theme: root.theme
                    type: root.type
                    compact: true
                    text: modelData.label + "  " + root.countFor(modelData.id)
                    selected: root.filterMode === modelData.id
                    onClicked: root.filterMode = modelData.id
                }
            }
            Item { Layout.fillWidth: true }
            ToolbarButton {
                theme: root.theme
                type: root.type
                compact: true
                text: root.width >= 760 ? "Open library folder" : ""
                iconName: "folder"
                toolTip: "Open library folder"
                onClicked: root.actionRequested("Mock action · opened the project library folder")
            }
        }

        Divider { theme: root.theme; Layout.fillWidth: true }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.viewMode === "list" ? 0 : 1

            Item {
                Flickable {
                    id: tableFlick
                    anchors.fill: parent
                    clip: true
                    contentWidth: Math.max(width, theme.density.libraryTableMinWidth)
                    contentHeight: height
                    flickableDirection: Flickable.HorizontalFlick
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.horizontal: ScrollBar {
                        policy: tableFlick.contentWidth > tableFlick.width
                            ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
                    }

                    ColumnLayout {
                        width: tableFlick.contentWidth
                        height: tableFlick.height
                        spacing: 0

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: theme.density.tableHeaderHeight
                            color: "transparent"
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: theme.density.sidePadding
                                anchors.rightMargin: theme.density.sidePadding
                                spacing: theme.density.itemGap
                                Text { Layout.fillWidth: true; text: "NAME"; color: theme.inkTertiary; font.family: type.family; font.pixelSize: type.sectionHeaderSize; font.weight: type.medium; font.letterSpacing: 0.7 }
                                Text { Layout.preferredWidth: theme.density.libraryStatusWidth; text: "STATUS"; color: theme.inkTertiary; font.family: type.family; font.pixelSize: type.sectionHeaderSize; font.weight: type.medium }
                                Text { Layout.preferredWidth: theme.density.libraryDateWidth; text: root.filterMode === "trash" ? "DELETED" : "MODIFIED"; color: theme.inkTertiary; font.family: type.family; font.pixelSize: type.sectionHeaderSize; font.weight: type.medium }
                                Text { Layout.preferredWidth: theme.density.librarySizeWidth; text: "SIZE"; color: theme.inkTertiary; font.family: type.family; font.pixelSize: type.sectionHeaderSize; font.weight: type.medium }
                                Text { Layout.preferredWidth: theme.density.libraryLocationWidth; text: "LOCATION"; color: theme.inkTertiary; font.family: type.family; font.pixelSize: type.sectionHeaderSize; font.weight: type.medium }
                                Text { Layout.preferredWidth: theme.density.libraryActionsWidth; text: "ACTIONS"; color: theme.inkTertiary; font.family: type.family; font.pixelSize: type.sectionHeaderSize; font.weight: type.medium }
                            }
                        }
                        Divider { theme: root.theme; Layout.fillWidth: true }

                        ListView {
                            id: projectList
                            objectName: "projectLibraryList"
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            model: root.visibleProjects
                            boundsBehavior: Flickable.StopAtBounds
                            delegate: Rectangle {
                                id: projectRow
                                required property var modelData
                                required property int index
                                width: ListView.view.width
                                height: theme.density.listRowHeight
                                color: root.selectedProjectId === modelData.id
                                    ? theme.selected
                                    : rowMouse.containsMouse ? theme.controlHover : "transparent"
                                radius: theme.radiusItem
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: theme.density.sidePadding
                                    anchors.rightMargin: theme.density.sidePadding
                                    spacing: theme.density.itemGap
                                    AppIcon {
                                        name: modelData.group === "archived" ? "archive" : "project"
                                        size: theme.density.iconDefault
                                        color: root.selectedProjectId === modelData.id ? theme.ink : theme.inkSecondary
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData.name
                                        color: theme.ink
                                        font.family: type.family
                                        font.pixelSize: type.listPrimarySize
                                        font.weight: root.selectedProjectId === modelData.id ? type.semibold : type.medium
                                        elide: Text.ElideRight
                                    }
                                    Item {
                                        Layout.preferredWidth: theme.density.libraryStatusWidth
                                        StatusBadge {
                                            anchors.left: parent.left
                                            anchors.verticalCenter: parent.verticalCenter
                                            theme: root.theme
                                            type: root.type
                                            text: modelData.status.toUpperCase()
                                            status: modelData.group === "active" && modelData.status.indexOf("Training") >= 0 ? "running"
                                                : modelData.group === "active" ? "success"
                                                : "neutral"
                                        }
                                    }
                                    Text { Layout.preferredWidth: theme.density.libraryDateWidth; text: modelData.date; color: theme.inkSecondary; font.family: type.family; font.pixelSize: type.metadataSize; elide: Text.ElideRight }
                                    Text { Layout.preferredWidth: theme.density.librarySizeWidth; text: modelData.size; color: theme.inkSecondary; font.family: type.family; font.pixelSize: type.metadataSize }
                                    Text { Layout.preferredWidth: theme.density.libraryLocationWidth; text: modelData.location; color: theme.inkSecondary; font.family: type.family; font.pixelSize: type.metadataSize; elide: Text.ElideMiddle }
                                    RowLayout {
                                        Layout.preferredWidth: theme.density.libraryActionsWidth
                                        spacing: theme.density.iconActionGap
                                        IconButton { theme: root.theme; type: root.type; muted: true; iconName: "folder"; toolTip: "Open directory"; onClicked: root.actionRequested("Mock action · opened " + modelData.name + " directory") }
                                        IconButton { visible: modelData.group !== "trash"; theme: root.theme; type: root.type; muted: true; iconName: "rename"; toolTip: "Rename"; onClicked: root.renameRequested(modelData) }
                                        IconButton { visible: modelData.group !== "trash"; theme: root.theme; type: root.type; muted: true; iconName: "copy"; toolTip: "Duplicate"; onClicked: root.actionRequested("Mock action · duplicated " + modelData.name) }
                                        IconButton { visible: modelData.group === "active"; theme: root.theme; type: root.type; muted: true; iconName: "archive"; toolTip: "Archive"; onClicked: root.actionRequested("Mock action · archived " + modelData.name) }
                                        IconButton { visible: modelData.group === "archived" || modelData.group === "trash"; theme: root.theme; type: root.type; muted: true; iconName: "restore"; toolTip: modelData.group === "trash" ? "Restore" : "Unarchive"; onClicked: root.actionRequested("Mock action · restored " + modelData.name) }
                                        IconButton { visible: modelData.group === "trash"; theme: root.theme; type: root.type; muted: true; iconName: "delete"; toolTip: "Delete forever"; danger: true; onClicked: root.purgeRequested(modelData) }
                                    }
                                }
                                MouseArea {
                                    id: rowMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    acceptedButtons: Qt.LeftButton
                                    propagateComposedEvents: true
                                    onClicked: function(mouse) {
                                        root.choose(modelData)
                                        mouse.accepted = false
                                    }
                                }
                                Behavior on color {
                                    ColorAnimation { duration: theme.motion.hoverDuration; easing.type: Easing.OutCubic }
                                }
                                Behavior on height {
                                    NumberAnimation { duration: theme.motion.densityDuration; easing.type: Easing.OutCubic }
                                }
                            }
                        }
                    }
                }
            }

            GridView {
                id: projectGrid
                objectName: "projectLibraryGrid"
                clip: true
                model: root.visibleProjects
                cellWidth: theme.density.libraryGridCellWidth
                cellHeight: theme.density.libraryGridCellHeight
                Behavior on cellWidth {
                    NumberAnimation { duration: theme.motion.densityDuration; easing.type: Easing.OutCubic }
                }
                Behavior on cellHeight {
                    NumberAnimation { duration: theme.motion.densityDuration; easing.type: Easing.OutCubic }
                }
                delegate: Panel {
                    required property var modelData
                    width: projectGrid.cellWidth - theme.density.itemGap
                    height: projectGrid.cellHeight - theme.density.itemGap
                    theme: root.theme
                    color: root.selectedProjectId === modelData.id ? theme.selected : theme.surface
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: theme.density.panelPadding
                        spacing: theme.density.itemGap
                        RowLayout {
                            Layout.fillWidth: true
                            AppIcon { name: modelData.group === "archived" ? "archive" : "project"; size: theme.density.iconMajor; color: theme.ink }
                            Item { Layout.fillWidth: true }
                            StatusBadge { theme: root.theme; type: root.type; text: modelData.status.toUpperCase(); status: modelData.group === "active" ? "success" : "neutral" }
                        }
                        Text { Layout.fillWidth: true; text: modelData.name; color: theme.ink; font.family: type.family; font.pixelSize: type.listPrimarySize; font.weight: root.selectedProjectId === modelData.id ? type.semibold : type.medium; elide: Text.ElideRight }
                        Text { Layout.fillWidth: true; text: modelData.location; color: theme.inkSecondary; font.family: type.family; font.pixelSize: type.metadataSize; elide: Text.ElideMiddle }
                        Item { Layout.fillHeight: true }
                        RowLayout {
                            Layout.fillWidth: true
                            Text { Layout.fillWidth: true; text: modelData.size; color: theme.inkTertiary; font.family: type.family; font.pixelSize: type.metadataSize }
                            IconButton { theme: root.theme; type: root.type; muted: true; iconName: "folder"; toolTip: "Open directory"; onClicked: root.actionRequested("Mock action · opened " + modelData.name + " directory") }
                            IconButton { theme: root.theme; type: root.type; muted: true; iconName: "manage"; toolTip: "Project actions"; onClicked: root.renameRequested(modelData) }
                        }
                    }
                    TapHandler { onTapped: root.choose(modelData) }
                }
            }
        }

        Text {
            visible: root.visibleProjects.length === 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: "No projects match this view."
            color: theme.inkTertiary
            font.family: type.family
            font.pixelSize: type.bodySize
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }
}
