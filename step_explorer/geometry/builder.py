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
    curved: bool = False


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
                points = self._edge_points(entity, snapshot)
                if len(points) >= 2:
                    snapshot.polylines.append(Polyline(entity.entity_id, points))
            elif name == "ORIENTED_EDGE":
                edge_refs = [item for item in entity.arguments if _ref(item) is not None]
                edge = self.document.entity(_ref(edge_refs[-1]) if edge_refs else -1)
                if edge and edge.type_name.upper() == "EDGE_CURVE":
                    points = self._edge_points(edge, snapshot)
                    if len(points) >= 2:
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
        curve_id = next((_ref(item) for item in entity.arguments[3:4]), None)
        curve = self.document.entity(curve_id or -1)
        if len(points) == 2 and curve and curve.type_name.upper() == "CIRCLE":
            same_sense = next(
                (item for item in reversed(entity.arguments) if isinstance(item, StepEnumeration)), None
            )
            sampled = self._circle_arc(
                curve,
                points[0],
                points[1],
                same_sense is None or same_sense.value.upper() == "T",
            )
            if sampled:
                return sampled
        return points

    def _circle_arc(
        self, circle: StepEntity, start: Point3, end: Point3, same_sense: bool
    ) -> tuple[Point3, ...]:
        placement_id = next((_ref(item) for item in circle.arguments if _ref(item) is not None), None)
        radius = next((_number(item) for item in circle.arguments if _number(item) is not None), None)
        placement = self.document.entity(placement_id or -1)
        if not placement or placement.type_name.upper() != "AXIS2_PLACEMENT_3D" or radius is None:
            return ()
        refs = [_ref(item) for item in placement.arguments if _ref(item) is not None]
        if not refs:
            return ()
        center = self._cartesian(refs[0])
        normal = self._direction(refs[1]) if len(refs) > 1 else (0.0, 0.0, 1.0)
        x_axis = self._direction(refs[2]) if len(refs) > 2 else None
        if center is None or normal is None:
            return ()
        normal = self._normalized(normal)
        if x_axis is None:
            seed = (1.0, 0.0, 0.0) if abs(normal[0]) < 0.9 else (0.0, 1.0, 0.0)
            x_axis = self._normalized(self._cross(seed, normal))
        else:
            x_axis = self._normalized(x_axis)
        y_axis = self._normalized(self._cross(normal, x_axis))
        if not normal or not x_axis or not y_axis:
            return ()

        def angle(point: Point3) -> float:
            delta = (point.x - center.x, point.y - center.y, point.z - center.z)
            return math.atan2(self._dot(delta, y_axis), self._dot(delta, x_axis))

        start_angle = angle(start)
        sweep = (angle(end) - start_angle) % (2.0 * math.pi)
        # Coincident endpoints denote a complete circle in STEP.
        if sweep < 1e-9:
            sweep = 2.0 * math.pi
        if not same_sense:
            sweep -= 2.0 * math.pi
        segments = max(4, int(math.ceil(abs(sweep) / (math.pi / 18.0))))
        result = []
        for index in range(segments + 1):
            parameter = start_angle + sweep * index / segments
            result.append(
                Point3(
                    center.x + radius * (math.cos(parameter) * x_axis[0] + math.sin(parameter) * y_axis[0]),
                    center.y + radius * (math.cos(parameter) * x_axis[1] + math.sin(parameter) * y_axis[1]),
                    center.z + radius * (math.cos(parameter) * x_axis[2] + math.sin(parameter) * y_axis[2]),
                )
            )
        # Preserve exact topology vertices, avoiding tiny seams from trigonometry.
        result[0], result[-1] = start, end
        return tuple(result)

    def _cartesian(self, entity_id: int) -> Point3 | None:
        entity = self.document.entity(entity_id)
        if not entity or entity.type_name.upper() != "CARTESIAN_POINT":
            return None
        values = next((_aggregate(item) for item in entity.arguments if isinstance(item, StepAggregate)), ())
        coords = [_number(item) for item in values[:3]]
        return Point3(*coords) if len(coords) == 3 and all(value is not None for value in coords) else None

    def _direction(self, entity_id: int) -> tuple[float, float, float] | None:
        entity = self.document.entity(entity_id)
        if not entity or entity.type_name.upper() != "DIRECTION":
            return None
        values = next((_aggregate(item) for item in entity.arguments if isinstance(item, StepAggregate)), ())
        coords = [_number(item) for item in values[:3]]
        return tuple(coords) if len(coords) == 3 and all(value is not None for value in coords) else None

    @staticmethod
    def _dot(first, second) -> float:
        return sum(a * b for a, b in zip(first, second))

    @staticmethod
    def _cross(first, second):
        return (
            first[1] * second[2] - first[2] * second[1],
            first[2] * second[0] - first[0] * second[2],
            first[0] * second[1] - first[1] * second[0],
        )

    @staticmethod
    def _normalized(vector):
        length = math.sqrt(sum(component * component for component in vector))
        return tuple(component / length for component in vector) if length > 1e-12 else None

    def _face_mesh(self, entity: StepEntity, snapshot: GeometrySnapshot, visible: dict[int, StepEntity]) -> Mesh | None:
        # AP203's ADVANCED_FACE has a bounds aggregate and a surface reference.
        bound_ids: list[int] = []
        for argument in entity.arguments:
            bound_ids.extend(item.entity_id for item in _aggregate(argument) if isinstance(item, StepReference))
        polygon: list[Point3] = []
        segments: list[tuple[Point3, ...]] = []
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
                    same_sense = next((item for item in oriented.arguments if isinstance(item, StepEnumeration)), None)
                    if same_sense and same_sense.value.upper() == "F":
                        points = tuple(reversed(points))
                    if len(points) < 2:
                        continue
                    segments.append(points)
                    if not polygon:
                        polygon.extend(points)
                    elif polygon[-1] == points[0]:
                        polygon.extend(points[1:])
                    elif polygon[-1] == points[1]:
                        # Some exporters store the edge direction opposite to
                        # the loop order. Reverse it instead of introducing a
                        # disconnected/self-crossing fan polygon.
                        reversed_points = tuple(reversed(points))
                        segments[-1] = reversed_points
                        polygon.extend(reversed_points[1:])
            break
        if len(polygon) >= 3 and polygon[0] == polygon[-1]:
            polygon.pop()
        if len(polygon) < 3:
            return None
        surface_id = next((_ref(item) for item in entity.arguments if _ref(item) is not None), None)
        surface = visible.get(surface_id or -1)
        curved = [segment for segment in segments if len(segment) > 2]
        if surface and surface.type_name.upper() == "CYLINDRICAL_SURFACE" and len(curved) == 2:
            first, second = curved
            if len(first) == len(second):
                # A bounded cylindrical patch is a ruled strip between its two
                # circular boundary arcs.  Stitch those arcs rather than using
                # a fan, which would incorrectly cap the cylinder with chords.
                if self._distance(first[0], second[0]) > self._distance(first[0], second[-1]):
                    second = tuple(reversed(second))
                points = first + second
                offset = len(first)
                triangles = []
                for index in range(len(first) - 1):
                    triangles.extend(((index, index + 1, offset + index + 1), (index, offset + index + 1, offset + index)))
                return Mesh(entity.entity_id, points, tuple(triangles), curved=True)
        # A fan is intentionally modest: this is an educational preview and the
        # boundary wire remains authoritative when a polygon is not planar.
        return Mesh(entity.entity_id, tuple(polygon), tuple((0, index, index + 1) for index in range(1, len(polygon) - 1)))

    @staticmethod
    def _distance(first: Point3, second: Point3) -> float:
        return math.sqrt((first.x - second.x) ** 2 + (first.y - second.y) ** 2 + (first.z - second.z) ** 2)
