"""Privacy-safe portable distribution diagnostics.

The bundle intentionally excludes requests, videos, project metadata, and
artifacts.  Only bounded, redacted host/Runtime reports and worker execution
records are included.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from packages.external_process import popen_external, run_external

from .portable import CORE_VERSION, doctor_report, layout_paths, load_manifest


DIAGNOSTIC_SCHEMA = "gaussianos-diagnostic-bundle/v1"
_MAX_LOG_BYTES = 64 * 1024
_WINDOWS_PATH = re.compile(r"(?i)(?<![A-Za-z0-9_])(?:[A-Z]:[\\/]|\\\\)[^\r\n\"']+")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_version(manifest: dict[str, Any]) -> str:
    components = manifest.get("components", [])
    locked = ", ".join(
        f"{item.get('component_id')}={item.get('version')}" for item in components
    )
    return locked or "unknown"


def _redaction_roots(extra: Iterable[Path] = ()) -> tuple[str, ...]:
    candidates = [
        layout_paths().distribution_root,
        Path.home(),
        Path(tempfile.gettempdir()),
        *(Path(item) for item in extra),
    ]
    values: list[str] = []
    for candidate in candidates:
        try:
            value = str(candidate.resolve())
        except OSError:
            value = str(candidate)
        if value and value not in values:
            values.append(value)
    return tuple(sorted(values, key=len, reverse=True))


def redact_text(value: str, *, extra_roots: Iterable[Path] = ()) -> str:
    """Remove user/distribution/project absolute paths from diagnostic text."""

    # Redact whole absolute paths before replacing known roots. Replacing a
    # root first hides the drive prefix and leaves private filenames behind.
    redacted = _WINDOWS_PATH.sub("<REDACTED_PATH>", value)
    for root in _redaction_roots(extra_roots):
        for spelling in {root, root.replace("\\", "/")}:
            redacted = re.sub(re.escape(spelling) + r'''(?:[/\\][^\r\n"']*)?''', "<REDACTED_PATH>", redacted, flags=re.I)
    return redacted


def redact_payload(value: Any, *, extra_roots: Iterable[Path] = ()) -> Any:
    if isinstance(value, dict):
        return {
            str(key): (
                "<REDACTED_ENVIRONMENT>"
                if str(key).upper() in {"PATH", "PYTHONHOME", "PYTHONPATH"}
                else redact_payload(item, extra_roots=extra_roots)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_payload(item, extra_roots=extra_roots) for item in value]
    if isinstance(value, str):
        return redact_text(value, extra_roots=extra_roots)
    return value


def _read_tail(path: Path, limit: int = _MAX_LOG_BYTES) -> str:
    try:
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            stream.seek(max(0, stream.tell() - limit))
            return stream.read().decode("utf-8", errors="replace")
    except OSError as exc:
        return f"<unavailable: {type(exc).__name__}>"


def _write_probe(path: Path) -> dict[str, Any]:
    marker = path / f".gaussianos-write-probe-{uuid4().hex}.tmp"
    try:
        path.mkdir(parents=True, exist_ok=True)
        with marker.open("x", encoding="utf-8") as stream:
            stream.write("diagnostic write probe\n")
            stream.flush()
            os.fsync(stream.fileno())
        marker.unlink()
        return {"status": "ok"}
    except OSError as exc:
        try:
            marker.unlink(missing_ok=True)
        except OSError:
            pass
        return {
            "status": "failed",
            "error_code": "path_not_writable",
            "message": f"{type(exc).__name__}: {exc}",
        }


def _disk_and_write_report() -> dict[str, Any]:
    layout = layout_paths()
    paths = {
        "Application": layout.application,
        "Runtime": layout.runtime,
        "Logs": layout.logs,
        "Cache": layout.cache,
        "Projects": layout.projects,
        "TEMP": Path(tempfile.gettempdir()),
    }
    report: dict[str, Any] = {}
    for label, path in paths.items():
        entry = _write_probe(path)
        try:
            usage = shutil.disk_usage(path)
            entry.update(
                {
                    "disk_total_bytes": usage.total,
                    "disk_free_bytes": usage.free,
                }
            )
        except OSError as exc:
            entry["disk_query"] = f"{type(exc).__name__}: {exc}"
        report[label] = entry
    return report


def _vc_runtime_report() -> dict[str, Any]:
    if os.name != "nt":
        return {"status": "not_applicable"}
    libraries: dict[str, str] = {}
    for name in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"):
        try:
            ctypes.WinDLL(name)
            libraries[name] = "available"
        except OSError as exc:
            libraries[name] = f"missing_or_unloadable: {exc}"
    return {
        "status": "ok"
        if all(value == "available" for value in libraries.values())
        else "incomplete",
        "libraries": libraries,
    }


def _gpu_report() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"status": "unavailable", "error_code": "nvidia_driver_missing"}
    command = [
        executable,
        "--query-gpu=name,driver_version,memory.total,compute_cap",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = run_external(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "status": "unknown",
            "error_code": "nvidia_query_failed",
            "message": f"{type(exc).__name__}: {exc}",
        }
    rows = []
    for line in completed.stdout.splitlines():
        fields = [item.strip() for item in line.split(",")]
        if len(fields) >= 4:
            rows.append(
                {
                    "name": fields[0],
                    "driver_version": fields[1],
                    "memory_mib": fields[2],
                    "compute_capability": fields[3],
                }
            )
    return {
        "status": "ok" if completed.returncode == 0 and rows else "unknown",
        "return_code": completed.returncode,
        "gpus": rows,
        "stderr_tail": completed.stderr[-2000:],
    }


def _critical_paths() -> dict[str, Path]:
    layout = layout_paths()
    return {
        "desktop": layout.application / "GaussianOS.exe",
        "worker_host": layout.application / "worker_host",
        "colmap": layout.runtime / "tools" / "colmap" / "3.13.0" / "bin" / "colmap.exe",
        "ffmpeg": layout.runtime / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe",
        "map_python": layout.runtime / "envs" / "mapanything-1.1.2" / "python.exe",
        "gsplat_python": layout.runtime / "envs" / "gsplat-1.5.3" / "python.exe",
    }


def _motw_report() -> dict[str, Any]:
    files: dict[str, Any] = {}
    for label, path in _critical_paths().items():
        if path.is_dir():
            continue
        zone_path = Path(str(path) + ":Zone.Identifier")
        try:
            zone = zone_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            zone = ""
        files[label] = {
            "exists": path.is_file(),
            "motw_present": bool(zone),
            "internet_zone": "ZoneId=3" in zone,
        }
    return {
        "status": "attention"
        if any(item["motw_present"] for item in files.values())
        else "ok",
        "files": files,
        "guidance": (
            "Do not disable antivirus. Restore a quarantined file, verify the package "
            "SHA-256, and allow only this verified GaussianOS release if your policy permits."
        ),
    }


def _powershell_json(command: str, *, timeout: int = 20) -> dict[str, Any]:
    if os.name != "nt":
        return {"status": "not_applicable"}
    executable = shutil.which("powershell.exe") or shutil.which("powershell")
    if not executable:
        return {"status": "unavailable", "message": "PowerShell was not found"}
    try:
        completed = run_external(
            [
                executable,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                command,
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "unavailable", "message": f"{type(exc).__name__}: {exc}"}
    payload: Any = None
    if completed.stdout.strip():
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            payload = completed.stdout[-4096:]
    return {
        "status": "ok" if completed.returncode == 0 else "unavailable",
        "return_code": completed.returncode,
        "data": payload,
        "stderr_tail": completed.stderr[-4096:],
    }


def _windows_security_report() -> dict[str, Any]:
    motw = _motw_report()
    if os.name != "nt":
        return {**motw, "defender": {"status": "not_applicable"}}
    defender = _powershell_json(
        "$s=Get-MpComputerStatus -ErrorAction Stop; "
        "$t=@(Get-MpThreatDetection -ErrorAction Stop | Select-Object ThreatID,ActionSuccess,CurrentThreatExecutionStatus,Resources); "
        "[ordered]@{AntivirusEnabled=$s.AntivirusEnabled;RealTimeProtectionEnabled=$s.RealTimeProtectionEnabled;ThreatDetections=$t}|ConvertTo-Json -Depth 5 -Compress"
    )
    executable = str(_critical_paths()["desktop"]).replace("'", "''")
    signature = _powershell_json(
        f"Get-AuthenticodeSignature -LiteralPath '{executable}' | Select-Object Status,StatusMessage | ConvertTo-Json -Compress"
    )
    signature_data = signature.get("data")
    signature_status = (
        signature_data.get("Status") if isinstance(signature_data, dict) else None
    )
    return {
        **motw,
        "defender": defender,
        "authenticode": signature,
        "smartscreen_assessment": (
            "internet_mark_present_unsigned_binary"
            if motw["status"] == "attention"
            and signature_status not in {0, "Valid"}
            else "no_direct_block_evidence"
        ),
    }


def _path_capabilities() -> dict[str, Any]:
    report: dict[str, Any] = {
        "distribution_path_characters": {
            "contains_spaces": " " in str(layout_paths().distribution_root),
            "contains_parentheses": any(
                item in str(layout_paths().distribution_root) for item in "()"
            ),
            "contains_non_ascii": any(
                ord(item) > 127 for item in str(layout_paths().distribution_root)
            ),
            "length": len(str(layout_paths().distribution_root)),
        }
    }
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\FileSystem",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
            report["windows_long_paths_enabled"] = bool(value)
        except OSError as exc:
            report["windows_long_paths_query"] = f"{type(exc).__name__}: {exc}"
    return report


def verify_build_manifest(*, full: bool) -> dict[str, Any]:
    root = layout_paths().distribution_root
    path = root / "build-manifest.json"
    if not path.is_file():
        return {
            "status": "unavailable",
            "error_code": "build_manifest_missing",
            "checked_files": 0,
            "missing": [],
            "corrupt": [],
        }
    try:
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
        entries = manifest["files"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return {
            "status": "failed",
            "error_code": "build_manifest_invalid",
            "message": f"{type(exc).__name__}: {exc}",
            "checked_files": 0,
            "missing": [],
            "corrupt": [],
        }
    important = {
        "Application/GaussianOS.exe",
        "runtime-manifest.json",
        "Application/worker_host/workers/recon_colmap/__main__.py",
        "Application/worker_host/workers/recon_mapanything/__main__.py",
        "Application/worker_host/workers/train_gsplat/__main__.py",
    }
    selected = entries if full else [item for item in entries if item.get("path") in important]
    missing: list[str] = []
    corrupt: list[str] = []
    checked = 0
    for item in selected:
        relative = str(item.get("path", "")).replace("\\", "/")
        candidate = root.joinpath(*relative.split("/"))
        if not candidate.is_file():
            missing.append(relative)
            continue
        checked += 1
        if candidate.stat().st_size != int(item.get("size_bytes", -1)):
            corrupt.append(relative)
        elif full or relative in important:
            if _sha256(candidate) != item.get("sha256"):
                corrupt.append(relative)
        if len(missing) + len(corrupt) >= 200:
            break
    return {
        "status": "ok" if not missing and not corrupt else "failed",
        "error_code": None if not missing and not corrupt else "package_integrity_failed",
        "manifest_sha256": _sha256(path),
        "manifest_file_count": int(manifest.get("file_count", len(entries))),
        "full_verification": full,
        "checked_files": checked,
        "missing": missing,
        "corrupt": corrupt,
    }


def _worker_probes() -> list[dict[str, Any]]:
    from .pipeline import RuntimePaths

    runtime = RuntimePaths.discover()
    probes = (
        ("colmap", runtime.worker_python, "workers.recon_colmap"),
        ("fallback", runtime.map_python, "workers.recon_mapanything"),
        ("train", runtime.gsplat_python, "workers.train_gsplat"),
    )
    environment = os.environ.copy()
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    results: list[dict[str, Any]] = []
    for stage, executable, module in probes:
        argv = [str(executable), "-B", "-m", module, "--help"]
        record: dict[str, Any] = {
            "stage": stage,
            "executable": str(executable),
            "argv": argv,
            "cwd": str(runtime.worker_cwd),
            "pid": None,
            "return_code": None,
        }
        try:
            process = popen_external(
                argv,
                cwd=runtime.worker_cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
            )
            record["pid"] = process.pid
            try:
                stdout, stderr = process.communicate(timeout=60)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                raise
            record.update(
                {
                    "status": "ok" if process.returncode == 0 else "failed",
                    "return_code": process.returncode,
                    "stdout_tail": stdout[-4096:].decode("utf-8", errors="replace"),
                    "stderr_tail": stderr[-4096:].decode("utf-8", errors="replace"),
                }
            )
        except (OSError, subprocess.SubprocessError) as exc:
            record.update(
                {
                    "status": "launch_failed",
                    "error_code": "worker_launch_failed",
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )
        results.append(record)
    return results


def _system_report() -> dict[str, Any]:
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "process_architecture_bits": struct.calcsize("P") * 8,
        "frozen": bool(getattr(sys, "frozen", False)),
        "core_version": CORE_VERSION,
        "vc_runtime": _vc_runtime_report(),
        "gpu": _gpu_report(),
        "storage_and_writes": _disk_and_write_report(),
        "security": _windows_security_report(),
        "paths": _path_capabilities(),
    }


def _collect_execution_records(search_roots: Iterable[Path]) -> list[dict[str, Any]]:
    candidates: list[Path] = []
    for root in search_roots:
        if not root.is_dir():
            continue
        try:
            candidates.extend(root.rglob("execution.json"))
        except OSError:
            continue
    records: list[dict[str, Any]] = []
    for path in sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)[:20]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            payload = {"state": "unreadable", "message": f"{type(exc).__name__}: {exc}"}
        payload["stdout_tail"] = _read_tail(path.with_name("stdout.log"))
        payload["stderr_tail"] = _read_tail(path.with_name("stderr.log"))
        records.append(payload)
    return records


def create_diagnostic_bundle(
    *,
    full: bool = True,
    project_roots: Iterable[Path] = (),
    include_worker_probes: bool = True,
) -> Path:
    """Create a sendable ZIP containing only bounded, redacted diagnostics."""

    layout = layout_paths()
    layout.logs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = layout.logs / f"GaussianOS-Diagnostics-{stamp}.zip"
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    roots = tuple(Path(item) for item in project_roots)
    manifest = load_manifest()
    doctor = doctor_report(full=full)
    report = {
        "schema_version": DIAGNOSTIC_SCHEMA,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "privacy": {
            "absolute_paths_redacted": True,
            "user_media_included": False,
            "project_content_included": False,
            "process_environment_included": False,
        },
        "versions": {
            "core": CORE_VERSION,
            "runtime_manifest_schema": manifest.get("schema_version"),
            "runtime_components": _runtime_version(manifest),
        },
        "doctor": doctor.payload(),
        "package_manifest": verify_build_manifest(full=full),
        "system": _system_report(),
        "worker_probes": _worker_probes() if include_worker_probes else [],
    }
    records = _collect_execution_records((layout.projects, *roots))
    related_logs: list[tuple[str, str]] = []
    log_candidates = [
        layout.logs / "desktop-ui.log",
        layout.logs / "doctor-report.txt",
        layout.logs / "doctor-report.json",
    ]
    for root in roots:
        if root.is_dir():
            log_candidates.extend(root.rglob("pipeline-error.json"))
    for index, path in enumerate(log_candidates[:20]):
        if path.is_file():
            related_logs.append((f"logs/log-{index:02d}{path.suffix}", _read_tail(path)))
    sanitized = redact_payload(report, extra_roots=roots)
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "diagnostic-report.json",
            json.dumps(sanitized, ensure_ascii=False, indent=2) + "\n",
        )
        for index, record in enumerate(records):
            archive.writestr(
                f"worker-executions/execution-{index:02d}.json",
                json.dumps(
                    redact_payload(record, extra_roots=roots),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
            )
        for name, content in related_logs:
            archive.writestr(name, redact_text(content, extra_roots=roots))
    os.replace(temporary, destination)
    return destination
