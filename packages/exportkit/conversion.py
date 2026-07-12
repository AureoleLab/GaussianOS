"""SceneBundle <-> graphdeco-gs-v1 PLY conversion entry points."""

from __future__ import annotations

import os
from pathlib import Path

from packages.contracts import SceneBundleManifest, ScenePayloadIndex
from packages.scene_bundle import (
    CameraTensors,
    SceneBundle,
    load_scene_bundle,
    write_scene_bundle,
)

from .ply import read_gaussian_ply_document, write_gaussian_ply


def _without_payload_references(manifest: SceneBundleManifest) -> SceneBundleManifest:
    return manifest.model_copy(update={"payloads": ScenePayloadIndex()})


def scene_bundle_to_gaussian_ply(
    bundle: SceneBundle | str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    overwrite: bool = False,
) -> Path:
    loaded = load_scene_bundle(bundle) if not isinstance(bundle, SceneBundle) else bundle
    if loaded.gaussians is None:
        raise ValueError("SceneBundle has no Gaussian payload")
    return write_gaussian_ply(
        destination,
        loaded.gaussians,
        loaded.manifest.spherical_harmonics,
        color_space=loaded.manifest.color_space,
        overwrite=overwrite,
    )


def gaussian_ply_to_scene_bundle(
    source: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    manifest: SceneBundleManifest,
    cameras: CameraTensors | None = None,
) -> SceneBundle:
    """Import PLY values while requiring truthful provenance from the caller.

    PLY cannot carry all required SceneBundle provenance. The caller must provide a
    manifest obtained from a trusted pipeline record; this function never invents it.
    """

    document = read_gaussian_ply_document(source)
    metadata = document.metadata
    if metadata.spherical_harmonics != manifest.spherical_harmonics:
        raise ValueError("PLY SH convention does not match the supplied SceneBundle manifest")
    if metadata.quaternion_order != manifest.quaternion_order:
        raise ValueError(
            "PLY quaternion order does not match the supplied SceneBundle manifest"
        )
    if metadata.color_space != manifest.color_space:
        raise ValueError("PLY color space does not match the supplied SceneBundle manifest")
    return write_scene_bundle(
        destination,
        _without_payload_references(manifest),
        cameras=cameras,
        gaussians=document.gaussians,
    )
