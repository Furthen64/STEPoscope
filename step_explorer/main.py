from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    from PySide6.QtWidgets import QApplication

    from .ui.main_window import MainWindow

    args = list(sys.argv[1:] if argv is None else argv)
    app = QApplication([sys.argv[0], *args])
    window = MainWindow(args[0] if args and not args[0].startswith("-") else None)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

