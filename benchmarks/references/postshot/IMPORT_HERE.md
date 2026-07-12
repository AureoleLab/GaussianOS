# Postshot reference — WAITING_FOR_REFERENCE

Import one subdirectory per scene (`001`, `002`, `003`) containing:

- the untouched Postshot Gaussian export or project export;
- fixed-camera PNG renders corresponding to every frozen holdout frame;
- `reference.manifest.json` with Postshot version, source video SHA-256,
  export/render file SHA-256 values, render resolution, color space, and the
  camera mapping to `benchmark_runs/p1_dataset_v1/dataset.manifest.json`;
- optional operator notes and runtime/VRAM measurements, clearly marked as
  measured or unavailable.

Do not substitute screenshots from another scene or estimate missing metrics.
