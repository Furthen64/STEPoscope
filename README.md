# STEPoscope

STEPoscope is an educational desktop STEP walker. It parses ISO-10303-21 text
itself, keeps unknown entities inspectable, exposes forward/reverse references,
and progressively previews points, vertices, edges, wires, and simple planar
faces in VTK.

The current first milestone provides:

- File-order and semantic/reference tree views.
- Semantic-mode color coding for geometry, topology, structure, and metadata.
- `View > Show only geometry` filtering for a focused shape/topology view.
- Previous/Next navigation, including reference-following in semantic mode.
- Raw entity source, parsed arguments, source position, and reference lists.
- Progressive geometry discovery with selected-entity highlighting.
- A toolbar-driven three-pane layout with separate interpretation and raw-source tabs.
- Persistent `File > Recent files` history containing the last five successfully opened files.
- Optional TOML configuration for inverting camera rotation while dragging.
- Playback controls for stepping through and animating the file-order geometry build-up.
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
```

The setting defaults to `false`. It can also be toggled at runtime from
`View > Invert mouse rotation`; that menu choice is persisted by the
application and takes precedence over the TOML value. Set
`STEPOSCOPE_CONFIG` to use a different TOML file.

After opening a STEP file, use the playback panel below the viewer to play,
pause, step forward or backward, or scrub through the build-up. `Tick rate`
controls how many STEP entities are added per second and is persisted between
sessions.

On Wayland, use the included launcher, which defaults to the XWayland-backed
Qt platform required by the current VTK embedding:

```sh
./runwl.sh examples/stepAP203/slot1.STEP
```

Run the tests with `uv run pytest`.

`slot1.STEP` is the intended development fixture from GENESIS.md, but it is
not part of this repository yet; the parser is not hard-coded to any entity ID.

The project intentionally does not use OpenCascade, FreeCAD, pythonOCC, or a
CAD kernel. STEP writing/editing and production CAD tessellation are out of
scope for this educational walker.
