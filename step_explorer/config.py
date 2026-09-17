"""Application settings loaded from an optional TOML file."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    """Settings that affect the interactive application."""

    invert_mouse_rotation: bool = False
    show_entity_labels: bool = False
    label_mode: str = "index"


def default_config_paths() -> tuple[Path, ...]:
    """Return config locations in precedence order.

    A local file is convenient for a portable checkout, while the XDG path
    gives an installed application a normal per-user config location.
    ``STEPOSCOPE_CONFIG`` is useful when launching the application from a
    desktop shortcut or when testing a configuration in isolation.
    """

    paths: list[Path] = []
    configured_path = os.environ.get("STEPOSCOPE_CONFIG")
    if configured_path:
        paths.append(Path(configured_path).expanduser())
    paths.append(Path.cwd() / "steposcope.toml")

    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")).expanduser()
    paths.append(config_home / "steposcope" / "config.toml")
    return tuple(paths)


def find_config_path() -> Path | None:
    """Find the first existing config file, if any."""

    return next((path for path in default_config_paths() if path.is_file()), None)


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load settings from *path* or the first discovered config file.

    Configuration is optional. A missing, unreadable, malformed, or invalid
    file falls back to the safe defaults so a typo cannot prevent the viewer
    from starting.
    """

    config_path = Path(path).expanduser() if path is not None else find_config_path()
    if config_path is None:
        return AppConfig()

    try:
        with config_path.open("rb") as config_file:
            values = tomllib.load(config_file)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return AppConfig()

    invert_rotation = values.get("invert_mouse_rotation", False)
    show_labels = values.get("show_entity_labels", False)
    label_mode = values.get("label_mode", "index")
    if not isinstance(label_mode, str) or label_mode not in {"index", "type"}:
        label_mode = "index"
    return AppConfig(
        invert_mouse_rotation=invert_rotation if isinstance(invert_rotation, bool) else False,
        show_entity_labels=show_labels if isinstance(show_labels, bool) else False,
        label_mode=label_mode,
    )


__all__ = ["AppConfig", "default_config_paths", "find_config_path", "load_config"]
