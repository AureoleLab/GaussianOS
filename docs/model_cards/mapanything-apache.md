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

No checkpoint was downloaded and no inference or COLMAP BA bridge was run in
this P1 workspace.  The host's current PyTorch 2.9.1+cu126 build lacks `sm_120`
support for its RTX 5090, so CUDA validation is blocked until an isolated,
compatible worker environment is installed.
