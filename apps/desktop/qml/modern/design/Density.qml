import QtQuick

QtObject {
    id: root
    property string mode: "standard"

    readonly property bool compact: mode === "compact"
    readonly property bool comfortable: mode === "comfortable"

    readonly property int toolbarHeight: compact ? 52 : comfortable ? 64 : 58
    readonly property int statusbarHeight: compact ? 22 : comfortable ? 26 : 24
    readonly property int sidebarWidth: compact ? 236 : comfortable ? 284 : 260
    readonly property int inspectorWidth: compact ? 296 : comfortable ? 344 : 320
    readonly property int controlHeight: compact ? 32 : comfortable ? 40 : 36
    readonly property int compactControlHeight: compact ? 28 : comfortable ? 36 : 32
    readonly property int iconButtonSize: compact ? 32 : comfortable ? 36 : 34
    readonly property int listRowHeight: compact ? 48 : comfortable ? 64 : 56
    readonly property int compactRowHeight: compact ? 38 : comfortable ? 48 : 42
    readonly property int tableHeaderHeight: compact ? 34 : comfortable ? 42 : 38
    readonly property int pagePadding: compact ? 20 : comfortable ? 36 : 28
    readonly property int panelPadding: compact ? 14 : comfortable ? 20 : 16
    readonly property int sidePadding: compact ? 10 : comfortable ? 16 : 12
    readonly property int itemGap: compact ? 6 : comfortable ? 12 : 8
    readonly property int sectionGap: compact ? 12 : comfortable ? 20 : 16

    // Visible glyphs remain optically smaller than their 32–36 px hit targets.
    readonly property int iconMicro: compact ? 10 : comfortable ? 12 : 11
    readonly property int iconDefault: compact ? 13 : comfortable ? 15 : 14
    readonly property int iconMajor: compact ? 15 : comfortable ? 17 : 16
    readonly property int iconBrand: compact ? 24 : comfortable ? 28 : 26
    readonly property int iconActionGap: compact ? 4 : comfortable ? 8 : 7
    readonly property int fontOffset: compact ? -1 : comfortable ? 1 : 0

    readonly property int splitHandleExtent: 8
    readonly property int sidebarMinWidth: 180
    readonly property int sidebarMaxWidth: 420
    readonly property int inspectorMinWidth: 260
    readonly property int inspectorMaxWidth: 520
    readonly property int viewerMinWidth: 520
    readonly property int viewerMinHeight: 280
    readonly property int activityLogCollapsedHeight: 38
    readonly property int activityLogHeight: compact ? 138 : comfortable ? 174 : 154

    readonly property int librarySearchWidth: compact ? 220 : comfortable ? 300 : 260
    readonly property int librarySortWidth: compact ? 112 : comfortable ? 144 : 128
    readonly property int libraryStatusWidth: compact ? 100 : comfortable ? 120 : 112
    readonly property int libraryDateWidth: compact ? 112 : comfortable ? 142 : 126
    readonly property int librarySizeWidth: compact ? 66 : comfortable ? 88 : 76
    readonly property int libraryLocationWidth: compact ? 140 : comfortable ? 210 : 174
    readonly property int libraryActionsWidth: compact ? 148 : comfortable ? 174 : 154
    readonly property int libraryTableMinWidth: compact ? 800 : comfortable ? 1000 : 900
    readonly property int libraryGridCellWidth: compact ? 204 : comfortable ? 260 : 230
    readonly property int libraryGridCellHeight: compact ? 148 : comfortable ? 184 : 164
}
