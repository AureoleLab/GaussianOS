"""PySide6/QML application entry point.

The QObject facade only queues control-plane work onto Python threads.  Qt's
main thread owns the UI and never imports a model or calls a Worker.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .pipeline import PipelineController, RuntimePaths, STAGES, TERMINAL_STAGE_STATES
from .project_store import Project, ProjectStore
from .viewer import ViewerScene, load_viewer_scene
from .sampling import discover_ffprobe
from .video_import import VideoImportSession


def project_view(project: Project) -> dict[str, Any]:
    """Return the durable snapshot plus UI-only progress/artifact fields."""
    value = project.to_dict()
    terminal = sum(
        value.get("stages", {}).get(name, {}).get("status") in TERMINAL_STAGE_STATES
        for name in STAGES
    )
    value["progress"] = 1.0 if project.status == "succeeded" else terminal / len(STAGES)
    artifacts = [
        path for name in STAGES
        for path in value.get("stages", {}).get(name, {}).get("artifact_paths", [])
    ]
    value["artifacts"] = list(dict.fromkeys(artifacts))
    ingest = value.get("stages", {}).get("ingest", {})
    value.setdefault("sampling", {})["colmap_input_frame_count"] = (
        int(ingest.get("metrics", {}).get("frame_count", 0))
        if ingest.get("status") == "succeeded" else 0
    )
    sampling = value.setdefault("sampling", {})
    if sampling.get("camera_timeline"):
        sampling["timeline"] = sampling["camera_timeline"]
    return value


def _qt():
    try:
        from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QObject, Property, QTimer, Qt, QUrl, Signal, Slot
        from PySide6.QtGui import QDesktopServices, QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtQuickControls2 import QQuickStyle
        from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineUrlRequestJob, QWebEngineUrlScheme, QWebEngineUrlSchemeHandler
        from PySide6.QtWebEngineQuick import QQuickWebEngineProfile, QtWebEngineQuick
    except ImportError as exc:  # keeps non-GUI callers free of Qt imports
        raise RuntimeError("Desktop GUI requires `uv sync --extra desktop`") from exc
    return locals()


def main() -> int:
    from .portable import doctor, import_offline, install, manifest_path, prepare_environment

    portable_data = prepare_environment()
    parser = argparse.ArgumentParser(description="Gaussian Factory P2 desktop GUI")
    default_state = portable_data if getattr(sys, "frozen", False) else Path.home() / ".gaussian-factory"
    parser.add_argument("--projects", type=Path, default=default_state / "projects")
    parser.add_argument("--artifacts", type=Path, default=default_state / "artifact-store")
    parser.add_argument("--acceptance-evidence", type=Path, help="capture a real rendered GUI after exercising viewer controls")
    parser.add_argument("--acceptance-delay-ms", type=int, default=12_000, help=argparse.SUPPRESS)
    parser.add_argument("--acceptance-import-video", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--acceptance-import-pro", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--acceptance-camera-timeline", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--doctor", action="store_true", help="check the portable runtime without starting the GUI")
    parser.add_argument("--runtime-list", action="store_true", help="list locked portable runtime assets")
    parser.add_argument("--runtime-install", action="append", default=[], metavar="ASSET_ID", help="download and verify a locked runtime asset")
    parser.add_argument("--runtime-install-all", action="store_true", help="download every runtime asset that has an approved URL")
    parser.add_argument("--runtime-import", type=Path, help="import a verified Full Offline runtime or locked asset directory")
    parser.add_argument("--portable-smoke-video", type=Path, help="commit one analyzed video import without starting reconstruction")
    parser.add_argument("--portable-smoke-output", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    operation_report = Path(sys.executable).resolve().parent / "runtime-operation-report.txt"
    if args.runtime_list or args.runtime_install or args.runtime_install_all or args.runtime_import:
        manifest = json.loads(manifest_path().read_text(encoding="utf-8"))
        lines: list[str] = []
        try:
            if args.runtime_list:
                for asset in manifest["assets"]:
                    mode = "download" if asset.get("url") else "offline import only"
                    lines.append(f"{asset['id']} {asset['version']} [{mode}]")
            selected = list(args.runtime_install)
            if args.runtime_install_all:
                selected.extend(asset["id"] for asset in manifest["assets"] if asset.get("url"))
            for asset_id in dict.fromkeys(selected):
                def progress(name: str, done: int, total: int) -> None:
                    current = lines + [f"Downloading {name}: {done}/{total} bytes"]
                    operation_report.write_text("\n".join(current) + "\n", encoding="utf-8")
                target = install(asset_id, progress)
                lines.append(f"Installed and verified: {asset_id} -> {target}")
            if args.runtime_import:
                imported = import_offline(args.runtime_import)
                if not imported:
                    raise RuntimeError("No manifest-locked runtime assets were found in the selected directory.")
                lines.extend(f"Imported and verified: {path}" for path in imported)
            remaining = doctor()
            lines.append("Runtime doctor: " + ("OK" if not remaining else f"{len(remaining)} issue(s) remain"))
            operation_report.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return 0
        except Exception as exc:
            lines.append(f"ERROR: {exc}")
            operation_report.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return 3
    if args.portable_smoke_video:
        output = (args.portable_smoke_output or (portable_data / "acceptance-smoke")).resolve()
        report_path = output / "portable-smoke-report.txt"
        session: VideoImportSession | None = None
        try:
            output.mkdir(parents=True, exist_ok=True)
            runtime = RuntimePaths.discover()
            session = VideoImportSession(
                args.portable_smoke_video.resolve(), runtime.ffmpeg, discover_ffprobe(runtime.ffmpeg),
            )
            requested = min(12, session.probe.total_frames)
            session.configure(
                "target_count", requested, 1.0, "seconds", 0,
                session.probe.total_frames - 1, "balanced",
            )
            analyzed = session.analyze()
            store = ProjectStore(output / "projects")
            controller = PipelineController(store, output / "artifacts", runtime=runtime)
            workspace = output / "workspaces" / f"video-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            project = controller.create_project("portable-import-smoke", workspace)
            committed = controller.commit_video_import(
                project.project_id, session.source, "balanced", analyzed,
            )
            lines = [
                "GaussianOS portable video import smoke: OK",
                f"project_id={committed.project_id}",
                f"status={committed.status}",
                f"input_kind={committed.input_kind}",
                f"input_path={committed.input_path}",
                f"analysis_status={committed.sampling.get('analysis_status')}",
                f"selected_frames={committed.sampling.get('selected_frame_count')}",
                f"timeline_frames={len(committed.sampling.get('timeline', []))}",
            ]
            report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return 0
        except Exception as exc:
            output.mkdir(parents=True, exist_ok=True)
            report_path.write_text(f"GaussianOS portable video import smoke: FAILED\n{exc}\n", encoding="utf-8")
            return 4
        finally:
            if session is not None:
                session.cancel()
    if args.doctor:
        messages = doctor()
        report = "GaussianOS runtime doctor: " + ("OK" if not messages else "\n- " + "\n- ".join(messages))
        print(report)
        if getattr(sys, "frozen", False):
            (Path(sys.executable).resolve().parent / "doctor-report.txt").write_text(report + "\n", encoding="utf-8")
        return 0 if not messages else 2
    qt = _qt()
    globals().update(qt)
    scheme = QWebEngineUrlScheme(b"gaussian")
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.HostAndPort)
    scheme.setDefaultPort(80)
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.SecureScheme
        | QWebEngineUrlScheme.Flag.LocalScheme
        | QWebEngineUrlScheme.Flag.LocalAccessAllowed
        | QWebEngineUrlScheme.Flag.CorsEnabled
    )
    QWebEngineUrlScheme.registerScheme(scheme)
    QtWebEngineQuick.initialize()
    QQuickStyle.setStyle("Fusion")
    app = QGuiApplication(sys.argv)
    store = ProjectStore(args.projects)
    controller = PipelineController(store, args.artifacts)
    try:
        controller.recover_interrupted_projects()
    except Exception:
        # The GUI still starts and surfaces a persistence error through its
        # normal control-plane actions instead of crashing during bootstrap.
        pass

    class ViewerSchemeHandler(QWebEngineUrlSchemeHandler):
        def __init__(self) -> None:
            super().__init__()
            self.scene: ViewerScene | None = None
            self._devices: set[QIODevice] = set()
            self.html = (Path(__file__).with_name("viewer_web") / "index.html").read_bytes()

        def set_scene(self, scene: ViewerScene) -> None:
            self.scene = scene

        def _reply_bytes(self, job: QWebEngineUrlRequestJob, mime: bytes, data: bytes) -> None:
            device = QBuffer(self)
            device.setData(QByteArray(data)); device.open(QIODevice.OpenModeFlag.ReadOnly)
            self._devices.add(device)
            job.destroyed.connect(lambda: (self._devices.discard(device), device.deleteLater()))
            job.reply(QByteArray(mime), device)

        def _reply_file(self, job: QWebEngineUrlRequestJob, path: Path, mime: bytes) -> None:
            from PySide6.QtCore import QFile
            device = QFile(str(path), self)
            if not device.open(QIODevice.OpenModeFlag.ReadOnly):
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound); return
            self._devices.add(device)
            job.destroyed.connect(lambda: (self._devices.discard(device), device.deleteLater()))
            job.reply(QByteArray(mime), device)

        def requestStarted(self, job: QWebEngineUrlRequestJob) -> None:
            path = job.requestUrl().path()
            if path in {"", "/", "/index.html"}:
                self._reply_bytes(job, b"text/html", self.html); return
            scene = self.scene
            if scene is None:
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound); return
            if path == "/meta.json":
                payload = json.dumps({
                    "artifact": scene.gaussian_path.name,
                    "gaussian_count": scene.gaussian_count,
                    "camera_positions": scene.camera_positions,
                    "cameras": scene.cameras,
                    "bounds_min": scene.bounds_min,
                    "bounds_max": scene.bounds_max,
                    "has_pointcloud": scene.pointcloud_path is not None,
                    "initial_camera_position": scene.initial_camera_position,
                    "initial_camera_forward": scene.initial_camera_forward,
                    "initial_camera_up": scene.initial_camera_up,
                    "initial_focus_distance": scene.initial_focus_distance,
                    "scene_root_transform": scene.scene_root_transform,
                    "canonical_world_up": scene.canonical_world_up,
                }, separators=(",", ":")).encode()
                self._reply_bytes(job, b"application/json", payload); return
            if path == "/scene.ply":
                self._reply_file(job, scene.gaussian_path, b"application/octet-stream"); return
            if path == "/points.ply" and scene.pointcloud_bytes is not None:
                self._reply_bytes(job, b"application/octet-stream", scene.pointcloud_bytes); return
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)

    viewer_handler = ViewerSchemeHandler()

    class Backend(QObject):
        changed = Signal()
        importChanged = Signal()
        viewerUrlChanged = Signal()
        viewerStatusChanged = Signal()
        event = Signal(str, str, object)
        acceptanceRequested = Signal()

        def __init__(self) -> None:
            super().__init__()
            self.projects: list[Project] = store.all()
            # Recent projects stay visible, but a normal launch starts at the
            # Welcome surface until the user explicitly opens one.
            self.selected = ""
            self.logs: list[str] = [f"Runtime doctor: {message}" for message in doctor()]
            self.viewer_url = "about:blank"
            self.viewer_status = "Select a completed project to load its Gaussian artifact"
            self.viewer_generation = 0
            self.persistence_failed: set[str] = set()
            self.acceptance_started = False
            self.sampling_analysis: set[str] = set()
            self.import_session: VideoImportSession | None = None
            self.import_state: dict[str, Any] = {}
            self.import_analysis_running = False
            self.import_generation = 0

        def _project(self) -> Project | None:
            try: return store.load(self.selected) if self.selected else None
            except FileNotFoundError: return None

        @Property(str, notify=changed)
        def projectsJson(self) -> str:
            values = [self._decorate(item) for item in self.projects]
            for item in values:
                if item["project_id"] in self.persistence_failed:
                    item["status"] = "failed"
            return json.dumps(values, ensure_ascii=False)

        @Property(str, notify=changed)
        def currentJson(self) -> str:
            current = self._project()
            value = self._decorate(current) if current else {}
            if value.get("project_id") in self.persistence_failed:
                value["status"] = "failed"
            return json.dumps(value, ensure_ascii=False)

        @Property(str, notify=changed)
        def logText(self) -> str:
            return "\n".join(self.logs[-400:])

        @Property(str, notify=viewerUrlChanged)
        def viewerUrl(self) -> str: return self.viewer_url

        @Property(str, notify=viewerStatusChanged)
        def viewerStatus(self) -> str: return self.viewer_status

        @Property(str, notify=importChanged)
        def importJson(self) -> str:
            return json.dumps(self.import_state, ensure_ascii=False)

        @Property(bool, constant=True)
        def acceptanceCameraTimeline(self) -> bool:
            return bool(args.acceptance_camera_timeline)

        @Slot(str)
        def beginVideoImport(self, source: str) -> None:
            self.import_generation += 1
            generation = self.import_generation
            if self.import_session is not None:
                self.import_session.cancel()
            self.import_session = None
            self.import_state = {"source": source, "status": "preflight", "sampling": {}}
            self.importChanged.emit()

            def preflight() -> None:
                try:
                    session = VideoImportSession(
                        source,
                        controller.runtime.ffmpeg,
                        discover_ffprobe(controller.runtime.ffmpeg),
                    )
                    self.event.emit("import_preflight_ready", "Video preflight completed", {"session": session, "generation": generation})
                except Exception as exc:
                    self.event.emit("import_preflight_failed", str(exc), {})

            threading.Thread(target=preflight, name="video-import-preflight", daemon=True).start()

        @Slot(str, int, float, str, int, int, str)
        def configureVideoImport(
            self, mode: str, requested: int, interval_value: float,
            interval_unit: str, in_frame: int, out_frame: int, profile: str,
        ) -> None:
            session = self.import_session
            if session is None:
                return
            try:
                sampling = session.configure(
                    mode, requested, interval_value, interval_unit,
                    in_frame, out_frame, profile,
                )
            except Exception as exc:
                self.import_state["error"] = str(exc)
                self.importChanged.emit()
                return
            self.import_state.update({"profile": profile, "sampling": sampling, "status": "analyzing"})
            self.import_state.pop("error", None)
            self.importChanged.emit()
            if self.import_analysis_running:
                return
            self.import_analysis_running = True

            def analyze_latest() -> None:
                while self.import_session is session and not session.cancelled:
                    try:
                        analyzed = session.analyze()
                    except InterruptedError:
                        continue
                    except Exception as exc:
                        self.event.emit("import_analysis_failed", str(exc), {})
                        return
                    self.event.emit("import_analysis_ready", "Video analysis completed", {"sampling": analyzed})
                    return

            threading.Thread(target=analyze_latest, name="video-import-analysis", daemon=True).start()

        @Slot()
        def cancelVideoImport(self) -> None:
            self.import_generation += 1
            if self.import_session is not None:
                self.import_session.cancel()
            self.import_session = None
            self.import_state = {}
            self.import_analysis_running = False
            self.importChanged.emit()

        @Slot()
        def generateVideoImport(self) -> None:
            session = self.import_session
            if session is None or session.sampling.get("analysis_status") != "complete":
                self.import_state["error"] = "Generate waits for the current analysis to complete"
                self.importChanged.emit()
                return
            project = self._project()
            if project is None:
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                root = args.projects.resolve().parent / "workspaces" / f"{session.source.stem}-{stamp}"
                project = controller.create_project(session.source.stem, root)
            try:
                committed = controller.commit_video_import(
                    project.project_id, session.source,
                    str(self.import_state.get("profile", session.profile)), session.snapshot(),
                )
            except Exception as exc:
                self.import_state["error"] = str(exc)
                self.importChanged.emit()
                return
            self.selected = committed.project_id
            session.cancel()
            self.import_session = None
            self.import_state = {}
            self.import_analysis_running = False
            self.importChanged.emit()
            self._refresh()
            self.start()

        @staticmethod
        def _decorate(project: Project) -> dict[str, Any]:
            return project_view(project)

        def _refresh(self) -> None:
            self.projects = store.all()
            self.changed.emit()

        @Slot(str, str)
        def createProject(self, name: str, root: str) -> None:
            if not name.strip() or not root.strip():
                self.logs.append("Project name and location are required")
            else:
                project = controller.create_project(name.strip(), root)
                self.selected = project.project_id
                self.logs.append(f"Created project {project.name}")
            self._refresh()

        @Slot(str)
        def selectProject(self, project_id: str) -> None:
            self.selected = project_id
            self._refresh()
            self.loadViewer()

        @Slot(str)
        def importInput(self, source: str) -> None:
            project = self._project()
            if project is None: return
            project_id = project.project_id
            self.logs.append(f"Probing input: {source}")
            self.changed.emit()
            def import_source() -> None:
                try:
                    controller.import_input(project_id, source)
                    self.event.emit("input_ready", f"Imported and probed {source}", {"project_id": project_id})
                except Exception as exc:
                    self.event.emit("input_failed", str(exc), {"project_id": project_id})
            threading.Thread(target=import_source, name=f"input-probe-{project_id[:8]}", daemon=True).start()

        @Slot(str)
        def setProfile(self, profile: str) -> None:
            project = self._project()
            if project is not None and profile in {"preview", "balanced", "quality"}:
                try:
                    controller.set_profile(project.project_id, profile)
                except Exception as exc:
                    self.logs.append(f"Profile update failed: {exc}")
            self._refresh()

        @Slot(str, int, float, str, int, int)
        def setSampling(self, mode: str, requested: int, interval_value: float, interval_unit: str, in_frame: int, out_frame: int) -> None:
            project = self._project()
            if project is None: return
            try:
                controller.set_sampling_config(
                    project.project_id, mode, requested, interval_value, interval_unit,
                    in_frame, out_frame,
                )
                self.logs.append(f"Sampling set to {mode}; configuration is Custom")
            except Exception as exc:
                self.logs.append(f"Sampling update failed: {exc}")
            self._refresh()

        @Slot()
        def analyzeSampling(self) -> None:
            project = self._project()
            if project is None or project.input_kind != "video" or project.project_id in self.sampling_analysis:
                return
            project_id = project.project_id
            self.sampling_analysis.add(project_id)
            self.logs.append("Frame analysis queued")
            self.changed.emit()
            def analyze() -> None:
                try:
                    analyzed = controller.analyze_sampling(project_id)
                    self.event.emit("sampling_ready", "Frame analysis completed", {"project_id": project_id, "selected": analyzed.sampling.get("selected_frame_count", 0)})
                except Exception as exc:
                    self.event.emit("sampling_failed", str(exc), {"project_id": project_id})
            threading.Thread(target=analyze, name=f"sampling-{project_id[:8]}", daemon=True).start()

        @Slot()
        def start(self) -> None:
            project = self._project()
            if project is None or project.status == "running": return
            self.persistence_failed.discard(project.project_id)
            def receive(kind: str, message: str, payload: dict[str, Any]) -> None:
                self.event.emit(kind, message, payload)
            def run() -> None:
                controller.run(project.project_id, receive)
                self.event.emit("complete", "Pipeline finished", {"project_id": project.project_id})
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
                bundle, gaussian = state.artifact_paths[:2]
                pointcloud = next((p for p in project.stages.get("export", type(state)()).artifact_paths if p.endswith(".pointcloud.ply")), None)
                self.viewer_status = "Loading and validating Gaussian artifact…"
                self.viewerStatusChanged.emit()
                def load() -> None:
                    try:
                        timeline = project.sampling.get("camera_timeline", [])
                        if project.sampling.get("camera_mapping_stale"):
                            timeline = []
                        scene = load_viewer_scene(bundle, gaussian, pointcloud, timeline)
                        self.event.emit("viewer_ready", "Viewer artifact validated", {"scene": scene})
                    except Exception as exc:
                        self.event.emit("viewer_failed", str(exc), {})
                threading.Thread(target=load, name="gaussian-viewer-load", daemon=True).start()
            else:
                self.viewer_status = "Run the pipeline to create a viewable Gaussian artifact"
                self.viewerStatusChanged.emit()

        @Slot()
        def openExportFolder(self) -> None:
            project = self._project()
            if project is not None:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(project.root) / "exports")))

        @Slot(str)
        def viewerPageTitle(self, title: str) -> None:
            if title.startswith("ready|"):
                self.logs.append(f"Viewer GPU page ready: {title.partition('|')[2]} Gaussians")
                if args.acceptance_evidence and not self.acceptance_started:
                    self.acceptance_started = True
                    QTimer.singleShot(700, self.acceptanceRequested.emit)
            elif title.startswith("motion|"):
                fps = title.partition("|")[2]
                self.logs.append(f"Viewer active-camera benchmark: {fps} FPS")
            elif title.startswith("error|"):
                next_status = f"Viewer render failed: {title.partition('|')[2]}"
                if self.viewer_status != next_status:
                    self.viewer_status = next_status
                    self.logs.append(self.viewer_status)
                    self.viewerStatusChanged.emit()
                    self.changed.emit()

        @Slot(str)
        def viewerAcceptanceResult(self, result: str) -> None:
            self.logs.append(f"Viewer interaction acceptance: {result}")
            self.changed.emit()
            def capture() -> None:
                self.changed.emit()
                def save() -> None:
                    destination = args.acceptance_evidence.resolve()
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    root = engine.rootObjects()[0]
                    if not root.grabWindow().save(str(destination)):
                        self.logs.append(f"Screenshot save failed: {destination}")
                    QTimer.singleShot(300, app.quit)
                QTimer.singleShot(200, save)
            # Large production scenes may need several frames for the first
            # depth sort and GPU upload before a meaningful capture exists.
            QTimer.singleShot(6_000, capture)

        @Slot(str, str, object)
        def handleEvent(self, kind: str, message: str, payload: object) -> None:
            """Queued Qt slot: all QML-facing updates remain on the GUI thread."""
            self.logs.append(f"{kind}: {message}")
            if kind == "persistence_failed" and isinstance(payload, dict):
                project_id = payload.get("project_id")
                if isinstance(project_id, str): self.persistence_failed.add(project_id)
            elif kind == "viewer_ready" and isinstance(payload, dict) and isinstance(payload.get("scene"), ViewerScene):
                scene = payload["scene"]
                viewer_handler.set_scene(scene)
                self.viewer_generation += 1
                self.viewer_url = f"gaussian://viewer/index.html?v={self.viewer_generation}"
                self.viewer_status = f"Loaded {scene.gaussian_count:,} Gaussians · SH degree {scene.sh_degree}"
                self.viewerUrlChanged.emit()
                self.viewerStatusChanged.emit()
            elif kind == "viewer_failed":
                self.viewer_url = "about:blank"
                self.viewer_status = f"Viewer load failed: {message}"
                self.viewerUrlChanged.emit()
                self.viewerStatusChanged.emit()
            elif kind in {"sampling_ready", "sampling_failed"} and isinstance(payload, dict):
                project_id = payload.get("project_id")
                if isinstance(project_id, str): self.sampling_analysis.discard(project_id)
            elif kind == "import_preflight_ready" and isinstance(payload, dict):
                session = payload.get("session")
                if payload.get("generation") != self.import_generation:
                    if isinstance(session, VideoImportSession):
                        session.cancel()
                elif isinstance(session, VideoImportSession):
                    self.import_session = session
                    self.import_state.update({
                        "source": str(session.source), "status": "ready",
                        "profile": session.profile, "sampling": session.snapshot(),
                    })
                    self.importChanged.emit()
            elif kind == "import_preflight_failed":
                self.import_state.update({"status": "failed", "error": message})
                self.importChanged.emit()
            elif kind == "import_analysis_ready" and isinstance(payload, dict):
                self.import_analysis_running = False
                self.import_state.update({"status": "ready", "sampling": payload.get("sampling", {})})
                self.importChanged.emit()
            elif kind == "import_analysis_failed":
                self.import_analysis_running = False
                self.import_state.update({"status": "failed", "error": message})
                self.importChanged.emit()
            self._refresh()

    QQuickWebEngineProfile.defaultProfile().installUrlSchemeHandler(b"gaussian", viewer_handler)
    backend = Backend()
    # Pipeline threads emit this signal; force queued delivery to Backend's Qt
    # thread so no Worker ever updates a QML-bound property directly.
    backend.event.connect(backend.handleEvent, Qt.QueuedConnection)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    qml = Path(__file__).with_name("qml") / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml)))
    if not engine.rootObjects(): return 2
    # Explicit acceptance capture is a diagnostic mode rather than a normal
    # launch, so it may open the newest project to exercise the real Viewer.
    if args.acceptance_evidence and backend.projects and not args.acceptance_import_video:
        backend.selected = backend.projects[0].project_id
        backend.changed.emit()
        backend.loadViewer()
    if args.acceptance_import_video:
        root = engine.rootObjects()[0]
        method = root.openProAcceptance if args.acceptance_import_pro else root.beginVideo
        QTimer.singleShot(250, lambda: method(str(args.acceptance_import_video.resolve())))
    if args.acceptance_evidence:
        def acceptance_deadline() -> None:
            destination = args.acceptance_evidence.resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            root = engine.rootObjects()[0]
            root.grabWindow().save(str(destination))
            app.quit()
        QTimer.singleShot(max(1_000, args.acceptance_delay_ms), acceptance_deadline)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
