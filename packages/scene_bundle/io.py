"""Integrity-checked safetensors persistence for SceneBundle v1."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np
import numpy.typing as npt
from safetensors import safe_open
from safetensors.numpy import load_file, save_file

from packages.contracts import (
    SCENE_BUNDLE_SCHEMA_VERSION,
    SceneBundleManifest,
    ScenePayloadIndex,
    TensorArtifactReference,
    TensorSpec,
)

from .tensors import CameraTensors, GaussianTensors, TensorValidationError


MANIFEST_FILENAME = "manifest.json"
CAMERAS_FILENAME = "cameras.safetensors"
GAUSSIANS_FILENAME = "gaussians.safetensors"


class SceneBundleIOError(ValueError):
    """Raised when a SceneBundle cannot be committed or integrity-checked."""


@dataclass(frozen=True, slots=True)
class SceneBundle:
    root: Path
    manifest: SceneBundleManifest
    cameras: CameraTensors | None
    gaussians: GaussianTensors | None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tensor_specs(
    tensors: Mapping[str, npt.NDArray[np.generic]],
) -> dict[str, TensorSpec]:
    return {
        name: TensorSpec(dtype=tensor.dtype.name, shape=tuple(tensor.shape))
        for name, tensor in sorted(tensors.items())
    }


def _artifact_reference(
    path: Path,
    relative_path: str,
    tensors: Mapping[str, npt.NDArray[np.generic]],
) -> TensorArtifactReference:
    return TensorArtifactReference(
        relative_path=relative_path,
        sha256=_sha256(path),
        byte_size=path.stat().st_size,
        tensors=_tensor_specs(tensors),
    )


def _canonical_manifest_bytes(manifest: SceneBundleManifest) -> bytes:
    payload = manifest.model_dump(mode="json")
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def write_scene_bundle(
    directory: str | os.PathLike[str],
    manifest: SceneBundleManifest,
    *,
    cameras: CameraTensors | None = None,
    gaussians: GaussianTensors | None = None,
) -> SceneBundle:
    """Validate, stage, and atomically commit a new SceneBundle directory.

    Existing output directories are never overwritten. This mirrors the pipeline's
    immutable artifact/attempt-directory contract.
    """

    destination = Path(directory).absolute()
    if destination.exists():
        raise FileExistsError(f"SceneBundle destination already exists: {destination}")
    if cameras is None and gaussians is None:
        raise SceneBundleIOError("a SceneBundle must contain cameras, Gaussians, or both")
    if manifest.payloads.cameras is not None or manifest.payloads.gaussians is not None:
        raise SceneBundleIOError("writer requires a manifest template without payload references")
    if gaussians is not None and (
        gaussians.sh_degree != manifest.spherical_harmonics.degree
    ):
        raise SceneBundleIOError(
            "Gaussian SH degree does not match manifest spherical_harmonics.degree"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.attempt-", dir=str(destination.parent)
        )
    )
    try:
        camera_ref: TensorArtifactReference | None = None
        gaussian_ref: TensorArtifactReference | None = None

        if cameras is not None:
            camera_tensors = cameras.to_safetensors()
            camera_path = staging / CAMERAS_FILENAME
            save_file(
                camera_tensors,
                str(camera_path),
                metadata={
                    "schema_version": SCENE_BUNDLE_SCHEMA_VERSION,
                    "payload_kind": "cameras",
                    "camera_convention": "opencv_cam2world",
                },
            )
            camera_ref = _artifact_reference(
                camera_path, CAMERAS_FILENAME, camera_tensors
            )

        if gaussians is not None:
            gaussian_tensors = gaussians.to_safetensors()
            gaussian_path = staging / GAUSSIANS_FILENAME
            save_file(
                gaussian_tensors,
                str(gaussian_path),
                metadata={
                    "schema_version": SCENE_BUNDLE_SCHEMA_VERSION,
                    "payload_kind": "gaussians",
                    "quaternion_order": "wxyz",
                    "scale_encoding": "natural_log",
                    "opacity_encoding": "logit",
                    "sh_degree": str(gaussians.sh_degree),
                },
            )
            gaussian_ref = _artifact_reference(
                gaussian_path, GAUSSIANS_FILENAME, gaussian_tensors
            )

        committed_manifest = manifest.model_copy(
            update={
                "payloads": ScenePayloadIndex(
                    cameras=camera_ref,
                    gaussians=gaussian_ref,
                )
            }
        )
        manifest_bytes = _canonical_manifest_bytes(committed_manifest)
        # Re-validate serialized JSON before making the directory visible.
        SceneBundleManifest.model_validate_json(manifest_bytes)
        (staging / MANIFEST_FILENAME).write_bytes(manifest_bytes)
        os.replace(staging, destination)
    except Exception:
        if staging.exists() and staging.parent == destination.parent:
            shutil.rmtree(staging)
        raise

    return load_scene_bundle(destination)


def _resolve_artifact(root: Path, reference: TensorArtifactReference) -> Path:
    root_resolved = root.resolve(strict=True)
    unresolved = root / Path(reference.relative_path)
    if unresolved.is_symlink():
        raise SceneBundleIOError(f"payload symlinks are not allowed: {reference.relative_path}")
    candidate = unresolved.resolve(strict=True)
    if candidate.parent != root_resolved:
        raise SceneBundleIOError(
            f"payload must be a direct child of the SceneBundle: {reference.relative_path}"
        )
    if not candidate.is_file():
        raise SceneBundleIOError(f"payload must be a regular file: {candidate}")
    return candidate


def _load_tensor_artifact(
    root: Path,
    reference: TensorArtifactReference,
    *,
    expected_filename: str,
    payload_kind: str,
) -> dict[str, npt.NDArray[np.generic]]:
    if reference.relative_path != expected_filename:
        raise SceneBundleIOError(
            f"{payload_kind} payload must be named {expected_filename}"
        )
    path = _resolve_artifact(root, reference)
    if path.stat().st_size != reference.byte_size:
        raise SceneBundleIOError(f"byte size mismatch for {path.name}")
    if _sha256(path) != reference.sha256:
        raise SceneBundleIOError(f"SHA-256 mismatch for {path.name}")

    try:
        with safe_open(path, framework="np") as handle:
            metadata = handle.metadata() or {}
    except Exception as exc:
        raise SceneBundleIOError(f"invalid safetensors file {path.name}: {exc}") from exc
    if metadata.get("schema_version") != SCENE_BUNDLE_SCHEMA_VERSION:
        raise SceneBundleIOError(f"wrong schema_version metadata in {path.name}")
    if metadata.get("payload_kind") != payload_kind:
        raise SceneBundleIOError(f"wrong payload_kind metadata in {path.name}")

    try:
        tensors = load_file(path)
    except Exception as exc:
        raise SceneBundleIOError(f"cannot load safetensors file {path.name}: {exc}") from exc
    actual_specs = _tensor_specs(tensors)
    if actual_specs != reference.tensors:
        raise SceneBundleIOError(f"tensor schema mismatch for {path.name}")
    return tensors


def load_scene_bundle(directory: str | os.PathLike[str]) -> SceneBundle:
    root = Path(directory).absolute()
    if not root.is_dir():
        raise SceneBundleIOError(f"SceneBundle directory does not exist: {root}")
    manifest_path = root / MANIFEST_FILENAME
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise SceneBundleIOError(f"missing regular {MANIFEST_FILENAME}")
    try:
        manifest = SceneBundleManifest.model_validate_json(manifest_path.read_bytes())
    except Exception as exc:
        raise SceneBundleIOError(f"invalid SceneBundle manifest: {exc}") from exc
    if manifest.payloads.cameras is None and manifest.payloads.gaussians is None:
        raise SceneBundleIOError("manifest does not reference any payload")

    cameras: CameraTensors | None = None
    gaussians: GaussianTensors | None = None
    try:
        if manifest.payloads.cameras is not None:
            tensors = _load_tensor_artifact(
                root,
                manifest.payloads.cameras,
                expected_filename=CAMERAS_FILENAME,
                payload_kind="cameras",
            )
            cameras = CameraTensors.from_safetensors(tensors)

        if manifest.payloads.gaussians is not None:
            tensors = _load_tensor_artifact(
                root,
                manifest.payloads.gaussians,
                expected_filename=GAUSSIANS_FILENAME,
                payload_kind="gaussians",
            )
            gaussians = GaussianTensors.from_safetensors(tensors)
            if gaussians.sh_degree != manifest.spherical_harmonics.degree:
                raise SceneBundleIOError(
                    "Gaussian SH degree does not match manifest spherical_harmonics.degree"
                )
    except TensorValidationError as exc:
        raise SceneBundleIOError(f"invalid SceneBundle tensor payload: {exc}") from exc

    return SceneBundle(
        root=root,
        manifest=manifest,
        cameras=cameras,
        gaussians=gaussians,
    )
