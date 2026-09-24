from step_explorer.visualization.vtk_view import VtkView


def test_disabling_autozoom_keeps_the_current_camera_framing():
    view = VtkView.__new__(VtkView)
    view.renderer = None
    view._initialized = False
    view.autozoom = True
    view._fit_camera_on_next_render = False

    view.set_autozoom(False)

    assert view.autozoom is False
    assert view._fit_camera_on_next_render is False


def test_enabling_autozoom_requests_a_camera_fit():
    view = VtkView.__new__(VtkView)
    view.renderer = None
    view._initialized = False
    view.autozoom = False
    view._fit_camera_on_next_render = False

    view.set_autozoom(True)

    assert view.autozoom is True
    assert view._fit_camera_on_next_render is True
