# P1 benchmark protocol

P1 uses one immutable dataset manifest for every reconstruction and trainer.
`benchmarks.protocol` samples each source video at 15 fps, assigns holdouts by a
fixed index rule, hashes every source and PNG, and records the exact FFmpeg
executable hash.  Frame QC is advisory only: candidates may not silently drop
different frames, because that would invalidate comparison.

The prepared local dataset is outside Git at
`benchmark_runs/p1_dataset_v1/dataset.manifest.json`.  Its identity is:

`sha256:152be2c9901a8652daa032ab5c35a65aaf3aa83fc1deb1a1afa41a2a2a3ab33d`

| Scene | Frozen frames | Train | Holdout |
|---|---:|---:|---:|
| 001 | 39 | 34 | 5 |
| 002 | 33 | 29 | 4 |
| 003 | 42 | 37 | 5 |

## Commands already run

```powershell
uv run python -m benchmarks.prepare_dataset I:\GaussianOS\testvid I:\GaussianOS\benchmark_runs\p1_dataset_v1 --fps 15 --holdout-stride 8 --holdout-offset 4
python benchmarks/probe_environment.py --input-dir testvid --dataset-manifest benchmark_runs/p1_dataset_v1/dataset.manifest.json --colmap .gaussian-factory/tools/colmap/3.13.0/bin/colmap.exe --output benchmarks/evidence/p1_environment.json
```

The preparation command refuses to overwrite a frozen scene directory.  Use a
new output directory if the sampling protocol changes; never mutate a dataset
used by existing result rows.

## Evidence and result files

- `evidence/p1_environment.json`: actual host, executable hashes, input hashes,
  media metadata, frozen split summary, and an explicit statement that the
  probe itself does not launch reconstruction or training.
- `evidence/ply_consumer_compatibility.json`: actual four-consumer test result
  for the generated Graphdeco PLY fixture, plus the explicit Brush gap.
- `evidence/gsplat_training.json`: native build identity and three formal
  7000-step training results.
- `evidence/trained_ply_consumers.json`: actual trained-scene PLY loading in
  ExportKit, gsply, SplatTransform, and Brush.
- `evidence/mapanything_fallback.json`: hard-case trigger, Apache inference,
  COLMAP export/BA, canonical camera validation, and normal-scene no-trigger.
- `references/`: explicit Postshot and legacy import contract; currently
  `WAITING_FOR_REFERENCE`.
- `benchmark_matrix.csv`: required candidate/profile combinations and current
  truthful state.
- `report_template.md`: metric schema for one completed run.
- `manual_visual_scorecard.csv`: fixed-camera human comparison form.
- `P1_BENCHMARK_STATUS.md`: current P1 result/status report.

Each run must store its StageRequest, StageResult, config hash, code/checkpoint
locks, stdout/stderr, GPU telemetry, camera output, rendered holdouts, PLY, and
consumer logs in an independent attempt directory.  A row is valid only when it
references the frozen dataset id above and all artifacts pass validation.

## Fairness rules

1. Reconstruction sees train frames only.  Holdouts are reserved for rendering
   metrics and fixed-camera comparisons.
2. Every candidate receives byte-identical PNGs in manifest order.
3. Candidate-specific preprocessing must be recorded and may resize pixels but
   may not change the selected image set.
4. Registered-frame ratio uses the frozen train-frame count as denominator.
5. PSNR, SSIM, and LPIPS use the same color-space conversion and crop/mask.
6. Peak VRAM is sampled over the complete worker lifetime after a GPU reset or a
   recorded clean baseline.
7. `NOT_RUN`, `BLOCKED`, and `FAILED` are results; they must never be converted
   to zero or omitted from aggregate tables.
8. Research-only candidates may run only from the research profile.  Their
   artifacts cannot be promoted into a production attempt.
