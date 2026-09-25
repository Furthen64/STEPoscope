"""Kernel-free STEP shell reports and deterministic offscreen rendering."""

from __future__ import annotations

import json
import math
from pathlib import Path

from .geometry.builder import GeometryBuilder, Mesh, Point3
from .step.parser import StepDocument
from .step.values import StepAggregate, StepEnumeration, StepReference


def _face_ids(document: StepDocument, shell) -> list[int]:
    return [
        value.entity_id
        for argument in shell.arguments
        if isinstance(argument, StepAggregate)
        for value in argument.values
        if isinstance(value, StepReference)
    ]


def _contribution(mesh: Mesh) -> float:
    total = 0.0
    for indices in mesh.triangles:
        p, q, r = (mesh.points[index] for index in indices)
        total += (
            p.x * (q.y * r.z - q.z * r.y)
            - p.y * (q.x * r.z - q.z * r.x)
            + p.z * (q.x * r.y - q.y * r.x)
        ) / 6.0
    return total


def _mean_normal(mesh: Mesh) -> list[float]:
    vector = [0.0, 0.0, 0.0]
    for a, b, c in mesh.triangles:
        p, q, r = (mesh.points[index] for index in (a, b, c))
        vector[0] += (q.y - p.y) * (r.z - p.z) - (q.z - p.z) * (r.y - p.y)
        vector[1] += (q.z - p.z) * (r.x - p.x) - (q.x - p.x) * (r.z - p.z)
        vector[2] += (q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x)
    length = math.sqrt(sum(value * value for value in vector))
    return [value / length for value in vector] if length > 1e-15 else [0.0, 0.0, 0.0]


def build_report(source: Path, document: StepDocument, meshes: list[Mesh]) -> dict:
    mesh_by_id = {mesh.entity_id: mesh for mesh in meshes}
    shells = [entity for entity in document.entities if entity.type_name.upper() in {"CLOSED_SHELL", "OPEN_SHELL"}]
    if not shells:
        shells = [None]
    solids = []
    for shell in shells:
        ids = _face_ids(document, shell) if shell else [entity.entity_id for entity in document.entities if entity.type_name.upper() == "ADVANCED_FACE"]
        contributions = {entity_id: _contribution(mesh_by_id[entity_id]) for entity_id in ids if entity_id in mesh_by_id}
        total = sum(contributions.values())
        scale = max((abs(value) for value in contributions.values()), default=1.0)
        eps = max(1e-12, scale * 1e-10)
        faces = []
        for entity_id in ids:
            mesh = mesh_by_id.get(entity_id)
            entity = document.entity(entity_id)
            contribution = contributions.get(entity_id, 0.0)
            if mesh:
                type_name, sense, applied = mesh.type_name, mesh.sense, mesh.sense_applied
                mean_normal = _mean_normal(mesh)
            else:
                surface_id = next((arg.entity_id for arg in (entity.arguments if entity else ()) if isinstance(arg, StepReference)), None)
                surface = document.entity(surface_id or -1)
                sense_arg = next((arg for arg in reversed(entity.arguments if entity else ()) if isinstance(arg, StepEnumeration)), None)
                type_name = surface.type_name.upper() if surface else "UNKNOWN"
                sense = f".{sense_arg.value.upper()}." if sense_arg else ".T."
                applied, mean_normal = False, [0.0, 0.0, 0.0]
            ok = abs(contribution) <= eps or abs(total) <= eps or contribution * total > 0
            faces.append({
                "entity_id": entity_id, "type_name": type_name, "sense": sense,
                "sense_applied": applied, "mean_normal": mean_normal,
                "signed_volume_contribution": contribution, "ok": ok,
            })
        solids.append({
            "shell_entity_id": shell.entity_id if shell else None,
            "faces": faces, "total_signed_volume": total,
            "n_inconsistent": sum(not face["ok"] for face in faces),
        })
    return {"source": str(source), "solids": solids}


def render_png(meshes: list[Mesh], report: dict, output: Path, width: int, height: int, camera: str, mode: str) -> None:
    import vtkmodules.all as vtk

    verdicts = {face["entity_id"]: face["ok"] for solid in report["solids"] for face in solid["faces"]}
    renderer = vtk.vtkRenderer()
    renderer.SetBackground(0.10, 0.12, 0.15)
    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(width, height)
    window.SetMultiSamples(0)
    window.AddRenderer(renderer)
    for mesh in meshes:
        points = vtk.vtkPoints()
        for point in mesh.points:
            points.InsertNextPoint(point.x, point.y, point.z)
        cells = vtk.vtkCellArray()
        for triangle in mesh.triangles:
            cell = vtk.vtkTriangle()
            for index, point_id in enumerate(triangle):
                cell.GetPointIds().SetId(index, point_id)
            cells.InsertNextCell(cell)
        data = vtk.vtkPolyData()
        data.SetPoints(points)
        data.SetPolys(cells)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(data)
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        if mode == "normals":
            actor.GetProperty().SetColor((0.2, 0.45, 1.0) if verdicts.get(mesh.entity_id, True) else (1.0, 0.15, 0.1))
        else:
            actor.GetProperty().SetColor(0.72, 0.76, 0.82)
        renderer.AddActor(actor)
    renderer.ResetCamera()
    cam = renderer.GetActiveCamera()
    focal = cam.GetFocalPoint()
    distance = cam.GetDistance()
    directions = {"front": (0, -1, 0), "top": (0, 0, 1), "right": (1, 0, 0), "iso": (1, -1, 1)}
    direction = directions[camera]
    length = math.sqrt(sum(value * value for value in direction))
    cam.SetPosition(*(focal[i] + distance * direction[i] / length for i in range(3)))
    cam.SetViewUp(0, 1, 0 if camera != "front" else 1)
    if camera == "front":
        cam.SetViewUp(0, 0, 1)
    cam.ParallelProjectionOn()
    renderer.ResetCamera()
    renderer.ResetCameraClippingRange()
    window.Render()
    capture = vtk.vtkWindowToImageFilter()
    capture.SetInput(window)
    capture.SetInputBufferTypeToRGB()
    capture.ReadFrontBufferOff()
    capture.Update()
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(str(output))
    writer.SetInputConnection(capture.GetOutputPort())
    writer.Write()
    window.Finalize()


def process_file(source: Path, output_base: Path, width: int, height: int, camera: str, mode: str) -> dict:
    document = StepDocument.from_file(source)
    snapshot = GeometryBuilder(document).build()
    report = build_report(source, document, snapshot.faces)
    output_base.parent.mkdir(parents=True, exist_ok=True)
    output_base.with_suffix(".json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    render_png(snapshot.faces, report, output_base.with_suffix(".png"), width, height, camera, mode)
    return report
