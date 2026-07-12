"""PySide6/QML application entry point.

The QObject facade only queues control-plane work onto Python threads.  Qt's
main thread owns the UI and never imports a model or calls a Worker.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path
from typing import Any

from .pipeline import PipelineController
from .project_store import Project, ProjectStore
from .viewer import viewer_payload


def _qt():
    try:
        from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
    except ImportError as exc:  # keeps non-GUI callers free of Qt imports
        raise RuntimeError("Desktop GUI requires `uv sync --extra desktop`") from exc
    return QObject, Property, QUrl, Signal, Slot, QGuiApplication, QQmlApplicationEngine


def main() -> int:
    QObject, Property, QUrl, Signal, Slot, QGuiApplication, QQmlApplicationEngine = _qt()
    parser = argparse.ArgumentParser(description="Gaussian Factory P2 desktop GUI")
    parser.add_argument("--projects", type=Path, default=Path.home() / ".gaussian-factory" / "projects")
    parser.add_argument("--artifacts", type=Path, default=Path.home() / ".gaussian-factory" / "artifact-store")
    args = parser.parse_args()
    store = ProjectStore(args.projects)
    controller = PipelineController(store, args.artifacts)

    class Backend(QObject):
        changed = Signal()
        event = Signal(str, str)

        def __init__(self) -> None:
            super().__init__()
            self.projects: list[Project] = store.all()
            self.selected = self.projects[0].project_id if self.projects else ""
            self.logs: list[str] = []
            self.viewer = json.dumps({"cameras": [], "points": [], "gaussians": []})

        def _project(self) -> Project | None:
            try: return store.load(self.selected) if self.selected else None
            except FileNotFoundError: return None

        @Property(str, notify=changed)
        def projectsJson(self) -> str:
            return json.dumps([item.to_dict() for item in self.projects], ensure_ascii=False)

        @Property(str, notify=changed)
        def currentJson(self) -> str:
            current = self._project()
            return json.dumps(current.to_dict() if current else {}, ensure_ascii=False)

        @Property(str, notify=changed)
        def logText(self) -> str:
            return "\n".join(self.logs[-400:])

        @Property(str, notify=changed)
        def viewerJson(self) -> str:
            return self.viewer

        def _refresh(self) -> None:
            self.projects = store.all()
            self.changed.emit()

        @Slot(str, str)
        def createProject(self, name: str, root: str) -> None:
            if not name.strip() or not root.strip():
                self.logs.append("Project name and location are required")
            else:
                project = store.create(name.strip(), root)
                self.selected = project.project_id
                self.logs.append(f"Created project {project.name}")
            self._refresh()

        @Slot(str)
        def selectProject(self, project_id: str) -> None:
            self.selected = project_id
            self._refresh()

        @Slot(str)
        def importInput(self, source: str) -> None:
            project = self._project()
            if project is None: return
            try:
                controller.import_input(project, source)
                self.logs.append(f"Imported {source}")
            except Exception as exc:
                self.logs.append(f"Import failed: {exc}")
            self._refresh()

        @Slot(str)
        def setProfile(self, profile: str) -> None:
            project = self._project()
            if project is not None and profile in {"preview", "balanced", "quality"}:
                project.profile = profile; store.save(project)
            self._refresh()

        @Slot()
        def start(self) -> None:
            project = self._project()
            if project is None or project.status == "running": return
            def receive(kind: str, message: str, payload: dict[str, Any]) -> None:
                self.event.emit(kind, message)
            def run() -> None:
                controller.run(project.project_id, receive)
                self.event.emit("complete", "Pipeline finished")
            threading.Thread(target=run, name=f"gaussian-run-{project.project_id[:8]}", daemon=True).start()
            self.logs.append("Pipeline queued")
            self._refresh()

        @Slot()
        def cancel(self) -> None:
            if self.selected: controller.cancel(self.selected)
            self.logs.append("Cancellation requested")
            self.changed.emit()

        @Slot()
        def loadViewer(self) -> None:
            project = self._project()
            if project is None: return
            state = project.stages.get("validate")
            if state and len(state.artifact_paths) >= 2:
                try:
                    self.viewer = viewer_payload(state.artifact_paths[0], state.artifact_paths[1])
                    self.logs.append("Viewer loaded camera trajectory and Gaussians")
                except Exception as exc:
                    self.logs.append(f"Viewer load failed: {exc}")
            self.changed.emit()

        @Slot(str, str)
        def handleEvent(self, kind: str, message: str) -> None:
            """Queued Qt slot: all QML-facing updates remain on the GUI thread."""
            self.logs.append(f"{kind}: {message}")
            self._refresh()

    app = QGuiApplication(sys.argv)
    backend = Backend()
    backend.event.connect(backend.handleEvent)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    qml = Path(__file__).with_name("qml") / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml)))
    if not engine.rootObjects(): return 2
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
