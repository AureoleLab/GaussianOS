# P1 model cards

These cards record eligibility and evidence; they do not claim benchmark
success.  Code-only tools such as FFmpeg, COLMAP, gsplat, Faster-GS, Brush, and
SplatTransform are indexed in `third_party/licenses/SOURCES.md` and pinned in
`third_party/locks/p1_candidates.lock.json`.

| Candidate | Profile | Checkpoint lock | P1 execution status |
|---|---|---|---|
| [MapAnything Apache](mapanything-apache.md) | production fallback candidate | complete | not downloaded; not run |
| [GLUEMAP](gluemap-research-only.md) | research-only | incomplete multi-model closure | blocked |
| [VGGT-Ω](vggt-omega-research-only.md) | research-only | revision known, hashes gated | blocked |
| [ImprovedGS](improvedgs-research-only.md) | research-only | no pretrained weight required | not run |

The production profile must reject every card marked research-only before any
worker process is launched.
