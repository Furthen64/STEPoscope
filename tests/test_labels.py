from step_explorer.ui.main_window import _label_for_entity_type


def test_rendered_entity_types_have_compact_labels():
    assert _label_for_entity_type("VERTEX_POINT") == "Vertex"
    assert _label_for_entity_type("EDGE_CURVE") == "Edge"
    assert _label_for_entity_type("ADVANCED_FACE") == "Face"
    assert _label_for_entity_type("MANIFOLD_SOLID_BREP") == "BREP"
    assert _label_for_entity_type("B_SPLINE_CURVE_WITH_KNOTS") == "NURBS"
