"""Shared semantic categories and colors for the tree and viewport."""

TOPOLOGY_TYPES = {
    "MANIFOLD_SOLID_BREP", "CLOSED_SHELL", "OPEN_SHELL", "ADVANCED_FACE",
    "FACE_OUTER_BOUND", "FACE_BOUND", "EDGE_LOOP", "ORIENTED_EDGE",
    "EDGE_CURVE", "VERTEX_POINT",
}
GEOMETRY_TYPES = {
    "CARTESIAN_POINT", "DIRECTION", "VECTOR", "AXIS2_PLACEMENT_3D",
    "LINE", "CIRCLE", "PLANE", "CYLINDRICAL_SURFACE",
}
STRUCTURE_HINTS = (
    "PRODUCT", "REPRESENTATION", "DEFINITION", "CONTEXT", "SHAPE_",
    "APPLICATION_", "DESIGN_",
)

CATEGORY_COLORS = {
    "Topology": "#ffb74d",
    "Geometry": "#4fc3f7",
    "Structure": "#ce93d8",
    "Metadata": "#90a4ae",
}


def category_for_type(type_name: str) -> str:
    normalized = type_name.upper()
    if normalized in TOPOLOGY_TYPES:
        return "Topology"
    if normalized in GEOMETRY_TYPES:
        return "Geometry"
    if normalized == "COMPLEX" or normalized.startswith(STRUCTURE_HINTS):
        return "Structure"
    return "Metadata"


def color_for_category(category: str) -> tuple[float, float, float]:
    value = CATEGORY_COLORS.get(category, CATEGORY_COLORS["Metadata"])
    return tuple(int(value[index : index + 2], 16) / 255 for index in (1, 3, 5))


def color_for_depth(category: str, depth: int) -> tuple[float, float, float]:
    """Shade a category color by displayed semantic-tree depth."""

    base = color_for_category(category)
    background = (0.10, 0.12, 0.15)
    strength = max(0.42, 1.0 - min(max(depth, 0), 12) * 0.055)
    return tuple(background[index] + (component - background[index]) * strength for index, component in enumerate(base))
