from workers._unavailable import run_unavailable
raise SystemExit(run_unavailable("frame_qc.builtin", "frame QC library exists, but its artifact worker adapter is not implemented in P1"))
