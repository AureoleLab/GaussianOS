"""P1 command-line surface; intentionally no desktop GUI."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from benchmarks.probe_environment import collect as collect_environment
from benchmarks.protocol import prepare_dataset
from packages.artifact_store import ArtifactStore
from packages.contracts import SceneBundleManifest, scene_bundle_json_schema
from packages.exportkit import (
    read_gaussian_ply,
    scene_bundle_to_gaussian_ply,
)
from packages.licensing import ProfilePolicyRegistry, evaluate_plugin_policy
from packages.pipeline import SubprocessWorkerRunner
from packages.plugin_sdk import (
    ExecutionProfile,
    PluginManifest,
    StageKind,
    StageRequest,
    model_json_schema_bundle,
)
from packages.scene_bundle import load_scene_bundle


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def _load_plugin(path: Path) -> PluginManifest:
    return PluginManifest.model_validate_json(path.read_text(encoding="utf-8"))


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _command_prepare(args: argparse.Namespace) -> int:
    manifest = prepare_dataset(
        args.input,
        args.output,
        frames_per_second=args.fps,
        holdout_stride=args.holdout_stride,
        holdout_offset=args.holdout_offset,
        ffmpeg=args.ffmpeg,
        ffprobe=args.ffprobe,
    )
    print(_json({
        "dataset_id": manifest.dataset_id,
        "manifest": str((args.output / "dataset.manifest.json").resolve()),
        "scenes": [
            {
                "scene_id": scene.scene_id,
                "frames": len(scene.frames),
                "train": sum(frame.split == "train" for frame in scene.frames),
                "holdout": sum(frame.split == "holdout" for frame in scene.frames),
            }
            for scene in manifest.scenes
        ],
    }))
    return 0


def _command_doctor(args: argparse.Namespace) -> int:
    payload = collect_environment(args.input, args.dataset_manifest, colmap_path=args.colmap)
    rendered = _json(payload) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


def _command_validate_bundle(args: argparse.Namespace) -> int:
    bundle = load_scene_bundle(args.bundle)
    print(_json({
        "status": "valid",
        "schema_version": bundle.manifest.schema_version,
        "camera_count": 0 if bundle.cameras is None else int(bundle.cameras.camtoworlds.shape[0]),
        "gaussian_count": 0 if bundle.gaussians is None else int(bundle.gaussians.means.shape[0]),
        "sh_degree": bundle.manifest.spherical_harmonics.degree,
    }))
    return 0


def _command_validate_ply(args: argparse.Namespace) -> int:
    gaussians = read_gaussian_ply(args.ply)
    print(_json({
        "status": "valid",
        "format": "graphdeco-gs-v1",
        "gaussian_count": int(gaussians.means.shape[0]),
        "sh_degree": gaussians.sh_degree,
        "quaternion_order": "wxyz",
        "opacity_encoding": "logit",
        "scale_encoding": "natural_log",
    }))
    return 0


def _command_export_ply(args: argparse.Namespace) -> int:
    destination = scene_bundle_to_gaussian_ply(args.bundle, args.output, overwrite=args.overwrite)
    print(_json({"status": "written", "path": str(destination)}))
    return 0


def _command_schema(args: argparse.Namespace) -> int:
    payload: dict[str, object] = {
        "SceneBundleManifest": scene_bundle_json_schema(),
        **model_json_schema_bundle(),
    }
    rendered = _json(payload) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


def _command_profile_check(args: argparse.Namespace) -> int:
    profile = ExecutionProfile(args.profile)
    manifest = _load_plugin(args.plugin_manifest)
    registry = ProfilePolicyRegistry.from_directory(args.profiles)
    decision = evaluate_plugin_policy(manifest, registry.get(profile), profile)
    print(_json({
        "allowed": decision.allowed,
        "profile": profile.value,
        "plugin_id": manifest.plugin_id,
        "reasons": decision.reasons,
    }))
    return 0 if decision.allowed else 3


def _command_contract_probe(args: argparse.Namespace) -> int:
    profile = ExecutionProfile(args.profile)
    plugin_path = REPOSITORY_ROOT / "workers" / "contract_probe" / "plugin.json"
    manifest = _load_plugin(plugin_path)
    registry = ProfilePolicyRegistry.from_directory(args.profiles)
    runner = SubprocessWorkerRunner(
        ArtifactStore(args.store),
        registry,
        worker_cwd=REPOSITORY_ROOT,
    )
    request = StageRequest(
        run_id=args.run_id,
        stage_id="contract-probe",
        stage_kind=StageKind.PROBE,
        plugin_id=manifest.plugin_id,
        plugin_version=manifest.plugin_version,
        profile=profile,
        config={"payload": args.payload, "mode": args.mode},
    )
    outcome = runner.run(request, manifest, timeout_seconds=args.timeout)
    print(outcome.result.model_dump_json(indent=2))
    return 0 if outcome.result.status.value == "succeeded" else 4


def _command_reconstruct_colmap(args: argparse.Namespace) -> int:
    profile = ExecutionProfile(args.profile)
    manifest = _load_plugin(REPOSITORY_ROOT / "workers" / "recon_colmap" / "plugin.json")
    registry = ProfilePolicyRegistry.from_directory(args.profiles)
    runner = SubprocessWorkerRunner(
        ArtifactStore(args.store), registry, worker_cwd=REPOSITORY_ROOT
    )
    executable = args.colmap.resolve()
    request = StageRequest(
        run_id=args.run_id,
        stage_id=f"recon-colmap-{args.scene_id}",
        stage_kind=StageKind.RECONSTRUCTION,
        plugin_id=manifest.plugin_id,
        plugin_version=manifest.plugin_version,
        profile=profile,
        config={
            "config_version": "recon-colmap/v1",
            "colmap_executable": str(executable),
            "colmap_executable_sha256": _sha256_path(executable),
            "images_path": str(args.images.resolve()),
            "expected_image_count": args.expected_image_count,
            "camera_model": args.camera_model,
            "use_gpu": not args.cpu,
            "minimum_registered_ratio": args.minimum_registered_ratio,
            "maximum_reprojection_error_px": args.maximum_reprojection_error,
            "maximum_step_over_median": args.maximum_step_ratio,
        },
    )
    outcome = runner.run(request, manifest, timeout_seconds=args.timeout)
    print(outcome.result.model_dump_json(indent=2))
    if outcome.committed_artifacts:
        print(_json({
            "committed_artifacts": [
                {"artifact_id": item.artifact_id, "path": str(item.path)}
                for item in outcome.committed_artifacts
            ]
        }))
    return 0 if outcome.result.status.value == "succeeded" else 4


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gaussian-factory",
        description="Gaussian Factory P1 validation and interchange CLI",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    prepare = subcommands.add_parser("prepare-benchmark", help="freeze common keyframes and holdouts")
    prepare.add_argument("input", type=Path)
    prepare.add_argument("output", type=Path)
    prepare.add_argument("--fps", type=float, default=15.0)
    prepare.add_argument("--holdout-stride", type=int, default=8)
    prepare.add_argument("--holdout-offset", type=int, default=4)
    prepare.add_argument("--ffmpeg", default="ffmpeg")
    prepare.add_argument("--ffprobe", default="ffprobe")
    prepare.set_defaults(handler=_command_prepare)

    doctor = subcommands.add_parser("doctor", help="record tools, GPU, packages, and input hashes")
    doctor.add_argument("--input", type=Path, default=REPOSITORY_ROOT / "testvid")
    doctor.add_argument("--dataset-manifest", type=Path)
    doctor.add_argument("--colmap", type=Path)
    doctor.add_argument("--output", type=Path)
    doctor.set_defaults(handler=_command_doctor)

    validate_bundle = subcommands.add_parser("validate-bundle", help="integrity-check a SceneBundle")
    validate_bundle.add_argument("bundle", type=Path)
    validate_bundle.set_defaults(handler=_command_validate_bundle)

    validate_ply = subcommands.add_parser("validate-gaussian-ply", help="strictly validate graphdeco-gs-v1 PLY")
    validate_ply.add_argument("ply", type=Path)
    validate_ply.set_defaults(handler=_command_validate_ply)

    export_ply = subcommands.add_parser("export-gaussian-ply", help="export a SceneBundle Gaussian payload")
    export_ply.add_argument("bundle", type=Path)
    export_ply.add_argument("output", type=Path)
    export_ply.add_argument("--overwrite", action="store_true")
    export_ply.set_defaults(handler=_command_export_ply)

    schema = subcommands.add_parser("schema", help="print canonical P1 JSON Schemas")
    schema.add_argument("--output", type=Path)
    schema.set_defaults(handler=_command_schema)

    profile = subcommands.add_parser("profile-check", help="evaluate a plugin against a host profile")
    profile.add_argument("plugin_manifest", type=Path)
    profile.add_argument("--profile", choices=[item.value for item in ExecutionProfile], default="production")
    profile.add_argument("--profiles", type=Path, default=REPOSITORY_ROOT / "configs" / "profiles")
    profile.set_defaults(handler=_command_profile_check)

    probe = subcommands.add_parser("contract-probe", help="run the real subprocess contract probe")
    probe.add_argument("--profile", choices=[item.value for item in ExecutionProfile], default="production")
    probe.add_argument("--profiles", type=Path, default=REPOSITORY_ROOT / "configs" / "profiles")
    probe.add_argument("--store", type=Path, default=REPOSITORY_ROOT / ".gaussian-factory" / "probe-store")
    probe.add_argument("--run-id", default="cli-probe")
    probe.add_argument("--payload", default="ok")
    probe.add_argument("--mode", default="success")
    probe.add_argument("--timeout", type=float, default=10.0)
    probe.set_defaults(handler=_command_contract_probe)

    reconstruct = subcommands.add_parser(
        "reconstruct-colmap", help="run locked COLMAP in an isolated Worker"
    )
    reconstruct.add_argument("scene_id")
    reconstruct.add_argument("images", type=Path)
    reconstruct.add_argument("--expected-image-count", type=int, required=True)
    reconstruct.add_argument("--colmap", type=Path, required=True)
    reconstruct.add_argument(
        "--camera-model", choices=["SIMPLE_RADIAL", "OPENCV"], default="SIMPLE_RADIAL"
    )
    reconstruct.add_argument("--cpu", action="store_true")
    reconstruct.add_argument("--minimum-registered-ratio", type=float, default=0.9)
    reconstruct.add_argument("--maximum-reprojection-error", type=float, default=2.0)
    reconstruct.add_argument("--maximum-step-ratio", type=float, default=4.0)
    reconstruct.add_argument(
        "--profile", choices=[item.value for item in ExecutionProfile], default="production"
    )
    reconstruct.add_argument(
        "--profiles", type=Path, default=REPOSITORY_ROOT / "configs" / "profiles"
    )
    reconstruct.add_argument(
        "--store",
        type=Path,
        default=REPOSITORY_ROOT / ".gaussian-factory" / "artifact-store",
    )
    reconstruct.add_argument("--run-id", default="p1-colmap")
    reconstruct.add_argument("--timeout", type=float, default=600.0)
    reconstruct.set_defaults(handler=_command_reconstruct_colmap)
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        return int(args.handler(args))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
