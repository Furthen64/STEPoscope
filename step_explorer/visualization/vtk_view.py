from __future__ import annotations

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


class VtkView(QWidget):
    """Render simple primitives; all STEP interpretation stays in GeometryBuilder."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._actors = []
        self._initialized = False
        self._last_snapshot = None
        self._last_selected_id = None
        self._last_labels = False
        if vtk is None or QVTKRenderWindowInteractor is None:
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel("VTK is not installed.\nParser and traversal remain available."))
            self.renderer = None
            return
        self.widget = QVTKRenderWindowInteractor(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.widget)
        self.renderer = vtk.vtkRenderer()
        self.renderer.SetBackground(0.10, 0.12, 0.15)
        self.widget.GetRenderWindow().AddRenderer(self.renderer)

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
            self._render_snapshot(self._last_snapshot, self._last_selected_id, self._last_labels)

    def show_snapshot(self, snapshot, selected_id: int | None = None, labels: bool = False) -> None:
        if self.renderer is None:
            return
        self._last_snapshot = snapshot
        self._last_selected_id = selected_id
        self._last_labels = labels
        if not self._initialized:
            return
        self._render_snapshot(snapshot, selected_id, labels)

    def _render_snapshot(self, snapshot, selected_id: int | None, labels: bool) -> None:
        for actor in self._actors:
            self.renderer.RemoveActor(actor)
        self._actors.clear()
        for entity_id, point in snapshot.points.items():
            self._add_point(entity_id, point.x, point.y, point.z, selected_id == entity_id, "Geometry")
        for entity_id, point in snapshot.vertices.items():
            self._add_point(entity_id, point.x, point.y, point.z, selected_id == entity_id, "Topology")
        for polyline in snapshot.polylines:
            category = "Geometry" if polyline.category == "edge" else "Structure"
            self._add_polyline(polyline.entity_id, polyline.points, selected_id == polyline.entity_id, category)
        for face in snapshot.faces:
            self._add_mesh(face, selected_id == face.entity_id)
        self.renderer.ResetCamera()
        self.widget.GetRenderWindow().Render()

    def _add_point(self, entity_id, x, y, z, selected, category):
        points = vtk.vtkPoints(); points.InsertNextPoint(x, y, z)
        cells = vtk.vtkCellArray(); cells.InsertNextCell(1); cells.InsertCellPoint(0)
        data = vtk.vtkPolyData(); data.SetPoints(points); data.SetVerts(cells)
        mapper = vtk.vtkPolyDataMapper(); mapper.SetInputData(data)
        actor = vtk.vtkActor(); actor.SetMapper(mapper); actor.GetProperty().SetPointSize(10 if selected else 6)
        actor.GetProperty().SetColor(1.0, 0.3, 0.2) if selected else actor.GetProperty().SetColor(*color_for_category(category))
        self.renderer.AddActor(actor); self._actors.append(actor)

    def _add_polyline(self, entity_id, points, selected, category):
        vtk_points = vtk.vtkPoints()
        for point in points: vtk_points.InsertNextPoint(point.x, point.y, point.z)
        line = vtk.vtkPolyLine(); line.GetPointIds().SetNumberOfIds(len(points))
        for index in range(len(points)): line.GetPointIds().SetId(index, index)
        cells = vtk.vtkCellArray(); cells.InsertNextCell(line)
        data = vtk.vtkPolyData(); data.SetPoints(vtk_points); data.SetLines(cells)
        mapper = vtk.vtkPolyDataMapper(); mapper.SetInputData(data)
        actor = vtk.vtkActor(); actor.SetMapper(mapper); actor.GetProperty().SetLineWidth(3 if selected else 1.5)
        actor.GetProperty().SetColor(1.0, 0.3, 0.2) if selected else actor.GetProperty().SetColor(*color_for_category(category))
        self.renderer.AddActor(actor); self._actors.append(actor)

    def _add_mesh(self, mesh, selected):
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
        if selected: actor.GetProperty().SetColor(1.0, 0.4, 0.2); actor.GetProperty().SetOpacity(0.55)
        self.renderer.AddActor(actor); self._actors.append(actor)
