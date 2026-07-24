from __future__ import annotations

from pathlib import Path


QML = Path(__file__).resolve().parents[2] / "apps" / "desktop" / "qml" / "classic"


def test_pro_preview_is_user_started_and_restores_position() -> None:
    main = (QML / "Main.qml").read_text(encoding="utf-8")

    assert "autoPlay: false" in main
    assert 'proDialog.open(); proPlayer.play()' not in main
    assert "if (proPreviewPriming)" in main
    assert '"proPreviewPosition": proPreviewPosition' in main
    assert "onOpened:" in main
    assert "restoreProPreview()" in main


def test_pro_and_viewer_timelines_have_persistent_horizontal_navigation() -> None:
    main = (QML / "Main.qml").read_text(encoding="utf-8")
    scrollbar = (QML / "GfHorizontalScrollBar.qml").read_text(encoding="utf-8")

    assert main.count("ScrollBar.horizontal: GfHorizontalScrollBar") == 2
    assert main.count("scrollTimelineByWheel(") == 3
    assert main.count("PointerDevice.Mouse | PointerDevice.TouchPad") == 2
    assert '"proTimelineScroll": proTimelineScroll' in main
    assert '"viewerTimelineScroll": viewerTimelineScroll' in main
    assert "policy: ScrollBar.AlwaysOn" in scrollbar
    assert "interactive: true" in scrollbar


def test_viewer_web_surface_is_aspect_fitted_on_a_themed_stage() -> None:
    main = (QML / "Main.qml").read_text(encoding="utf-8")

    assert "id: viewerStage" in main
    assert "theme.dark ? theme.surfaceRaised : theme.surfaceSunken" in main
    assert "readonly property real sourceAspect" in main
    assert "width: Math.min(parent.width - 2, (parent.height - 2) * sourceAspect)" in main
    assert "height: Math.min(parent.height - 2, (parent.width - 2) / sourceAspect)" in main
    assert 'objectName: "gaussianViewer"' in main
