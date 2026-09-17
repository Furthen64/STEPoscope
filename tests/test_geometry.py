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
