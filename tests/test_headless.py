import json

from step_explorer.headless import build_report, process_file
from step_explorer.geometry.builder import GeometryBuilder
from step_explorer.step.parser import parse_step


def _box_source(flipped_face: int | None = None) -> str:
    points = ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))
    faces = ((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7))
    lines = ["ISO-10303-21;DATA;"]
    for index, point in enumerate(points, 1):
        lines.append(f"#{index}=CARTESIAN_POINT('',({point[0]}.,{point[1]}.,{point[2]}.));")
    normals = ((0,0,-1),(0,0,1),(0,-1,0),(1,0,0),(0,1,0),(-1,0,0))
    for index, normal in enumerate(normals, 9):
        lines.append(f"#{index}=DIRECTION('',({normal[0]}.,{normal[1]}.,{normal[2]}.));")
    next_id = 15
    face_ids = []
    for face_number, vertices in enumerate(faces):
        oriented = []
        for start, end in zip(vertices, vertices[1:] + vertices[:1]):
            edge, occurrence = next_id, next_id + 1
            next_id += 2
            lines.append(f"#{edge}=EDGE_CURVE('',#{start + 1},#{end + 1},$,.T.);")
            lines.append(f"#{occurrence}=ORIENTED_EDGE('',*,*,#{edge},.T.);")
            oriented.append(occurrence)
        loop, bound, placement, surface, face_id = range(next_id, next_id + 5)
        next_id += 5
        lines.append(f"#{loop}=EDGE_LOOP('',({','.join('#' + str(value) for value in oriented)}));")
        lines.append(f"#{bound}=FACE_OUTER_BOUND('',#{loop},.T.);")
        lines.append(f"#{placement}=AXIS2_PLACEMENT_3D('',#{vertices[0] + 1},#{face_number + 9},$);")
        lines.append(f"#{surface}=PLANE('',#{placement});")
        sense = "F" if flipped_face == face_number else "T"
        lines.append(f"#{face_id}=ADVANCED_FACE('',(#{bound}),#{surface},.{sense}.);")
        face_ids.append(face_id)
    lines.append(f"#{next_id}=CLOSED_SHELL('',({','.join('#' + str(value) for value in face_ids)}));")
    lines.append("ENDSEC;END-ISO-10303-21;")
    return "\n".join(lines)


def test_box_report_flags_the_flipped_face(tmp_path):
    document = parse_step(_box_source(flipped_face=2))
    meshes = GeometryBuilder(document).build().faces
    report = build_report(tmp_path / "box.step", document, meshes)

    inconsistent = [face["entity_id"] for face in report["solids"][0]["faces"] if not face["ok"]]
    assert inconsistent == [meshes[2].entity_id]
    json.dumps(report)


def test_headless_outputs_are_deterministic(tmp_path):
    source = tmp_path / "box.step"
    source.write_text(_box_source(), encoding="utf-8")

    process_file(source, tmp_path / "first" / "box", 160, 120, "iso", "normals")
    process_file(source, tmp_path / "second" / "box", 160, 120, "iso", "normals")

    assert (tmp_path / "first" / "box.json").read_bytes() == (tmp_path / "second" / "box.json").read_bytes()
    assert (tmp_path / "first" / "box.png").read_bytes() == (tmp_path / "second" / "box.png").read_bytes()
