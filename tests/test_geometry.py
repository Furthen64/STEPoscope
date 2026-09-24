import pytest

from step_explorer.geometry import ControlNet, ControlNetStatus, GeometryBuilder, Point3
from step_explorer.step.parser import parse_step


def test_points_vertices_and_edges_are_interpreted():
    source = """ISO-10303-21;DATA;
    #1=CARTESIAN_POINT('',(0.,0.,0.));
    #2=CARTESIAN_POINT('',(1.,0.,0.));
    #3=VERTEX_POINT('',#1);
    #4=VERTEX_POINT('',#2);
    #5=EDGE_CURVE('',#3,#4,$,.T.);
    ENDSEC;END-ISO-10303-21;"""
    snapshot = GeometryBuilder(parse_step(source)).build()
    assert snapshot.points[1] == Point3(0.0, 0.0, 0.0)
    assert snapshot.vertices[3] == Point3(0.0, 0.0, 0.0)
    assert snapshot.polylines[0].points == (Point3(0.0, 0.0, 0.0), Point3(1.0, 0.0, 0.0))


def test_control_net_preserves_grid_order_and_exposes_adjacent_segments():
    p00, p01, p02 = (
        Point3(0.0, 0.0, 0.0),
        Point3(0.0, 1.0, 0.0),
        Point3(0.0, 2.0, 0.0),
    )
    p10, p11, p12 = (
        Point3(1.0, 0.0, 0.0),
        Point3(1.0, 1.0, 0.0),
        Point3(1.0, 2.0, 0.0),
    )
    control_net = ControlNet(42, ((p00, p01, p02), (p10, p11, p12)))

    assert (control_net.row_count, control_net.column_count) == (2, 3)
    assert control_net.point_markers == (p00, p01, p02, p10, p11, p12)
    assert control_net.row_segments == ((p00, p01), (p01, p02), (p10, p11), (p11, p12))
    assert control_net.column_segments == ((p00, p10), (p01, p11), (p02, p12))


def test_control_net_density_keeps_an_evenly_distributed_coarse_grid():
    control_net = ControlNet(
        42,
        tuple(
            tuple(Point3(float(row), float(column), 0.0) for column in range(5))
            for row in range(5)
        ),
    )

    coarse = control_net.at_density(0)
    assert coarse.rows == (
        (Point3(0.0, 0.0, 0.0), Point3(0.0, 4.0, 0.0)),
        (Point3(4.0, 0.0, 0.0), Point3(4.0, 4.0, 0.0)),
    )
    assert control_net.at_density(100) == control_net


@pytest.mark.parametrize(
    "rows, message",
    (
        (((Point3(0.0, 0.0, 0.0), Point3(0.0, 1.0, 0.0)),), "at least two rows"),
        (((Point3(0.0, 0.0, 0.0),), (Point3(1.0, 0.0, 0.0),)), "at least two columns"),
        (
            (
                (Point3(0.0, 0.0, 0.0), Point3(0.0, 1.0, 0.0)),
                (Point3(1.0, 0.0, 0.0),),
            ),
            "rectangular",
        ),
    ),
)
def test_control_net_rejects_incomplete_grids(rows, message):
    with pytest.raises(ValueError, match=message):
        ControlNet(42, rows)


def test_control_net_status_describes_each_playback_state():
    assert ControlNetStatus(1, "ready").description == "Control net ready"
    assert ControlNetStatus(2, "invalid").description == "Invalid control-point grid"
    assert ControlNetStatus(3, "waiting", (4,)).description == "Waiting for 1 control point"
    assert ControlNetStatus(4, "waiting", (5, 6)).description == "Waiting for 2 control points"


def test_bspline_surface_extracts_a_complete_control_net_after_forward_reference_arrives():
    source = """ISO-10303-21;DATA;
    #1=CARTESIAN_POINT('',(0.,0.,0.));
    #2=CARTESIAN_POINT('',(0.,1.,0.));
    #3=CARTESIAN_POINT('',(1.,0.,0.));
    #5=B_SPLINE_SURFACE_WITH_KNOTS('',1,1,((#1,#2),(#3,#4)),.UNSPECIFIED.,.F.,.F.,.F.,(2,2),(2,2),(0.,1.),(0.,1.),.UNSPECIFIED.);
    #4=CARTESIAN_POINT('',(1.,1.,0.));
    ENDSEC;END-ISO-10303-21;"""
    document = parse_step(source)

    incomplete_snapshot = GeometryBuilder(document).build(3)
    assert incomplete_snapshot.control_nets == []
    assert incomplete_snapshot.control_net_statuses == [ControlNetStatus(5, "waiting", (4,))]

    snapshot = GeometryBuilder(document).build()
    assert len(snapshot.control_nets) == 1
    assert snapshot.control_net_statuses == [ControlNetStatus(5, "ready")]
    control_net = snapshot.control_nets[0]
    assert control_net.entity_id == 5
    assert control_net.rows == (
        (Point3(0.0, 0.0, 0.0), Point3(0.0, 1.0, 0.0)),
        (Point3(1.0, 0.0, 0.0), Point3(1.0, 1.0, 0.0)),
    )


def test_bspline_surface_skips_a_malformed_control_grid():
    source = """ISO-10303-21;DATA;
    #1=CARTESIAN_POINT('',(0.,0.,0.));
    #2=CARTESIAN_POINT('',(0.,1.,0.));
    #3=CARTESIAN_POINT('',(1.,0.,0.));
    #4=B_SPLINE_SURFACE_WITH_KNOTS('',1,1,((#1,#2),(#3)),.UNSPECIFIED.,.F.,.F.,.F.,(2,2),(2,2),(0.,1.),(0.,1.),.UNSPECIFIED.);
    ENDSEC;END-ISO-10303-21;"""

    snapshot = GeometryBuilder(parse_step(source)).build()
    assert snapshot.control_nets == []
    assert snapshot.control_net_statuses == [ControlNetStatus(4, "invalid")]


def test_circles_loft_fixture_exposes_its_two_bspline_control_nets():
    from pathlib import Path

    source = Path("examples/circleslofted/step/circlesloft1.STEP").read_text()
    snapshot = GeometryBuilder(parse_step(source)).build()

    assert [(net.entity_id, net.row_count, net.column_count) for net in snapshot.control_nets] == [
        (117, 18, 5),
        (295, 18, 5),
    ]
    assert not {34, 355}.intersection(face.entity_id for face in snapshot.faces)


def test_circles_loft_surfaces_wait_for_forward_referenced_points_during_playback():
    from pathlib import Path

    source = Path("examples/circleslofted/step/circlesloft1.STEP").read_text()
    document = parse_step(source)

    waiting = GeometryBuilder(document).build(320)
    assert [(status.entity_id, status.state) for status in waiting.control_net_statuses] == [
        (117, "waiting"),
        (295, "waiting"),
    ]
    assert waiting.control_nets == []
    assert waiting.faces == []

    ready = GeometryBuilder(document).build()
    assert [(status.entity_id, status.state) for status in ready.control_net_statuses] == [
        (117, "ready"),
        (295, "ready"),
    ]


def test_face_loop_respects_oriented_edge_sense():
    source = """ISO-10303-21;DATA;
    #1=CARTESIAN_POINT('',(0.,0.,0.));
    #2=CARTESIAN_POINT('',(1.,0.,0.));
    #3=CARTESIAN_POINT('',(1.,1.,0.));
    #4=CARTESIAN_POINT('',(0.,1.,0.));
    #5=EDGE_CURVE('',#1,#2,$,.T.);
    #6=EDGE_CURVE('',#3,#2,$,.T.);
    #7=EDGE_CURVE('',#3,#4,$,.T.);
    #8=EDGE_CURVE('',#4,#1,$,.T.);
    #9=ORIENTED_EDGE('',*,*,#5,.T.);
    #10=ORIENTED_EDGE('',*,*,#6,.F.);
    #11=ORIENTED_EDGE('',*,*,#7,.T.);
    #12=ORIENTED_EDGE('',*,*,#8,.T.);
    #13=EDGE_LOOP('',(#9,#10,#11,#12));
    #14=FACE_OUTER_BOUND('',#13,.T.);
    #15=ADVANCED_FACE('',(#14),$,.T.);
    ENDSEC;END-ISO-10303-21;"""

    snapshot = GeometryBuilder(parse_step(source)).build()

    assert len(snapshot.faces) == 1
    assert snapshot.faces[0].points == (
        Point3(0.0, 0.0, 0.0),
        Point3(1.0, 0.0, 0.0),
        Point3(1.0, 1.0, 0.0),
        Point3(0.0, 1.0, 0.0),
    )


def test_circle_edge_is_sampled_as_an_arc():
    source = """ISO-10303-21;DATA;
    #1=CARTESIAN_POINT('',(0.,0.,0.));
    #2=DIRECTION('',(0.,0.,1.));
    #3=DIRECTION('',(1.,0.,0.));
    #4=AXIS2_PLACEMENT_3D('',#1,#2,#3);
    #5=CIRCLE('',#4,1.);
    #6=CARTESIAN_POINT('',(1.,0.,0.));
    #7=CARTESIAN_POINT('',(-1.,0.,0.));
    #8=VERTEX_POINT('',#6);
    #9=VERTEX_POINT('',#7);
    #10=EDGE_CURVE('',#8,#9,#5,.T.);
    ENDSEC;END-ISO-10303-21;"""

    edge = GeometryBuilder(parse_step(source)).build().polylines[0]

    assert len(edge.points) == 19
    assert edge.points[0] == Point3(1.0, 0.0, 0.0)
    assert edge.points[-1] == Point3(-1.0, 0.0, 0.0)
    assert max(point.y for point in edge.points) == 1.0


def test_slot_fixture_builds_curved_edges_and_cylindrical_strips():
    from pathlib import Path

    snapshot = GeometryBuilder(parse_step(Path("examples/stepAP203/slot1.STEP").read_text())).build()

    curved_edges = [edge for edge in snapshot.polylines if len(edge.points) > 2]
    cylindrical_faces = [face for face in snapshot.faces if face.curved]
    assert len(curved_edges) == 12  # Four EDGE_CURVEs and their loop occurrences.
    assert len(cylindrical_faces) == 2
    assert all(len(face.triangles) == 36 for face in cylindrical_faces)


def test_freecad_surface_curves_and_unordered_face_bounds_are_rendered():
    """FreeCAD wraps model curves and may emit holes before the outer loop."""
    from pathlib import Path

    snapshot = GeometryBuilder(
        parse_step(Path("examples/stepAP203/twoHoledCylinders_Freecad.step").read_text())
    ).build()

    assert len(snapshot.faces) == 11
    assert sum(edge.category == "edge" and len(edge.points) > 2 for edge in snapshot.polylines) == 10
    assert sum(face.curved for face in snapshot.faces) == 5

    top = next(face for face in snapshot.faces if face.entity_id == 516)
    assert len(top.points) > 100
    assert len(top.triangles) > 100
    # No generated triangle may bridge across either circular opening.
    holes = ((0.0, 0.0, 39.853569882), (-177.68662511, 177.68662511, 71.74429427))
    for triangle in top.triangles:
        vertices = [top.points[index] for index in triangle]
        x = sum(point.x for point in vertices) / 3
        y = sum(point.y for point in vertices) / 3
        assert all((x - cx) ** 2 + (y - cy) ** 2 >= radius**2 * 0.99 for cx, cy, radius in holes)
