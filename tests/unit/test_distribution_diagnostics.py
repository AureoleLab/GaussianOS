from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.desktop import diagnostics
from apps.desktop.pipeline import PipelineController, PipelineStartError, RuntimePaths
from apps.desktop.project_store import ProjectStore
from packages.plugin_sdk import ErrorCode, ExecutionProfile, StageKind, StageRequest
from workers.recon_colmap import __main__ as recon_colmap


def _portable_layout(root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        distribution_root=root,
        application=root / "Application",
        runtime=root / "Runtime",
        settings=root / "Settings",
        cache=root / "Cache",
        logs=root / "Logs",
        projects=root / "Projects",
        exports=root / "Exports",
    )


def _runtime(layout: SimpleNamespace) -> RuntimePaths:
    worker_host = layout.application / "worker_host"
    colmap = layout.runtime / "tools" / "colmap" / "3.13.0" / "bin" / "colmap.exe"
    ffmpeg = layout.runtime / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    map_python = layout.runtime / "envs" / "mapanything-1.1.2" / "python.exe"
    gsplat_python = layout.runtime / "envs" / "gsplat-1.5.3" / "python.exe"
    lpips_checkpoint = (
        layout.runtime
        / "downloads"
        / "lpips-alexnet"
        / "checkpoints"
        / "alexnet-owt-7be5be79.pth"
    )
    files = (
        layout.application / "GaussianOS.exe",
        colmap,
        ffmpeg,
        map_python,
        gsplat_python,
        worker_host / "workers" / "recon_colmap" / "__main__.py",
        worker_host / "workers" / "recon_mapanything" / "__main__.py",
        worker_host / "workers" / "train_gsplat" / "__main__.py",
        lpips_checkpoint,
    )
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test")
    return RuntimePaths(
        colmap,
        str(ffmpeg),
        map_python,
        worker_host,
        map_python,
        gsplat_python,
        layout.runtime / "sources" / "gsplat-v1.5.3",
        layout.runtime / "sources" / "map-anything-v1.1.2",
        layout.runtime / "downloads" / "map" / "model.safetensors",
        layout.runtime / "downloads" / "map" / "config.json",
        layout.runtime / "sources" / "dinov2",
        layout.runtime / "downloads" / "dino" / "model.pth",
        lpips_checkpoint,
    )


def _doctor(*, gpu: str = "ok") -> SimpleNamespace:
    return SimpleNamespace(
        core_status="ok",
        runtime_status="ok",
        gpu_status=gpu,
        issues=(),
        payload=lambda: {
            "core_status": "ok",
            "runtime_status": "ok",
            "gpu_status": gpu,
            "issues": [],
        },
    )


def _controller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[PipelineController, object, SimpleNamespace]:
    layout = _portable_layout(tmp_path / "portable")
    runtime = _runtime(layout)
    store = ProjectStore(tmp_path / "metadata")
    project = store.create("portable", tmp_path / "library")
    project.input_kind = "images"
    project.input_path = str(tmp_path / "input")
    store.save(project)
    controller = PipelineController(
        store, tmp_path / "artifacts", runtime, enforce_preflight=True
    )
    monkeypatch.setattr("apps.desktop.portable.layout_paths", lambda: layout)
    monkeypatch.setattr(
        "apps.desktop.portable.load_manifest",
        lambda: {
            "schema_version": "gaussianos-runtime-manifest/v3",
            "components": [{"component_id": "runtime", "version": "1"}],
        },
    )
    monkeypatch.setattr("apps.desktop.portable.doctor_report", lambda full=False: _doctor())
    return controller, project, layout


def test_preflight_reports_missing_or_quarantined_runtime_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller, project, _ = _controller(tmp_path, monkeypatch)
    controller.runtime.gsplat_python.unlink()

    with pytest.raises(PipelineStartError) as captured:
        controller.preflight(project)

    assert captured.value.error_code == "runtime_file_missing"
    assert captured.value.failure_kind == "runtime_integrity"
    assert "quarantine" in str(captured.value).lower()
    assert captured.value.diagnostics["missing_or_quarantined_files"]


def test_preflight_reports_write_denial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller, project, layout = _controller(tmp_path, monkeypatch)
    monkeypatch.setattr(
        controller,
        "_write_probe",
        lambda path: "PermissionError: denied" if path == layout.cache else None,
    )

    with pytest.raises(PipelineStartError) as captured:
        controller.preflight(project)

    assert captured.value.error_code == "path_not_writable"
    assert captured.value.diagnostics["write_failures"] == {
        "cache": "PermissionError: denied"
    }


def test_preflight_rejects_runtime_inventory_size_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller, project, _ = _controller(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "apps.desktop.portable.load_manifest",
        lambda: {
            "schema_version": "gaussianos-runtime-manifest/v3",
            "components": [
                {
                    "component_id": "mapanything-environment",
                    "version": "1",
                    "relative_install_path": "envs/mapanything-1.1.2",
                    "installed_size_bytes": 0,
                }
            ],
        },
    )

    with pytest.raises(PipelineStartError) as captured:
        controller.preflight(project)

    assert captured.value.error_code == "runtime_component_size_mismatch"
    assert captured.value.diagnostics["runtime_size_mismatches"][0][
        "component_id"
    ] == "mapanything-environment"


def test_preflight_reports_insufficient_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller, project, _ = _controller(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "apps.desktop.pipeline.shutil.disk_usage",
        lambda _: SimpleNamespace(total=10 * 1024**3, used=9 * 1024**3, free=1024),
    )

    with pytest.raises(PipelineStartError) as captured:
        controller.preflight(project)

    assert captured.value.error_code == "disk_space_insufficient"
    assert captured.value.diagnostics["disk_free_bytes"] == 1024


def test_colmap_no_initial_pair_is_fallback_eligible_quality_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "colmap.exe"
    executable.write_bytes(b"colmap")
    images = tmp_path / "images"
    images.mkdir()
    for index in range(3):
        (images / f"{index}.png").write_bytes(b"image")
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    request = StageRequest(
        run_id="run",
        stage_id="colmap",
        stage_kind=StageKind.RECONSTRUCTION,
        plugin_id="recon.colmap",
        plugin_version="3.13.0+gf.1",
        profile=ExecutionProfile.PRODUCTION,
        attempt_id="attempt-test",
        attempt_dir=str(attempt),
        cancellation_file=str(attempt / "cancel"),
        config={
            "config_version": "recon-colmap/v1",
            "colmap_executable": str(executable),
            "colmap_executable_sha256": recon_colmap.EXPECTED_WINDOWS_CUDA_EXE_SHA256,
            "images_path": str(images),
            "expected_image_count": 3,
            "camera_model": "SIMPLE_RADIAL",
            "use_gpu": True,
            "minimum_registered_ratio": 0.9,
            "maximum_reprojection_error_px": 2.0,
            "maximum_step_over_median": 4.0,
        },
    )
    monkeypatch.setattr(
        recon_colmap,
        "_sha256_file",
        lambda _: recon_colmap.EXPECTED_WINDOWS_CUDA_EXE_SHA256,
    )

    def command(command: list[str], _: Path) -> tuple[float, str]:
        if "mapper" in command:
            raise RuntimeError(
                "command mapper failed with exit code 1: No good initial image pair found"
            )
        return 0.1, "ok"

    monkeypatch.setattr(recon_colmap, "_run_command", command)
    result, exit_code = recon_colmap._run(
        request, attempt / "result.json", datetime.now(timezone.utc)
    )

    assert exit_code == 10
    assert result.error is not None
    assert result.error.code is ErrorCode.OUTPUT_VALIDATION_FAILED
    assert result.error.details["failure_kind"] == "quality_gate"
    assert result.error.details["fallback_eligible"] is True


def test_diagnostic_zip_redacts_paths_and_excludes_project_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "Private User" / "GaussianOS"
    layout = _portable_layout(root)
    layout.logs.mkdir(parents=True)
    layout.projects.mkdir(parents=True)
    project = tmp_path / "Secret Client" / "project"
    attempt = project / "attempt"
    attempt.mkdir(parents=True)
    private_video = tmp_path / "Secret Client" / "private-video.mp4"
    private_video.write_bytes(b"PRIVATE_VIDEO_BYTES")
    (attempt / "execution.json").write_text(
        json.dumps(
            {
                "executable": str(root / "Runtime" / "python.exe"),
                "argv": [str(private_video)],
                "cwd": str(project),
                "environment": {"PATH": str(tmp_path / "private-path")},
            }
        ),
        encoding="utf-8",
    )
    (attempt / "stdout.log").write_text(f"reading {private_video}\n", encoding="utf-8")
    (attempt / "stderr.log").write_text("worker failed\n", encoding="utf-8")
    monkeypatch.setattr(diagnostics, "layout_paths", lambda: layout)
    monkeypatch.setattr(
        diagnostics,
        "load_manifest",
        lambda: {"schema_version": "test", "components": []},
    )
    monkeypatch.setattr(diagnostics, "doctor_report", lambda full: _doctor())
    monkeypatch.setattr(
        diagnostics, "verify_build_manifest", lambda full: {"status": "ok"}
    )
    monkeypatch.setattr(
        diagnostics, "_system_report", lambda: {"message": str(private_video)}
    )
    monkeypatch.setattr(diagnostics, "_worker_probes", lambda: [])

    bundle = diagnostics.create_diagnostic_bundle(
        full=True, project_roots=(project,)
    )

    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        content = b"\n".join(archive.read(name) for name in names)
    assert "diagnostic-report.json" in names
    assert any(name.startswith("worker-executions/") for name in names)
    assert b"PRIVATE_VIDEO_BYTES" not in content
    assert str(root).encode() not in content
    assert str(project).encode() not in content
    assert b"private-video.mp4" not in content
    assert b"REDACTED" in content


def test_build_manifest_detects_corruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = _portable_layout(tmp_path / "package")
    layout.distribution_root.mkdir(parents=True)
    payload = layout.distribution_root / "payload.bin"
    payload.write_bytes(b"damaged")
    manifest = {
        "file_count": 1,
        "files": [
            {
                "path": "payload.bin",
                "size_bytes": len(b"damaged"),
                "sha256": "0" * 64,
            }
        ],
    }
    (layout.distribution_root / "build-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    monkeypatch.setattr(diagnostics, "layout_paths", lambda: layout)

    report = diagnostics.verify_build_manifest(full=True)

    assert report["status"] == "failed"
    assert report["error_code"] == "package_integrity_failed"
    assert report["corrupt"] == ["payload.bin"]
