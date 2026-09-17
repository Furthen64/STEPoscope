from step_explorer.config import AppConfig, load_config


def test_mouse_rotation_setting_is_loaded_from_toml(tmp_path):
    config_path = tmp_path / "steposcope.toml"
    config_path.write_text(
        "invert_mouse_rotation = true\nshow_entity_labels = true\nlabel_mode = \"type\"\nmax_entity_labels = 400\n",
        encoding="utf-8",
    )

    assert load_config(config_path) == AppConfig(
        invert_mouse_rotation=True,
        show_entity_labels=True,
        label_mode="type",
        max_entity_labels=400,
    )


def test_label_limit_is_clamped(tmp_path):
    config_path = tmp_path / "labels.toml"
    config_path.write_text("max_entity_labels = 5000\n", encoding="utf-8")

    assert load_config(config_path).max_entity_labels == 2000


def test_missing_and_invalid_config_use_defaults(tmp_path):
    assert load_config(tmp_path / "missing.toml") == AppConfig()

    config_path = tmp_path / "invalid.toml"
    config_path.write_text("invert_mouse_rotation = \"yes\"\n", encoding="utf-8")
    assert load_config(config_path) == AppConfig()
