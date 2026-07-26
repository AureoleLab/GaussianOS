import QtQuick

QtObject {
    objectName: "motionTokens"
    property bool reducedMotion: false
    property bool densityChanging: false

    readonly property int reducedDuration: 140
    readonly property int pressDuration: reducedMotion ? 120 : 105
    readonly property int hoverDuration: reducedMotion ? reducedDuration : 140
    readonly property int sectionDuration: reducedMotion ? reducedDuration : 210
    readonly property int dialogDuration: reducedMotion ? reducedDuration : 250
    readonly property int toastDuration: reducedMotion ? reducedDuration : 220
    readonly property int paneDuration: reducedMotion ? reducedDuration : 290
    readonly property int stateDuration: reducedMotion ? reducedDuration : 260
    readonly property int menuDuration: reducedMotion ? reducedDuration : 190
    readonly property int densityDuration: reducedMotion ? reducedDuration : 160
    readonly property int pageTransitionDuration: reducedMotion ? 150 : 290
    readonly property int inspectorTransitionDuration: reducedMotion ? 150 : 240
    readonly property int splitSnapDuration: reducedMotion ? reducedDuration : 140
    readonly property int navigationSelectionDuration: reducedMotion ? 120 : 180
    readonly property int resultDuration: reducedMotion ? reducedDuration : 220
    readonly property int viewerDuration: reducedMotion ? reducedDuration : 240
    readonly property int timelineScrollDuration: reducedMotion ? 120 : 145
    readonly property int adaptivePaneDuration: densityChanging ? densityDuration : paneDuration

    readonly property real pressScale: reducedMotion ? 1.0 : 0.975
    readonly property real dialogScale: reducedMotion ? 1.0 : 0.975
    readonly property real stateScale: reducedMotion ? 1.0 : 0.985
    readonly property int smallTravel: reducedMotion ? 0 : 8
    readonly property int paneTravel: reducedMotion ? 0 : 16
    readonly property int pageTravel: reducedMotion ? 0 : 18
    readonly property int inspectorTravel: reducedMotion ? 0 : 10
    readonly property real pageScale: reducedMotion ? 1.0 : 0.992
    readonly property int inspectorDelay: reducedMotion ? 0 : 40

    // Restrained non-linear curves. Each ends with the BezierSpline sentinel.
    readonly property var standardCurve: [0.20, 0.00, 0.00, 1.00, 1.00, 1.00]
    readonly property var emphasizedCurve: [0.16, 1.00, 0.30, 1.00, 1.00, 1.00]
    readonly property var navigationCurve: [0.22, 1.00, 0.36, 1.00, 1.00, 1.00]
}
