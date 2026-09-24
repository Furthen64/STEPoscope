import pytest

from step_explorer.geometry.builder import GeometryBuilder, Mesh, Point3
from step_explorer.step.parser import parse_step
from step_explorer.visualization.vtk_view import VtkView, vtk


@pytest.mark.parametrize("surface_type", ["PLANE", "CYLINDRICAL_SURFACE"])
@pytest.mark.parametrize("sense, expected", [("T", (0, 1, 2)), ("F", (0, 2, 1))])
def test_face_preview_winding_follows_step_surface_sense(surface_type, sense, expected):
    surface_arguments = "'',#3" if surface_type == "PLANE" else "'',#3,1."
    source = f"""ISO-10303-21;DATA;
    #1=ADVANCED_FACE('',(),#2,.{sense}.);
    #2={surface_type}({surface_arguments});
    #3=AXIS2_PLACEMENT_3D('',#4,#5,$);
    #4=CARTESIAN_POINT('',(0.,0.,0.));
    #5=DIRECTION('',(0.,0.,1.));
    ENDSEC;END-ISO-10303-21;"""
    document = parse_step(source)
    builder = GeometryBuilder(document)
    points = (
        (Point3(0, 0, 0), Point3(1, 0, 0), Point3(0, 1, 0))
        if surface_type == "PLANE" else
        (Point3(1, 0, 0), Point3(0.5, 0.8660254, 0), Point3(1, 0, 1))
    )

    assert builder._oriented_face_triangles(document.entity(1), document.entity(2), points, ((0, 1, 2),)) == (expected,)


@pytest.mark.skipif(vtk is None, reason="VTK is not installed")
def test_face_orientation_colors_front_and_back_without_transparency():
    view = VtkView.__new__(VtkView)
    view.renderer = vtk.vtkRenderer()
    view._actors = []
    view.normal_display = "Face orientation"
    mesh = Mesh(7, (Point3(0, 0, 0), Point3(1, 0, 0), Point3(0, 1, 0)), ((0, 1, 2),))

    view._add_mesh(mesh, selected=False, labels=False, label_scale=1.0, label_text="")

    actor = view._actors[0]
    assert actor.GetProperty().GetOpacity() == 1.0
    assert actor.GetProperty().GetColor() == pytest.approx((0.2, 0.5, 1.0))
    assert actor.GetBackfaceProperty().GetColor() == pytest.approx((1.0, 0.25, 0.2))


@pytest.mark.skipif(vtk is None, reason="VTK is not installed")
def test_normal_vectors_add_directional_arrows():
    view = VtkView.__new__(VtkView)
    view.renderer = vtk.vtkRenderer()
    view._actors = []
    view.normal_display = "Vectors"
    view._normal_length = 1.0
    mesh = Mesh(7, (Point3(0, 0, 0), Point3(1, 0, 0), Point3(0, 1, 0)), ((0, 1, 2),))

    view._add_mesh(mesh, selected=False, labels=False, label_scale=1.0, label_text="")

    assert len(view._actors) == 2
    mapper = view._actors[1].GetMapper()
    mapper.Update()
    assert mapper.GetInput().GetNumberOfPoints() > 0
    assert mapper.GetInput().GetBounds()[5] == pytest.approx(1.0)
