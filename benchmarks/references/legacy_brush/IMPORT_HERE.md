# Legacy COLMAP + Brush reference — WAITING_FOR_REFERENCE

Import one subdirectory per scene (`001`, `002`, `003`) containing:

- the original Gaussian PLY produced by the old workflow;
- fixed-camera PNG renders corresponding to every frozen holdout frame;
- `reference.manifest.json` with COLMAP/Brush versions, all source and output
  SHA-256 values, render settings, and frozen-camera mapping;
- any recorded training time, peak VRAM, Gaussian count, and operator notes.

The installed Brush 0.3.0 compatibility binary is not itself an old-workflow
reference and must not be used to fabricate one.
