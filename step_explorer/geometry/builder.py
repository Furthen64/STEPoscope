"""Understand a useful, deliberately small subset of STEP geometry/topology."""

from dataclasses import dataclass, field
import math

from ..step.parser import StepDocument, StepEntity
from ..step.values import StepAggregate, StepEnumeration, StepNumber, StepReference, StepTypedValue, StepValue


@dataclass(frozen=True)
class Point3:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class Polyline:
    entity_id: int
    points: tuple[Point3, ...]
    category: str = "edge"


@dataclass(frozen=True)
class Mesh:
    entity_id: int
    points: tuple[Point3, ...]
    triangles: tuple[tuple[int, int, int], ...]


@dataclass
class GeometrySnapshot:
    points: dict[int, Point3] = field(default_factory=dict)
    vertices: dict[int, Point3] = field(default_factory=dict)
    polylines: list[Polyline] = field(default_factory=list)
    faces: list[Mesh] = field(default_factory=list)

    def point_for(self, entity_id: int) -> Point3 | None:
        return self.points.get(entity_id) or self.vertices.get(entity_id)


def _ref(value: StepValue) -> int | None:
    return value.entity_id if isinstance(value, StepReference) else None


def _aggregate(value: StepValue) -> tuple[StepValue, ...]:
    return value.values if isinstance(value, StepAggregate) else ()


def _number(value: StepValue) -> float | None:
    return float(value.value) if isinstance(value, StepNumber) else None


class GeometryBuilder:
    """Build simple primitives from all entities up to a physical order."""

    def __init__(self, document: StepDocument):
        self.document = document

    def build(self, through_order: int | None = None) -> GeometrySnapshot:
        entities = self.document.entities if through_order is None else self.document.entities[: through_order + 1]
        visible = {entity.entity_id: entity for entity in entities}
        snapshot = GeometrySnapshot()
        for entity in entities:
            if entity.type_name.upper() == "CARTESIAN_POINT":
                coords = _aggregate(entity.arguments[1] if len(entity.arguments) > 1 else entity.arguments[0])
                if len(coords) >= 3 and all(_number(item) is not None for item in coords[:3]):
                    snapshot.points[entity.entity_id] = Point3(*(_number(item) for item in coords[:3]))
        for entity in entities:
            if entity.type_name.upper() == "VERTEX_POINT":
                target = next((_ref(item) for item in entity.arguments if _ref(item) is not None), None)
                if target in snapshot.points:
                    snapshot.vertices[entity.entity_id] = snapshot.points[target]
        for entity in entities:
            name = entity.type_name.upper()
            if name == "EDGE_CURVE":
                endpoints = [_ref(item) for item in entity.arguments if _ref(item) is not None][:2]
                points = tuple(snapshot.point_for(item) for item in endpoints if item is not None and snapshot.point_for(item) is not None)
                if len(points) == 2:
                    snapshot.polylines.append(Polyline(entity.entity_id, points))
            elif name == "ORIENTED_EDGE":
                edge_refs = [item for item in entity.arguments if _ref(item) is not None]
                edge = self.document.entity(_ref(edge_refs[-1]) if edge_refs else -1)
                if edge and edge.type_name.upper() == "EDGE_CURVE":
                    points = self._edge_points(edge, snapshot)
                    if len(points) == 2:
                        same_sense = next((item for item in entity.arguments if isinstance(item, StepEnumeration)), None)
                        if same_sense and same_sense.value.upper() == "F":
                            points = tuple(reversed(points))
                        snapshot.polylines.append(Polyline(entity.entity_id, points, "oriented-edge"))
            elif name == "ADVANCED_FACE":
                mesh = self._face_mesh(entity, snapshot, visible)
                if mesh:
                    snapshot.faces.append(mesh)
        return snapshot

    def _edge_points(self, entity: StepEntity, snapshot: GeometrySnapshot) -> tuple[Point3, ...]:
        refs = [_ref(item) for item in entity.arguments if _ref(item) is not None][:2]
        points = tuple(snapshot.point_for(item) for item in refs if item is not None and snapshot.point_for(item) is not None)
        return points

    def _face_mesh(self, entity: StepEntity, snapshot: GeometrySnapshot, visible: dict[int, StepEntity]) -> Mesh | None:
        # AP203's ADVANCED_FACE has a bounds aggregate and a surface reference.
        bound_ids: list[int] = []
        for argument in entity.arguments:
            bound_ids.extend(item.entity_id for item in _aggregate(argument) if isinstance(item, StepReference))
        polygon: list[Point3] = []
        for bound_id in bound_ids:
            bound = visible.get(bound_id)
            if not bound or bound.type_name.upper() not in {"FACE_OUTER_BOUND", "FACE_BOUND"}:
                continue
            loop_id = next((_ref(item) for item in bound.arguments if _ref(item) is not None), None)
            loop = visible.get(loop_id or -1)
            if not loop or loop.type_name.upper() != "EDGE_LOOP":
                continue
            loop_items = next((_aggregate(argument) for argument in loop.arguments if isinstance(argument, StepAggregate)), ())
            for oriented_id in (_ref(item) for item in loop_items):
                oriented = visible.get(oriented_id or -1)
                if not oriented:
                    continue
                edge_refs = [_ref(item) for item in oriented.arguments if _ref(item) is not None]
                edge = visible.get(edge_refs[-1] if edge_refs else -1)
                if edge:
                    points = self._edge_points(edge, snapshot)
                    if points:
                        if not polygon or polygon[-1] != points[0]:
                            polygon.append(points[0])
                        polygon.append(points[-1])
            break
        if len(polygon) >= 3 and polygon[0] == polygon[-1]:
            polygon.pop()
        if len(polygon) < 3:
            return None
        # A fan is intentionally modest: this is an educational preview and the
        # boundary wire remains authoritative when a polygon is not planar.
        return Mesh(entity.entity_id, tuple(polygon), tuple((0, index, index + 1) for index in range(1, len(polygon) - 1)))
