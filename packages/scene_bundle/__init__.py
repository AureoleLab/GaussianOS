"""SceneBundle v1 tensor validation and safe persistence."""

from .io import (
    CAMERAS_FILENAME,
    GAUSSIANS_FILENAME,
    MANIFEST_FILENAME,
    SceneBundle,
    SceneBundleIOError,
    load_scene_bundle,
    write_scene_bundle,
)

from .tensors import (
    CameraTensors,
    GaussianTensors,
    PointCloudTensors,
    TensorValidationError,
)

__all__ = [
    "CAMERAS_FILENAME",
    "GAUSSIANS_FILENAME",
    "MANIFEST_FILENAME",
    "CameraTensors",
    "GaussianTensors",
    "PointCloudTensors",
    "SceneBundle",
    "SceneBundleIOError",
    "TensorValidationError",
    "load_scene_bundle",
    "write_scene_bundle",
]
