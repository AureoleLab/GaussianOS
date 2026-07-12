# GLUEMAP model card — research-only

## Identity

- Code: `colmap/gluemap` commit
  `adc9e4bb5f41014d3f7c157a879edc278588c829` (`main`, no release tag).
- Package version at that commit: `0.1.0`.
- GLUEMAP code license: BSD-3-Clause.
- Official sources: [repository](https://github.com/colmap/gluemap/tree/adc9e4bb5f41014d3f7c157a879edc278588c829)
  and [paper/project references](https://github.com/colmap/gluemap/tree/adc9e4bb5f41014d3f7c157a879edc278588c829#gluemap-global-structure-from-motion-meets-feedforward-reconstruction).

## Why it is isolated

Product policy classifies GLUEMAP as research-only even though its own code is
permissively licensed.  Upstream explicitly limits that license statement to
GLUEMAP itself.  The default pipeline expects Pi3, SALAD, VGGSfM tracker, and
Doppelgangers++ checkpoints and vendors several feed-forward projects as
submodules.  Those exact checkpoint revisions, SHA-256 values, and license
obligations are not closed in P1.

The lock therefore sets `execution_allowed=false`.  A future research run must
first add every code/submodule commit and every checkpoint hash, then execute
only through `recon_gluemap` under the research profile.  No GLUEMAP code or
model is eligible for the production dependency graph.

## Execution status

Not installed and not run.  No reconstruction, registration ratio, trajectory,
or quality result is claimed.
