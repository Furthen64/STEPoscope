from __future__ import annotations

from dataclasses import dataclass

from ..ui.colors import color_for_category

try:
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
except ImportError:  # pragma: no cover - allows parser use without GUI extras
    QLabel = QVBoxLayout = QWidget = object  # type: ignore[misc,assignment]

try:
    from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
    import vtkmodules.all as vtk
except ImportError:  # pragma: no cover - allows a Qt-only install to open files
    QVTKRenderWindowInteractor = None
    vtk = None


@dataclass(frozen=True)
class _LabelSpec:
    entity_id: int
    anchor: tuple[float, float, float]
    color: tuple[float, float, float]
    scale: float
    text: str
    selected: bool
    priority: int
    arrival_order: int = 0


if vtk is not None:

    class MouseRotationStyle(vtk.vtkInteractorStyleTrackballCamera):
        """Trackball camera style with optional inverted mouse rotation."""

        def __init__(self, invert_rotation: bool = False):
            super().__init__()
            self.set_invert_rotation(invert_rotation)
            self._middle_mouse_orbiting = False

        def set_invert_rotation(self, enabled: bool) -> None:
            self.invert_rotation = bool(enabled)

        def OnMiddleButtonDown(self):
            """Use Blender-like middle-mouse orbiting.

            Shift+middle-mouse keeps VTK's pan behavior, which matches
            Blender's Shift+middle-mouse navigation.
            """

            interactor = self.GetInteractor()
            self._middle_mouse_orbiting = interactor is not None and not interactor.GetShiftKey()
            if self._middle_mouse_orbiting:
                super().OnLeftButtonDown()
            else:
                super().OnMiddleButtonDown()

        def OnMiddleButtonUp(self):
            if self._middle_mouse_orbiting:
                super().OnLeftButtonUp()
            else:
                super().OnMiddleButtonUp()
            self._middle_mouse_orbiting = False

        def OnChar(self):
            """Reset both framing and orientation when the user presses R."""

            interactor = self.GetInteractor()
            key = interactor.GetKeySym().lower() if interactor is not None else ""
            if key == "r":
                self.reset_camera()
                return
            super().OnChar()

        def reset_camera(self) -> None:
            interactor = self.GetInteractor()
            renderer = self.GetCurrentRenderer()
            if renderer is None and interactor is not None:
                event_x, event_y = interactor.GetEventPosition()
                renderer = interactor.FindPokedRenderer(event_x, event_y)
            if renderer is None:
                return

            # vtkRenderer.ResetCamera() fits the scene but intentionally keeps
            # the current view direction. Restore VTK's home direction after
            # fitting so R also removes orbiting and roll.
            renderer.ResetCamera()
            camera = renderer.GetActiveCamera()
            focal_point = camera.GetFocalPoint()
            distance = camera.GetDistance()
            camera.SetPosition(focal_point[0], focal_point[1], focal_point[2] + distance)
            camera.SetViewUp(0.0, 1.0, 0.0)
            camera.OrthogonalizeViewUp()
            renderer.ResetCameraClippingRange()
            if interactor is not None:
                interactor.Render()

        def OnMouseMove(self):
            if not self.invert_rotation or self.GetState() != vtk.VTKIS_ROTATE:
                super().OnMouseMove()
                return

            interactor = self.GetInteractor()
            if interactor is None:
                super().OnMouseMove()
                return

            event_position = interactor.GetEventPosition()
            last_event_position = interactor.GetLastEventPosition()
            # VTK's camera style reads both positions during Rotate().
            # Swapping them reverses the rotation delta without affecting
            # the interactor's event history after this callback returns.
            interactor.SetEventPosition(*last_event_position)
            interactor.SetLastEventPosition(*event_position)
            try:
                super().OnMouseMove()
            finally:
                interactor.SetEventPosition(*event_position)
                interactor.SetLastEventPosition(*last_event_position)


class VtkView(QWidget):
    """Render simple primitives; all STEP interpretation stays in GeometryBuilder."""

    # Labels are deliberately bounded: each label is a VTK actor and collision
    # placement is performed in display space. A few hundred useful labels are
    # much more responsive than tens of thousands of overlapping actors.
    DEFAULT_MAX_ENTITY_LABELS = 250
    LABEL_SPACING = 42.0
    LABEL_GRID_SIZE = 48.0

    def __init__(
        self,
        parent=None,
        invert_mouse_rotation: bool = False,
        max_entity_labels: int = DEFAULT_MAX_ENTITY_LABELS,
    ):
        super().__init__(parent)
        self.invert_mouse_rotation = bool(invert_mouse_rotation)
        self.max_entity_labels = self._clamp_label_limit(max_entity_labels)
        self._actors = []
        self._initialized = False
        self._last_snapshot = None
        self._last_selected_id = None
        self._last_labels = False
        self._last_label_mode = "index"
        self._last_label_texts: dict[int, str] = {}
        self._last_label_orders: dict[int, int] = {}
        self._last_label_time = 0
        self._active_label_orders: dict[int, int] = {}
        self._active_label_time = 0
        if vtk is None or QVTKRenderWindowInteractor is None:
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel("VTK is not installed.\nParser and traversal remain available."))
            self.renderer = None
            return
        self.widget = QVTKRenderWindowInteractor(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.widget)
        self.interactor_style = MouseRotationStyle(self.invert_mouse_rotation)
        self.widget.GetRenderWindow().GetInteractor().SetInteractorStyle(self.interactor_style)
        self.renderer = vtk.vtkRenderer()
        self.renderer.SetBackground(0.10, 0.12, 0.15)
        self.widget.GetRenderWindow().AddRenderer(self.renderer)

    def set_invert_mouse_rotation(self, enabled: bool) -> None:
        self.invert_mouse_rotation = bool(enabled)
        if self.renderer is not None:
            self.interactor_style.set_invert_rotation(self.invert_mouse_rotation)

    def set_labels(self, enabled: bool) -> None:
        self._last_labels = bool(enabled)
        if self.renderer is not None and self._initialized and self._last_snapshot is not None:
            self._render_snapshot(
                self._last_snapshot,
                self._last_selected_id,
                self._last_labels,
                self._last_label_mode,
                self._last_label_texts,
                self._last_label_orders,
                self._last_label_time,
            )

    def set_max_entity_labels(self, limit: int) -> None:
        """Change the label actor budget used for subsequent renders."""

        self.max_entity_labels = self._clamp_label_limit(limit)
        if self.renderer is not None and self._initialized and self._last_snapshot is not None:
            self._render_snapshot(
                self._last_snapshot,
                self._last_selected_id,
                self._last_labels,
                self._last_label_mode,
                self._last_label_texts,
                self._last_label_orders,
                self._last_label_time,
            )

    @classmethod
    def _clamp_label_limit(cls, limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int):
            return cls.DEFAULT_MAX_ENTITY_LABELS
        return max(1, min(2000, limit))

    def set_label_mode(self, mode: str) -> None:
        self._last_label_mode = mode if mode in {"index", "type"} else "index"
        if self.renderer is not None and self._initialized and self._last_snapshot is not None:
            self._render_snapshot(
                self._last_snapshot,
                self._last_selected_id,
                self._last_labels,
                self._last_label_mode,
                self._last_label_texts,
                self._last_label_orders,
                self._last_label_time,
            )

    def showEvent(self, event):
        """Initialize VTK only after Qt has created and shown the native window.

        QVTKRenderWindowInteractor obtains a native window ID in its
        constructor. Initializing it before the containing QMainWindow is
        shown can leave that ID stale on X11/XWayland and produces BadWindow
        errors during the first resize.
        """

        super().showEvent(event)
        self._ensure_initialized()

    def closeEvent(self, event):
        if self._initialized:
            self.widget.Finalize()
            self._initialized = False
        super().closeEvent(event)

    def _ensure_initialized(self):
        if self.renderer is None or self._initialized:
            return
        self.widget.Initialize()
        self._initialized = True
        if self._last_snapshot is not None:
            self._render_snapshot(
                self._last_snapshot,
                self._last_selected_id,
                self._last_labels,
                self._last_label_mode,
                self._last_label_texts,
                self._last_label_orders,
                self._last_label_time,
            )

    def show_snapshot(
        self,
        snapshot,
        selected_id: int | None = None,
        labels: bool = False,
        label_mode: str = "index",
        label_texts: dict[int, str] | None = None,
        label_orders: dict[int, int] | None = None,
        label_time: int | None = None,
    ) -> None:
        if self.renderer is None:
            return
        self._last_snapshot = snapshot
        self._last_selected_id = selected_id
        self._last_labels = labels
        self._last_label_mode = label_mode if label_mode in {"index", "type"} else "index"
        self._last_label_texts = label_texts or {}
        self._last_label_orders = label_orders or {}
        self._last_label_time = label_time if label_time is not None else 0
        if not self._initialized:
            return
        self._render_snapshot(
            snapshot,
            selected_id,
            labels,
            self._last_label_mode,
            self._last_label_texts,
            self._last_label_orders,
            self._last_label_time,
        )

    def _render_snapshot(
        self,
        snapshot,
        selected_id: int | None,
        labels: bool,
        label_mode: str,
        label_texts,
        label_orders,
        label_time: int,
    ) -> None:
        for actor in self._actors:
            self.renderer.RemoveActor(actor)
        self._actors.clear()
        self._label_specs: list[_LabelSpec] = []
        self._active_label_orders = label_orders
        self._active_label_time = label_time
        label_scale = self._label_scale(snapshot) if labels else 1.0
        for entity_id, point in snapshot.points.items():
            self._add_point(
                entity_id,
                point.x,
                point.y,
                point.z,
                selected_id == entity_id,
                "Geometry",
                labels,
                label_scale,
                self._label_text(entity_id, label_mode, label_texts),
            )
        for entity_id, point in snapshot.vertices.items():
            self._add_point(
                entity_id,
                point.x,
                point.y,
                point.z,
                selected_id == entity_id,
                "Topology",
                labels,
                label_scale,
                self._label_text(entity_id, label_mode, label_texts),
            )
        for polyline in snapshot.polylines:
            category = "Geometry" if polyline.category == "edge" else "Structure"
            self._add_polyline(
                polyline.entity_id,
                polyline.points,
                selected_id == polyline.entity_id,
                category,
                labels,
                label_scale,
                self._label_text(polyline.entity_id, label_mode, label_texts),
            )
        for face in snapshot.faces:
            self._add_mesh(
                face,
                selected_id == face.entity_id,
                labels,
                label_scale,
                self._label_text(face.entity_id, label_mode, label_texts),
            )
        self.renderer.ResetCamera()
        if labels:
            self._place_labels()
        self.widget.GetRenderWindow().Render()

    def _label_scale(self, snapshot) -> float:
        points = [*snapshot.points.values(), *snapshot.vertices.values()]
        points.extend(point for polyline in snapshot.polylines for point in polyline.points)
        points.extend(point for face in snapshot.faces for point in face.points)
        if not points:
            return 1.0
        span = max(
            max(point.x for point in points) - min(point.x for point in points),
            max(point.y for point in points) - min(point.y for point in points),
            max(point.z for point in points) - min(point.z for point in points),
        )
        return max(span * 0.03, 1e-9)

    @staticmethod
    def _label_text(entity_id, label_mode, label_texts):
        if label_mode == "type":
            return label_texts.get(entity_id, "Entity")
        return f"#{entity_id}"

    def _add_label(self, entity_id, position, color, scale, text, selected=False, priority=0):
        arrival_order = self._active_label_orders.get(entity_id, self._active_label_time)
        self._label_specs.append(
            _LabelSpec(entity_id, position, color, scale, text, selected, priority, arrival_order)
        )

    def _place_labels(self) -> None:
        """Place labels in display space and add callouts for collisions."""

        width, height = self.widget.GetRenderWindow().GetSize()
        if width <= 0 or height <= 0:
            return

        occupied: list[tuple[float, float, float, float]] = []
        candidates = self._visible_label_candidates(width, height)
        for spec, display_anchor, label_width, label_height, fade in candidates:
            entity_id = spec.entity_id
            anchor = spec.anchor
            color = self._fade_color(spec.color, fade)
            scale = spec.scale
            text = spec.text
            position, box, displaced = self._label_position(
                display_anchor,
                label_width,
                label_height,
                occupied,
                width,
                height,
            )
            occupied.append(box)
            label_position = self._display_to_world(position[0], position[1], display_anchor[2])
            label = vtk.vtkBillboardTextActor3D()
            label.SetInput(text)
            label.SetPosition(*label_position)
            label.SetScale(scale, scale, scale)
            label.SetPickable(False)
            text_property = label.GetTextProperty()
            text_property.SetColor(*color)
            text_property.SetOpacity(1.0 - 0.9 * fade)
            text_property.SetBold(True)
            if displaced:
                text_property.SetBackgroundColor(0.06, 0.08, 0.11)
                text_property.SetBackgroundOpacity(0.88 * (1.0 - 0.9 * fade))
                text_property.SetFrame(True)
                text_property.SetFrameColor(*color)
                text_property.SetFrameWidth(1)
            self.renderer.AddActor(label)
            self._actors.append(label)
            if displaced:
                self._add_leader(anchor, label_position, color, 1.0 - 0.9 * fade)

    def _visible_label_candidates(self, width, height):
        """Project, prioritize, and thin labels before creating VTK actors.

        The old path attempted collision placement for every rendered entity.
        This selection pass projects each rendered entity once and limits the
        expensive actor/collision path to the configured budget.
        Selected entities win, followed by newer labels and then entity
        priority. A screen-space grid prevents a dense cluster from consuming
        the whole budget.
        """

        projected = []
        for order, spec in enumerate(self._label_specs):
            display_anchor = self._world_to_display(spec.anchor)
            x, y = display_anchor[:2]
            label_width = max(30.0, 8.0 * len(spec.text) + 8.0)
            label_height = 22.0
            if x < -label_width or x > width or y < -label_height or y > height:
                continue
            projected.append((spec, display_anchor, label_width, label_height, order))

        projected.sort(key=lambda item: (not item[0].selected, -item[0].arrival_order, item[0].priority, item[4]))
        accepted = []
        grid: dict[tuple[int, int], list[tuple[float, float, float]]] = {}
        spacing = self.LABEL_SPACING
        cell_size = self.LABEL_GRID_SIZE
        largest_accepted_radius = 0.0
        for spec, display_anchor, label_width, label_height, _order in projected:
            if len(accepted) >= self.max_entity_labels:
                break
            x, y = display_anchor[:2]
            radius = max(spacing, label_width / 2.0, label_height / 2.0)
            cell_x = int(x // cell_size)
            cell_y = int(y // cell_size)
            nearby = False
            radius_in_cells = max(1, int((radius + largest_accepted_radius) // cell_size) + 1)
            for neighbor_x in range(cell_x - radius_in_cells, cell_x + radius_in_cells + 1):
                for neighbor_y in range(cell_y - radius_in_cells, cell_y + radius_in_cells + 1):
                    for other_x, other_y, other_radius in grid.get((neighbor_x, neighbor_y), ()):
                        required = radius + other_radius
                        if (x - other_x) ** 2 + (y - other_y) ** 2 < required**2:
                            nearby = True
                            break
                    if nearby:
                        break
                if nearby:
                    break
            if nearby:
                continue
            grid.setdefault((cell_x, cell_y), []).append((x, y, radius))
            largest_accepted_radius = max(largest_accepted_radius, radius)
            fade = 0.0 if spec.selected else self._label_fade(len(accepted))
            accepted.append((spec, display_anchor, label_width, label_height, fade))
        return accepted

    def _label_fade(self, accepted_index: int) -> float:
        """Fade the oldest labels as the visible label budget fills."""

        fade_start = max(1, int(self.max_entity_labels * 0.72))
        fade_end = max(fade_start + 1, self.max_entity_labels - 1)
        return min(0.88, max(0.0, (accepted_index - fade_start) / (fade_end - fade_start)))

    @staticmethod
    def _fade_color(color, fade):
        background = (0.10, 0.12, 0.15)
        return tuple(
            background_component + (component - background_component) * (1.0 - fade)
            for component, background_component in zip(color, background)
        )

    def _label_position(self, anchor, label_width, label_height, occupied, width, height):
        gap = 7.0
        initial = (min(anchor[0] + gap, width - label_width), min(anchor[1] + gap, height - label_height))
        candidates = [initial]
        for radius in range(1, 8):
            distance = radius * (max(label_width, label_height) + gap)
            candidates.extend(
                (
                    anchor[0] + dx * distance,
                    anchor[1] + dy * distance,
                )
                for dx, dy in ((1, 1), (1, -1), (-1, 1), (-1, -1), (0, 1), (0, -1), (1, 0), (-1, 0))
            )
        for x, y in candidates:
            x = max(2.0, min(x, width - label_width - 2.0))
            y = max(2.0, min(y, height - label_height - 2.0))
            box = (x, y, x + label_width, y + label_height)
            if not any(self._boxes_overlap(box, other) for other in occupied):
                return (x, y), box, (x, y) != initial
        x, y = initial
        return (x, y), (x, y, x + label_width, y + label_height), True

    @staticmethod
    def _boxes_overlap(first, second) -> bool:
        return first[0] < second[2] and first[2] > second[0] and first[1] < second[3] and first[3] > second[1]

    def _world_to_display(self, position):
        self.renderer.SetWorldPoint(*position, 1.0)
        self.renderer.WorldToDisplay()
        return self.renderer.GetDisplayPoint()

    def _display_to_world(self, x, y, z):
        self.renderer.SetDisplayPoint(x, y, z)
        self.renderer.DisplayToWorld()
        world = self.renderer.GetWorldPoint()
        divisor = world[3] or 1.0
        return tuple(component / divisor for component in world[:3])

    def _add_leader(self, anchor, label_position, color, opacity=1.0):
        line = vtk.vtkLineSource()
        line.SetPoint1(*anchor)
        line.SetPoint2(*label_position)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(line.GetOutputPort())
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(*color)
        actor.GetProperty().SetOpacity(opacity)
        actor.GetProperty().SetLineWidth(1.0)
        actor.SetPickable(False)
        self.renderer.AddActor(actor)
        self._actors.append(actor)

    def _center(self, points):
        return tuple(
            sum(getattr(point, axis) for point in points) / len(points)
            for axis in ("x", "y", "z")
        )

    def _add_point(self, entity_id, x, y, z, selected, category, labels, label_scale, label_text):
        points = vtk.vtkPoints(); points.InsertNextPoint(x, y, z)
        cells = vtk.vtkCellArray(); cells.InsertNextCell(1); cells.InsertCellPoint(0)
        data = vtk.vtkPolyData(); data.SetPoints(points); data.SetVerts(cells)
        mapper = vtk.vtkPolyDataMapper(); mapper.SetInputData(data)
        actor = vtk.vtkActor(); actor.SetMapper(mapper); actor.GetProperty().SetPointSize(10 if selected else 6)
        color = (1.0, 0.3, 0.2) if selected else color_for_category(category)
        actor.GetProperty().SetColor(*color)
        self.renderer.AddActor(actor); self._actors.append(actor)
        if labels:
            priority = 2 if category == "Topology" else 3
            self._add_label(entity_id, (x, y, z), color, label_scale, label_text, selected, priority)

    def _add_polyline(self, entity_id, points, selected, category, labels, label_scale, label_text):
        vtk_points = vtk.vtkPoints()
        for point in points: vtk_points.InsertNextPoint(point.x, point.y, point.z)
        line = vtk.vtkPolyLine(); line.GetPointIds().SetNumberOfIds(len(points))
        for index in range(len(points)): line.GetPointIds().SetId(index, index)
        cells = vtk.vtkCellArray(); cells.InsertNextCell(line)
        data = vtk.vtkPolyData(); data.SetPoints(vtk_points); data.SetLines(cells)
        mapper = vtk.vtkPolyDataMapper(); mapper.SetInputData(data)
        actor = vtk.vtkActor(); actor.SetMapper(mapper); actor.GetProperty().SetLineWidth(3 if selected else 1.5)
        color = (1.0, 0.3, 0.2) if selected else color_for_category(category)
        actor.GetProperty().SetColor(*color)
        self.renderer.AddActor(actor); self._actors.append(actor)
        if labels:
            self._add_label(entity_id, self._center(points), color, label_scale, label_text, selected, 1)

    def _add_mesh(self, mesh, selected, labels, label_scale, label_text):
        points = vtk.vtkPoints()
        for point in mesh.points: points.InsertNextPoint(point.x, point.y, point.z)
        triangles = vtk.vtkCellArray()
        for a, b, c in mesh.triangles:
            triangle = vtk.vtkTriangle()
            triangle.GetPointIds().SetId(0, a); triangle.GetPointIds().SetId(1, b); triangle.GetPointIds().SetId(2, c)
            triangles.InsertNextCell(triangle)
        data = vtk.vtkPolyData(); data.SetPoints(points); data.SetPolys(triangles)
        mapper = vtk.vtkPolyDataMapper(); mapper.SetInputData(data)
        actor = vtk.vtkActor(); actor.SetMapper(mapper); actor.GetProperty().SetOpacity(0.35); actor.GetProperty().SetColor(0.3, 0.7, 1.0)
        if mesh.curved:
            # Shared vertices plus Phong interpolation make sampled analytic
            # surfaces read as smooth rather than as a row of flat facets.
            normals = vtk.vtkPolyDataNormals()
            normals.SetInputData(data)
            normals.SplittingOff()
            normals.ConsistencyOn()
            mapper.SetInputConnection(normals.GetOutputPort())
            actor.GetProperty().SetInterpolationToPhong()
        else:
            # Planar previews are triangulated with a fan. Lighting can give
            # those triangles different normals and create a diagonal split.
            actor.GetProperty().LightingOff()
        if selected: actor.GetProperty().SetColor(1.0, 0.4, 0.2); actor.GetProperty().SetOpacity(0.55)
        self.renderer.AddActor(actor); self._actors.append(actor)
        if labels:
            color = (1.0, 0.4, 0.2) if selected else (0.3, 0.7, 1.0)
            self._add_label(mesh.entity_id, self._center(mesh.points), color, label_scale, label_text, selected, 0)
