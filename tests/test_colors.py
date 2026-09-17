from step_explorer.ui.colors import color_for_depth


def test_semantic_colors_shade_with_depth():
    shallow = color_for_depth("Topology", 0)
    deep = color_for_depth("Topology", 6)
    assert shallow != deep
    assert all(deep_component < shallow_component for deep_component, shallow_component in zip(deep, shallow))

