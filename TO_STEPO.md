# TO_STEPO.md — make STEPoscope a headless orientation oracle

You are working in the STEPoscope repo. A sibling project (SteppifySOLID,
`/home/fat64/repos/SteppifySOLID`) hand-writes AP203 STEP files and needs a
**raw, kernel-free ground-truth judge** for one bug class: inverted
`ADVANCED_FACE` sense flags (`.T.`/`.F.`), i.e. face normals pointing into the
material instead of out of it.

## Why this project is the judge (read first)

- OCCT-based tools (FreeCAD, Plasticity) **silently heal** inconsistent shells
  on import. They cannot be trusted to detect this bug class — they mask it.
- STEPoscope parses AP203 line-by-line and never heals. That makes it the ideal
  raw judge. It is currently GUI-only; this task adds a headless mode so the
  other repo can run it in batch / CI.

## Hard rules

1. **Never repair, snap, reorient, or "fix" input geometry.** Render exactly
   what the file says. No healing of any kind, ever — that is the entire point.
2. Deterministic output: same input file → identical PNG bytes and JSON
   (fixed camera, fixed size, no timestamps in outputs).
3. uv only (see AGENTS.md). Linux target. Do not break existing GUI mode;
   headless is additive. The `render` subcommand must not import Qt at module
   load time (lazy-import the GUI path only) so it works display-less.

## Current state (verified 2026-09-25)

- Entry: `steposcope` script → `step_explorer/main.py` → PySide6 QApplication +
  MainWindow. GUI-only today.
- Parsing: `step/` package (`StepEntity`, `StepEnumeration`, refs).
- Meshing: `geometry/builder.py`. `_oriented_face_triangles` (~lines 458–491)
  applies the ADVANCED_FACE sense to triangle winding, but **only for PLANE and
  CYLINDRICAL_SURFACE**: `.T.` ⇒ normal along placement axis (plane) / radially
  outward from its own cylinder axis; `.F.` flips. ORIENTED_EDGE sense handled
  ~line 205 / ~397. All other surface types keep raw triangulation winding.
- VTK ≥ 9.3 already a dependency (`vtkContourTriangulator` in builder).

## Requirements

### P0 — headless render CLI

```
python -m step_explorer render FILE... --out DIR
    [--width 1200 --height 900] [--camera iso|front|top|right]
    [--mode normals|shaded]
```

- No window. Offscreen VTK rendering (`SetOffScreenRendering(1)`). If this
  machine's VTK build lacks OSMesa/EGL, fall back to an `xvfb-run` wrapper and
  document which path works here.
- Per input file write `<stem>.png` + `<stem>.json`.
- Exit codes: `0` all shells consistent · `1` any inconsistency found ·
  `2` parse/IO error. (It must be able to gate a CI run.)

### P0 — JSON report (the real ground truth; PNG is for eyeballing)

Per file:

```json
{"source": "...", "solids": [{"faces": [
   {"entity_id": 35, "type_name": "CYLINDRICAL_SURFACE", "sense": ".F.",
    "mean_normal": [x,y,z], "signed_volume_contribution": v, "ok": false}
 ], "total_signed_volume": V, "n_inconsistent": 1}]}
```

- Signed volume contribution per face = Σ over its triangles of
  `det([p0,p1,p2])/6` with origin at world 0 (divergence theorem). For a
  consistently outward-oriented closed shell, every face's contribution shares
  the sign of the total; one flipped face flips its own contribution →
  detectable without knowing what is "inside".
- `ok = sign(contribution) == sign(total)` (guard `|contribution| > eps`).
  **This shell-consistency test is the judge.**
- ⚠️ Known trap that already burned us: bore/concave cylindrical faces
  *legitimately* have normals pointing **toward** their own surface axis. A
  naive "normal must point away from its own cylinder axis" check gives false
  positives on complex4 (r=2), complex5 (r=3), slotfillet1 (r≈11.117) —
  SolidWorks' own reference files show identical signatures there. Do not use
  per-face radial heuristics as the verdict; only shell consistency.

### P1 — normal-color render mode (`--mode normals`)

Color each triangle blue if its face's signed-volume contribution agrees with
the shell total, red otherwise (optionally shade by magnitude so flat-on views
stay readable). State this exact convention in `--help` and README so colors
are interpretable. Colors must reflect the sense flag (they do today for
plane/cylinder via winding alignment).

### P1 — extend sense-winding alignment beyond PLANE/CYLINDRICAL

Cover CONICAL_SURFACE, SPHERICAL_SURFACE, TOROIDAL_SURFACE (present in our
corpus: cone1, sphere1/2, torus1) using the same pattern as existing code:
derive the analytic positive-side direction from the surface entity +
AXIS2_PLACEMENT_3D, apply the sense sign. For B-spline/NURBS surfaces: first
document current behavior (VTK tessellation winding vs analytic side) before
changing anything. Add a per-face report field `sense_applied: true|false|approx`
so we always know which faces the judge fully covers.

### P2 — batch ergonomics

Accept directories/globs; stable output names; one combined `summary.json`.
No comparison helper needed — the other repo diffs JSONs itself.

## Test vectors / acceptance criteria

From SteppifySOLID (`/home/fat64/repos/SteppifySOLID`):

- **Known inverted** (pre-fix emission), expect exactly these faces flagged
  inconsistent and red in PNG:
  - `/tmp/opencode/em_head/exports/step/complex2/complex2.step` — face #35 → CYLINDRICAL_SURFACE #5, r=2, `.F.` (wrong)
  - `/tmp/opencode/em_head/exports/step/surbod2/surbod2.step` — face #83 → #64, r=2
  - `/tmp/opencode/em_head/exports/step/ear/ear.step` — face #1009 → #997, r=1
- **Fixed emission**: `/tmp/opencode/em4/exports/step/<part>/<part>.step` for
  the same parts → zero inconsistencies.
- **Ground truth**: `corpus/<part>/step/*.STEP` (SolidWorks references) → zero
  inconsistencies across the corpus.
- **Bore false-positive guard**: complex4, complex5, slotfillet1 (ours AND
  reference) must report *consistent* despite inward-toward-axis cylinder
  normals.
- Full corpus (28 parts): box1 box2 boxcyl1 circlesloft1 complex1 complex2
  complex4 complex5 cone1 cubecluster1 cylinder1 cylinder3 cylinder4 cylinder5
  cylinder6 cylindercut1 ear polygon1 resistor revolve1 slot1 slotfillet1
  sphere1 sphere2 spindle1 surbod1 surbod2 torus1. Note: slotfillet1 has a
  separate known-broken shell on the SteppifySOLID side — report it, don't
  chase it here.

## Tests to add (pytest already configured, `tests/`)

1. Unit: sense application in `_oriented_face_triangles` for plane + cylinder
   (`.T.` vs `.F.` flip winding as specified).
2. Judge: hand-built tiny box STEP string; flip one face's sense → JSON flags
   exactly that face, exit code 1.
3. CLI end-to-end under `tmp_path`: produces `<stem>.png` + `<stem>.json`,
   deterministic across two runs.
