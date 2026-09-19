# Gaussian PLY compatibility harness

`test_graphdeco_consumers.py` keeps consumer identities explicit:

- ExportKit strict loader: first-party structural and numeric validation.
- `plyfile==1.1.3`: independent general-purpose PLY parser.
- `gsply==0.4.6`: independent Gaussian-specific parser, including exact SH recovery.
- SplatTransform `v3.0.0` (`daf6338…`): independent Gaussian CLI. Run this network/cache-dependent check with `GAUSSIAN_FACTORY_RUN_EXTERNAL_COMPAT=1`.

- Brush `0.3.0`: independent CLI loading with a malformed-file negative control.
  Enable external compatibility and set `GAUSSIAN_FACTORY_BRUSH_EXE` to the
  pinned binary. This proves file loading, not a rendered Brush scene.

RC6 acceptance also loaded the actual ordinary and fallback exported Gaussian
PLY files with all four independent consumers, beyond the synthetic unit fixture.
