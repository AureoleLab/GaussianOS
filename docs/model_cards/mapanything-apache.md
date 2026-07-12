# MapAnything Apache model card

## Identity and intended role

- Role: automatic reconstruction fallback when the default COLMAP path fails,
  followed by COLMAP bundle adjustment.
- Code: `facebookresearch/map-anything` tag `v1.1.2`, commit
  `c845b8f4f6cde0c20aecd87573656c3f69f5b2b0`.
- Checkpoint repository: `facebook/map-anything-apache`, revision
  `00f9c245bbcb60522d1ed7f9e9d88462c6e3f38a`.
- Artifact: `model.safetensors`, 4,914,062,480 bytes, SHA-256
  `fa06c0fdccefc5048e072c85935d5789b1e36b307f3859033c17f9dcb9fd5201`.
- Code and checkpoint license: Apache-2.0, as stated by the
  [official repository](https://github.com/facebookresearch/map-anything/tree/c845b8f4f6cde0c20aecd87573656c3f69f5b2b0)
  and [official model card](https://huggingface.co/facebook/map-anything-apache).
- Required DINOv2 ViT-g/14 backbone: commit
  `7764ea0f912e53c92e82eb78a2a1631e92725fc8`, official
  `dinov2_vitg14_pretrain.pth`, 4,546,108,579 bytes, SHA-256
  `baf8467e50af277596bbbafa06887c177ee899ab46033649c383577d7e9309d3`.
  The DINOv2 model card declares Apache-2.0. It is now an explicit production
  checkpoint lock rather than an implicit `torch.hub` download.

## Interface expectations

The upstream project supports multi-image reconstruction and can export COLMAP
data.  The P1 adapter must still validate, rather than assume, camera direction,
intrinsics scaling, metric-scale flags, image ordering, confidence thresholds,
and handedness before converting results into SceneBundle.  COLMAP bundle
adjustment must consume the exact frozen training frames; holdout frames must
never enter reconstruction or BA.

## Eligibility and limitations

The Apache variant is license-eligible for the production fallback.  The
similarly named `facebook/map-anything` checkpoint is CC-BY-NC-4.0 and must not
be substituted.  Selection must match the full repository id and verify the
downloaded SHA-256 before model loading.

## P1 execution result

Both checkpoints were downloaded and hash-verified. An isolated Python 3.12.13,
PyTorch 2.9.1+cu130 Worker ran on RTX 5090 (`sm_120`). The deterministic hard
case produced no COLMAP matches (0/12 registered), then MapAnything recovered
12/12 cameras, exported a COLMAP 3.13 model, and COLMAP bundle adjustment
converged in 5 iterations. The BA model contains 7,989 multi-view points with
mean track length 6.347227. Canonical OpenCV cam2world `CameraTensors` validation
passed. A normal 39-frame scene registered 39/39 in COLMAP and the fallback was
correctly denied before model loading.

The upstream exporter targets pycolmap 3.10. The Worker carries a repository-owned
3.13 adapter for Rig/Frame pose registration and removes single-view points before
BA; no upstream source is modified. Reconstruction-stage validation covers the
SceneBundle camera payload only and does not claim that Gaussian training ran.
