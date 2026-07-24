from __future__ import annotations

from pathlib import Path


DESKTOP = Path(__file__).resolve().parents[2] / "apps" / "desktop"
QML = DESKTOP / "qml" / "classic"


def test_p29_design_tokens_cover_global_themes_and_states() -> None:
    tokens = (QML / "DesignTokens.qml").read_text(encoding="utf-8")

    assert 'mode: "light"' in tokens
    assert 'mode === "dark"' in tokens
    assert 'mode === "system"' in tokens
    assert 'dark ? "#111111"' in tokens
    for state in ("accentHover", "accentPressed", "textDisabled", "success", "warning", "error"):
        assert f"property color {state}" in tokens
    for duration in ("motionFast", "motionNormal", "motionSlow"):
        assert f"property int {duration}" in tokens


def test_p29_uses_one_theme_for_every_qml_surface() -> None:
    main = (QML / "Main.qml").read_text(encoding="utf-8")

    assert 'DesignTokens { id: theme; mode: window.themeMode }' in main
    assert 'property string themeMode: "light"' in main
    assert 'window.themeMode = "dark"' in main
    assert 'window.themeMode = "system"' in main
    assert "darkTokens" not in main
    assert "forceDark" not in main


def test_p29_preserves_frontend_backend_actions_and_viewer_identity() -> None:
    main = (QML / "Main.qml").read_text(encoding="utf-8")
    viewer = (DESKTOP / "viewer_web" / "index.html").read_text(encoding="utf-8")

    for action in (
        "createProject", "selectProject", "beginVideoImport", "configureVideoImport",
        "generateVideoImport", "cancelVideoImport", "importInput", "setProfile",
        "setSampling", "analyzeSampling", "start", "cancel", "loadViewer",
        "openExportFolder", "viewerPageTitle", "viewerAcceptanceResult",
    ):
        assert f"backend.{action}" in main
    assert 'objectName: "gaussianViewer"' in main
    assert "viewerCamera.setCamera" in main
    assert "setFreeView" in viewer


def test_p29_button_content_is_centered_in_a_stretched_control() -> None:
    button = (QML / "GfButton.qml").read_text(encoding="utf-8")

    assert "contentItem: Item" in button
    assert "id: contentRow" in button
    assert "anchors.centerIn: parent" in button
    assert "Accessible.role: Accessible.Button" in button


def test_p29_workspace_is_resizable_animated_and_persistent() -> None:
    main = (QML / "Main.qml").read_text(encoding="utf-8")

    assert "import QtQuick.LocalStorage" in main
    assert main.count("SplitView {") >= 4
    assert "GaussianFactoryUILayout" in main
    assert "queueLayoutSave" in main
    assert "resetLayout" in main
    assert "GfSplitHandle" in main
    assert "GfSkeleton" in main
    assert "GfStatusDot" in main


def test_startup_defaults_to_welcome_and_restore_is_opt_in() -> None:
    main = (QML / "Main.qml").read_text(encoding="utf-8")
    backend = (DESKTOP / "main.py").read_text(encoding="utf-8")

    assert 'property bool restoreLastProject: false' in main
    assert 'text: "Restore last project at startup"' in main
    assert '"restoreLastProject": restoreLastProject' in main
    assert "if (restoreLastProject && lastProjectId)" in main
    assert "onClicked: openRecentProject(modelData.project_id)" in main
    assert "self.session = ProjectSession()" in backend
    assert "self.session.switch(project_id)" in backend
    assert "viewer_handler.clear_scene()" in backend
    assert "if backend.selected:\n        backend.loadViewer()" not in backend


def test_new_project_folder_supports_native_browse_and_manual_entry() -> None:
    main = (QML / "Main.qml").read_text(encoding="utf-8")

    assert "id: projectFolderPicker" in main
    assert 'title: "Choose project library folder"' in main
    assert "projectRoot.text = selectedPath" in main
    assert 'text: "Browse…"' in main
    assert 'toolTip: "Choose a project library in File Explorer"' in main
    assert "onClicked: chooseProjectFolder()" in main
    assert '"lastWorkingFolder": lastWorkingFolder' in main
    assert "onAccepted: if (projectName.text.trim()" in main


def test_p30_project_switch_and_soft_delete_are_explicit() -> None:
    main = (QML / "Main.qml").read_text(encoding="utf-8")
    backend = (DESKTOP / "main.py").read_text(encoding="utf-8")

    assert 'text: "Move “" + deleteProjectName + "” to trash?"' in main
    assert "backend.deleteProject(target)" in main
    assert 'enabled: modelData.status !== "running"' in main
    assert "legacy/shared workspace" in main
    assert "viewerPlayback.stop()" in main
    assert "timelinePreviewSource = \"\"" in main
    assert "self.session.switch(project_id)" in backend
    assert "viewer_handler.clear_scene()" in backend
    assert "self.session.accepts(data)" in backend


def test_media_position_signal_uses_explicit_qml_handler_parameters() -> None:
    main = (QML / "Main.qml").read_text(encoding="utf-8")

    assert "onPositionChanged: function()" in main
    assert "proPreviewPosition = proPlayer.position" in main


def test_p31_lifecycle_cleanup_and_permanent_delete_are_explicit() -> None:
    main = (QML / "Main.qml").read_text(encoding="utf-8")
    backend = (DESKTOP / "main.py").read_text(encoding="utf-8")

    for action in (
        "renameProject",
        "duplicateProject",
        "setProjectArchived",
        "restoreProject",
        "purgeProject",
        "cleanupProject",
    ):
        assert f"backend.{action}" in main
        assert f"def {action}" in backend
    assert "Estimated space to release: " in main
    assert "Type the project name to confirm: " in main
    assert "purgeConfirmation.text === purgeProjectName" in main
    assert 'text: "Copy Inputs & Settings"' in main
    assert 'text: "Copy Complete Valid Project"' in main


def test_p29_refined_palette_is_neutral_and_accent_is_restrained() -> None:
    tokens = (QML / "DesignTokens.qml").read_text(encoding="utf-8")

    for color in ('"#181818"', '"#1c1c1c"', '"#222222"'):
        assert color in tokens
    assert 'primaryControl: dark ? "#303030"' in tokens
    assert "shimmerBase" in tokens
    assert "shimmerHighlight" in tokens


def test_p29_qml_scopes_and_repeated_combo_motion_are_explicit() -> None:
    main = (QML / "Main.qml").read_text(encoding="utf-8")
    combo = (QML / "GfComboBox.qml").read_text(encoding="utf-8")

    assert "id: welcomeCanvas" in main
    assert "welcomeCanvas.requestPaint()" in main
    assert "required property int index" in combo
    assert "onVisibleChanged" in combo
    assert "menuOpenMotion.restart()" in combo
