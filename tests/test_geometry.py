from step_explorer.geometry import GeometryBuilder, Point3
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
