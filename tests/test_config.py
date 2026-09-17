from step_explorer.config import AppConfig, load_config


def test_mouse_rotation_setting_is_loaded_from_toml(tmp_path):
    config_path = tmp_path / "steposcope.toml"
    config_path.write_text("invert_mouse_rotation = true\n", encoding="utf-8")

    assert load_config(config_path) == AppConfig(invert_mouse_rotation=True)


def test_missing_and_invalid_config_use_defaults(tmp_path):
    assert load_config(tmp_path / "missing.toml") == AppConfig()

    config_path = tmp_path / "invalid.toml"
    config_path.write_text("invert_mouse_rotation = \"yes\"\n", encoding="utf-8")
    assert load_config(config_path) == AppConfig()
