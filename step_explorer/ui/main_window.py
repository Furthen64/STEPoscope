from __future__ import annotations

from pathlib import Path

from ..geometry import GeometryBuilder
from ..step.parser import StepDocument
from .entity_details import EntityDetails
from .entity_tree import EntityTree
from ..visualization.vtk_view import VtkView

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QComboBox,
    QTabWidget,
    QToolBar,
)


class MainWindow(QMainWindow):
    def __init__(self, initial_path: str | None = None):
        super().__init__()
        self.setWindowTitle("STEPoscope — STEP walker")
        self.resize(1500, 850)
        self.document: StepDocument | None = None
        self.settings = QSettings("STEPoscope", "STEPoscope")
        self.recent_files: list[str] = self._load_recent_files()
        self.current_id: int | None = None
        self.semantic_history: list[int] = []
        self.semantic_cursor = -1
        self.discovered_order = -1
        self.tree = EntityTree()
        self.details = EntityDetails()
        self.raw_source = EntityDetails()
        self.details_tabs = QTabWidget()
        self.details_tabs.addTab(self.details, "Interpretation")
        self.details_tabs.addTab(self.raw_source, "Raw STEP")
        self.viewport = VtkView()
        self.mode = QComboBox(); self.mode.addItems(["File order", "Semantic"])
        self.legend = QLabel()
        self.status = QLabel("Open an ISO-10303-21 STEP file to begin.")
        self.previous_button = QPushButton("Previous")
        self.next_button = QPushButton("Next")
        self.open_button = QPushButton("Open STEP…")
        self._build_file_menu()
        self._build_ui()
        self._connect_signals()
        if initial_path:
            self.open_path(initial_path)

    def _build_file_menu(self):
        file_menu = self.menuBar().addMenu("File")
        open_action = QAction("Open STEP…", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_dialog)
        file_menu.addAction(open_action)
        self.recent_menu = file_menu.addMenu("Recent files")
        self.recent_menu.aboutToShow.connect(self._populate_recent_menu)
        file_menu.addSeparator()
        clear_action = QAction("Clear recent files", self)
        clear_action.triggered.connect(self._clear_recent_files)
        file_menu.addAction(clear_action)
        file_menu.addSeparator()
        close_action = QAction("Quit", self)
        close_action.setShortcut("Ctrl+Q")
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)
        self._populate_recent_menu()

        view_menu = self.menuBar().addMenu("View")
        self.geometry_only_action = QAction("Show only geometry", self)
        self.geometry_only_action.setCheckable(True)
        self.geometry_only_action.setShortcut("Ctrl+Shift+G")
        self.geometry_only_action.setToolTip("Hide organizational, approval, and other non-shape entities")
        self.geometry_only_action.toggled.connect(self._geometry_filter_changed)
        view_menu.addAction(self.geometry_only_action)

    def _load_recent_files(self) -> list[str]:
        stored = self.settings.value("recent_files", [])
        if isinstance(stored, str):
            stored = [stored]
        return [str(path) for path in (stored or [])][:5]

    def _save_recent_files(self):
        self.settings.setValue("recent_files", self.recent_files[:5])

    def _add_recent_file(self, path: str):
        normalized = str(Path(path).expanduser().resolve())
        self.recent_files = [normalized, *(item for item in self.recent_files if item != normalized)][:5]
        self._save_recent_files()
        self._populate_recent_menu()

    def _populate_recent_menu(self):
        self.recent_menu.clear()
        if not self.recent_files:
            empty_action = self.recent_menu.addAction("No recent files")
            empty_action.setEnabled(False)
            return
        for path in self.recent_files:
            action = self.recent_menu.addAction(path)
            action.setToolTip(path)
            action.triggered.connect(lambda _checked=False, recent_path=path: self.open_path(recent_path))

    def _clear_recent_files(self):
        self.recent_files.clear()
        self._save_recent_files()
        self._populate_recent_menu()

    def _build_ui(self):
        toolbar = QToolBar("Navigation", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        toolbar.addWidget(self.open_button)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" Mode: "))
        toolbar.addWidget(self.mode)
        toolbar.addWidget(self.previous_button)
        toolbar.addWidget(self.next_button)
        toolbar.addSeparator()
        toolbar.addWidget(self.legend)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.details_tabs)
        splitter.addWidget(self.viewport)
        splitter.setSizes([300, 420, 780])
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(2, 3)
        self.setCentralWidget(splitter)
        self.statusBar().addWidget(self.status, 1)
        self.setStyleSheet(
            "QToolBar { spacing: 6px; padding: 4px; }"
            "QTreeWidget { alternate-background-color: #20242a; }"
            "QTabWidget::pane { border: 1px solid #343a40; }"
        )

    def _connect_signals(self):
        self.open_button.clicked.connect(self.open_dialog)
        self.previous_button.clicked.connect(lambda: self.navigate(-1))
        self.next_button.clicked.connect(lambda: self.navigate(1))
        self.mode.currentTextChanged.connect(self._mode_changed)
        self.tree.selected_entity.connect(self.select_entity)

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open STEP file", "", "STEP files (*.step *.stp *.STEP *.STP);;All files (*)")
        if path:
            self.open_path(path)

    def open_path(self, path: str):
        try:
            self.document = StepDocument.from_file(path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not parse STEP file", str(exc))
            return
        self._add_recent_file(path)
        self.setWindowTitle(f"STEPoscope — {Path(path).name}")
        self.status.setText(f"{len(self.document.entities)} entities")
        self.semantic_history = []
        self.semantic_cursor = -1
        self.discovered_order = -1
        self._refresh_tree()
        if self.document.entities:
            self.select_entity(self.document.entities[0].entity_id)

    def _refresh_tree(self):
        if self.document:
            self.tree.set_document(
                self.document,
                self.mode.currentText(),
                geometry_only=self.geometry_only_action.isChecked(),
            )
            if self.current_id not in self.tree.visible_entity_ids and self.tree.visible_entity_ids:
                self.select_entity(self.tree.visible_entity_ids[0])

    def _geometry_filter_changed(self, _enabled: bool):
        self._refresh_tree()

    def _mode_changed(self, mode: str):
        self.legend.setText(
            "<span style='color:#4fc3f7'>Geometry</span>  "
            "<span style='color:#ffb74d'>Topology</span>  "
            "<span style='color:#ce93d8'>Structure</span>  "
            "<span style='color:#90a4ae'>Metadata</span>"
            if mode == "Semantic" else ""
        )
        self._refresh_tree()

    def select_entity(self, entity_id: int, record_semantic_history: bool = True):
        if not self.document or entity_id not in self.document.by_id:
            return
        self.current_id = entity_id
        entity = self.document.entity(entity_id)
        if record_semantic_history and self.mode.currentText() == "Semantic":
            if self.semantic_cursor + 1 < len(self.semantic_history):
                self.semantic_history = self.semantic_history[: self.semantic_cursor + 1]
            if not self.semantic_history or self.semantic_history[-1] != entity_id:
                self.semantic_history.append(entity_id)
            self.semantic_cursor = len(self.semantic_history) - 1
        self.discovered_order = max(self.discovered_order, entity.order)
        self.details.show_entity(entity, self.document)
        self.raw_source.setPlainText(entity.raw)
        snapshot = GeometryBuilder(self.document).build(self.discovered_order)
        self.viewport.show_snapshot(snapshot, selected_id=entity_id)
        self.status.setText(f"#{entity_id} {entity.type_name} · {entity.order + 1}/{len(self.document.entities)}")

    def navigate(self, delta: int):
        if not self.document or not self.document.entities:
            return
        if self.mode.currentText() == "Semantic" and self.current_id in self.document.by_id:
            if delta < 0 and self.semantic_cursor > 0:
                self.semantic_cursor -= 1
                self.select_entity(self.semantic_history[self.semantic_cursor], record_semantic_history=False)
                return
            if delta > 0:
                next_id = next((item for item in self.document.outgoing.get(self.current_id, ()) if item in self.document.by_id), None)
                if next_id is not None:
                    self.select_entity(next_id)
                return
        current_order = self.document.entity(self.current_id).order if self.current_id in self.document.by_id else 0
        order = max(0, min(len(self.document.entities) - 1, current_order + delta))
        self.select_entity(self.document.entities[order].entity_id)
