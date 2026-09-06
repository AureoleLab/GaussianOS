"""Prove whether standalone backbone initialization survives the full checkpoint.

Compare every final parameter and buffer, including non-persistent buffers;
write only hashes, never a second model checkpoint. The production default
remains unchanged until this audit and packaged fallback validation pass.
"""
import gc
import hashlib
import json
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
from workers.recon_mapanything.__main__ import FallbackConfig, _load_model
import torch

stage = root / "build/public-beta/stage"
runtime = stage / "Runtime"
config = FallbackConfig(
    config_version="recon-mapanything/v1", images_path=str(stage), expected_image_count=12,
    mapanything_source=str(runtime / "sources/map-anything-v1.1.2"),
    mapanything_checkpoint=str(runtime / "downloads/map-anything-apache-00f9c245/model.safetensors"),
    mapanything_config=str(runtime / "downloads/map-anything-apache-00f9c245/config.json"),
    dinov2_source=str(runtime / "sources/dinov2-7764ea0"),
    dinov2_checkpoint=str(runtime / "downloads/dinov2-7764ea0/dinov2_vitg14_pretrain.pth"),
    colmap_executable=str(runtime / "tools/colmap/3.13.0/bin/colmap.exe"),
)
results = []
for load_backbone in (True, False):
    torch.manual_seed(42)
    torch.cuda.manual_seed_all(42)
    print(f"LOAD pretrained_backbone={load_backbone}", flush=True)
    model, aliases = _load_model(config, load_backbone_weights=load_backbone)
    hashes = {}
    for kind, entries in (("parameter", model.named_parameters(remove_duplicate=False)),
                           ("buffer", model.named_buffers(remove_duplicate=False))):
        for name, value in entries:
            data = value.detach().contiguous().cpu().numpy()
            hashes[f"{kind}:{name}"] = {"shape": list(data.shape), "dtype": str(data.dtype),
                                       "sha256": hashlib.sha256(data.tobytes()).hexdigest()}
    results.append({"pretrained_backbone": load_backbone, "shared_aliases": aliases, "tensors": hashes})
    print(f"HASHED {len(hashes)} tensors", flush=True)
    del model, value, data
    gc.collect()
    torch.cuda.empty_cache()
report = {"schema_version": "gaussianos-model-initialization-equivalence/v1",
          "identical": results[0]["tensors"] == results[1]["tensors"], "results": results,
          "checkpoint_sha256": "fa06c0fdccefc5048e072c85935d5789b1e36b307f3859033c17f9dcb9fd5201"}
out = root / "build/public-beta/evidence/mapanything-initialization-equivalence.json"
out.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"IDENTICAL={report['identical']}", flush=True)
raise SystemExit(0 if report["identical"] else 1)
