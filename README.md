# STEPoscope

STEPoscope is an educational desktop STEP walker. It parses ISO-10303-21 text
itself, keeps unknown entities inspectable, exposes forward/reverse references,
and progressively previews points, vertices, edges, wires, and simple planar
faces in VTK.

The current first milestone provides:

- File-order, semantic/reference, and playback source-list views.
- Semantic-mode color coding for geometry, topology, structure, and metadata.
- `View > Show only geometry` filtering for a focused shape/topology view.
- `Save Geometry only STEP file` in the toolbar and File menu, which writes a
  new STEP file with shape data and the references needed to load it.
- Previous/Next navigation, including reference-following in semantic mode.
- Raw entity source, parsed arguments, source position, and reference lists.
- Progressive geometry discovery with selected-entity highlighting.
- A Normals dropdown with hidden, vector-arrow, and blue-front/red-back face
  orientation displays.
- A toolbar-driven three-pane layout with separate interpretation and raw-source tabs.
- Persistent `File > Recent files` history containing the last five successfully opened files.
- Optional TOML configuration for inverting camera rotation while dragging.
- Playback controls for stepping through and animating the file-order geometry build-up.
- B-spline surface control-net previews with per-surface, coarse-to-full mixer faders.
- A generic parser for multiline entities, nested values, strings, numbers,
  enumerations, `$`, `*`, typed values, and unknown entity types.

## Setup

This project uses `uv` and Python 3.12:

```sh
uv sync
uv run steposcope
```

You can open a file directly with:

```sh
uv run steposcope path/to/model.STEP
```

To reverse the direction of mouse-driven camera rotation, create
`steposcope.toml` in the working directory (or
`~/.config/steposcope/config.toml`) with:

```toml
invert_mouse_rotation = true
autozoom = true
show_entity_labels = false
label_mode = "index" # or "type"
max_entity_labels = 250
```

`invert_mouse_rotation` and `show_entity_labels` default to `false`; `autozoom`
defaults to `true`; `label_mode` defaults to `"index"`. Entity labels can be toggled at runtime
from `View > Show entity labels` or with `L`. Use `View > Label content` or
`T` to switch between line indices and friendly entity types. Mouse rotation
can be toggled from `View > Invert mouse rotation`. Disable `View > Autozoom`
to keep your camera framing while playback adds geometry. These menu choices are
persisted by the application and take precedence over their TOML values. Set
`STEPOSCOPE_CONFIG` to use a different TOML file.

Labels are selected in screen space and capped at `max_entity_labels` (default
250), so enabling them remains usable for large STEP files. The selected entity
is preferred, followed by newer labels. As the budget fills, older labels fade
toward the viewport background and eventually drop out.

After opening a STEP file, use the playback panel below the viewer to play,
pause, step forward or backward, or scrub through the build-up. Press `Space`
over the OpenGL viewer to play/pause. `Tick rate` controls how many STEP
entities are added per second and is persisted between sessions. Pressing Play
switches to the Playback listing, which follows the current STEP record in file
order. Click a record in that listing to pause and seek to it.

The **Normals** dropdown changes how rendered faces show orientation. **Vectors**
draws arrows along the preview mesh normals. **Face orientation** shows blue
front faces and red back faces as seen from the camera; rotate the model to
inspect both sides. Red is not by itself proof of a bad face. For planar and
cylindrical faces, STEPoscope aligns preview triangles with the STEP face sense.
Unsupported or unevaluated surfaces, including B-spline surfaces, cannot yet
provide a reliable normal diagnostic.

## B-spline control-net previews

When a STEP file contains a `B_SPLINE_SURFACE_WITH_KNOTS`, STEPoscope can show
its control net as green points and connecting grid lines. This is an honest
preview of the surface's construction data, not a tessellation: most control
points do not lie on the exact NURBS surface.

The **Surface control nets** panel appears below playback once B-spline
surfaces are encountered. A surface remains disabled while its
forward-referenced control points have not yet appeared in file-order
playback. Once ready, its vertical fader selects an evenly distributed,
coarse-to-full subset of its grid without changing the STEP model. The lowest
setting retains the full-spanning 2-by-2 cage; the highest uses every control
point. The panel is absent for files without B-spline surfaces.

Surface evaluation and filled NURBS tessellation remain out of scope.

Camera navigation also supports Blender-like middle-mouse orbiting; hold
Shift while dragging with the middle mouse button to pan. Press `R` over the
viewer to reset the framing, orbit, and roll together.

On Wayland, use the included launcher, which defaults to the XWayland-backed
Qt platform required by the current VTK embedding:

```sh
./runwl.sh examples/stepAP203/slot1.STEP
```

Run the tests with `uv run pytest`.

`slot1.STEP` is the intended development fixture from GENESIS.md, but it is
not part of this repository yet; the parser is not hard-coded to any entity ID.

The project intentionally does not use OpenCascade, FreeCAD, pythonOCC, or a
CAD kernel. The geometry-only save action filters existing STEP records; it does
not rebuild or heal CAD geometry. General STEP editing and production CAD
tessellation are out of scope for this educational walker.
