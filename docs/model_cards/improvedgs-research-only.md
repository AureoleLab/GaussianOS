# ImprovedGS model card — research-only

## Identity and license

- Code: `XiaoBin2001/Improved-GS` commit
  `20b5db343a87c2f9fb4b70c6e39ff1f042a8a47a` (`main`, no release tag).
- License: ImprovedGS Non-Commercial Research License.
- Official sources: [repository](https://github.com/XiaoBin2001/Improved-GS/tree/20b5db343a87c2f9fb4b70c6e39ff1f042a8a47a),
  [license](https://github.com/XiaoBin2001/Improved-GS/blob/20b5db343a87c2f9fb4b70c6e39ff1f042a8a47a/LICENSE.md),
  and [project page](https://xiaobin2001.github.io/improved-gs-web/).

The repository's license permits non-commercial research, education, and
evaluation only.  It also identifies separately licensed third-party code,
including Gaussian-Splatting-licensed `simple-knn` and MIT `fused-ssim`.
Consequently it cannot enter the production profile, binary, or dependency
closure.

## Runtime and execution status

Upstream recommends Python 3.10.19, CUDA 12.1, and PyTorch 2.1.1+cu121, while
also warning that other combinations were not systematically tested.  The P1
host is Python 3.13.9 with CUDA toolkit 12.6 and an RTX 5090; its installed
PyTorch lacks `sm_120`.  No ImprovedGS environment was created and no training
was run.  Any future evaluation must be isolated in `train_improvedgs` under the
research profile and must retain all third-party notices.
