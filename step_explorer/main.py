from __future__ import annotations

import sys


def _render_main(argv: list[str]) -> int:
    import argparse
    import glob
    import json
    from pathlib import Path

    from .headless import process_file

    parser = argparse.ArgumentParser(prog="steposcope render", description="Render STEP files and judge raw shell orientation.")
    parser.add_argument("files", nargs="+", help="STEP files, directories, or glob patterns")
    parser.add_argument("--out", required=True, type=Path, help="output directory")
    parser.add_argument("--width", type=int, default=1200)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--camera", choices=("iso", "front", "top", "right"), default="iso")
    parser.add_argument("--mode", choices=("normals", "shaded"), default="normals", help="normals colors consistent faces blue and inconsistent faces red; shaded uses neutral material")
    args = parser.parse_args(argv)
    paths: list[Path] = []
    for item in args.files:
        expanded = [Path(path) for path in glob.glob(item, recursive=True)] or [Path(item)]
        for path in expanded:
            paths.extend(sorted(candidate for candidate in path.rglob("*") if candidate.suffix.lower() in {".step", ".stp"}) if path.is_dir() else [path])
    paths = list(dict.fromkeys(path.resolve() for path in paths))
    args.out.mkdir(parents=True, exist_ok=True)
    reports, errors = [], []
    used: dict[str, int] = {}
    for path in paths:
        stem = path.stem
        used[stem] = used.get(stem, 0) + 1
        name = stem if used[stem] == 1 else f"{stem}-{used[stem]}"
        try:
            reports.append(process_file(path, args.out / name, args.width, args.height, args.camera, args.mode))
        except Exception as exc:
            errors.append({"source": str(path), "error": str(exc)})
            print(f"steposcope: {path}: {exc}", file=sys.stderr)
    summary = {"reports": reports, "errors": errors}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if errors:
        return 2
    return 1 if any(solid["verdict"] != "consistent" for report in reports for solid in report["solids"]) else 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "render":
        return _render_main(args[1:])
    from PySide6.QtWidgets import QApplication

    from .ui.main_window import MainWindow
    app = QApplication([sys.argv[0], *args])
    window = MainWindow(args[0] if args and not args[0].startswith("-") else None)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
