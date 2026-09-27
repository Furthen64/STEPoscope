"""Kernel-free STEP shell reports and deterministic offscreen rendering."""

from __future__ import annotations

import json
import math
from collections import defaultdict
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


def _edge_judgement(meshes: list[Mesh]) -> tuple[int, list[list[int]], set[int]]:
    """Return open-edge count, equally wound triangle pairs, and their faces.

    Meshes own separate point arrays, so vertices are welded by deterministic
    coordinate keys solely for adjacency. Geometry itself is never changed.
    """

    coordinates = [point for mesh in meshes for point in mesh.points]
    if not coordinates:
        return 0, [], set()
    extent = max(
        (max(getattr(point, axis) for point in coordinates) - min(getattr(point, axis) for point in coordinates)
         for axis in ("x", "y", "z")),
        default=1.0,
    )
    tolerance = max(extent * 1e-9, 1e-10)

    def vertex_key(point: Point3) -> tuple[int, int, int]:
        return tuple(round(value / tolerance) for value in (point.x, point.y, point.z))

    # undirected edge -> (directed start/end, global triangle id, face id)
    adjacency: dict[tuple[tuple[int, int, int], tuple[int, int, int]], list[tuple[object, object, int, int]]] = defaultdict(list)
    triangle_id = 0
    for mesh in meshes:
        keys = [vertex_key(point) for point in mesh.points]
        for triangle in mesh.triangles:
            triangle_id += 1
            for start_index, end_index in zip(triangle, (triangle[1], triangle[2], triangle[0])):
                start, end = keys[start_index], keys[end_index]
                edge = (start, end) if start <= end else (end, start)
                adjacency[edge].append((start, end, triangle_id, mesh.entity_id))

    n_boundary_edges = sum(len(incidents) != 2 for incidents in adjacency.values())
    bad_edges: list[list[int]] = []
    face_constraints: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for incidents in adjacency.values():
        if len(incidents) != 2:
            continue
        first, second = incidents
        same_direction = first[0] == second[0] and first[1] == second[1]
        if same_direction:
            bad_edges.append([first[2], second[2]])
        if first[3] != second[3]:
            parity = 1 if same_direction else 0
            face_constraints[first[3]].append((second[3], parity))
            face_constraints[second[3]].append((first[3], parity))

    # Solve the relative winding constraints per connected component. Each
    # component may be globally inverted, so choose the assignment requiring
    # the fewest face flips; global signed volume handles an all-face flip.
    bad_faces: set[int] = set()
    unseen = {mesh.entity_id for mesh in meshes}
    while unseen:
        root = min(unseen)
        assignment = {root: 0}
        stack = [root]
        while stack:
            face_id = stack.pop()
            for neighbor, parity in face_constraints.get(face_id, ()):
                expected = assignment[face_id] ^ parity
                if neighbor not in assignment:
                    assignment[neighbor] = expected
                    stack.append(neighbor)
        unseen.difference_update(assignment)
        ones = {face_id for face_id, value in assignment.items() if value}
        zeros = set(assignment) - ones
        bad_faces.update(ones if len(ones) <= len(zeros) else zeros)
    bad_edges.sort()
    return n_boundary_edges, bad_edges, bad_faces


def build_report(source: Path, document: StepDocument, meshes: list[Mesh]) -> dict:
    mesh_by_id = {mesh.entity_id: mesh for mesh in meshes}
    shells = [entity for entity in document.entities if entity.type_name.upper() in {"CLOSED_SHELL", "OPEN_SHELL"}]
    if not shells:
        shells = [None]
    solids = []
    for shell in shells:
        ids = _face_ids(document, shell) if shell else [entity.entity_id for entity in document.entities if entity.type_name.upper() == "ADVANCED_FACE"]
        shell_meshes = [mesh_by_id[entity_id] for entity_id in ids if entity_id in mesh_by_id]
        contributions = {mesh.entity_id: _contribution(mesh) for mesh in shell_meshes}
        total = sum(contributions.values())
        scale = max((abs(value) for value in contributions.values()), default=1.0)
        eps = max(1e-12, scale * 1e-10)
        n_boundary_edges, bad_edges, bad_faces = _edge_judgement(shell_meshes)
        global_sign_ok = total > eps
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
            faces.append({
                "entity_id": entity_id, "type_name": type_name, "sense": sense,
                "sense_applied": applied, "mean_normal": mean_normal,
                "signed_volume_contribution": contribution,
                "ok": entity_id not in bad_faces,
            })
        coverage_ok = all(face["sense_applied"] is True for face in faces)
        if n_boundary_edges:
            verdict = "open"
        elif not coverage_ok:
            verdict = "unreliable"
        elif bad_edges or not global_sign_ok:
            verdict = "inconsistent"
        else:
            verdict = "consistent"
        if verdict != "consistent":
            for face in faces:
                face["ok"] = False if verdict in {"open", "unreliable"} or not global_sign_ok else face["ok"]
        solids.append({
            "shell_entity_id": shell.entity_id if shell else None,
            "faces": faces, "total_signed_volume": total,
            "n_inconsistent": sum(face["entity_id"] in bad_faces for face in faces),
            "n_boundary_edges": n_boundary_edges,
            "bad_edges": bad_edges,
            "verdict": verdict,
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
