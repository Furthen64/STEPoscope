# Handover: per-face identity + multi-view in the headless renderer

Task for whoever picks this up in the STEPoscope repo. Written by the SteppifySOLID
side while debugging `corpus/slotfillet1`; it is self-contained and needs no context
from that conversation.

## Why

The headless JSON report is excellent at saying *that* a shell is wrong
(`verdict`, `n_boundary_edges`, per-face `signed_volume_contribution`) but it cannot
say *where*. Right now a render is one flat blue/red blob, and identifying "which
ADVANCED_FACE is the cone-shaped flare" means eyeballing a picture and then
cross-referencing numbers by hand.

The interactive GUI already has all of this (`vtk_view.py`: per-face `entity_id`
labels, click-to-select, `set_label_mode`). The headless path throws it away. This
task is about closing that gap, not inventing new analysis.

## State of the repo — read this first

There are **uncommitted changes** in the working tree before you start:

```
 M step_explorer/geometry/builder.py   (+50)
 M tests/test_geometry.py               (+13)
?? examples/spindle1.step
?? examples/spindle1_geometry.step
```

They are not yours and not related to this task. Do not discard them, do not
`git checkout`, do not `git stash`. Commit only the files you create or edit for
this task, and leave those two modified files alone unless you have a specific
reason to touch them. If you need to be safe, ask before committing.

## Environment

uv only — no `pip`, no `python -m venv`. `.venv` already exists.

```bash
cd ~/github/STEPoscope
uv sync
uv run pytest tests/ -q          # baseline: must be green BEFORE you change anything
```

Run the CLI the same way:

```bash
uv run --project ~/github/STEPoscope steposcope render <file.step> --out temp/steposcope --mode normals
```

## Where the code is

| What | Where |
|---|---|
| CLI arg parsing | `step_explorer/main.py:14-21` (`_render_main`) |
| Render + report driver | `step_explorer/headless.py:238-245` (`process_file`) |
| The actual VTK render | `step_explorer/headless.py:178-235` (`render_png`) |
| Per-face color decision today | `step_explorer/headless.py:206-209` |
| Camera placement | `step_explorer/headless.py:211-224` |
| `Mesh` dataclass | `step_explorer/geometry/builder.py:28-35` |
| Face-label precedent in the GUI | `step_explorer/visualization/vtk_view.py:409-412`, `_label_text` at `:437` |
| Existing headless tests | `tests/test_headless.py` |

`Mesh` already carries everything you need:

```python
@dataclass(frozen=True)
class Mesh:
    entity_id: int          # the ADVANCED_FACE's #id — this is the label to draw
    points: tuple[Point3, ...]
    triangles: tuple[tuple[int, int, int], ...]
    curved: bool = False
    type_name: str = "UNKNOWN"
    sense: str = "."
    sense_applied: bool | str = False
```

`meshes` is one `Mesh` per face, in `render_png`'s loop. So a distinct color and a
label per face are both a few lines each, with no plumbing through the parser or
builder.

## What to build

### 1. Distinct color per face

Replace the binary blue/red at `headless.py:206-209` with a third `--mode`, e.g.
`faces`, that assigns each `entity_id` a stable hue.

- **Stable and order-independent.** Derive the hue from the `entity_id` (hash it), or
  from its index in a `sorted()` set of ids — *not* from iteration order. Two runs over
  the same file must agree, and a face must keep its color when a sibling face is
  added or removed. `test_headless_outputs_are_deterministic` will catch order
  dependence, but it will not catch "stable across unrelated edits", so reason about
  that deliberately.
- Use evenly spaced hues (golden-angle, or HSV with `id * 0.618034` turns) at high
  saturation and a fixed value so nothing washes out against the dark background.
- Keep `normals` exactly as it is. It is the default and other people depend on it.
- **Acknowledge the limit:** past ~12 faces, hues collide and the ID text is what
  actually disambiguates. That is fine — color is a grouping aid, the label is the
  information. Do not try to make color alone carry it.

### 2. Face ID labels

Draw `#<entity_id>` at each face's centroid, offset slightly along the face normal so
it does not z-fight with the surface.

- Follow the GUI's approach: `vtk.vtkBillboardTextActor3D` or `vtkVectorText`, one per
  face, added to the same renderer. `_add_label` in `vtk_view.py:442` is the
  precedent, including its collision/priority handling.
- The existing renderer uses `SetMultiSamples(0)` and offscreen rendering; verify
  labels survive that and are actually legible at the default 1200x900.
- Scale font size relative to the scene so it works at the test size of 160x120 too.
- If a face is degenerate or has no triangles, skip its label rather than crashing.

### 3. Multi-view

Add a `--views` flag emitting several PNGs per input, e.g.
`--views iso,front,top,right`, writing `<name>-<view>.png`. Reuse the existing
`directions` dict at `headless.py:215` and the `SetViewUp` special-case for `front` —
that logic is already correct, it just needs to run in a loop.

The reason this matters: comparing our output against a SolidWorks reference STEP is
the primary workflow, and it only works if both are rendered from *matched* angles.

- When `--views` is not passed, keep writing a single `<name>.png` so existing callers
  and `test_headless_outputs_are_deterministic` do not break.
- Every view must call `ResetCamera()` / `ResetCameraClippingRange()` independently
  (as today) so each is framed on the whole model.

### 4. Tests

Extend `tests/test_headless.py`:

- `faces` mode produces different colors for different faces, and the *same* color for
  the same `entity_id` across two runs.
- Two faces that are adjacent in the file are still distinguishable (guards against
  an off-by-one in the hue stride).
- `--views` writes the expected filenames; default single-view behavior is unchanged.
- A face with a large `entity_id` still renders (no modulo/stride bug).
- The existing determinism test must still pass, including byte-identical PNGs.

## Definition of done

- `uv run pytest tests/ -q` green.
- `steposcope render <some.step> --out temp/x --mode faces --views iso,front,top,right`
  produces 4 PNGs where you can read each face's `#id` off the surface.
- Existing `normals` mode is byte-identical to before for a given input (the
  determinism test is the guard).
- Committed on a branch, with a commit message in the repo's existing style — recent
  subjects are short imperative phrases, e.g. "Replace volume heuristic with edge
  orientation judge", "headless", "Normals added".

## What the consumer wants from this

From `SteppifySOLID`, run as:

```bash
./tools/steposcope_check.sh exports/step/<part>/<part>.step corpus/<part>/step/<part>.STEP
```

Ideally that wrapper grows a `--mode faces` passthrough once this lands. The immediate
pain it solves: `slotfillet1` has a 17-face shell where exactly one face is
geometrically wrong, and the report can name its volume contribution but not place it.
