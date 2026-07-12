# Gaussian PLY compatibility harness

`test_graphdeco_consumers.py` keeps consumer identities explicit:

- ExportKit strict loader: first-party structural and numeric validation.
- `plyfile==1.1.3`: independent general-purpose PLY parser.
- `gsply==0.4.6`: independent Gaussian-specific parser, including exact SH recovery.
- SplatTransform `v3.0.0` (`daf6338…`): independent Gaussian CLI. Run this network/cache-dependent check with `GAUSSIAN_FACTORY_RUN_EXTERNAL_COMPAT=1`.

The harness does **not** claim Brush compatibility. Brush needs its separately pinned
binary plus a real load/render check; it is unavailable in the current environment.
