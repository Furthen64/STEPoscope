from __future__ import annotations

import sys


def _render_main(argv: list[str]) -> int:
    import argparse
    import glob
    import json
    import time
    from pathlib import Path

    from .headless import CAMERA_DIRECTIONS, process_file
    from .progress import Progress

    def views(value: str) -> tuple[str, ...]:
        requested = tuple(dict.fromkeys(part.strip() for part in value.split(",") if part.strip()))
        invalid = [view for view in requested if view not in CAMERA_DIRECTIONS]
        if not requested or invalid:
            choices = ", ".join(CAMERA_DIRECTIONS)
            detail = f"unknown view(s): {', '.join(invalid)}; " if invalid else ""
            raise argparse.ArgumentTypeError(f"{detail}choose a comma-separated list from: {choices}")
        return requested

    parser = argparse.ArgumentParser(prog="steposcope render", description="Render STEP files and judge raw shell orientation.")
    parser.add_argument("files", nargs="+", help="STEP files, directories, or glob patterns")
    parser.add_argument("--out", required=True, type=Path, help="output directory")
    parser.add_argument("--width", type=int, default=1200)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--camera", choices=("iso", "front", "top", "right"), default="iso")
    parser.add_argument("--views", type=views, help="comma-separated views to render (iso,front,top,right); overrides --camera")
    parser.add_argument("--mode", choices=("normals", "shaded", "faces"), default="normals", help="normals colors consistent faces blue and inconsistent faces red; shaded uses neutral material; faces colors and labels each face by STEP id")
    parser.add_argument("--quiet", action="store_true", help="suppress progress reporting on stderr")
    parser.add_argument("--max-labels", type=int, default=0, metavar="N",
                        help="cap faces-mode labels to the N largest faces (0 = no cap). "
                             "Text actors dominate the render on dense files: ~35s/view for "
                             "3500 labels versus ~5s for 400.")
    parser.add_argument("--fit-box", metavar="X0,Y0,Z0,X1,Y1,Z1", default=None,
                        help="frame the camera on these world bounds instead of each file's own. "
                             "Pass the SAME box for every file in a comparison: the default "
                             "per-file auto-fit rescales every render to fill the frame, so a "
                             "uniform size difference between two files is invisible.")
    args = parser.parse_args(argv)
    fit_box = None
    if args.fit_box:
        try:
            values = tuple(float(v) for v in args.fit_box.split(","))
        except ValueError:
            parser.error(f"--fit-box must be 6 comma-separated numbers, got {args.fit_box!r}")
        if len(values) != 6 or not all(values[i] < values[i + 3] for i in range(3)):
            parser.error(f"--fit-box needs X0<X1, Y0<Y1, Z0<Z1; got {args.fit_box!r}")
        fit_box = values
    paths: list[Path] = []
    for item in args.files:
        expanded = [Path(path) for path in glob.glob(item, recursive=True)] or [Path(item)]
        for path in expanded:
            paths.extend(sorted(candidate for candidate in path.rglob("*") if candidate.suffix.lower() in {".step", ".stp"}) if path.is_dir() else [path])
    paths = list(dict.fromkeys(path.resolve() for path in paths))
    args.out.mkdir(parents=True, exist_ok=True)
    reports, errors = [], []
    used: dict[str, int] = {}
    progress = Progress(enabled=not args.quiet)
    total = len(paths)
    wall = time.time()
    progress.stage(f"{total} file(s), mode={args.mode}")
    for index, path in enumerate(paths, start=1):
        stem = path.stem
        used[stem] = used.get(stem, 0) + 1
        name = stem if used[stem] == 1 else f"{stem}-{used[stem]}"
        progress.end_item()
        progress.stage(f"[{index}/{total}] {path.name}")
        try:
            reports.append(process_file(path, args.out / name, args.width, args.height, args.camera, args.mode, args.views, progress=progress, max_labels=args.max_labels, fit_box=fit_box))
        except Exception as exc:
            errors.append({"source": str(path), "error": str(exc)})
            print(f"steposcope: {path}: {exc}", file=sys.stderr)
    progress.note(f"total {time.time() - wall:.2f}s for {len(reports)} file(s), {len(errors)} error(s)")
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
