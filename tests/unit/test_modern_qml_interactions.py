from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest


MODERN = (
    Path(__file__).resolve().parents[2]
    / "apps"
    / "desktop"
    / "qml"
    / "modern"
)
COMPONENTS = MODERN / "components"


def run_qml_probe(script: str) -> str:
    if importlib.util.find_spec("PySide6") is None:
        pytest.skip("PySide6 desktop extra is not installed")
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_recent_project_hover_state_is_delegate_local() -> None:
    sidebar = (COMPONENTS / "Sidebar.qml").read_text(encoding="utf-8-sig")
    item = (COMPONENTS / "SidebarItem.qml").read_text(encoding="utf-8-sig")

    assert "delegate: SidebarItem" in sidebar
    assert "readonly property bool pointerHovered: rowHover.hovered" in item
    assert "HoverHandler {\n        id: rowHover" in item
    assert "root.pointerHovered ? theme.controlHover" in item
    assert "enabled: root.pointerHovered || root.selected || root.down" in item
    assert "readonly property bool manageVisible" in item
    assert "visible: root.manageVisible" in item
    assert "root.hovered" not in item


def test_project_library_rows_do_not_overlay_child_actions_with_mouse_area() -> None:
    library = (COMPONENTS / "ProjectLibrary.qml").read_text(encoding="utf-8-sig")

    assert "id: projectRow" in library
    assert "readonly property bool rowHovered: rowHover.hovered" in library
    assert "activeFocusOnTab: true" in library
    assert "id: rowTap" in library
    assert "id: rowMouse" not in library
    assert "propagateComposedEvents" not in library
    assert "projectRow.forceActiveFocus(Qt.MouseFocusReason)" in library


def test_camera_timeline_has_mouse_touchpad_and_scrollbar_navigation() -> None:
    viewer = (COMPONENTS / "ViewerPane.qml").read_text(encoding="utf-8-sig")

    assert 'objectName: "cameraTimeline"' in viewer
    assert 'objectName: "cameraTimelineWheelHandler"' in viewer
    assert 'objectName: "cameraTimelineScrollBar"' in viewer
    assert 'objectName: "cameraTimelineScrollThumb"' in viewer
    assert "ScrollBar.horizontal: ScrollBar" in viewer
    assert "policy: ScrollBar.AlwaysOn" in viewer
    assert "interactive: true" in viewer
    assert "visible: timelineList.overflowing" in viewer
    assert "PointerDevice.Mouse | PointerDevice.TouchPad" in viewer
    assert "event.pixelDelta.x" in viewer
    assert "event.angleDelta.x" in viewer
    assert "root.scrollTimelineBy(-pixel, false)" in viewer
    assert "root.scrollTimelineBy(-angle / 120 * 72, true)" in viewer
    assert "id: timelineWheelMotion" in viewer


def test_timeline_frames_keep_selection_focus_and_press_feedback() -> None:
    viewer = (COMPONENTS / "ViewerPane.qml").read_text(encoding="utf-8-sig")

    assert "delegate: AbstractButton" in viewer
    assert "focusPolicy: Qt.StrongFocus" in viewer
    assert "scale: down ? theme.motion.pressScale : 1" in viewer
    assert "root.playhead === index ? theme.selected" in viewer
    assert "onClicked: root.activateFrame(index)" in viewer
    assert "timelineList.positionViewAtIndex(index, ListView.Contain)" in viewer


def test_shared_controls_cover_interaction_states() -> None:
    for name in ("ToolbarButton.qml", "IconButton.qml", "ComboField.qml"):
        source = (COMPONENTS / name).read_text(encoding="utf-8-sig")
        assert "hoverEnabled: true" in source
        assert "focusPolicy: Qt.StrongFocus" in source
        assert "pressScale" in source
        assert "inkDisabled" in source or "opacity: enabled ? 1 : 0.46" in source

    combo = (COMPONENTS / "ComboField.qml").read_text(encoding="utf-8-sig")
    assert "required property int index" in combo
    assert "highlighted: hovered || root.highlightedIndex === delegateRoot.index" in combo
    assert "text: root.textAt(delegateRoot.index)" in combo
    assert "delegateRoot.down ? theme.controlPressed" in combo
    assert "delegateRoot.visualFocus ? 1 : 0" in combo

    card = (COMPONENTS / "ChoiceCard.qml").read_text(encoding="utf-8-sig")
    for state in ("root.down", "root.selected", "root.hovered", "root.visualFocus", "root.enabled"):
        assert state in card


def test_error_color_token_and_combo_delegate_are_runtime_safe() -> None:
    theme = (MODERN / "design" / "Theme.qml").read_text(encoding="utf-8-sig")
    main = (MODERN / "Main.qml").read_text(encoding="utf-8-sig")

    assert "readonly property color error: danger" in theme
    assert "color: theme.error" in main

    script = r'''
from PySide6.QtCore import QByteArray, QUrl, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

messages = []
qInstallMessageHandler(lambda _kind, _context, message: messages.append(message))
app = QGuiApplication([])
engine = QQmlEngine()
qml = r"""
import QtQuick
import QtQuick.Controls
import "__DESIGN__" as Design
import "__COMPONENTS__" as UI
ApplicationWindow {
    width: 320
    height: 180
    visible: true
    Design.Motion { id: motion }
    Design.Density { id: density }
    Design.Theme { id: theme; motion: motion; density: density }
    Design.Typography { id: typography; densityMode: density.mode }
    UI.ComboField {
        id: combo
        objectName: "combo"
        anchors.centerIn: parent
        width: 220
        theme: theme
        type: typography
        model: ["Modified", "Name", "Size"]
    }
    Component.onCompleted: combo.popup.open()
}
"""
component = QQmlComponent(engine)
component.setData(
    QByteArray(qml.encode()),
    QUrl("file:///gaussianos/combo_runtime_smoke.qml"),
)
if component.status() != QQmlComponent.Ready:
    raise RuntimeError("\n".join(error.toString() for error in component.errors()))
window = component.create()
app.processEvents()
QTest.qWait(250)
bad = [message for message in messages if "ReferenceError" in message or "index is not defined" in message]
assert not bad, bad
print("combo-runtime-safe")
window.close()
'''
    output = run_qml_probe(
        script.replace("__DESIGN__", (MODERN / "design").as_uri()).replace(
            "__COMPONENTS__", COMPONENTS.as_uri()
        )
    )
    assert "combo-runtime-safe" in output


def test_directory_actions_pass_only_project_and_run_identity_to_backend() -> None:
    main = (MODERN / "Main.qml").read_text(encoding="utf-8-sig")
    inspector = (COMPONENTS / "Inspector.qml").read_text(encoding="utf-8-sig")
    library = (COMPONENTS / "ProjectLibrary.qml").read_text(encoding="utf-8-sig")
    sidebar = (COMPONENTS / "Sidebar.qml").read_text(encoding="utf-8-sig")

    for action in (
        "openProjectDirectory",
        "openLibraryDirectory",
        "openRunDirectory",
        "openInputsDirectory",
        "openArtifactsDirectory",
        "openExportsDirectory",
    ):
        assert f"backend.{action}" in main
    assert "backend.openProjectFolder" not in main
    assert "backend.openProjectsFolder" not in main
    assert "backend.openExportFolder" not in main
    assert '"location": String(project.workspace_path || "")' in main
    assert "project.root || project.internal_workspace" not in main
    assert 'title: "Files"' in inspector
    assert "selectedLibraryPath" in library
    assert "enabled: !!root.currentProjectId && root.libraryPath.length > 0" in sidebar


def test_motion_tokens_and_critical_surfaces_are_non_linear_and_reduced() -> None:
    motion = (MODERN / "design" / "Motion.qml").read_text(encoding="utf-8-sig")
    main = (MODERN / "Main.qml").read_text(encoding="utf-8-sig")
    viewer = (COMPONENTS / "ViewerPane.qml").read_text(encoding="utf-8-sig")
    library = (COMPONENTS / "ProjectLibrary.qml").read_text(encoding="utf-8-sig")

    assert "readonly property int reducedDuration: 140" in motion
    for token in (
        "pageTransitionDuration",
        "inspectorTransitionDuration",
        "dialogDuration",
        "menuDuration",
        "sectionDuration",
        "resultDuration",
        "viewerDuration",
    ):
        assert token in motion
    assert "BezierSpline" in main
    assert "theme.motion.sectionDuration" in viewer
    assert "theme.motion.viewerDuration" in viewer
    assert "id: resultChangeMotion" in library
    assert "id: viewModeMotion" in library
    assert "ScriptAction { script: root.viewMode = root.pendingViewMode }" in library
    assert "alwaysRunToEnd: false" in library
    assert "UI.ChoiceCard" in main


def test_sidebar_hover_isolation_qml_smoke() -> None:
    script = r'''
from PySide6.QtCore import QByteArray, QObject, QPoint, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

app = QGuiApplication([])
engine = QQmlEngine()
qml = r"""
import QtQuick
import QtQuick.Controls
import "__COMPONENTS__" as UI
ApplicationWindow {
    id: shell
    width: 320
    height: 160
    visible: true
    property QtObject densityTokens: QtObject {
        property int listRowHeight: 56
        property int compactRowHeight: 40
        property int iconDefault: 16
        property int compactControlHeight: 28
        property int iconButtonSize: 30
        property int iconMajor: 18
    }
    property QtObject motionTokens: QtObject {
        property real pressScale: 0.98
        property int pressDuration: 100
        property int hoverDuration: 140
        property int navigationSelectionDuration: 180
        property int densityDuration: 1
        property var navigationCurve: [0.22, 1, 0.36, 1, 1, 1]
        property var emphasizedCurve: [0.16, 1, 0.3, 1, 1, 1]
    }
    property QtObject themeTokens: QtObject {
        property color selected: "#dddddd"
        property color controlPressed: "#cccccc"
        property color controlHover: "#eeeeee"
        property color focus: "#111111"
        property color accent: "#111111"
        property color inkSecondary: "#555555"
        property color ink: "#111111"
        property color inkTertiary: "#777777"
        property color inkDisabled: "#aaaaaa"
        property int radiusItem: 8
        property int radiusControl: 6
        property var density: shell.densityTokens
        property var motion: shell.motionTokens
    }
    property QtObject typeTokens: QtObject {
        property string family: "Arial"
        property int semibold: 600
        property int medium: 500
        property int listPrimarySize: 13
        property int metadataSize: 10
    }
    Column {
        anchors.fill: parent
        UI.SidebarItem {
            objectName: "rowOne"
            width: parent.width
            theme: shell.themeTokens
            type: shell.typeTokens
            text: "One"
            detail: "IDLE"
        }
        UI.SidebarItem {
            objectName: "rowTwo"
            width: parent.width
            theme: shell.themeTokens
            type: shell.typeTokens
            text: "Two"
            detail: "IDLE"
        }
    }
}
"""
component = QQmlComponent(engine)
component.setData(
    QByteArray(qml.encode()),
    QUrl("file:///gaussianos/sidebar_hover_smoke.qml"),
)
if component.status() != QQmlComponent.Ready:
    raise RuntimeError("\n".join(error.toString() for error in component.errors()))
window = component.create()
app.processEvents()
QTest.qWait(100)
row_one = window.findChild(QObject, "rowOne")
row_two = window.findChild(QObject, "rowTwo")
window.requestActivate()
QTest.mouseMove(window, QPoint(300, 150))
QTest.qWait(20)
QTest.mouseMove(window, QPoint(40, 28))
QTest.qWait(160)
assert row_one.property("pointerHovered") is True
assert row_two.property("pointerHovered") is False
QTest.mouseMove(window, QPoint(40, 84))
QTest.qWait(10)
assert row_one.property("pointerHovered") is False
assert row_two.property("pointerHovered") is True
print("hover-isolated")
window.close()
'''
    output = run_qml_probe(
        script.replace("__COMPONENTS__", COMPONENTS.as_uri())
    )
    assert "hover-isolated" in output


def test_ninety_frame_timeline_scrollbar_qml_smoke() -> None:
    script = r'''
from PySide6.QtCore import QByteArray, QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QWheelEvent
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from PySide6.QtWebEngineQuick import QtWebEngineQuick

QtWebEngineQuick.initialize()
app = QGuiApplication([])
engine = QQmlEngine()
frames = "[" + ",".join(
    '{"frame_index":%d,"registration_status":"unregistered"}' % index
    for index in range(90)
) + "]"
qml = r"""
import QtQuick
import QtQuick.Controls
import "__DESIGN__" as Design
import "__COMPONENTS__" as UI
ApplicationWindow {
    width: 900
    height: 600
    visible: true
    Design.Motion { id: motion }
    Design.Density { id: density; mode: "standard" }
    Design.Theme { id: theme; motion: motion; density: density }
    Design.Typography { id: typography; densityMode: density.mode }
    UI.ViewerPane {
        id: pane
        objectName: "pane"
        anchors.fill: parent
        theme: theme
        type: typography
        viewerUrl: "data:text/html,<html></html>"
        timeline: __FRAMES__
    }
}
""".replace("__FRAMES__", frames)
component = QQmlComponent(engine)
component.setData(
    QByteArray(qml.encode()),
    QUrl("file:///gaussianos/timeline_scroll_smoke.qml"),
)
if component.status() != QQmlComponent.Ready:
    raise RuntimeError("\n".join(error.toString() for error in component.errors()))
window = component.create()
app.processEvents()
QTest.qWait(500)
pane = window.findChild(QObject, "pane")
timeline = window.findChild(QQuickItem, "cameraTimeline")
scrollbar = window.findChild(QQuickItem, "cameraTimelineScrollBar")
scroll_thumb = window.findChild(QQuickItem, "cameraTimelineScrollThumb")
assert timeline.property("contentWidth") > timeline.property("width")
assert scrollbar.property("visible") is True
assert timeline.property("contentX") == 0
wheel_position = timeline.mapToScene(QPointF(120, 24))
wheel_global = window.mapToGlobal(
    QPoint(round(wheel_position.x()), round(wheel_position.y()))
)
wheel = QWheelEvent(
    wheel_position,
    QPointF(wheel_global),
    QPoint(),
    QPoint(0, -120),
    Qt.NoButton,
    Qt.NoModifier,
    Qt.NoScrollPhase,
    False,
)
QGuiApplication.sendEvent(window, wheel)
QTest.qWait(220)
assert timeline.property("contentX") > 0
assert pane.property("playhead") == -1
before_track_click = timeline.property("contentX")
track_position = scrollbar.mapToScene(
    QPointF(scrollbar.property("width") * 0.75, 5)
)
QTest.mouseClick(
    window,
    Qt.LeftButton,
    Qt.NoModifier,
    QPoint(round(track_position.x()), round(track_position.y())),
)
QTest.qWait(100)
assert timeline.property("contentX") > before_track_click
assert pane.property("playhead") == -1
before_thumb_drag = timeline.property("contentX")
thumb_position = scroll_thumb.mapToScene(
    QPointF(scroll_thumb.width() / 2, scroll_thumb.height() / 2)
)
thumb_start = QPoint(round(thumb_position.x()), round(thumb_position.y()))
thumb_end = QPoint(thumb_start.x() + 60, thumb_start.y())
QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, thumb_start)
QTest.mouseMove(window, thumb_end, 80)
QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, thumb_end)
QTest.qWait(100)
assert timeline.property("contentX") > before_thumb_drag
assert pane.property("playhead") == -1
pane.scrollTimelineBy(100000, False)
app.processEvents()
maximum = timeline.property("contentWidth") - timeline.property("width")
assert abs(timeline.property("contentX") - maximum) < 1
print("timeline-90-scrollable")
window.close()
'''
    output = run_qml_probe(
        script.replace("__DESIGN__", (MODERN / "design").as_uri()).replace(
            "__COMPONENTS__", COMPONENTS.as_uri()
        )
    )
    assert "timeline-90-scrollable" in output
