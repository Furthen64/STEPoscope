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
    cylindrical_faces = [face for face in snapshot.faces if face.triangles[0][2] > 2]
    assert len(curved_edges) == 12  # Four EDGE_CURVEs and their loop occurrences.
    assert len(cylindrical_faces) == 2
    assert all(len(face.triangles) == 36 for face in cylindrical_faces)
