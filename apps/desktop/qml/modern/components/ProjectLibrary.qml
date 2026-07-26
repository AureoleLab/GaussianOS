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
    property string pendingViewMode: viewMode
    property string sortMode: "Modified"
    property string searchText: ""
    property string selectedProjectId: ""
    property string selectedLibraryPath: ""
    property string hoveredProjectId: ""
    property var projects: []
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
    signal openLibraryRequested()
    signal openFolderRequested(var project)
    signal renameRequested(var project)
    signal duplicateRequested(var project)
    signal archiveRequested(var project, bool archived)
    signal deleteRequested(var project)
    signal restoreRequested(var project)
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
    function animateResults() {
        resultChangeMotion.restart()
    }
    function requestViewMode(mode) {
        if (mode === viewMode && !viewModeMotion.running)
            return
        pendingViewMode = mode
        viewModeMotion.restart()
    }

    onProjectsChanged: hoveredProjectId = ""
    onFilterModeChanged: {
        hoveredProjectId = ""
        animateResults()
    }
    onSortModeChanged: {
        hoveredProjectId = ""
        animateResults()
    }
    onSearchTextChanged: {
        hoveredProjectId = ""
        searchMotionTimer.restart()
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
                    color: parent.enabled && parent.hovered && !parent.activeFocus
                        ? theme.controlHover : theme.control
                    border.width: parent.activeFocus ? 2 : 1
                    border.color: parent.activeFocus ? theme.focus : theme.line
                    Behavior on color {
                        ColorAnimation { duration: theme.motion.hoverDuration; easing.type: Easing.OutCubic }
                    }
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
                onClicked: root.requestViewMode("list")
            }
            IconButton {
                objectName: "gridViewToggle"
                theme: root.theme; type: root.type
                iconName: "grid"
                toolTip: "Grid view"
                toggle: true
                selected: root.viewMode === "grid"
                onClicked: root.requestViewMode("grid")
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
                enabled: root.selectedProjectId.length > 0
                    && root.selectedLibraryPath.length > 0
                onClicked: root.openLibraryRequested()
            }
        }

        Divider { theme: root.theme; Layout.fillWidth: true }

        StackLayout {
            id: resultsHost
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
                                objectName: "projectRow-" + modelData.id
                                readonly property bool rowSelected: root.selectedProjectId === modelData.id
                                readonly property bool rowHovered:
                                    root.hoveredProjectId === modelData.id
                                width: ListView.view.width
                                height: theme.density.listRowHeight
                                activeFocusOnTab: true
                                scale: rowTap.pressed ? theme.motion.pressScale : 1
                                color: rowSelected
                                    ? theme.selected
                                    : rowTap.pressed ? theme.controlPressed
                                    : rowHovered ? theme.controlHover : "transparent"
                                radius: theme.radiusItem
                                border.width: activeFocus ? 1 : 0
                                border.color: theme.focus
                                Accessible.name: modelData.name
                                Accessible.role: Accessible.ListItem
                                Keys.onPressed: function(event) {
                                    if (event.key === Qt.Key_Return
                                            || event.key === Qt.Key_Enter
                                            || event.key === Qt.Key_Space) {
                                        root.choose(modelData)
                                        event.accepted = true
                                    }
                                }
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: theme.density.sidePadding
                                    anchors.rightMargin: theme.density.sidePadding
                                    spacing: theme.density.itemGap
                                    AppIcon {
                                        name: modelData.group === "archived" ? "archive" : "project"
                                        size: theme.density.iconDefault
                                        color: projectRow.rowSelected || projectRow.rowHovered
                                            ? theme.ink : theme.inkSecondary
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData.name
                                        color: theme.ink
                                        font.family: type.family
                                        font.pixelSize: type.listPrimarySize
                                        font.weight: projectRow.rowSelected ? type.semibold : type.medium
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
                                        IconButton { visible: modelData.group !== "trash"; theme: root.theme; type: root.type; muted: true; iconName: "folder"; toolTip: "Open project folder"; onClicked: root.openFolderRequested(modelData) }
                                        IconButton { visible: modelData.group !== "trash"; theme: root.theme; type: root.type; muted: true; iconName: "rename"; toolTip: "Rename"; onClicked: root.renameRequested(modelData) }
                                        IconButton { visible: modelData.group !== "trash"; theme: root.theme; type: root.type; muted: true; iconName: "copy"; toolTip: "Duplicate"; onClicked: root.duplicateRequested(modelData) }
                                        IconButton { visible: modelData.group === "archived" || modelData.group === "trash"; theme: root.theme; type: root.type; muted: true; iconName: "restore"; toolTip: modelData.group === "trash" ? "Restore" : "Unarchive"; onClicked: modelData.group === "trash" ? root.restoreRequested(modelData) : root.archiveRequested(modelData, false) }
                                        IconButton { visible: modelData.group !== "trash"; theme: root.theme; type: root.type; muted: true; danger: true; iconName: "trash"; toolTip: "Move to Trash"; onClicked: root.deleteRequested(modelData) }
                                        IconButton { visible: modelData.group === "trash"; theme: root.theme; type: root.type; muted: true; iconName: "delete"; toolTip: "Delete forever"; danger: true; onClicked: root.purgeRequested(modelData) }
                                    }
                                }
                                HoverHandler {
                                    id: rowHover
                                    cursorShape: Qt.PointingHandCursor
                                    onHoveredChanged: {
                                        if (hovered)
                                            root.hoveredProjectId = modelData.id
                                        else if (root.hoveredProjectId === modelData.id)
                                            root.hoveredProjectId = ""
                                    }
                                }
                                TapHandler {
                                    id: rowTap
                                    acceptedButtons: Qt.LeftButton
                                    gesturePolicy: TapHandler.ReleaseWithinBounds
                                    onTapped: {
                                        projectRow.forceActiveFocus(Qt.MouseFocusReason)
                                        root.choose(modelData)
                                    }
                                }
                                Behavior on scale {
                                    NumberAnimation {
                                        duration: theme.motion.pressDuration
                                        easing.type: Easing.BezierSpline
                                        easing.bezierCurve: theme.motion.emphasizedCurve
                                    }
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
                    id: projectCard
                    required property var modelData
                    objectName: "projectCard-" + modelData.id
                    readonly property bool cardSelected: root.selectedProjectId === modelData.id
                    readonly property bool cardHovered:
                        root.hoveredProjectId === modelData.id
                    width: projectGrid.cellWidth - theme.density.itemGap
                    height: projectGrid.cellHeight - theme.density.itemGap
                    theme: root.theme
                    activeFocusOnTab: true
                    scale: cardTap.pressed ? theme.motion.pressScale : 1
                    color: cardSelected ? theme.selected
                        : cardTap.pressed ? theme.controlPressed
                        : cardHovered ? theme.controlHover
                        : theme.surface
                    border.width: activeFocus ? 2 : 1
                    border.color: activeFocus ? theme.focus
                        : cardSelected ? theme.lineStrong : theme.lineSubtle
                    Accessible.name: modelData.name
                    Accessible.role: Accessible.ListItem
                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Return
                            || event.key === Qt.Key_Enter
                            || event.key === Qt.Key_Space) {
                            root.choose(modelData)
                            event.accepted = true
                        }
                    }
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
                        Text { Layout.fillWidth: true; text: modelData.name; color: theme.ink; font.family: type.family; font.pixelSize: type.listPrimarySize; font.weight: projectCard.cardSelected ? type.semibold : type.medium; elide: Text.ElideRight }
                        Text { Layout.fillWidth: true; text: modelData.location; color: theme.inkSecondary; font.family: type.family; font.pixelSize: type.metadataSize; elide: Text.ElideMiddle }
                        Item { Layout.fillHeight: true }
                        RowLayout {
                            Layout.fillWidth: true
                            Text { Layout.fillWidth: true; text: modelData.size; color: theme.inkTertiary; font.family: type.family; font.pixelSize: type.metadataSize }
                            IconButton { visible: modelData.group !== "trash"; theme: root.theme; type: root.type; muted: true; iconName: "folder"; toolTip: "Open project folder"; onClicked: root.openFolderRequested(modelData) }
                            IconButton { theme: root.theme; type: root.type; muted: true; iconName: "manage"; toolTip: "Project actions"; onClicked: root.renameRequested(modelData) }
                            IconButton { visible: modelData.group !== "trash"; theme: root.theme; type: root.type; muted: true; danger: true; iconName: "trash"; toolTip: "Move to Trash"; onClicked: root.deleteRequested(modelData) }
                        }
                    }
                    HoverHandler {
                        id: cardHover
                        cursorShape: Qt.PointingHandCursor
                        onHoveredChanged: {
                            if (hovered)
                                root.hoveredProjectId = modelData.id
                            else if (root.hoveredProjectId === modelData.id)
                                root.hoveredProjectId = ""
                        }
                    }
                    TapHandler {
                        id: cardTap
                        acceptedButtons: Qt.LeftButton
                        gesturePolicy: TapHandler.ReleaseWithinBounds
                        onTapped: {
                            projectCard.forceActiveFocus(Qt.MouseFocusReason)
                            root.choose(modelData)
                        }
                    }
                    Behavior on border.color {
                        ColorAnimation { duration: theme.motion.hoverDuration; easing.type: Easing.OutCubic }
                    }
                    Behavior on scale {
                        NumberAnimation {
                            duration: theme.motion.pressDuration
                            easing.type: Easing.BezierSpline
                            easing.bezierCurve: theme.motion.emphasizedCurve
                        }
                    }
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

    Timer {
        id: searchMotionTimer
        interval: 45
        onTriggered: root.animateResults()
    }

    SequentialAnimation {
        id: viewModeMotion
        alwaysRunToEnd: false
        ParallelAnimation {
            NumberAnimation {
                target: resultsHost
                property: "opacity"
                to: 0.15
                duration: theme.motion.resultDuration * 0.4
                easing.type: Easing.InCubic
            }
            NumberAnimation {
                target: resultsHost
                property: "scale"
                to: theme.motion.stateScale
                duration: theme.motion.resultDuration * 0.4
                easing.type: Easing.InCubic
            }
        }
        ScriptAction { script: root.viewMode = root.pendingViewMode }
        ParallelAnimation {
            NumberAnimation {
                target: resultsHost
                property: "opacity"
                to: 1
                duration: theme.motion.resultDuration * 0.6
                easing.type: Easing.BezierSpline
                easing.bezierCurve: theme.motion.standardCurve
            }
            NumberAnimation {
                target: resultsHost
                property: "scale"
                to: 1
                duration: theme.motion.resultDuration * 0.6
                easing.type: Easing.BezierSpline
                easing.bezierCurve: theme.motion.standardCurve
            }
        }
    }

    SequentialAnimation {
        id: resultChangeMotion
        alwaysRunToEnd: false
        ParallelAnimation {
            NumberAnimation {
                target: resultsHost
                property: "opacity"
                to: 0.72
                duration: theme.motion.resultDuration * 0.35
                easing.type: Easing.InCubic
            }
            NumberAnimation {
                target: resultsHost
                property: "scale"
                to: theme.motion.stateScale
                duration: theme.motion.resultDuration * 0.35
                easing.type: Easing.InCubic
            }
        }
        ParallelAnimation {
            NumberAnimation {
                target: resultsHost
                property: "opacity"
                to: 1
                duration: theme.motion.resultDuration * 0.65
                easing.type: Easing.BezierSpline
                easing.bezierCurve: theme.motion.standardCurve
            }
            NumberAnimation {
                target: resultsHost
                property: "scale"
                to: 1
                duration: theme.motion.resultDuration * 0.65
                easing.type: Easing.BezierSpline
                easing.bezierCurve: theme.motion.standardCurve
            }
        }
    }
}
