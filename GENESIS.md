That locks the V1 scope well enough. I would not ask more questions before implementation.

For the parser, I would take the **pragmatic ISO-10303-21 parser** route: preserve everything faithfully, understand references and common argument types, but do not try to implement the complete AP203 EXPRESS schema yet. Unknown entities must remain inspectable rather than becoming parse failures.

For faces, I would explicitly tell the agent to be opportunistic rather than perfectionist:

* once a closed wire corresponding to a face is understood, attempt to render a translucent face;
* planar faces should be the first reliable case;
* curved faces can be approximated/tessellated from their underlying STEP geometry;
* rendering failure must never prevent traversal;
* wires remain visible through/over faces;
* faces should default to semi-transparent so the underlying topology stays understandable.

For balloon labels, VTK is actually well suited. Vertices can label their coordinates/entity IDs, edges can label their entity/curve/orientation, and faces can label surface type, normal/orientation, entity ID, etc. The label's leader should point to the vertex, edge midpoint, or approximate face centroid.

Here is the prompt I would give the coding agent:

> Build a Python 3.12 desktop application for interactively exploring ISO-10303-21 STEP files, initially targeting AP203 files.
>
> This is an educational **STEP walker**, not a CAD editor and not a general CAD kernel.
>
> Use:
>
> * Python 3.12
> * `uv` for the environment/dependencies
> * PySide6 for the GUI
> * VTK for visualization
> * pytest for tests
>
> Do NOT use OpenCascade, FreeCAD, pythonOCC, or another STEP/CAD kernel. The purpose is to parse and understand the STEP representation ourselves.
>
> The canonical development fixture is `slot1.STEP`. Design the parser generally, but make sure this file works well.
>
> ## Primary goal
>
> The user should be able to open a STEP file and traverse it in two different ways:
>
> 1. **Physical/file-order mode**
>
>    * Walk through the actual STEP file progressively.
>    * Header, DATA section, entity instances, etc.
>    * Previous/Next advances according to their physical/order position.
>    * As geometric information becomes available, progressively show it in the VTK viewport.
> 2. **Semantic/reference mode**
>
>    * Follow STEP entity references rather than file order.
>
>    * Let the user start at something such as a `MANIFOLD_SOLID_BREP` and descend through references:
>
>      MANIFOLD_SOLID_BREP
>      → CLOSED_SHELL
>      → ADVANCED_FACE
>      → FACE_OUTER_BOUND
>      → EDGE_LOOP
>      → ORIENTED_EDGE
>      → EDGE_CURVE
>      → geometry / vertices
>
>    * The user must also be able to freely expand/collapse and navigate the reference tree.
>
> These are two views of the SAME parsed entity database, not two separate parsers.
>
> ## Architecture
>
> Use a small structured application rather than a monolithic script.
>
> Suggested layout:
>
> ```text
> step_explorer/
>     main.py
>
>     ui/
>         main_window.py
>         entity_tree.py
>         entity_details.py
>
>     step/
>         lexer.py
>         parser.py
>         values.py
>         entities.py
>         graph.py
>
>     visualization/
>         vtk_view.py
>         geometry_builder.py
>         labels.py
>
>     tests/
> ```
>
> Adjust this when justified, but maintain separation between parsing, semantic/reference graph, UI, and rendering.
>
> ## STEP parser
>
> Implement a pragmatic ISO-10303-21 parser ourselves.
>
> It should understand at least:
>
> * HEADER and DATA sections
> * entity IDs such as `#25`
> * entity names/types
> * strings
> * numbers
> * `$`
> * `*`
> * enumerations such as `.T.` / `.F.` and named enums
> * entity references
> * nested argument lists
> * typed/nested values where encountered
>
> Multiline entities must work.
>
> Do not assume one entity = one physical line.
>
> Preserve:
>
> * entity ID
> * entity type
> * parsed arguments
> * original/raw source text
> * approximate source position/order
>
> Unknown entity types must parse generically. Do NOT hard-fail because an AP203 entity has not been semantically implemented yet.
>
> Build both:
>
> ```text
> outgoing references:
> #25 → #132
>
> incoming references:
> #132 ← #25
> ```
>
> Keep parsing independent of visualization.
>
> Do not implement the complete `CONFIG_CONTROL_DESIGN` EXPRESS schema yet.
>
> ## GUI
>
> Use a PySide6 `QMainWindow`.
>
> Prefer splitter-based layout.
>
> Initial layout concept:
>
> ```text
> ┌─────────────────────────────────────────────────────────────┐
> │ File / navigation controls                                 │
> ├──────────────────┬────────────────────┬─────────────────────┤
> │ entity/tree      │ entity details     │ VTK viewport        │
> │                  │                    │                     │
> │                  │                    │                     │
> ├──────────────────┴────────────────────┴─────────────────────┤
> │ raw STEP source / current entity                           │
> └─────────────────────────────────────────────────────────────┘
> ```
>
> The details view should display things like:
>
> * entity ID
> * entity type
> * arguments
> * referenced entities
> * entities referring to this entity
> * raw STEP representation
> * known semantic interpretation if implemented
>
> Selecting something in the tree should synchronize with the viewport.
>
> ## Visualization philosophy
>
> VTK is ONLY the renderer.
>
> Do not hide STEP interpretation inside VTK.
>
> The data flow should conceptually remain:
>
> ```text
> STEP text
>     ↓
> our parser
>     ↓
> our entity/reference representation
>     ↓
> our geometry interpretation
>     ↓
> simple visualization primitives
>     ↓
> VTK
> ```
>
> ## Initial supported geometry
>
> Implement progressively, concentrating on entities encountered by `slot1.STEP`.
>
> Important initial targets include:
>
> * `CARTESIAN_POINT`
> * `DIRECTION`
> * `VECTOR`
> * `AXIS2_PLACEMENT_3D`
> * `LINE`
> * `CIRCLE`
> * `VERTEX_POINT`
> * `EDGE_CURVE`
> * `ORIENTED_EDGE`
> * `EDGE_LOOP`
> * `FACE_OUTER_BOUND`
> * `ADVANCED_FACE`
> * `PLANE`
> * `CYLINDRICAL_SURFACE`
> * `CLOSED_SHELL`
> * `MANIFOLD_SOLID_BREP`
>
> Not every one needs complete rendering immediately, but they should be inspectable and traversable.
>
> ## Progressive rendering
>
> Graphics should appear as understanding becomes available.
>
> Examples:
>
> * `CARTESIAN_POINT` → visible point
> * `DIRECTION` → vector/arrow where meaningful
> * `AXIS2_PLACEMENT_3D` → local coordinate triad
> * `VERTEX_POINT` → topology vertex
> * `EDGE_CURVE` → line/arc/curve segment
> * `ORIENTED_EDGE` → visibly indicate direction if practical
> * `EDGE_LOOP` → complete wire
> * `ADVANCED_FACE` → attempt translucent filled face
>
> Keep topology distinguishable from pure geometry where practical.
>
> ## Faces
>
> Once enough wires exist to identify a face boundary, attempt to show the face.
>
> Do not require production-quality CAD tessellation.
>
> Priorities:
>
> 1. planar faces should work reliably;
> 2. curved faces should be approximated where feasible;
> 3. if a face cannot be tessellated, leave its wire visible and continue gracefully.
>
> A face-rendering failure must NEVER stop file parsing or traversal.
>
> Render faces semi-transparently by default so edges and vertices remain visible.
>
> Keep boundary wires visible.
>
> It is acceptable for early tessellation to be somewhat crude as long as the implementation is understandable and isolated for later improvement.
>
> ## Labels / annotations
>
> Add optional VTK balloon/caption-style annotations with leader lines.
>
> They should be togglable globally and preferably by category:
>
> * vertices
> * edges
> * faces
>
> Useful labels include:
>
> Vertex:
>
> ```text
> #41 VERTEX_POINT
> xyz=(...)
> ```
>
> Edge:
>
> ```text
> #72 EDGE_CURVE
> CIRCLE
> same_sense=.T.
> ```
>
> Face:
>
> ```text
> #91 ADVANCED_FACE
> PLANE
> orientation=.T.
> ```
>
> Where available, also show useful information such as:
>
> * normals
> * orientations
> * entity IDs
> * referenced geometry
> * coordinates
>
> Position leaders approximately at:
>
> * vertex position
> * edge midpoint
> * face centroid
>
> Do not spend excessive effort avoiding every label overlap in V1.
>
> ## Traversal behavior
>
> Add:
>
> ```text
> Previous
> Next
> ```
>
> and a mode selector:
>
> ```text
> File order | Semantic
> ```
>
> In file-order mode, Next walks the parsed physical entity stream.
>
> In semantic mode, navigation should follow the currently selected semantic/reference path.
>
> Selecting entities manually must remain possible in either mode.
>
> As navigation occurs:
>
> * update selection
> * show raw source
> * show interpreted attributes
> * update/highlight geometry
> * optionally add newly understood geometry to the persistent viewport
>
> Provide a distinction between:
>
> * geometry discovered so far
> * currently selected/highlighted geometry
>
> ## Important design rule
>
> Do not special-case the slot model by entity ID.
>
> It is acceptable to implement support because particular entity TYPES are encountered in `slot1.STEP`, but nothing should say things like:
>
> ```python
> if entity.id == 132:
>     ...
> ```
>
> ## Testing
>
> Add parser tests from the beginning.
>
> Test:
>
> * primitive values
> * nested argument lists
> * references
> * strings
> * multiline entities
> * null/omitted values
> * reference graph
> * reverse references
>
> Include an integration/smoke test that parses `slot1.STEP`.
>
> Parsing the fixture should report sensible counts and should not lose entities silently.
>
> Geometry tests should test transformations/math independently where possible instead of testing pixels.
>
> ## Error handling
>
> Prefer partial understanding over failure.
>
> If an entity is syntactically valid but semantically unsupported:
>
> ```text
> Parsed: yes
> Visualization: unsupported
> ```
>
> not:
>
> ```text
> ERROR
> ```
>
> The application should make unsupported concepts obvious to the user while still allowing navigation through them.
>
> ## Scope exclusions
>
> Do not implement:
>
> * editing STEP
> * writing STEP
> * full AP203 validation
> * full EXPRESS interpreter
> * constraint checking
> * commercial-quality tessellation
> * OpenCascade integration
> * conversion to another CAD format
>
> This is an interactive educational walker.
>
> ## First milestone
>
> Get the complete skeleton running before aggressively implementing geometry.
>
> A successful first milestone is:
>
> 1. application launches;
> 2. `slot1.STEP` opens;
> 3. entities parse;
> 4. entity tree is visible;
> 5. raw entity data is visible;
> 6. references can be followed;
> 7. Previous/Next works;
> 8. VTK viewport is embedded successfully;
> 9. at least CARTESIAN_POINT / VERTEX_POINT entities can visibly appear and be highlighted.
>
> Then incrementally add edges, circles, loops and faces.
>
> Work in small testable steps. Run tests after meaningful parser/geometry changes. Do not rewrite large components merely because later geometry support exposes a missing abstraction; preserve working parser behavior while extending it.

One detail in that prompt is particularly intentional: **the viewport should accumulate “geometry understood so far.”**

That gives the physical walk a potentially very satisfying effect. You start with essentially nothing, then points and coordinate systems begin appearing, then geometry, then topology starts connecting it, then wires close, then translucent faces suddenly materialize. By the time you arrive at `MANIFOLD_SOLID_BREP`, you've effectively watched the file explain the object to you.

