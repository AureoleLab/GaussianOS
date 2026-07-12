"""Real gsplat 1.5.3 CUDA training worker for the P1 benchmark."""

from __future__ import annotations

import argparse
import enum
import hashlib
import json
import math
import os
import sys
import time
import typing
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

# The locked CUDA environment uses Python 3.10.  Keep the compatibility shim
# inside this worker process so the host contracts remain untouched.
if not hasattr(enum, "StrEnum"):
    class _StrEnum(str, enum.Enum):
        def __str__(self) -> str:
            return str(self.value)

    enum.StrEnum = _StrEnum  # type: ignore[attr-defined]
if not hasattr(typing, "Self"):
    from typing_extensions import Self as _Self

    typing.Self = _Self  # type: ignore[attr-defined]

import imageio.v2 as imageio
import lpips
import numpy as np
import cv2
import torch
import torch.nn.functional as F
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from scipy.spatial import cKDTree

from packages.contracts import (
    InputFileHash,
    NormalizationTransform,
    PluginProvenance,
    SceneBundleManifest,
    SphericalHarmonicsSpec,
)
from packages.exportkit import read_gaussian_ply, write_gaussian_ply
from packages.plugin_sdk import (
    ArtifactFile,
    ArtifactManifest,
    ErrorCode,
    QualityCheck,
    QualityReport,
    StageError,
    StageRequest,
    StageResult,
    StageStatus,
)
from packages.quality import read_images_txt
from packages.scene_bundle import CameraTensors, GaussianTensors, write_scene_bundle


GSPLAT_VERSION = "1.5.3"
GSPLAT_COMMIT = "937e29912570c372bed6747a5c9bf85fed877bae"
COLMAP_COMMIT = "0b31f98133b470eae62811b557dc2bcff1e4f9a5"


class TrainConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    config_version: Literal["train-gsplat/v1"]
    scene_id: str = Field(pattern=r"^[0-9A-Za-z._-]+$")
    data_dir: str = Field(min_length=1)
    dataset_manifest: str = Field(min_length=1)
    gsplat_source: str = Field(min_length=1)
    data_factor: int = Field(default=4, ge=1, le=8)
    max_steps: int = Field(ge=1000, le=30000)
    seed: int = Field(default=42, ge=0)
    sh_degree: int = Field(default=3, ge=0, le=3)
    sh_degree_interval: int = Field(default=500, ge=1)
    minimum_psnr_gain_db: float = Field(default=0.25, ge=-20.0)
    reconstruction_plugin_id: Literal["recon.colmap", "recon.mapanything"] = "recon.colmap"


class _P1Parser:
    """Dependency-light COLMAP text reader with the gsplat example data surface."""

    def __init__(self, data_dir: str, factor: int, normalize: bool, test_every: int):
        del test_every
        root = Path(data_dir)
        model = root / "sparse" / "0"
        camera_lines = [
            line.split() for line in (model / "cameras.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        if not camera_lines:
            raise ValueError("COLMAP model contains no cameras")
        camera_data: dict[int, tuple[np.ndarray, tuple[int, int]]] = {}
        for fields in camera_lines:
            camera_id, camera_model = int(fields[0]), fields[1]
            if camera_model not in {"SIMPLE_PINHOLE", "SIMPLE_RADIAL", "PINHOLE"}:
                raise ValueError(f"unsupported COLMAP camera model for gsplat: {camera_model}")
            width, height = int(fields[2]) // factor, int(fields[3]) // factor
            values = [float(value) for value in fields[4:]]
            if camera_model in {"SIMPLE_PINHOLE", "SIMPLE_RADIAL"}:
                fx = fy = values[0] / factor
                cx, cy = values[1] / factor, values[2] / factor
            else:
                fx, fy, cx, cy = (value / factor for value in values[:4])
            camera_data[camera_id] = (
                np.asarray([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float64),
                (width, height),
            )
        poses = read_images_txt(model / "images.txt")
        self.image_names = [pose.image_name for pose in poses]
        image_root = root / (f"images_{factor}" if factor > 1 else "images")
        self.image_paths = [str(image_root / name) for name in self.image_names]
        if not all(Path(path).is_file() for path in self.image_paths):
            raise FileNotFoundError("one or more frozen gsplat input images are missing")
        self.camtoworlds = np.stack([pose.cam2world for pose in poses]).astype(np.float64)
        self.camera_ids = [pose.camera_id for pose in poses]
        self.undistort_map = None
        self.undistort_roi = None
        # P1's single-camera COLMAP path may contain SIMPLE_RADIAL distortion.
        # MapAnything+BA may legitimately produce one PINHOLE per frame, so it
        # bypasses this legacy shared-camera correction.
        if len(camera_data) == 1 and camera_model == "SIMPLE_RADIAL" and len(values) > 3 and values[3] != 0.0:
            k = camera_data[camera_id][0]
            distortion = np.asarray([values[3], 0.0, 0.0, 0.0, 0.0], dtype=np.float64)
            new_k, roi = cv2.getOptimalNewCameraMatrix(k, distortion, (width, height), 0)
            map_x, map_y = cv2.initUndistortRectifyMap(
                k, distortion, None, new_k, (width, height), cv2.CV_32FC1
            )
            x, y, roi_width, roi_height = (int(value) for value in roi)
            new_k[0, 2] -= x
            new_k[1, 2] -= y
            camera_data[camera_id] = (new_k, (width, height))
            self.undistort_map = (map_x, map_y)
            self.undistort_roi = (x, y, roi_width, roi_height)
            width, height = roi_width, roi_height
        self.Ks_dict = {camera_id: item[0] for camera_id, item in camera_data.items()}
        self.params_dict = {camera_id: np.empty(0, dtype=np.float32) for camera_id in camera_data}
        self.imsize_dict = {camera_id: item[1] for camera_id, item in camera_data.items()}
        self.mask_dict = {camera_id: None for camera_id in camera_data}
        positions: list[list[float]] = []
        colors: list[list[int]] = []
        with (model / "points3D.txt").open("r", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip() or line.startswith("#"):
                    continue
                point = line.split()
                positions.append([float(value) for value in point[1:4]])
                colors.append([int(value) for value in point[4:7]])
        self.points = np.asarray(positions, dtype=np.float32)
        self.points_rgb = np.asarray(colors, dtype=np.uint8)
        if len(self.points) < 4:
            raise ValueError("COLMAP seed cloud has fewer than four points")
        transform = np.eye(4, dtype=np.float64)
        if normalize:
            center = self.camtoworlds[:, :3, 3].mean(axis=0)
            radius = np.linalg.norm(self.camtoworlds[:, :3, 3] - center, axis=1).max()
            if not np.isfinite(radius) or radius <= 0:
                raise ValueError("camera normalization radius is invalid")
            scale = 1.0 / radius
            transform[:3, :3] *= scale
            transform[:3, 3] = -scale * center
            self.camtoworlds[:, :3, 3] = (
                scale * self.camtoworlds[:, :3, 3] - scale * center
            )
            self.points = (scale * self.points.astype(np.float64) - scale * center).astype(np.float32)
        self.transform = transform
        camera_center = self.camtoworlds[:, :3, 3].mean(axis=0)
        self.scene_scale = float(np.linalg.norm(self.camtoworlds[:, :3, 3] - camera_center, axis=1).max())


class _P1Dataset:
    def __init__(self, parser: _P1Parser, split: str = "train"):
        del split
        self.parser = parser
        self.indices = np.arange(len(parser.image_names))

    def __len__(self) -> int:
        return len(self.indices)

    def __getitem__(self, item: int) -> dict[str, torch.Tensor]:
        index = int(self.indices[item])
        camera_id = self.parser.camera_ids[index]
        image = imageio.imread(self.parser.image_paths[index])[..., :3]
        if self.parser.undistort_map is not None and self.parser.undistort_roi is not None:
            image = cv2.remap(image, *self.parser.undistort_map, cv2.INTER_LINEAR)
            x, y, width, height = self.parser.undistort_roi
            image = image[y : y + height, x : x + width]
        return {
            "K": torch.from_numpy(self.parser.Ks_dict[camera_id].copy()).float(),
            "camtoworld": torch.from_numpy(self.parser.camtoworlds[index].copy()).float(),
            "image": torch.from_numpy(np.ascontiguousarray(image)).float(),
            "image_id": torch.tensor(item),
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _atomic_result(path: Path, result: StageResult) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    payload = json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False)
    try:
        temporary.write_text(payload + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _failure(request: StageRequest, started: datetime, code: ErrorCode, message: str) -> StageResult:
    return StageResult(
        request_id=request.request_id,
        run_id=request.run_id,
        stage_id=request.stage_id,
        plugin_id=request.plugin_id,
        plugin_version=request.plugin_version,
        status=StageStatus.FAILED,
        started_at=started,
        finished_at=datetime.now(timezone.utc),
        error=StageError(code=code, message=message[:4000], retryable=code is ErrorCode.CUDA_OOM),
    )


def _ssim(x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    """Standard 11x11 Gaussian-window SSIM for NCHW tensors in [0,1]."""
    coords = torch.arange(11, device=x.device, dtype=x.dtype) - 5
    kernel = torch.exp(-(coords * coords) / (2 * 1.5 * 1.5))
    kernel = kernel / kernel.sum()
    window = (kernel[:, None] * kernel[None, :]).expand(3, 1, 11, 11)
    mu_x = F.conv2d(x, window, padding=5, groups=3)
    mu_y = F.conv2d(y, window, padding=5, groups=3)
    sigma_x = F.conv2d(x * x, window, padding=5, groups=3) - mu_x.square()
    sigma_y = F.conv2d(y * y, window, padding=5, groups=3) - mu_y.square()
    sigma_xy = F.conv2d(x * y, window, padding=5, groups=3) - mu_x * mu_y
    c1, c2 = 0.01**2, 0.03**2
    score = ((2 * mu_x * mu_y + c1) * (2 * sigma_xy + c2)) / (
        (mu_x.square() + mu_y.square() + c1) * (sigma_x + sigma_y + c2)
    )
    return score.mean()


def _rgb_to_sh(rgb: torch.Tensor) -> torch.Tensor:
    return (rgb - 0.5) / 0.28209479177387814


def _load_upstream(config: TrainConfig):
    source = Path(config.gsplat_source).resolve()
    if not (source / "examples" / "datasets" / "colmap.py").is_file():
        raise FileNotFoundError("locked gsplat source checkout is incomplete")
    import subprocess

    commit = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True, encoding="utf-8"
    ).strip()
    if commit != GSPLAT_COMMIT:
        raise RuntimeError(f"gsplat source commit mismatch: {commit}")
    from gsplat.rendering import rasterization
    from gsplat.strategy import DefaultStrategy

    return _P1Dataset, _P1Parser, rasterization, DefaultStrategy


def _split_indices(parser, manifest_path: Path, scene_id: str) -> tuple[np.ndarray, np.ndarray, dict]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scene = next(item for item in manifest["scenes"] if item["scene_id"] == scene_id)
    split_by_name = {Path(item["image_path"]).name: item["split"] for item in scene["frames"]}
    missing = sorted(set(parser.image_names) - set(split_by_name))
    if missing:
        raise ValueError(f"COLMAP images are absent from frozen dataset manifest: {missing[:3]}")
    train = np.asarray([i for i, name in enumerate(parser.image_names) if split_by_name[name] == "train"])
    holdout = np.asarray([i for i, name in enumerate(parser.image_names) if split_by_name[name] == "holdout"])
    if len(train) < 3 or len(holdout) < 1:
        raise ValueError("frozen train/holdout split is invalid")
    return train, holdout, scene


def _make_dataset(Dataset, parser, indices: np.ndarray):
    dataset = Dataset(parser, split="train")
    dataset.indices = indices
    return dataset


def _initialize(parser, sh_degree: int, device: torch.device):
    points = np.asarray(parser.points, dtype=np.float32)
    colors = np.asarray(parser.points_rgb, dtype=np.float32) / 255.0
    distances, _ = cKDTree(points).query(points, k=min(4, len(points)))
    scale = np.maximum(np.mean(distances[:, 1:] ** 2, axis=1) ** 0.5, 1e-7)
    scales = np.log(scale).astype(np.float32)[:, None].repeat(3, axis=1)
    n = len(points)
    sh = np.zeros((n, (sh_degree + 1) ** 2, 3), dtype=np.float32)
    sh[:, 0, :] = (colors - 0.5) / 0.28209479177387814
    values = {
        "means": (torch.from_numpy(points), 1.6e-4 * float(parser.scene_scale)),
        "scales": (torch.from_numpy(scales), 5e-3),
        "quats": (torch.randn(n, 4), 1e-3),
        "opacities": (torch.full((n,), torch.logit(torch.tensor(0.1)).item()), 5e-2),
        "sh0": (torch.from_numpy(sh[:, :1, :]), 2.5e-3),
        "shN": (torch.from_numpy(sh[:, 1:, :]), 2.5e-3 / 20),
    }
    params = torch.nn.ParameterDict({k: torch.nn.Parameter(v[0]) for k, v in values.items()}).to(device)
    optimizers = {
        k: torch.optim.Adam([{"params": params[k], "lr": lr, "name": k}], eps=1e-15)
        for k, (_, lr) in values.items()
    }
    return params, optimizers


def _render(rasterization, params, data, sh_degree: int, device: torch.device):
    c2w = data["camtoworld"].to(device).unsqueeze(0)
    k = data["K"].to(device).unsqueeze(0)
    pixels = (data["image"].to(device) / 255.0).unsqueeze(0)
    h, w = pixels.shape[1:3]
    colors, alphas, info = rasterization(
        means=params["means"],
        quats=params["quats"],
        scales=torch.exp(params["scales"]),
        opacities=torch.sigmoid(params["opacities"]),
        colors=torch.cat((params["sh0"], params["shN"]), dim=1),
        viewmats=torch.linalg.inv(c2w),
        Ks=k,
        width=w,
        height=h,
        packed=False,
        absgrad=True,
        sh_degree=sh_degree,
        near_plane=0.01,
        render_mode="RGB",
    )
    return colors.clamp(0, 1), pixels, info


@torch.no_grad()
def _evaluate(rasterization, params, dataset, sh_degree: int, device: torch.device, lpips_model, render_dir: Path | None):
    values = {"psnr": [], "ssim": [], "lpips": []}
    for index in range(len(dataset)):
        render, target, _ = _render(rasterization, params, dataset[index], sh_degree, device)
        mse = F.mse_loss(render, target)
        values["psnr"].append(float((-10.0 * torch.log10(mse.clamp_min(1e-12))).item()))
        render_nchw, target_nchw = render.permute(0, 3, 1, 2), target.permute(0, 3, 1, 2)
        values["ssim"].append(float(_ssim(render_nchw, target_nchw).item()))
        values["lpips"].append(float(lpips_model(render_nchw * 2 - 1, target_nchw * 2 - 1).item()))
        if render_dir is not None:
            canvas = torch.cat((target[0], render[0]), dim=1).mul(255).byte().cpu().numpy()
            imageio.imwrite(render_dir / f"holdout_{index:02d}_gt-render.png", canvas)
    return {key: float(np.mean(items)) for key, items in values.items()}


def _artifact_files(root: Path) -> tuple[ArtifactFile, ...]:
    media = {".json": "application/json", ".ply": "application/vnd.ply", ".png": "image/png", ".safetensors": "application/octet-stream"}
    return tuple(
        ArtifactFile(relative_path=p.relative_to(root).as_posix(), sha256=_sha256(p), size_bytes=p.stat().st_size, media_type=media.get(p.suffix.lower(), "application/octet-stream"))
        for p in sorted(root.rglob("*")) if p.is_file()
    )


def _scene_bundle(config: TrainConfig, parser, params, scene: dict, output: Path) -> tuple[Path, Path, GaussianTensors]:
    means = params["means"].detach().float().cpu().numpy()
    scales = params["scales"].detach().float().clamp(-20, 20).cpu().numpy()
    quats = F.normalize(params["quats"].detach().float(), dim=-1).cpu().numpy()
    # +20 rounds sigmoid to exactly 1 in float32; SceneBundle deliberately
    # rejects that irreversible endpoint.
    opacities = params["opacities"].detach().float().clamp(-15, 15).cpu().numpy()[:, None]
    sh = torch.cat((params["sh0"], params["shN"]), dim=1).detach().float().cpu().numpy()
    gaussians = GaussianTensors(
        means=np.ascontiguousarray(means.astype(np.float32)),
        log_scales=np.ascontiguousarray(scales.astype(np.float32)),
        quats_wxyz=np.ascontiguousarray(quats.astype(np.float32)),
        opacity_logits=np.ascontiguousarray(opacities.astype(np.float32)),
        sh_coeffs=np.ascontiguousarray(sh.astype(np.float32)),
    )
    cameras = CameraTensors(
        camtoworlds=np.ascontiguousarray(parser.camtoworlds.astype(np.float32)),
        intrinsics=np.ascontiguousarray(np.stack([parser.Ks_dict[c] for c in parser.camera_ids]).astype(np.float32)),
        image_sizes=np.ascontiguousarray(np.asarray([parser.imsize_dict[c] for c in parser.camera_ids], dtype=np.int32)),
        camera_ids=np.arange(len(parser.image_names), dtype=np.int64),
    )
    config_hash = _json_hash(config.model_dump(mode="json"))
    model_hash = _json_hash({p.name: _sha256(p) for p in sorted((Path(config.data_dir) / "sparse" / "0").glob("*.txt"))})
    manifest = SceneBundleManifest(
        world_unit="scene_units",
        has_metric_scale=False,
        normalization_transform=NormalizationTransform(source_to_scene=tuple(tuple(float(x) for x in row) for row in parser.transform)),
        spherical_harmonics=SphericalHarmonicsSpec(degree=config.sh_degree),
        color_space="linear_srgb",
        input_files=(InputFileHash(logical_path=f"inputs/{scene['source']['file_name']}", sha256=scene["source"]["sha256"]),),
        reconstruction_plugin=PluginProvenance(
            plugin_id=config.reconstruction_plugin_id,
            plugin_version="v1.1.2" if config.reconstruction_plugin_id == "recon.mapanything" else "3.13.0",
            upstream_commit="c845b8f4f6cde0c20aecd87573656c3f69f5b2b0" if config.reconstruction_plugin_id == "recon.mapanything" else COLMAP_COMMIT,
            config_sha256=model_hash,
            weight_sha256=(),
            code_license="Apache-2.0" if config.reconstruction_plugin_id == "recon.mapanything" else "BSD-3-Clause",
            # The fallback's checkpoint is captured by its reconstruction
            # artifact provenance; the training SceneBundle contains no copied
            # reconstruction weights and therefore has an empty weight list.
            checkpoint_license="NO_CHECKPOINT",
        ),
        trainer_plugin=PluginProvenance(plugin_id="train.gsplat", plugin_version="v1.5.3", upstream_commit=GSPLAT_COMMIT, config_sha256=config_hash, weight_sha256=(), code_license="Apache-2.0", checkpoint_license="NO_CHECKPOINT"),
    )
    bundle_path = output / f"{config.scene_id}.scene-bundle"
    write_scene_bundle(bundle_path, manifest, cameras=cameras, gaussians=gaussians)
    ply_path = output / f"{config.scene_id}.graphdeco-gs-v1.ply"
    write_gaussian_ply(ply_path, gaussians, manifest.spherical_harmonics, color_space="linear_srgb")
    loaded = read_gaussian_ply(ply_path)
    if loaded.means.shape != gaussians.means.shape:
        raise RuntimeError("exported PLY failed self-consumer validation")
    return bundle_path, ply_path, gaussians


def _run(request: StageRequest, started: datetime) -> tuple[StageResult, int]:
    try:
        config = TrainConfig.model_validate(request.config)
        if request.attempt_dir is None or request.attempt_id is None or request.cancellation_file is None:
            raise ValueError("host did not bind attempt paths")
        if request.plugin_id != "train.gsplat" or request.plugin_version != "v1.5.3":
            raise ValueError("request/plugin lock mismatch")
    except (ValidationError, ValueError) as exc:
        return _failure(request, started, ErrorCode.INVALID_REQUEST, str(exc)), 2
    try:
        Dataset, Parser, rasterization, DefaultStrategy = _load_upstream(config)
        import gsplat
        if gsplat.__version__ != GSPLAT_VERSION or not torch.cuda.is_available():
            raise RuntimeError("gsplat 1.5.3 CUDA runtime is unavailable")
        device = torch.device("cuda:0")
        if torch.cuda.get_device_capability(device) != (12, 0):
            raise RuntimeError(f"expected sm_120 GPU, got {torch.cuda.get_device_capability(device)}")
        parser = Parser(data_dir=config.data_dir, factor=config.data_factor, normalize=True, test_every=8)
        train_indices, holdout_indices, scene = _split_indices(parser, Path(config.dataset_manifest), config.scene_id)
        trainset = _make_dataset(Dataset, parser, train_indices)
        holdout = _make_dataset(Dataset, parser, holdout_indices)
        torch.manual_seed(config.seed)
        np.random.seed(config.seed)
        params, optimizers = _initialize(parser, config.sh_degree, device)
        strategy = DefaultStrategy(
            refine_start_iter=500,
            refine_stop_iter=max(501, config.max_steps - 100),
            refine_every=100,
            reset_every=3000,
            verbose=True,
        )
        strategy.check_sanity(params, optimizers)
        strategy_state = strategy.initialize_state(scene_scale=float(parser.scene_scale) * 1.1)
        scheduler = torch.optim.lr_scheduler.ExponentialLR(optimizers["means"], gamma=0.01 ** (1.0 / config.max_steps))
        lpips_model = lpips.LPIPS(net="alex").to(device).eval()
        torch.cuda.reset_peak_memory_stats(device)
        initial = _evaluate(rasterization, params, holdout, 0, device, lpips_model, None)
        training_started = time.perf_counter()
        last_loss = math.inf
        for step in range(config.max_steps):
            if step % 25 == 0 and Path(request.cancellation_file).is_file():
                raise InterruptedError("training cancelled")
            data = trainset[np.random.randint(0, len(trainset))]
            degree = min(step // config.sh_degree_interval, config.sh_degree)
            render, target, info = _render(rasterization, params, data, degree, device)
            strategy.step_pre_backward(params=params, optimizers=optimizers, state=strategy_state, step=step, info=info)
            l1 = F.l1_loss(render, target)
            score = _ssim(render.permute(0, 3, 1, 2), target.permute(0, 3, 1, 2))
            loss = 0.8 * l1 + 0.2 * (1.0 - score)
            loss.backward()
            last_loss = float(loss.item())
            for optimizer in optimizers.values():
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
            scheduler.step()
            strategy.step_post_backward(params=params, optimizers=optimizers, state=strategy_state, step=step, info=info, packed=False)
            if step % 100 == 0:
                print(f"scene={config.scene_id} step={step}/{config.max_steps} loss={last_loss:.6f} gaussians={len(params['means'])}", flush=True)
        torch.cuda.synchronize(device)
        train_seconds = time.perf_counter() - training_started
        peak_vram = torch.cuda.max_memory_allocated(device) / (1024**3)
        output = Path(request.attempt_dir) / "outputs" / f"gsplat-{request.request_id.hex}"
        render_dir = output / "renders"
        render_dir.mkdir(parents=True, exist_ok=False)
        final = _evaluate(rasterization, params, holdout, config.sh_degree, device, lpips_model, render_dir)
        _, ply_path, gaussians = _scene_bundle(config, parser, params, scene, output)
        metrics = {
            "steps": float(config.max_steps), "train_images": float(len(trainset)), "holdout_images": float(len(holdout)),
            "initial_psnr_db": initial["psnr"], "psnr_db": final["psnr"], "psnr_gain_db": final["psnr"] - initial["psnr"],
            "ssim": final["ssim"], "lpips": final["lpips"], "training_seconds": train_seconds,
            "peak_vram_gib": peak_vram, "gaussian_count": float(len(gaussians.means)), "final_loss": last_loss,
            "export_bytes": float(ply_path.stat().st_size),
        }
        (output / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        checks = (
            QualityCheck(check_id="training.native_cuda", passed=Path(gsplat.__file__).with_name("csrc.pyd").is_file(), message=str(Path(gsplat.__file__).with_name("csrc.pyd"))),
            QualityCheck(check_id="training.effective", passed=metrics["psnr_gain_db"] >= config.minimum_psnr_gain_db, message="holdout PSNR improved", metrics={"psnr_gain_db": metrics["psnr_gain_db"]}),
            QualityCheck(check_id="training.finite", passed=all(math.isfinite(v) for v in metrics.values()), message="all metrics are finite"),
            QualityCheck(check_id="export.self_consumer", passed=True, message="ExportKit reloaded exported graphdeco-gs-v1 PLY"),
        )
        if not all(check.passed for check in checks):
            return _failure(request, started, ErrorCode.OUTPUT_VALIDATION_FAILED, f"gsplat quality gate failed: {metrics}"), 10
        artifact = ArtifactManifest(
            artifact_id=output.name, artifact_type="scene_bundle_gaussian", format_version="scene-bundle/v1+graphdeco-gs-v1",
            producer_plugin_id=request.plugin_id, producer_plugin_version=request.plugin_version,
            source_request_id=request.request_id, source_attempt_id=request.attempt_id,
            files=_artifact_files(output), metadata={"scene_id": config.scene_id, "gsplat_commit": GSPLAT_COMMIT, "cuda_arch": "sm_120"},
        )
        quality = QualityReport(passed=True, checks=checks, metrics=metrics)
        return StageResult(request_id=request.request_id, run_id=request.run_id, stage_id=request.stage_id, plugin_id=request.plugin_id, plugin_version=request.plugin_version, status=StageStatus.SUCCEEDED, started_at=started, finished_at=datetime.now(timezone.utc), artifacts=(artifact,), quality_report=quality), 0
    except InterruptedError as exc:
        return _failure(request, started, ErrorCode.CANCELLED, str(exc)), 10
    except torch.cuda.OutOfMemoryError as exc:
        return _failure(request, started, ErrorCode.CUDA_OOM, str(exc)), 10
    except Exception as exc:
        return _failure(request, started, ErrorCode.WORKER_CRASHED, f"{type(exc).__name__}: {exc}"), 10


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-json", type=Path, required=True)
    parser.add_argument("--result-json", type=Path, required=True)
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    try:
        request = StageRequest.model_validate_json(args.request_json.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"invalid request: {exc}", file=sys.stderr)
        return 2
    result, code = _run(request, started)
    _atomic_result(args.result_json, result)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
