"""Create a deterministic low-detail case from real frozen P1 frames."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmark_runs" / "p1_dataset_v1" / "dataset.manifest.json"
OUTPUT = ROOT / "benchmark_runs" / "mapanything-fallback" / "hard-case-001" / "images"


def main() -> int:
    dataset = json.loads(MANIFEST.read_text(encoding="utf-8"))
    scene = next(item for item in dataset["scenes"] if item["scene_id"] == "001")
    train = [item for item in scene["frames"] if item["split"] == "train"]
    selected = [train[round(i * (len(train) - 1) / 11)] for i in range(12)]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for stale in OUTPUT.glob("*"):
        if stale.is_file():
            stale.unlink()
    records = []
    for output_index, frame in enumerate(selected):
        source = ROOT / "benchmark_runs" / "p1_dataset_v1" / frame["image_path"]
        with Image.open(source) as image:
            image = image.convert("RGB").resize((256, 144), Image.Resampling.LANCZOS)
            image = image.filter(ImageFilter.GaussianBlur(radius=2.5))
            image = ImageEnhance.Contrast(image).enhance(0.58)
            image = ImageEnhance.Brightness(image).enhance(0.72 if output_index % 2 else 1.0)
            target = OUTPUT / f"hard_{output_index:03d}.png"
            image.save(target, format="PNG")
        records.append({
            "output": target.name,
            "source_frame_id": frame["frame_id"],
            "source_sha256": frame["sha256"],
        })
    manifest = {
        "schema_version": "mapanything-hard-case/v1",
        "description": "12 real frames, 256x144, Gaussian blur 2.5 px, contrast 0.58, alternating exposure",
        "expected_images": 12,
        "records": records,
    }
    (OUTPUT.parent / "hard-case.manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
