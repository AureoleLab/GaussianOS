from workers._unavailable import run_unavailable
raise SystemExit(run_unavailable("train.gsplat", "PyTorch cu130 CUDA smoke passed, but gsplat extension build is blocked by missing CUDA 13 nvcc and MSVC cl"))
