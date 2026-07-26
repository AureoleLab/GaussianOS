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
from .directory_opening import DirectoryOpenResult, ProjectDirectoryService
from .project_entries import project_display_path
from .project_paths import ProjectPaths
from .project_store import (
    Project,
    ProjectDeleteError,
    ProjectStore,
    ProjectStoreError,
)
from .project_session import AsyncIdentity, ProjectSession
from .viewer import ViewerScene, load_viewer_scene
from .sampling import discover_ffprobe
from .ui_settings import UI_CHOICES, UiSettingsStore, resolve_ui
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
    value["legacy_shared_workspace"] = project.workspace_kind == "legacy_shared"
    value["legacy_workspace"] = project.workspace_kind != "isolated"
    paths = ProjectPaths.from_project(project)
    value["workspace_path"] = str(paths.workspace)
    value["library_path"] = str(paths.library_root) if project.library_root else ""
    value["display_path"] = str(project_display_path(project))
    value["internal_workspace"] = str(paths.workspace)
    if project.run_id:
        run_root = paths.run(project.run_id).root
        value["active_run_path"] = str(run_root)
        value["active_run_status"] = "available" if run_root.is_dir() else "stale"
    else:
        value["active_run_path"] = ""
        value["active_run_status"] = "none"
    return value


def _configure_application_identity(application: Any) -> None:
    """Set identifiers before construction so QML Settings can persist."""

    application.setOrganizationName("AureoleLab")
    application.setOrganizationDomain("gaussianos.com")
    application.setApplicationName("GaussianOS")


def _qt():
    try:
        from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QObject, Property, QTimer, Qt, QUrl, Signal, Slot
        from PySide6.QtGui import QDesktopServices, QFont, QFontDatabase, QGuiApplication
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
    parser.add_argument(
        "--ui",
        choices=UI_CHOICES,
        help="select the Modern or Classic desktop shell for this launch",
    )
    parser.add_argument(
        "--safe-ui",
        action="store_true",
        help="force the Classic compatibility shell for this launch",
    )
    parser.add_argument("--acceptance-evidence", type=Path, help="capture a real rendered GUI after exercising viewer controls")
    parser.add_argument("--acceptance-delay-ms", type=int, default=12_000, help=argparse.SUPPRESS)
    parser.add_argument("--acceptance-import-video", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--acceptance-import-pro", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--acceptance-camera-timeline", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--acceptance-theme",
        choices=("light", "dark", "system"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--acceptance-density",
        choices=("compact", "standard", "comfortable"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--acceptance-weight",
        choices=("light", "balanced", "strong"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--acceptance-page",
        choices=("workspace", "library"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--acceptance-dialog",
        choices=("settings", "new-project"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--acceptance-force-modern-failure",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--acceptance-ui-settings",
        type=Path,
        help=argparse.SUPPRESS,
    )
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
    ui_settings = UiSettingsStore(
        args.acceptance_ui_settings or default_state / "ui-settings.json"
    )
    ui_selection = resolve_ui(
        args.ui,
        safe_ui=args.safe_ui,
        persisted=ui_settings.preferred_ui,
    )
    ui_log_path = default_state / "logs" / "desktop-ui.log"

    def record_ui(message: str) -> None:
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        line = f"{stamp} {message}"
        print(f"[GaussianOS] {message}", file=sys.stderr)
        try:
            ui_log_path.parent.mkdir(parents=True, exist_ok=True)
            with ui_log_path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(line + "\n")
        except OSError:
            # A read-only portable location must not prevent Classic fallback.
            pass

    record_ui(
        f"UI selection resolved to {ui_selection.name} ({ui_selection.source})"
    )
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
    _configure_application_identity(QGuiApplication)
    app = QGuiApplication(sys.argv)
    font_names = (
        "Montserrat-Regular.ttf",
        "Montserrat-Medium.ttf",
        "Montserrat-SemiBold.ttf",
        "Montserrat-Bold.ttf",
    )
    font_roots = (
        Path(sys.executable).resolve().parent / "fonts",
        Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts",
        Path("C:/Windows/Fonts"),
    )
    for root in font_roots:
        for name in font_names:
            candidate = root / name
            if candidate.exists():
                QFontDatabase.addApplicationFont(str(candidate))
    app.setFont(QFont("Montserrat", 10))
    store = ProjectStore(args.projects)
    controller = PipelineController(store, args.artifacts)
    directory_service = ProjectDirectoryService(
        store,
        lambda path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))),
    )
    try:
        controller.recover_interrupted_projects()
    except Exception:
        # The GUI still starts and surfaces a persistence error through its
        # normal control-plane actions instead of crashing during bootstrap.
        pass
    try:
        lifecycle_recovery = controller.recover_lifecycle_residuals()
    except Exception as exc:
        lifecycle_recovery = [f"Lifecycle recovery warning: {exc}"]
    try:
        project_entry_recovery = directory_service.entries.reconcile()
    except Exception as exc:
        project_entry_recovery = [f"Project folder entry recovery warning: {exc}"]
    runtime_messages = doctor()

    class ViewerSchemeHandler(QWebEngineUrlSchemeHandler):
        def __init__(self) -> None:
            super().__init__()
            self.scene: ViewerScene | None = None
            self._devices: set[QIODevice] = set()
            self.html = (Path(__file__).with_name("viewer_web") / "index.html").read_bytes()

        def set_scene(self, scene: ViewerScene) -> None:
            self.scene = scene

        def clear_scene(self) -> None:
            self.scene = None

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
        settingsChanged = Signal()
        activeUiChanged = Signal()
        event = Signal(str, str, object)
        acceptanceRequested = Signal()

        def __init__(self) -> None:
            super().__init__()
            self.projects: list[Project] = store.all()
            # Recent projects stay visible, but a normal launch starts at the
            # Welcome surface until the user explicitly opens one.
            self.session = ProjectSession()
            self.logs: list[str] = [
                f"UI shell: {ui_selection.name} ({ui_selection.source})",
                *[f"Runtime doctor: {message}" for message in runtime_messages],
                *lifecycle_recovery,
                *project_entry_recovery,
            ]
            self.active_ui = ui_selection.name
            self.viewer_url = "about:blank"
            self.viewer_status = "Select a completed project to load its Gaussian artifact"
            self.viewer_revision = 0
            self.persistence_failed: set[str] = set()
            self.acceptance_started = False
            self.sampling_analysis: set[str] = set()
            self.import_session: VideoImportSession | None = None
            self.import_state: dict[str, Any] = {}
            self.import_analysis_running = False
            self.import_generation = 0
            self.import_target_project_id = ""
            self.import_target_generation = 0

        def _project(self) -> Project | None:
            try:
                return store.load(self.session.project_id) if self.session.project_id else None
            except (FileNotFoundError, ProjectStoreError):
                return None

        def _identity(
            self,
            project: Project,
            stage: str,
            *,
            run_id: str | None = None,
            generation: int | None = None,
        ) -> dict[str, Any]:
            return AsyncIdentity(
                project_id=project.project_id,
                run_id=run_id,
                generation=self.session.generation if generation is None else generation,
                stage=stage,
            ).payload()

        def _clear_project_presentation(self, status: str) -> None:
            viewer_handler.clear_scene()
            self.viewer_url = "about:blank"
            self.viewer_status = status
            self.viewerUrlChanged.emit()
            self.viewerStatusChanged.emit()

        def _activate_project(self, project_id: str, *, load_viewer: bool = True) -> None:
            project = store.load(project_id) if project_id else None
            if project is not None and project.archived:
                raise ProjectStoreError(
                    "Archived projects must be restored before they can be opened."
                )
            self.session.switch(project_id)
            self._clear_project_presentation(
                "Validating project artifacts…"
                if project is not None
                else "Select a completed project to load its Gaussian artifact"
            )
            self._refresh()
            if project is not None and load_viewer:
                self.loadViewer()

        @Property(str, notify=changed)
        def projectsJson(self) -> str:
            values = [self._decorate(item) for item in self.projects]
            for item in values:
                if item["project_id"] in self.persistence_failed:
                    item["status"] = "failed"
            return json.dumps(values, ensure_ascii=False)

        @Property(str, notify=changed)
        def trashJson(self) -> str:
            return json.dumps(
                [
                    {
                        "project_id": entry.project_id,
                        "name": entry.name,
                        "deleted_at": entry.deleted_at,
                        "estimated_bytes": entry.estimated_bytes,
                        "legacy_workspace_preserved": entry.legacy_workspace_preserved,
                    }
                    for entry in store.trash_entries()
                ],
                ensure_ascii=False,
            )

        @Property(str, notify=changed)
        def currentJson(self) -> str:
            current = self._project()
            value = self._decorate(current) if current else {}
            value["ui_generation"] = self.session.generation
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

        @Property(str, notify=settingsChanged)
        def preferredUi(self) -> str:
            return ui_settings.preferred_ui or "modern"

        @Property(str, notify=activeUiChanged)
        def activeUi(self) -> str:
            return self.active_ui

        @Property(str, notify=settingsChanged)
        def settingsJson(self) -> str:
            return json.dumps(
                {
                    "preferred_ui": self.preferredUi,
                    "active_ui": self.active_ui,
                    "restart_required": self.preferredUi != self.active_ui,
                    "path": str(ui_settings.path),
                },
                ensure_ascii=False,
            )

        @Property(str, constant=True)
        def runtimeJson(self) -> str:
            return json.dumps(
                {
                    "status": "ok" if not runtime_messages else "attention",
                    "messages": runtime_messages,
                },
                ensure_ascii=False,
            )

        @Property(str, notify=importChanged)
        def importJson(self) -> str:
            return json.dumps(self.import_state, ensure_ascii=False)

        def _set_active_ui(self, value: str) -> None:
            if self.active_ui == value:
                return
            self.active_ui = value
            self.logs.append(f"UI shell changed during startup fallback: {value}")
            self.activeUiChanged.emit()
            self.settingsChanged.emit()
            self.changed.emit()

        @Slot(str)
        def setPreferredUi(self, value: str) -> None:
            try:
                ui_settings.set_preferred_ui(value)
                self.logs.append(
                    f"Preferred UI set to {value}; restart required to apply"
                )
            except (OSError, ValueError) as exc:
                self.logs.append(f"UI preference update failed: {exc}")
            self.settingsChanged.emit()
            self.changed.emit()

        @Property(bool, constant=True)
        def acceptanceCameraTimeline(self) -> bool:
            return bool(args.acceptance_camera_timeline)

        @Slot(str)
        def beginVideoImport(self, source: str) -> None:
            self.import_generation += 1
            generation = self.import_generation
            self.import_target_project_id = self.session.project_id
            self.import_target_generation = self.session.generation
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
                    self.event.emit("import_preflight_failed", str(exc), {"generation": generation})

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
            generation = self.import_generation

            def analyze_latest() -> None:
                while self.import_session is session and not session.cancelled:
                    try:
                        analyzed = session.analyze()
                    except InterruptedError:
                        continue
                    except Exception as exc:
                        self.event.emit("import_analysis_failed", str(exc), {"generation": generation})
                        return
                    self.event.emit(
                        "import_analysis_ready",
                        "Video analysis completed",
                        {"sampling": analyzed, "generation": generation},
                    )
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
            self.import_target_project_id = ""
            self.importChanged.emit()

        @Slot()
        def generateVideoImport(self) -> None:
            session = self.import_session
            if session is None or session.sampling.get("analysis_status") != "complete":
                self.import_state["error"] = "Generate waits for the current analysis to complete"
                self.importChanged.emit()
                return
            if (
                self.import_target_project_id
                and (
                    self.session.project_id != self.import_target_project_id
                    or self.session.generation != self.import_target_generation
                )
            ):
                self.import_state["error"] = (
                    "The active project changed during import; reopen the import for the current project."
                )
                self.importChanged.emit()
                return
            project = (
                store.load(self.import_target_project_id)
                if self.import_target_project_id
                else None
            )
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
            session.cancel()
            self.import_session = None
            self.import_state = {}
            self.import_analysis_running = False
            self.import_target_project_id = ""
            self.importChanged.emit()
            self._activate_project(committed.project_id, load_viewer=False)
            self.start()

        @staticmethod
        def _decorate(project: Project) -> dict[str, Any]:
            return project_view(project)

        def _refresh(self) -> None:
            self.projects = store.all()
            self.changed.emit()

        def _report_directory_result(self, result: DirectoryOpenResult) -> None:
            if result.status == "duplicate":
                return
            self.logs.append(result.message)
            self.changed.emit()

        def _ensure_project_entry(self, project: Project) -> None:
            if project.workspace_kind != "isolated":
                return
            try:
                entry = directory_service.entries.ensure(project)
                self.logs.append(f"Project folder ready: {entry}")
            except Exception as exc:
                self.logs.append(f"Project folder entry warning: {exc}")

        @Slot(str, str)
        def createProject(self, name: str, root: str) -> None:
            if not name.strip() or not root.strip():
                self.logs.append("Project name and location are required")
            else:
                project = controller.create_project(name.strip(), root)
                self._ensure_project_entry(project)
                self.logs.append(f"Created project {project.name}")
                self._activate_project(project.project_id)
                return
            self._refresh()

        @Slot(str)
        def selectProject(self, project_id: str) -> None:
            try:
                self._activate_project(project_id)
            except Exception as exc:
                self.logs.append(f"Project switch failed: {exc}")
                self.changed.emit()

        @Slot(str)
        def importInput(self, source: str) -> None:
            project = self._project()
            if project is None: return
            project_id = project.project_id
            generation = self.session.generation
            identity = self._identity(project, "ingest", generation=generation)
            self.logs.append(f"Probing input: {source}")
            self.changed.emit()
            def import_source() -> None:
                try:
                    controller.import_input(project_id, source)
                    self.event.emit(
                        "input_ready",
                        f"Imported and probed {source}",
                        identity,
                    )
                except Exception as exc:
                    self.event.emit("input_failed", str(exc), identity)
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
            generation = self.session.generation
            identity = self._identity(project, "timeline", generation=generation)
            self.sampling_analysis.add(project_id)
            self.logs.append("Frame analysis queued")
            self.changed.emit()
            def analyze() -> None:
                try:
                    analyzed = controller.analyze_sampling(project_id)
                    self.event.emit(
                        "sampling_ready",
                        "Frame analysis completed",
                        {
                            **identity,
                            "selected": analyzed.sampling.get("selected_frame_count", 0),
                        },
                    )
                except Exception as exc:
                    self.event.emit("sampling_failed", str(exc), identity)
            threading.Thread(target=analyze, name=f"sampling-{project_id[:8]}", daemon=True).start()

        @Slot()
        def start(self) -> None:
            project = self._project()
            if project is None or project.status == "running" or project.archived:
                return
            self.persistence_failed.discard(project.project_id)
            project_id = project.project_id
            generation = self.session.switch(project_id)
            run_id = controller.new_run_id(project_id)
            self.session.begin_run(project_id, run_id)
            self._clear_project_presentation("Pipeline is preparing a new project run…")
            def receive(kind: str, message: str, payload: dict[str, Any]) -> None:
                self.event.emit(kind, message, payload)
            def run() -> None:
                identity = AsyncIdentity(project_id, run_id, generation, "pipeline").payload()
                try:
                    completed = controller.run(
                        project_id,
                        receive,
                        run_id=run_id,
                        generation=generation,
                    )
                    self.event.emit(
                        "complete",
                        "Pipeline finished",
                        {**identity, "status": completed.status},
                    )
                except Exception as exc:
                    self.event.emit("run_failed", str(exc), identity)
            threading.Thread(target=run, name=f"gaussian-run-{project_id[:8]}", daemon=True).start()
            self.logs.append("Pipeline queued")
            self._refresh()

        @Slot()
        def cancel(self) -> None:
            if self.session.project_id:
                self.session.cancel_run(self.session.project_id)
                controller.cancel(self.session.project_id)
            self.logs.append("Cancellation requested")
            self.changed.emit()

        @Slot()
        def loadViewer(self) -> None:
            project = self._project()
            if project is None or project.archived:
                self._clear_project_presentation(
                    "Select a completed project to load its Gaussian artifact"
                )
                return
            generation = self.session.generation
            project_id = project.project_id
            run_id = project.run_id
            self._clear_project_presentation(
                "Loading and validating Gaussian artifact…"
            )
            state = project.stages.get("validate")
            export_state = project.stages.get("export")
            if (
                project.status == "succeeded"
                and state
                and state.status == "succeeded"
                and export_state
                and export_state.status == "succeeded"
                and len(state.artifact_paths) >= 2
            ):
                bundle, gaussian = state.artifact_paths[:2]
                pointcloud = next(
                    (
                        path
                        for path in export_state.artifact_paths
                        if path.endswith(".pointcloud.ply")
                    ),
                    None,
                )
                timeline = project.sampling.get("camera_timeline", [])
                try:
                    paths = store.paths(project)
                    if project.workspace_kind == "isolated":
                        receipt = json.loads(
                            paths.viewer_manifest.read_text(encoding="utf-8")
                        )
                        if (
                            receipt.get("schema_version")
                            != "gaussianos-viewer-scene/v1"
                            or receipt.get("project_id") != project_id
                            or receipt.get("run_id") != run_id
                            or receipt.get("committed") is not True
                            or receipt.get("bundle") != bundle
                            or receipt.get("gaussian") != gaussian
                        ):
                            raise ValueError(
                                "viewer receipt does not match the active project run"
                            )
                        for candidate in (bundle, gaussian, receipt.get("pointcloud")):
                            if candidate and not paths.contains(candidate):
                                raise ValueError(
                                    "viewer artifact is outside the owning project workspace"
                                )
                        pointcloud = receipt.get("pointcloud")
                        if not run_id:
                            raise ValueError("isolated viewer artifact has no run identity")
                        timeline_receipt = json.loads(
                            paths.run(run_id).timeline_manifest.read_text(
                                encoding="utf-8"
                            )
                        )
                        if (
                            timeline_receipt.get("project_id") != project_id
                            or timeline_receipt.get("run_id") != run_id
                            or timeline_receipt.get("stage") != "timeline"
                        ):
                            raise ValueError(
                                "camera timeline does not belong to the active project run"
                            )
                        timeline = timeline_receipt.get("records", [])
                except Exception as exc:
                    self.viewer_status = f"Viewer ownership validation failed: {exc}"
                    self.viewerStatusChanged.emit()
                    return

                def load() -> None:
                    try:
                        selected_timeline = (
                            []
                            if project.sampling.get("camera_mapping_stale")
                            else timeline
                        )
                        scene = load_viewer_scene(
                            bundle,
                            gaussian,
                            pointcloud,
                            selected_timeline,
                            project_id=project_id,
                            run_id=run_id,
                            generation=generation,
                        )
                        self.event.emit(
                            "viewer_ready",
                            "Viewer artifact validated",
                            {
                                **AsyncIdentity(
                                    project_id, run_id, generation, "viewer"
                                ).payload(),
                                "scene": scene,
                            },
                        )
                    except Exception as exc:
                        self.event.emit(
                            "viewer_failed",
                            str(exc),
                            AsyncIdentity(
                                project_id, run_id, generation, "viewer"
                            ).payload(),
                        )
                threading.Thread(
                    target=load,
                    name=f"gaussian-viewer-load-{project_id[:8]}",
                    daemon=True,
                ).start()
            else:
                self.viewer_status = "Run the pipeline to create a viewable Gaussian artifact"
                self.viewerStatusChanged.emit()

        @Slot(str)
        def openProjectDirectory(self, project_id: str) -> None:
            self._report_directory_result(
                directory_service.open(project_id, "workspace")
            )

        @Slot(str)
        def openLibraryDirectory(self, project_id: str) -> None:
            self._report_directory_result(
                directory_service.open(project_id, "library")
            )

        @Slot(str, str)
        def openRunDirectory(self, project_id: str, run_id: str) -> None:
            self._report_directory_result(
                directory_service.open(project_id, "run", run_id or None)
            )

        @Slot(str, str)
        def openInputsDirectory(self, project_id: str, run_id: str) -> None:
            self._report_directory_result(
                directory_service.open(project_id, "inputs", run_id or None)
            )

        @Slot(str, str)
        def openArtifactsDirectory(self, project_id: str, run_id: str) -> None:
            self._report_directory_result(
                directory_service.open(project_id, "artifacts", run_id or None)
            )

        @Slot(str, str)
        def openExportsDirectory(self, project_id: str, run_id: str) -> None:
            self._report_directory_result(
                directory_service.open(project_id, "exports", run_id or None)
            )

        @Slot(str)
        def deleteProject(self, project_id: str) -> None:
            entry_paths: list[Path] = []
            try:
                target = store.load(project_id)
                if target.status == "running":
                    raise ProjectDeleteError(
                        "Running projects cannot be deleted; cancel and wait first."
                    )
                entry_paths = directory_service.entries.entries_for(target)
                if entry_paths:
                    directory_service.entries.remove_captured(target, entry_paths)
                try:
                    deleted = store.delete(project_id)
                except Exception:
                    if entry_paths:
                        self._ensure_project_entry(target)
                    raise
            except Exception as exc:
                self.logs.append(f"Project delete blocked: {exc}")
                self._refresh()
                return
            self.logs.append(
                f"Moved project {target.name} to GaussianOS trash"
                + (
                    "; legacy workspace files were preserved"
                    if deleted.legacy_workspace_preserved
                    else ""
                )
            )
            self.persistence_failed.discard(project_id)
            self.sampling_analysis.discard(project_id)
            if self.session.remove_project(project_id):
                self._clear_project_presentation(
                    "Select a completed project to load its Gaussian artifact"
                )
            self._refresh()

        @Slot(str, str)
        def renameProject(self, project_id: str, name: str) -> None:
            try:
                renamed = store.rename(project_id, name)
                self._ensure_project_entry(renamed)
                self.logs.append(f"Renamed project to {renamed.name}")
            except Exception as exc:
                self.logs.append(f"Project rename blocked: {exc}")
            self._refresh()

        @Slot(str, str, str)
        def duplicateProject(self, project_id: str, name: str, mode: str) -> None:
            generation = self.session.generation
            self.logs.append(f"Project copy queued ({mode})")
            self.changed.emit()
            def duplicate() -> None:
                try:
                    copied = store.duplicate(project_id, name, mode=mode)
                    self.event.emit(
                        "lifecycle_duplicate_ready",
                        f"Duplicated project as {copied.name} ({mode})",
                        {
                            "source_project_id": project_id,
                            "generation": generation,
                            "project_id": copied.project_id,
                            "mode": mode,
                        },
                    )
                except Exception as exc:
                    self.event.emit(
                        "lifecycle_failed",
                        f"Project duplicate blocked: {exc}",
                        {
                            "source_project_id": project_id,
                            "generation": generation,
                        },
                    )
            threading.Thread(
                target=duplicate,
                name=f"project-copy-{project_id[:8]}",
                daemon=True,
            ).start()

        @Slot(str, bool)
        def setProjectArchived(self, project_id: str, archived: bool) -> None:
            try:
                project = store.set_archived(project_id, archived)
                self.logs.append(
                    f"{'Archived' if archived else 'Restored'} project {project.name}"
                )
                if archived and self.session.remove_project(project_id):
                    self._clear_project_presentation(
                        "Select a completed project to load its Gaussian artifact"
                    )
            except Exception as exc:
                self.logs.append(f"Project archive operation blocked: {exc}")
            self._refresh()

        @Slot(str)
        def restoreProject(self, project_id: str) -> None:
            try:
                restored = store.restore(project_id)
                self._ensure_project_entry(restored)
                self.logs.append(f"Restored project {restored.name} from trash")
            except Exception as exc:
                self.logs.append(f"Project restore blocked: {exc}")
            self._refresh()

        @Slot(str)
        def purgeProject(self, project_id: str) -> None:
            def purge() -> None:
                try:
                    released = store.purge(project_id)
                    self.event.emit(
                        "lifecycle_refresh",
                        f"Permanently deleted project; released approximately {released} bytes",
                        {},
                    )
                except Exception as exc:
                    self.event.emit(
                        "lifecycle_failed",
                        f"Permanent delete blocked: {exc}",
                        {},
                    )
            threading.Thread(
                target=purge,
                name=f"project-purge-{project_id[:8]}",
                daemon=True,
            ).start()

        @Slot(str, str)
        def cleanupProject(self, project_id: str, target: str) -> None:
            generation = self.session.generation
            def cleanup() -> None:
                try:
                    cleaned = controller.cleanup_project(project_id, target)
                    self.event.emit(
                        "lifecycle_cleanup_ready",
                        f"Cleared {target} outputs for {cleaned.name}",
                        {
                            "project_id": project_id,
                            "generation": generation,
                        },
                    )
                except Exception as exc:
                    self.event.emit(
                        "lifecycle_failed",
                        f"Project cleanup blocked: {exc}",
                        {
                            "project_id": project_id,
                            "generation": generation,
                        },
                    )
            threading.Thread(
                target=cleanup,
                name=f"project-cleanup-{project_id[:8]}",
                daemon=True,
            ).start()

        @Slot(str)
        def viewerPageTitle(self, title: str) -> None:
            scene = viewer_handler.scene
            if (
                scene is None
                or scene.project_id != self.session.project_id
                or scene.generation != self.session.generation
            ):
                return
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
            data = payload if isinstance(payload, dict) else {}

            if kind.startswith("lifecycle_"):
                owner = data.get("source_project_id") or data.get("project_id")
                if (
                    owner
                    and data.get("generation") is not None
                    and (
                        owner != self.session.project_id
                        or data.get("generation") != self.session.generation
                    )
                ):
                    self._refresh()
                    return
                self.logs.append(message)
                if kind == "lifecycle_duplicate_ready":
                    source_project_id = data.get("source_project_id")
                    copied_project_id = str(data.get("project_id", ""))
                    if copied_project_id:
                        self._ensure_project_entry(store.load(copied_project_id))
                    if (
                        source_project_id == self.session.project_id
                        and data.get("generation") == self.session.generation
                    ):
                        self._activate_project(
                            copied_project_id,
                            load_viewer=data.get("mode") == "complete",
                        )
                        return
                elif kind == "lifecycle_cleanup_ready":
                    if (
                        data.get("project_id") == self.session.project_id
                        and data.get("generation") == self.session.generation
                    ):
                        self.session.switch(self.session.project_id)
                        self._clear_project_presentation(
                            "Project outputs were cleared; run the required stages again"
                        )
                self._refresh()
                return

            if kind.startswith("import_"):
                if data.get("generation") != self.import_generation:
                    session = data.get("session")
                    if isinstance(session, VideoImportSession):
                        session.cancel()
                    return
                self.logs.append(f"{kind}: {message}")
                if kind == "import_preflight_ready":
                    session = data.get("session")
                    if isinstance(session, VideoImportSession):
                        self.import_session = session
                        self.import_state.update({
                            "source": str(session.source), "status": "ready",
                            "profile": session.profile, "sampling": session.snapshot(),
                        })
                        self.importChanged.emit()
                elif kind == "import_preflight_failed":
                    self.import_state.update({"status": "failed", "error": message})
                    self.importChanged.emit()
                elif kind == "import_analysis_ready":
                    self.import_analysis_running = False
                    self.import_state.update({
                        "status": "ready", "sampling": data.get("sampling", {})
                    })
                    self.importChanged.emit()
                elif kind == "import_analysis_failed":
                    self.import_analysis_running = False
                    self.import_state.update({"status": "failed", "error": message})
                    self.importChanged.emit()
                return

            project_id = data.get("project_id")
            run_id = data.get("run_id")
            if isinstance(project_id, str):
                if kind in {"sampling_ready", "sampling_failed"}:
                    self.sampling_analysis.discard(project_id)
                if kind in {"complete", "run_failed"} and isinstance(run_id, str):
                    self.session.finish_run(project_id, run_id)
                accepted = self.session.accepts(data)
                if accepted and isinstance(run_id, str) and kind != "run_failed":
                    try:
                        accepted = store.load(project_id).run_id == run_id
                    except ProjectStoreError:
                        accepted = False
                if not accepted:
                    self.projects = store.all()
                    self.changed.emit()
                    return
                if data.get("stage") not in {
                    *STAGES, "pipeline", "viewer", "timeline", "ingest"
                }:
                    return

            self.logs.append(f"{kind}: {message}")
            if kind == "persistence_failed" and isinstance(project_id, str):
                self.persistence_failed.add(project_id)
            elif kind == "viewer_ready" and isinstance(data.get("scene"), ViewerScene):
                scene = data["scene"]
                if (
                    scene.project_id != self.session.project_id
                    or scene.run_id != run_id
                    or scene.generation != self.session.generation
                ):
                    return
                viewer_handler.set_scene(scene)
                self.session.viewer_project_id = scene.project_id
                self.session.viewer_run_id = scene.run_id
                self.viewer_revision += 1
                self.viewer_url = f"gaussian://viewer/index.html?v={self.viewer_revision}"
                self.viewer_status = f"Loaded {scene.gaussian_count:,} Gaussians · SH degree {scene.sh_degree}"
                self.viewerUrlChanged.emit()
                self.viewerStatusChanged.emit()
            elif kind == "viewer_failed":
                viewer_handler.clear_scene()
                self.viewer_url = "about:blank"
                self.viewer_status = f"Viewer load failed: {message}"
                self.viewerUrlChanged.emit()
                self.viewerStatusChanged.emit()
            elif kind == "complete":
                self._refresh()
                if data.get("status") == "succeeded":
                    self.loadViewer()
                return
            elif kind == "run_failed":
                self._clear_project_presentation(f"Pipeline could not start: {message}")
            self._refresh()

    QQuickWebEngineProfile.defaultProfile().installUrlSchemeHandler(b"gaussian", viewer_handler)
    backend = Backend()
    # Pipeline threads emit this signal; force queued delivery to Backend's Qt
    # thread so no Worker ever updates a QML-bound property directly.
    backend.event.connect(backend.handleEvent, Qt.QueuedConnection)

    def load_shell(name: str) -> tuple[Any, list[str]]:
        shell_engine = QQmlApplicationEngine()
        warnings: list[str] = []
        shell_engine.warnings.connect(
            lambda values: warnings.extend(str(value) for value in values)
        )
        context = shell_engine.rootContext()
        context.setContextProperty("backend", backend)
        context.setContextProperty("startupWidth", 1600)
        context.setContextProperty("startupHeight", 900)
        context.setContextProperty("startupTheme", "light")
        context.setContextProperty("useSavedSettings", True)
        qml_name = (
            "MissingAcceptanceRoot.qml"
            if name == "modern" and args.acceptance_force_modern_failure
            else "Main.qml"
        )
        qml = Path(__file__).with_name("qml") / name / qml_name
        record_ui(f"Loading {name} shell from {qml}")
        shell_engine.load(QUrl.fromLocalFile(str(qml)))
        return shell_engine, warnings

    engine, shell_warnings = load_shell(ui_selection.name)
    if not engine.rootObjects() and ui_selection.name == "modern":
        detail = " | ".join(shell_warnings[-8:]) or "no QML root object"
        record_ui(f"ModernUI load failed; falling back to ClassicUI: {detail}")
        backend.logs.append(
            f"ModernUI load failed; ClassicUI fallback activated: {detail}"
        )
        engine.deleteLater()
        engine, shell_warnings = load_shell("classic")
        backend._set_active_ui("classic")
    if not engine.rootObjects():
        detail = " | ".join(shell_warnings[-8:]) or "no QML root object"
        record_ui(f"{backend.active_ui} shell load failed: {detail}")
        return 2
    record_ui(f"{backend.active_ui} shell loaded successfully")
    root = engine.rootObjects()[0]
    if backend.active_ui == "modern":
        if args.acceptance_theme:
            root.setProperty("themeMode", args.acceptance_theme)
        if args.acceptance_density:
            root.setProperty("interfaceSize", args.acceptance_density)
        if args.acceptance_weight:
            root.setProperty("typographyWeight", args.acceptance_weight)
        if args.acceptance_page:
            root.setProperty("currentPage", args.acceptance_page)
        if args.acceptance_dialog:
            dialog_name = (
                "settingsDialog"
                if args.acceptance_dialog == "settings"
                else "newProjectDialog"
            )
            dialog = root.findChild(QObject, dialog_name)
            if dialog is not None:
                QTimer.singleShot(100, dialog.open)
    # Explicit acceptance capture is a diagnostic mode rather than a normal
    # launch, so it may open the newest project to exercise the real Viewer.
    if args.acceptance_evidence and backend.projects and not args.acceptance_import_video:
        backend._activate_project(backend.projects[0].project_id)
    if args.acceptance_import_video:
        method = root.openProAcceptance if args.acceptance_import_pro else root.beginVideo
        QTimer.singleShot(250, lambda: method(str(args.acceptance_import_video.resolve())))
    if args.acceptance_evidence:
        def acceptance_deadline() -> None:
            destination = args.acceptance_evidence.resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            root.grabWindow().save(str(destination))
            app.quit()
        QTimer.singleShot(max(1_000, args.acceptance_delay_ms), acceptance_deadline)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
