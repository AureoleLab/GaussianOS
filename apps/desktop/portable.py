"""Portable distribution layout, runtime verification, install, and repair.

The application and its mutable data are siblings in a distribution root::

    Application/  Runtime/  Settings/  Cache/  Logs/  Projects/  Exports/

Legacy flat portable builds remain readable. Runtime changes are staged,
verified, and atomically committed one component at a time. No operation in
this module writes to a project or export directory.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import threading
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from functools import wraps
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Literal
from uuid import uuid4

from packages.file_lock import FileLock
from packages.external_process import run_external

_mutation_state = threading.local()


def _serialized_runtime_mutation(function):
    @wraps(function)
    def locked(*args, **kwargs):
        if getattr(_mutation_state, "active", False):
            return function(*args, **kwargs)
        layout = layout_paths(create=True)
        with FileLock(layout.cache / "RuntimeLocks" / "install.lock", operation="runtime install/repair",
                      project_id="Runtime", timeout=0):
            _mutation_state.active = True
            try:
                return function(*args, **kwargs)
            finally:
                _mutation_state.active = False
    return locked


RUNTIME_SCHEMA = "gaussianos-runtime-manifest/v3"
CORE_VERSION = "0.1.0-beta.1"
_DISTRIBUTION_ROOT_ENV = "GAUSSIANOS_DISTRIBUTION_ROOT"
_MAX_DOWNLOAD_ATTEMPTS = 3


@dataclass(frozen=True)
class PortableLayout:
    distribution_root: Path
    application: Path
    runtime: Path
    settings: Path
    cache: Path
    logs: Path
    projects: Path
    exports: Path


DoctorCategory = Literal[
    "core",
    "runtime_missing",
    "runtime_incomplete",
    "runtime_integrity",
    "gpu",
    "external_tool",
    "project_data",
]


@dataclass(frozen=True)
class DoctorIssue:
    category: DoctorCategory
    code: str
    message: str
    component_id: str | None = None
    path: str | None = None


@dataclass(frozen=True)
class DoctorReport:
    core_status: Literal["ok", "damaged"]
    runtime_status: Literal["ok", "not_installed", "incomplete", "integrity_failed"]
    gpu_status: Literal["ok", "unavailable", "incompatible", "unknown"]
    external_tools_status: Literal["ok", "missing"]
    project_data_status: Literal["ok", "issue"]
    full_verification: bool
    issues: tuple[DoctorIssue, ...]

    @property
    def exit_code(self) -> int:
        if self.core_status != "ok":
            return 3
        if self.runtime_status != "ok":
            return 2
        if self.gpu_status in {"unavailable", "incompatible"} or (
            self.gpu_status == "unknown" and any(issue.category == "gpu" for issue in self.issues)
        ):
            return 4
        if self.external_tools_status != "ok":
            return 5
        if self.project_data_status != "ok":
            return 6
        return 0

    def payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["issues"] = [asdict(issue) for issue in self.issues]
        payload["exit_code"] = self.exit_code
        return payload


def _is_portable_context() -> bool:
    return bool(getattr(sys, "frozen", False) or os.environ.get(_DISTRIBUTION_ROOT_ENV))


def distribution_root() -> Path:
    override = os.environ.get(_DISTRIBUTION_ROOT_ENV)
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        executable_root = Path(sys.executable).resolve().parent
        if executable_root.name.casefold() == "application":
            candidate = executable_root.parent
            if (candidate / "runtime-manifest.json").is_file():
                return candidate
        return executable_root
    return Path(__file__).resolve().parents[2]


def portable_root() -> Path:
    """Backward-compatible name for the distribution root."""

    return distribution_root()


def manifest_path() -> Path:
    root = distribution_root()
    installed = root / "runtime-manifest.json"
    if installed.is_file() or _is_portable_context():
        return installed
    return root / "dist" / "runtime-manifest.json"


def load_manifest(path: str | Path | None = None) -> dict[str, Any]:
    source = Path(path).resolve() if path is not None else manifest_path()
    payload = json.loads(source.read_text(encoding="utf-8-sig"))
    validate_manifest(payload)
    return payload


def _portable_relative(value: str, field: str) -> PurePosixPath:
    raw = value.replace("\\", "/")
    path = PurePosixPath(raw)
    if (
        not raw
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or ":" in path.parts[0]
        or any(":" in part or "\x00" in part or part.endswith((" ", "."))
               or re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part)
               for part in path.parts)
    ):
        raise ValueError(f"{field} must be a portable relative path: {value!r}")
    folded = [part.casefold() for part in path.parts]
    for left, right in zip(folded, folded[1:]):
        if left == "runtime" and right == "runtime":
            raise ValueError(f"{field} contains forbidden runtime/runtime nesting")
    return path


def _components(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return list(manifest.get("components", []))


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != RUNTIME_SCHEMA:
        raise ValueError(
            f"unsupported runtime manifest schema: {manifest.get('schema_version')!r}"
        )
    platform = manifest.get("platform")
    if not isinstance(platform, dict):
        raise ValueError("runtime manifest platform must be an object")
    if platform.get("os") != "windows" or platform.get("architecture") != "x86_64":
        raise ValueError("runtime manifest is not for windows-x86_64")
    compatible = manifest.get("compatible_gaussianos_versions")
    if not isinstance(compatible, list) or not compatible:
        raise ValueError("compatible_gaussianos_versions must be a non-empty list")
    _portable_relative(str(manifest.get("runtime_root", "")), "runtime_root")
    components = manifest.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("runtime manifest components must be a non-empty list")
    seen: set[str] = set()
    for component in components:
        required = {
            "component_id",
            "version",
            "platform",
            "architecture",
            "relative_install_path",
            "installed_size_bytes",
            "tree_sha256",
            "dependencies",
            "required",
            "source",
            "compatible_gaussianos_versions",
            "verification",
        }
        missing = sorted(required - set(component))
        if missing:
            raise ValueError(
                f"component {component.get('component_id', '<unknown>')} missing: {missing}"
            )
        component_id = str(component["component_id"])
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", component_id) or component_id in seen:
            raise ValueError(f"duplicate or empty component_id: {component_id!r}")
        seen.add(component_id)
        _portable_relative(
            str(component["relative_install_path"]),
            f"{component_id}.relative_install_path",
        )
        if not isinstance(component["installed_size_bytes"], int):
            raise ValueError(f"{component_id}.installed_size_bytes must be an integer")
        tree_hash = str(component["tree_sha256"])
        if tree_hash and (
            len(tree_hash) != 64
            or any(character not in "0123456789abcdef" for character in tree_hash)
        ):
            raise ValueError(f"{component_id}.tree_sha256 must be lowercase SHA-256")
        if not isinstance(component["dependencies"], list):
            raise ValueError(f"{component_id}.dependencies must be a list")
        if not isinstance(component["required"], bool):
            raise ValueError(f"{component_id}.required must be boolean")
        if not isinstance(component["source"], dict):
            raise ValueError(f"{component_id}.source must be an object")
        if not isinstance(component["verification"], list) or not component["verification"]:
            raise ValueError(f"{component_id}.verification must be a non-empty list")
        for check in component["verification"]:
            _portable_relative(str(check.get("path", "")), f"{component_id}.verification.path")
            if check.get("type", "file") == "file":
                if not isinstance(check.get("size_bytes"), int):
                    raise ValueError(f"{component_id} file check requires size_bytes")
                digest = str(check.get("sha256", ""))
                if len(digest) != 64:
                    raise ValueError(f"{component_id} file check requires SHA-256")
    unknown_dependencies = sorted(
        {
            dependency
            for component in components
            for dependency in component["dependencies"]
            if dependency not in seen
        }
    )
    if unknown_dependencies:
        raise ValueError(f"unknown component dependencies: {unknown_dependencies}")
    graph = {c["component_id"]: c["dependencies"] for c in components}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name):
        if name in visiting:
            raise ValueError(f"Runtime dependency cycle at {name}")
        if name in visited:
            return
        visiting.add(name)
        for dependency in graph[name]:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)

    for name in graph:
        visit(name)


def layout_paths(create: bool = False) -> PortableLayout:
    root = distribution_root()
    if _is_portable_context():
        manifest: dict[str, Any] = {}
        try:
            manifest = load_manifest()
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        runtime_name = str(manifest.get("runtime_root", "Runtime"))
        application = root / "Application"
        if getattr(sys, "frozen", False):
            application = Path(sys.executable).resolve().parent
        layout = PortableLayout(
            root,
            application,
            root / runtime_name,
            root / "Settings",
            root / "Cache",
            root / "Logs",
            root / "Projects",
            root / "Exports",
        )
    else:
        factory = root / ".gaussian-factory"
        layout = PortableLayout(
            root,
            root,
            factory,
            factory / "settings",
            factory / "cache",
            factory / "logs",
            factory / "projects",
            factory / "exports",
        )
    if create:
        for path in (
            layout.runtime,
            layout.settings,
            layout.cache,
            layout.logs,
            layout.projects,
            layout.exports,
        ):
            path.mkdir(parents=True, exist_ok=True)
    return layout


def prepare_environment() -> PortableLayout:
    """Pin caches and tool discovery to portable, explicitly separated roots."""

    layout = layout_paths(create=_is_portable_context())
    if not _is_portable_context():
        return layout
    temp = layout.cache / "Temp"
    temp.mkdir(parents=True, exist_ok=True)
    os.environ["TORCH_HOME"] = str(layout.cache / "Torch")
    os.environ["HF_HOME"] = str(layout.cache / "HuggingFace")
    os.environ["XDG_CACHE_HOME"] = str(layout.cache)
    os.environ["TEMP"] = str(temp)
    os.environ["TMP"] = str(temp)
    tool_dirs = (
        layout.runtime / "tools" / "ffmpeg" / "bin",
        layout.runtime / "tools" / "git" / "cmd",
        layout.runtime / "tools" / "git" / "bin",
    )
    existing = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join(
        [*(str(path) for path in tool_dirs if path.is_dir()), existing]
    )
    return layout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_entries(root: Path) -> Iterable[tuple[str, int, str]]:
    for path in sorted(
        (candidate for candidate in root.rglob("*") if candidate.is_file()),
        key=lambda candidate: candidate.relative_to(root).as_posix().casefold(),
    ):
        relative = path.relative_to(root).as_posix()
        yield relative, path.stat().st_size, _sha256(path)


def tree_sha256(root: str | Path) -> str:
    base = Path(root)
    digest = hashlib.sha256()
    for relative, size, file_hash in _tree_entries(base):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def tree_size(root: str | Path) -> int:
    return sum(path.stat().st_size for path in Path(root).rglob("*") if path.is_file())


def _runtime_component_path(component: dict[str, Any], runtime: Path | None = None) -> Path:
    base = runtime or layout_paths().runtime
    relative = _portable_relative(
        str(component["relative_install_path"]), "relative_install_path"
    )
    target = base.joinpath(*relative.parts)
    resolved_base = base.resolve()
    resolved_target = target.resolve()
    if resolved_target != resolved_base and resolved_base not in resolved_target.parents:
        raise ValueError(f"runtime component escapes Runtime: {target}")
    return target


def _component_by_id(
    manifest: dict[str, Any], component_id: str
) -> dict[str, Any]:
    component = next(
        (
            candidate
            for candidate in _components(manifest)
            if candidate["component_id"] == component_id
        ),
        None,
    )
    if component is None:
        raise ValueError(f"Unknown runtime component: {component_id}")
    return component


def _verify_component(
    component: dict[str, Any],
    root: Path,
    *,
    full: bool,
) -> list[DoctorIssue]:
    component_id = str(component["component_id"])
    issues: list[DoctorIssue] = []
    if not root.is_dir():
        return [
            DoctorIssue(
                "runtime_missing",
                "component_missing",
                f"Runtime component is not installed: {component_id}.",
                component_id,
                str(root),
            )
        ]
    for check in component["verification"]:
        relative = _portable_relative(str(check["path"]), "verification.path")
        target = root.joinpath(*relative.parts)
        expected_type = check.get("type", "file")
        exists = target.is_dir() if expected_type == "directory" else target.is_file()
        if not exists:
            issues.append(
                DoctorIssue(
                    "runtime_incomplete",
                    "required_path_missing",
                    f"Runtime component {component_id} is incomplete: {relative.as_posix()}.",
                    component_id,
                    str(target),
                )
            )
            continue
        if expected_type == "file":
            expected_size = int(check["size_bytes"])
            actual_size = target.stat().st_size
            if actual_size != expected_size:
                issues.append(
                    DoctorIssue(
                        "runtime_integrity",
                        "file_size_mismatch",
                        f"Runtime integrity failed for {component_id}: "
                        f"{relative.as_posix()} is {actual_size} bytes, expected {expected_size}.",
                        component_id,
                        str(target),
                    )
                )
                continue
            if full and _sha256(target) != check["sha256"]:
                issues.append(
                    DoctorIssue(
                        "runtime_integrity",
                        "file_hash_mismatch",
                        f"Runtime SHA-256 failed for {component_id}: {relative.as_posix()}.",
                        component_id,
                        str(target),
                    )
                )
    expected_size = int(component["installed_size_bytes"])
    expected_tree = str(component["tree_sha256"])
    if full and not issues and expected_size:
        actual_size = tree_size(root)
        if actual_size != expected_size:
            issues.append(
                DoctorIssue(
                    "runtime_integrity",
                    "component_size_mismatch",
                    f"Runtime component {component_id} has {actual_size} bytes, "
                    f"expected {expected_size}.",
                    component_id,
                    str(root),
                )
            )
        elif expected_tree and tree_sha256(root) != expected_tree:
            issues.append(
                DoctorIssue(
                    "runtime_integrity",
                    "component_tree_hash_mismatch",
                    f"Runtime component tree SHA-256 failed: {component_id}.",
                    component_id,
                    str(root),
                )
            )
    return issues


def verify_runtime(*, full: bool = False) -> list[DoctorIssue]:
    manifest = load_manifest()
    runtime = layout_paths().runtime
    issues: list[DoctorIssue] = []
    for component in _components(manifest):
        if component["required"] or _runtime_component_path(component, runtime).exists():
            issues.extend(
                _verify_component(
                    component,
                    _runtime_component_path(component, runtime),
                    full=full,
                )
            )
    return issues


def _gpu_issues(manifest: dict[str, Any]) -> tuple[list[DoctorIssue], str]:
    if os.name != "nt":
        return [], "unknown"
    if not shutil.which("nvidia-smi"):
        return [
            DoctorIssue(
                "gpu",
                "nvidia_driver_missing",
                "NVIDIA driver was not detected; GPU reconstruction and training are unavailable.",
            )
        ], "unavailable"
    try:
        extended = bool(manifest.get("minimum_compute_capability") or manifest.get("minimum_driver_major"))
        query = run_external(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,driver_version,compute_cap" if extended else "--query-gpu=memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if query.returncode != 0:
            raise OSError(query.stderr.strip() or "nvidia-smi query failed")
        rows = [line.split(",") for line in query.stdout.splitlines() if line.strip()]
        # Workers currently use cuda:0. Checking the largest GPU could approve
        # a machine whose actual selected device cannot execute the pipeline.
        memory = int(rows[0][0].strip())
        minimum = int(manifest.get("minimum_vram_mib", 8192))
        if memory < minimum:
            return [
                DoctorIssue(
                    "gpu",
                    "vram_below_minimum",
                    f"GPU VRAM is {memory} MiB; the locked runtime requires {minimum} MiB.",
                )
            ], "incompatible"
        if extended:
            driver_major = int(rows[0][1].strip().split(".")[0])
            capability = float(rows[0][2].strip())
            minimum_driver = int(manifest.get("minimum_driver_major", 0))
            if driver_major < minimum_driver:
                return [DoctorIssue("gpu", "nvidia_driver_too_old",
                        f"NVIDIA driver {rows[0][1].strip()} is too old; this Runtime requires driver {minimum_driver} or newer.")], "incompatible"
            if capability < float(manifest.get("minimum_compute_capability", 0)):
                return [DoctorIssue("gpu", "gpu_architecture_unsupported",
                        f"GPU compute capability {capability} is below the supported minimum {manifest['minimum_compute_capability']}.")], "incompatible"
        return [], "ok"
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return [
            DoctorIssue(
                "gpu",
                "nvidia_query_failed",
                "NVIDIA driver exists, but GPU compatibility could not be queried.",
            )
        ], "unknown"


def doctor_report(*, full: bool = False) -> DoctorReport:
    prepare_environment()
    try:
        manifest = load_manifest()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        issue = DoctorIssue(
            "core",
            "runtime_manifest_invalid",
            f"Core runtime manifest is missing or invalid: {exc}",
            path=str(manifest_path()),
        )
        return DoctorReport(
            "damaged", "not_installed", "unknown", "missing", "ok", full, (issue,)
        )
    issues = verify_runtime(full=full)
    runtime_issues = list(issues)
    if any(issue.category == "runtime_integrity" for issue in runtime_issues):
        runtime_status = "integrity_failed"
    elif any(issue.category == "runtime_incomplete" for issue in runtime_issues):
        runtime_status = "incomplete"
    elif any(issue.category == "runtime_missing" for issue in runtime_issues):
        missing_count = sum(
            issue.category == "runtime_missing" for issue in runtime_issues
        )
        required_count = sum(
            bool(component["required"]) for component in _components(manifest)
        )
        runtime_status = (
            "not_installed" if missing_count == required_count else "incomplete"
        )
    else:
        runtime_status = "ok"
    gpu_issues, gpu_status = _gpu_issues(manifest)
    issues.extend(gpu_issues)
    external_missing = any(
        issue.component_id in {"ffmpeg", "colmap", "portable-git"}
        for issue in runtime_issues
    )
    return DoctorReport(
        "ok",
        runtime_status,
        gpu_status,  # type: ignore[arg-type]
        "missing" if external_missing else "ok",
        "ok",
        full,
        tuple(issues),
    )


def doctor(*, full: bool = False) -> list[str]:
    """Backward-compatible actionable diagnostic messages."""

    return [issue.message for issue in doctor_report(full=full).issues]


def _safe_extract(
    archive, destination: Path, strip_components: int = 0, *, max_bytes: int | None = None
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    base = destination.resolve()
    with zipfile.ZipFile(archive) as source:
        total = 0
        entries = []
        seen = set()
        for member in source.infolist():
            # Validate before stripping too: an absolute/traversing prefix must
            # never be made acceptable by removing its first path segment.
            relative = _portable_relative(member.filename.rstrip("/"), "archive member")
            if stat.S_ISLNK(member.external_attr >> 16):
                raise RuntimeError(f"Archive links are not supported: {member.filename}")
            parts = relative.parts[strip_components:]
            if not parts:
                continue
            target = destination.joinpath(*parts)
            resolved = target.resolve()
            if resolved != base and base not in resolved.parents:
                raise RuntimeError(f"unsafe archive member: {member.filename}")
            key = str(resolved).casefold()
            if key in seen:
                raise RuntimeError(f"Duplicate archive target: {member.filename}")
            seen.add(key)
            if not member.is_dir():
                total += member.file_size
            entries.append((member, target))
        if max_bytes is not None and total > max_bytes:
            raise RuntimeError(f"Archive exceeds locked installed size: {total} > {max_bytes}")
        for member, target in entries:
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with (
                    source.open(member) as input_stream,
                    target.open("wb") as output_stream,
                ):
                    shutil.copyfileobj(input_stream, output_stream)


def _download(
    component: dict[str, Any],
    progress: Callable[[str, int, int], None] | None,
) -> Path | list[Path]:
    from .runtime_downloads import download_verified, SegmentedReader

    source = component["source"]
    artifact = source.get("artifact")
    component_id = str(component["component_id"])
    if not isinstance(artifact, dict) or not (source.get("url") or artifact.get("parts")):
        raise RuntimeError(f"{component_id} has no published payload; use the verified Offline Runtime.")
    downloads = layout_paths(create=True).cache / "RuntimeDownloads"
    downloads.mkdir(parents=True, exist_ok=True)
    parts = artifact.get("parts") or [{**artifact, "url": source["url"]}]
    paths = []
    completed = 0
    for part in parts:
        filename = _portable_relative(str(part["filename"]), "artifact.filename")
        if len(filename.parts) != 1:
            raise ValueError("Artifact filenames must have no directory components")
        target = downloads / filename.name
        base = completed
        callback = (lambda done, _total, base=base: progress(component_id, base + done, int(artifact["size_bytes"]))) if progress else None
        paths.append(download_verified(str(part["url"]), target, size=int(part["size_bytes"]),
                                       digest=str(part["sha256"]), progress=callback))
        completed += int(part["size_bytes"])
    if len(paths) > 1:
        digest = hashlib.sha256()
        with SegmentedReader(paths) as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                digest.update(block)
        if completed != int(artifact["size_bytes"]) or digest.hexdigest() != artifact["sha256"]:
            raise RuntimeError(f"Combined archive SHA-256 mismatch for {component_id}")
        return paths
    return paths[0]


def _atomic_commit(staged: Path, destination: Path) -> Path:
    runtime = layout_paths().runtime.resolve()
    resolved = destination.resolve()
    if resolved != runtime and runtime not in resolved.parents:
        raise RuntimeError(f"refusing to commit outside Runtime: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = destination.parent / f".{destination.name}.rollback-{uuid4().hex}"
    had_destination = destination.exists()
    try:
        if had_destination:
            os.replace(destination, backup)
        os.replace(staged, destination)
    except Exception:
        if had_destination and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    if backup.exists():
        shutil.rmtree(backup)
    return destination


def _stage_component(
    component: dict[str, Any],
    populate: Callable[[Path], None],
) -> Path:
    layout = layout_paths(create=True)
    component_id = str(component["component_id"])
    staging_root = layout.runtime / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    staged = staging_root / f"{component_id}-{uuid4().hex}"
    staged.mkdir(parents=True)
    try:
        populate(staged)
        issues = _verify_component(component, staged, full=True)
        if issues:
            raise RuntimeError(
                "Component verification failed:\n"
                + "\n".join(issue.message for issue in issues)
            )
        destination = _runtime_component_path(component, layout.runtime)
        return _atomic_commit(staged, destination)
    except Exception:
        if staged.exists():
            shutil.rmtree(staged)
        raise


@_serialized_runtime_mutation
def install(
    component_id: str,
    progress: Callable[[str, int, int], None] | None = None,
) -> Path:
    """Download, stage, fully verify, and atomically install one component."""

    manifest = load_manifest()
    component = _component_by_id(manifest, component_id)
    for dependency in component["dependencies"]:
        dependency_component = _component_by_id(manifest, dependency)
        dependency_path = _runtime_component_path(dependency_component)
        if _verify_component(dependency_component, dependency_path, full=False):
            install(dependency, progress)
    artifact_info = component["source"].get("artifact", {})
    downloads = layout_paths().cache / "RuntimeDownloads"
    remaining_download = 0
    for part in artifact_info.get("parts", [artifact_info]):
        if not part.get("filename"):
            continue
        name = _portable_relative(str(part["filename"]), "artifact.filename")
        if len(name.parts) != 1:
            raise ValueError("Artifact filenames must have no directory components")
        completed = downloads / name.name
        partial = completed.with_name(completed.name + ".part")
        cached = completed if completed.is_file() else partial
        existing_bytes = cached.stat().st_size if cached.is_file() else 0
        remaining_download += max(0, int(part["size_bytes"]) - existing_bytes)
    peak_needed = remaining_download + int(component["installed_size_bytes"]) + 512 * 1024**2
    if shutil.disk_usage(layout_paths().runtime).free < peak_needed:
        raise OSError(f"Not enough free space to download and install {component_id}: {peak_needed} bytes required")
    archive = _download(component, progress)
    source = component["source"]
    artifact = source["artifact"]
    needed = int(component["installed_size_bytes"]) + 512 * 1024**2
    if shutil.disk_usage(layout_paths().runtime).free < needed:
        raise OSError(f"Not enough space to install {component_id}: {needed} bytes required")

    def populate(staged: Path) -> None:
        archive_type = artifact.get("archive")
        if archive_type == "zip":
            if isinstance(archive, list):
                from .runtime_downloads import SegmentedReader
                with SegmentedReader(archive) as stream:
                    _safe_extract(stream, staged, int(artifact.get("strip_components", 0)), max_bytes=int(component["installed_size_bytes"]))
            else:
                _safe_extract(archive, staged, int(artifact.get("strip_components", 0)), max_bytes=int(component["installed_size_bytes"]))
        elif archive_type == "file":
            relative = _portable_relative(
                str(artifact["install_as"]), f"{component_id}.artifact.install_as"
            )
            target = staged.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(archive, target)
        else:
            raise RuntimeError(
                f"unsupported artifact archive type for {component_id}: {archive_type}"
            )

    target = _stage_component(component, populate)
    # Successfully committed components are their own verified cache. Retain
    # only interrupted downloads, avoiding a duplicate installed Runtime.
    for downloaded in archive if isinstance(archive, list) else [archive]:
        downloaded.unlink(missing_ok=True)
    return target


def _offline_package_root(source: Path) -> tuple[Path, Path]:
    candidates = [source, source.parent]
    for candidate in candidates:
        manifest = candidate / "runtime-manifest.json"
        if manifest.is_file():
            runtime_name = str(load_manifest(manifest).get("runtime_root", "Runtime"))
            runtime = candidate / runtime_name
            if runtime.is_dir():
                return candidate, runtime
    if source.is_dir() and source.name.casefold() == "runtime":
        manifest = source.parent / "runtime-manifest.json"
        if manifest.is_file():
            return source.parent, source
    raise RuntimeError(
        "Offline Runtime must contain runtime-manifest.json and its declared Runtime directory."
    )


@_serialized_runtime_mutation
def ensure_runtime_phase(phase: str, progress=None) -> list[Path]:
    """Install a complete capability automatically, retaining verified components."""
    manifest = load_manifest()
    installed = []
    for component in _components(manifest):
        component_phase = component.get("install_phase", "base")
        if component_phase != phase:
            continue
        path = _runtime_component_path(component)
        if _verify_component(component, path, full=False):
            installed.append(install(str(component["component_id"]), progress))
    return installed


@_serialized_runtime_mutation
def import_offline(source: str | Path) -> list[Path]:
    """Fully verify and atomically import every present manifest component."""

    package_root, runtime_source = _offline_package_root(Path(source).resolve())
    source_manifest_path = package_root / "runtime-manifest.json"
    source_manifest = load_manifest(source_manifest_path)
    local_manifest = load_manifest()
    if _sha256(source_manifest_path) != _sha256(manifest_path()):
        if source_manifest != local_manifest:
            raise RuntimeError(
                "Offline Runtime manifest does not exactly match this Portable Core."
            )
    nested = runtime_source / str(source_manifest["runtime_root"])
    if nested.is_dir():
        raise RuntimeError(
            f"Offline Runtime contains forbidden runtime/runtime nesting: {nested}"
        )
    installed: list[Path] = []
    for component in _components(local_manifest):
        source_component = _runtime_component_path(component, runtime_source)
        if not source_component.is_dir():
            if component["required"]:
                raise RuntimeError(
                    f"Offline Runtime is missing required component: "
                    f"{component['component_id']}"
                )
            continue

        def populate(staged: Path, component_source: Path = source_component) -> None:
            shutil.copytree(component_source, staged, dirs_exist_ok=True)

        installed.append(_stage_component(component, populate))
    return installed


@_serialized_runtime_mutation
def repair(
    component_id: str,
    offline_source: str | Path | None = None,
    progress: Callable[[str, int, int], None] | None = None,
) -> Path:
    """Repair one damaged component without touching user data."""

    if offline_source is None:
        return install(component_id, progress)
    package_root, runtime_source = _offline_package_root(
        Path(offline_source).resolve()
    )
    source_manifest = load_manifest(package_root / "runtime-manifest.json")
    local_manifest = load_manifest()
    if source_manifest != local_manifest:
        raise RuntimeError("Offline Runtime manifest does not match this Core.")
    component = _component_by_id(local_manifest, component_id)
    source_component = _runtime_component_path(component, runtime_source)
    if not source_component.is_dir():
        raise RuntimeError(f"Offline Runtime component is missing: {component_id}")

    def populate(staged: Path) -> None:
        shutil.copytree(source_component, staged, dirs_exist_ok=True)

    return _stage_component(component, populate)
