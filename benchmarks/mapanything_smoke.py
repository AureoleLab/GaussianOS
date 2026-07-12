"""Load the pinned Apache checkpoint locally and run real CUDA inference."""

from __future__ import annotations

import argparse
import gc
import json
import subprocess
import time
from pathlib import Path

import torch
from safetensors.torch import load_file

from mapanything.models import MapAnything
from mapanything.utils.image import load_images


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--dinov2-source", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("images", nargs="+")
    args = parser.parse_args()
    source_commit = subprocess.check_output(
        ["git", "-C", str(args.source), "rev-parse", "HEAD"], text=True, encoding="utf-8"
    ).strip()
    dino_commit = subprocess.check_output(
        ["git", "-C", str(args.dinov2_source), "rev-parse", "HEAD"], text=True, encoding="utf-8"
    ).strip()
    if source_commit != "c845b8f4f6cde0c20aecd87573656c3f69f5b2b0":
        raise RuntimeError("MapAnything source commit mismatch")
    if dino_commit != "7764ea0f912e53c92e82eb78a2a1631e92725fc8":
        raise RuntimeError("DINOv2 source commit mismatch")
    config = json.loads((args.checkpoint_dir / "config.json").read_text(encoding="utf-8"))
    # The full encoder is present in the Apache checkpoint. Avoid an unrelated
    # torch.hub network fetch before loading those exact local tensors.
    config["encoder_config"]["uses_torch_hub"] = False
    original_hub_load = torch.hub.load

    def pinned_hub_load(repo_or_dir, model, *model_args, **kwargs):
        if repo_or_dir == "facebookresearch/dinov2":
            kwargs["source"] = "local"
            kwargs.pop("force_reload", None)
            return original_hub_load(str(args.dinov2_source.resolve()), model, *model_args, **kwargs)
        return original_hub_load(repo_or_dir, model, *model_args, **kwargs)

    torch.hub.load = pinned_hub_load
    model = MapAnything(**config)
    state = load_file(str(args.checkpoint_dir / "model.safetensors"), device="cpu")
    loaded_keys = set(state)
    # The upstream local-weight demo deliberately uses strict=False because
    # this checkpoint deduplicates shared DPT module aliases in safetensors.
    incompatible = model.load_state_dict(state, strict=False)
    model_state = model.state_dict()
    loaded_storage = {
        model_state[key].untyped_storage().data_ptr()
        for key in loaded_keys
        if key in model_state
    }
    uncovered = [
        key for key in incompatible.missing_keys
        if model_state[key].untyped_storage().data_ptr() not in loaded_storage
    ]
    if incompatible.unexpected_keys or uncovered:
        raise RuntimeError("non-alias checkpoint incompatibility")
    del state
    gc.collect()
    device = torch.device("cuda:0")
    model = model.to(device).eval()
    views = load_images([str(path) for path in args.images])
    torch.cuda.reset_peak_memory_stats(device)
    started = time.perf_counter()
    with torch.inference_mode():
        outputs = model.infer(
            views,
            memory_efficient_inference=True,
            minibatch_size=1,
            use_amp=True,
            amp_dtype="bf16",
            apply_mask=True,
            mask_edges=True,
            apply_confidence_mask=False,
        )
    torch.cuda.synchronize(device)
    result = {
        "device": torch.cuda.get_device_name(device),
        "capability": list(torch.cuda.get_device_capability(device)),
        "views": len(outputs),
        "resolution": list(outputs[0]["depth_z"].shape),
        "finite_camera_poses": all(torch.isfinite(item["camera_poses"]).all().item() for item in outputs),
        "finite_depth": all(torch.isfinite(item["depth_z"]).all().item() for item in outputs),
        "shared_alias_missing_key_count": len(incompatible.missing_keys),
        "uncovered_missing_key_count": len(uncovered),
        "unexpected_key_count": len(incompatible.unexpected_keys),
        "seconds": time.perf_counter() - started,
        "peak_vram_gib": torch.cuda.max_memory_allocated(device) / (1024**3),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
