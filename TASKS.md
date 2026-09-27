# TASKS.md — STEPoscope as orientation oracle for SteppifySOLID

## Context (why this exists)

SteppifySOLID (`/home/fat64/repos/SteppifySOLID`) hand-writes AP203 STEP and is
debugging inverted `ADVANCED_FACE` sense flags (`.T.`/`.F.`) — face normals
pointing into the material. OCCT-based judges (FreeCAD, Plasticity) silently
heal inconsistent shells on import, so they mask this bug class. STEPoscope
parses AP203 line-by-line and never heals → it is the raw ground-truth judge.
Hard rule: **never repair/snap/reorient input geometry; deterministic output.**

## Current state (verified working 2026-09-25 — do not redo)

- Headless CLI works: `python -m step_explorer render FILE... --out DIR
  [--mode normals|shaded]`, per-file `<stem>.png`+`<stem>.json`, exit codes
  0/1/2 behave.
- Sense flag applied to triangle winding for PLANE + CYLINDRICAL_SURFACE
  (`geometry/builder.py::_oriented_face_triangles`).
- Judge caught SteppifySOLID's known bugs exactly: pre-fix complex2 flagged
  only face #35, surbord2 only #83; both clean post-fix (surbod2 V=1773.86 ≈
  OCCT oracle 1774.25).
- BUT the v1 verdict criterion is proven wrong (see Task 1): SolidWorks' own
  reference files mass-flag (resistor ref: 267 faces, cubecluster: 19, plus
  boxcyl1 / complex1_ap203 / complex4 / complex5 / cylinder5 / cylinder6 /
  polygon1 / revolve1 / ear / slotfillet1 / torus1).

## Progress (2026-09-26)

- Task 1 complete: reports now include `verdict`, `n_boundary_edges`, and
  `bad_edges`; signed-volume contributions are diagnostic only. Relative face
  winding is solved from shared triangle edges, while total signed volume
  detects a whole-shell flip.
- Unsupported surface coverage now caps a watertight shell at `unreliable`.
- Two-loop cylindrical faces are stitched as surface strips. This removes the
  old false verdicts for `boxcyl1`, `cylinder1`, `cylinder5`, and the bore cases
  `complex4`/`complex5`.
- Unbounded single-face spheres and tori now receive deterministic closed
  analytic meshes and report `consistent` for SteppifySOLID's emitted files.
- Remaining Task 2 work: surface-aware trimmed tessellation for bounded
  sphere, torus, cone, and NURBS/complex faces. Reference versions of these
  shapes currently report `open` or `unreliable`, rather than vacuous clean.

## Task 1 — replace the v1 per-face verdict with an edge-based judge (P0)

The v1 rule `ok = sign(face volume contribution) == sign(total volume)` is
mathematically wrong in general: per-face r·n contributions are legitimately
negative for correctly-oriented faces whenever the world origin lies outside/
near the solid. Replace it. Keep `signed_volume_contribution` in JSON as
**diagnostic only**, never the verdict.

New judge — all three required, per shell:

1. **Watertightness**: mesh-edge → incident-triangle adjacency; every interior
   edge shared by exactly two triangles. Report `n_boundary_edges`; if > 0 set
   `"verdict": "open"` and do NOT call the shell consistent or inconsistent.
   (Today sphere1/sphere2/circlesloft1/cylindercut1 references yield total
   V=0.0 — open or cancelling meshes; their current "clean" is vacuous.)
2. **Edge-winding consistency**: each interior edge's two incident triangles
   must traverse it in opposite directions (one i→j, other j→i). A face flipped
   vs its neighbors makes all of its boundary edges *agree* → flag those edges,
   attribute to incident faces. Local, convexity- and origin-independent — the
   real shell-consistency invariant (what BRepCheck does topologically).
3. **Global sign**: Σ det(p0,p1,p2)/6 over all triangles > 0 (outward
   convention). Catches whole-shell flips, which test 2 alone misses.

Per-face `ok` = no flagged edge on its boundary AND tests 1–3 pass globally.
JSON: per solid add `"verdict": "consistent"|"inconsistent"|"open"` and
`"bad_edges": [[tri_a_id, tri_b_id], ...]`.

⚠️ Bore trap: bore/concave cylindrical faces legitimately have normals toward
their own surface axis. Never reintroduce a per-face radial verdict — the v2
edge test is immune by construction. (Our complex4/complex5 flags were proven
identical in SolidWorks references → artifacts, not file bugs.)

## Task 2 — close meshing gaps that make verdicts unreliable (P1)

a) **NURBS/COMPLEX sense** (`sense_applied=false` today): ear totals are
   garbage (ours -65 vs ref +12) because raw tessellation winding may oppose
   analytic side. Cheap honest fix first: if any face of a shell has
   `sense_applied=false`, cap the verdict at `"unreliable"` (report it, don't
   call inconsistent). Stretch: apply true B-spline surface normals like the
   plane/cylinder path does.
b) **TOROIDAL_SURFACE alignment**: missing today; torus1 reference reads total
   V<0 = global flip. Same pattern as existing code (analytic positive-side
   direction from entity + AXIS2_PLACEMENT_3D × sense sign). Also cover
   CONICAL and SPHERICAL while there.
c) **Diagnose the V=0.0 spheres**: with watertightness reporting (Task 1.1)
   determine whether sphere meshes are open or self-cancelling, and fix
   triangulation so closed analytic surfaces produce closed meshes.

## Acceptance criteria (run after Tasks 1+2)

```
cd /home/fat64/github/STEPoscope
uv run python -m step_explorer render --out /tmp/a_head  --mode normals \
  /tmp/opencode/em_head/exports/step/{complex2,surbod2}/...   # explicit paths
uv run python -m step_explorer render --out /tmp/a_fixed --mode normals \
  /tmp/opencode/em4/exports/step/*/*.step
uv run python -m step_explorer render --out /tmp/a_ref   --mode normals \
  /home/fat64/repos/SteppifySOLID/corpus/*/step/*.STEP
```

- em_head: complex2 → exactly face #35 bad; surbod2 → exactly #83; exit 1.
- em4 (all 28 parts): consistent everywhere except slotfillet1, which has a
  known-broken shell on the SteppifySOLID side — expect `inconsistent` or
  `open`, reported honestly.
- References: every file currently false-flagged (boxcyl1, complex1_ap203,
  complex4, complex5, cube1_sw2022 ×N, cylinder5, cylinder6, polygon1,
  resistor, revolve1) must come back `consistent`. ear/slotfillet1 may be
  `unreliable` until Task 2a lands; sphere/circlesloft1/cylindercut1 must be
  either `consistent` or honestly `open` — never vacuous-clean with V=0.0.
- torus1 reference: `consistent` after Task 2b (today V<0).

## Tests to add (pytest configured in tests/)

1. Sense application unit test: plane + cylinder, `.T.` vs `.F.` flip winding.
2. Judge: hand-built box STEP string, one face flipped → verdict
   `inconsistent`, bad edges exactly on that face's boundary, exit 1.
3. CLI end-to-end under tmp_path: png+json produced, byte-identical across two
   runs.
4. Regression guard for the v1 bug class: a correctly-oriented box placed FAR
   from the origin (corner at (50,60,70)) → `consistent`, zero bad edges, even
   though several per-face contributions are negative.
