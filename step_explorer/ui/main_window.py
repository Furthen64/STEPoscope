from __future__ import annotations

from pathlib import Path

from ..config import AppConfig, load_config
from ..geometry import GeometryBuilder
from ..step.parser import StepDocument
from .entity_details import EntityDetails
from .entity_tree import EntityTree
from ..visualization.vtk_view import VtkView

from PySide6.QtCore import QEvent, QSettings, QTimer, Qt
from PySide6.QtGui import QAction, QActionGroup
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
    QHBoxLayout,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


def _label_for_entity_type(type_name: str) -> str:
    """Return a compact, useful type label for rendered STEP entities."""

    name = type_name.upper()
    if "BREP" in name or "MANIFOLD_SOLID" in name:
        return "BREP"
    if "NURBS" in name or "B_SPLINE" in name:
        return "NURBS"
    if name == "CARTESIAN_POINT":
        return "Point"
    if name == "VERTEX_POINT":
        return "Vertex"
    if name == "ORIENTED_EDGE":
        return "Oriented Edge"
    if name == "EDGE_CURVE" or "EDGE" in name:
        return "Edge"
    if "FACE" in name:
        return "Face"
    if "SHELL" in name:
        return "Shell"
    if "CURVE" in name:
        return "Curve"
    if "SURFACE" in name:
        return "Surface"
    return type_name.replace("_", " ").title()


class MainWindow(QMainWindow):
    def __init__(self, initial_path: str | None = None, config: AppConfig | None = None):
        super().__init__()
        self.setWindowTitle("STEPoscope — STEP walker")
        self.resize(1500, 850)
        self.document: StepDocument | None = None
        self.geometry_builder: GeometryBuilder | None = None
        self.config = config or load_config()
        self.settings = QSettings("STEPoscope", "STEPoscope")
        self.invert_mouse_rotation = self._load_invert_mouse_rotation()
        self.show_entity_labels = self._load_show_entity_labels()
        self.label_mode = self._load_label_mode()
        self.playback_tick_rate = self._load_playback_tick_rate()
        self.playback_order = 0
        self.playback_timer = QTimer(self)
        self.playback_timer.setInterval(self._playback_interval())
        self.playback_timer.timeout.connect(self._playback_tick)
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
        self.viewport = VtkView(
            invert_mouse_rotation=self.invert_mouse_rotation,
            max_entity_labels=self.config.max_entity_labels,
        )
        self.mode = QComboBox(); self.mode.addItems(["File order", "Semantic"])
        self.legend = QLabel()
        self.status = QLabel("Open an ISO-10303-21 STEP file to begin.")
        self.previous_button = QPushButton("Previous")
        self.next_button = QPushButton("Next")
        self.open_button = QPushButton("Open STEP…")
        self.play_button = QPushButton("Play")
        self.play_button.setCheckable(True)
        self.step_backward_button = QPushButton("Step backward")
        self.step_forward_button = QPushButton("Step forward")
        self.playback_progress = QSlider(Qt.Orientation.Horizontal)
        self.playback_progress.setRange(0, 0)
        self.playback_progress.setToolTip("Choose the point in the STEP entity build-up")
        self.playback_tick_rate_spin = QSpinBox()
        self.playback_tick_rate_spin.setRange(1, 60)
        self.playback_tick_rate_spin.setValue(self.playback_tick_rate)
        self.playback_tick_rate_spin.setSuffix(" steps/s")
        self.playback_tick_rate_spin.setToolTip("Number of STEP entities added per second during playback")
        self.playback_frame_label = QLabel("0 / 0")
        self.hotkey_legend = QLabel(
            "Hotkeys: Ctrl+O open · Ctrl+Q quit · Ctrl+Shift+G geometry only · "
            "Space play/pause · L labels · T label content · R reset camera · "
            "MMB orbit · Shift+MMB pan"
        )
        self.hotkey_legend.setToolTip("Keyboard and mouse shortcuts for the STEP viewer")
        self._build_file_menu()
        self._build_ui()
        self._connect_signals()
        if initial_path:
            self.open_path(initial_path)

    def _build_file_menu(self):
        file_menu = self.menuBar().addMenu("File")
        open_action = QAction("Open STEP…", self)
        open_action.setShortcut("Ctrl+O")
        open_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
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
        close_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)
        self._populate_recent_menu()

        view_menu = self.menuBar().addMenu("View")
        self.geometry_only_action = QAction("Show only geometry", self)
        self.geometry_only_action.setCheckable(True)
        self.geometry_only_action.setShortcut("Ctrl+Shift+G")
        self.geometry_only_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.geometry_only_action.setToolTip("Hide organizational, approval, and other non-shape entities")
        self.geometry_only_action.toggled.connect(self._geometry_filter_changed)
        view_menu.addAction(self.geometry_only_action)
        self.invert_mouse_rotation_action = QAction("Invert mouse rotation", self)
        self.invert_mouse_rotation_action.setCheckable(True)
        self.invert_mouse_rotation_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.invert_mouse_rotation_action.setChecked(self.invert_mouse_rotation)
        self.invert_mouse_rotation_action.setToolTip("Reverse the direction of camera rotation while dragging")
        view_menu.addAction(self.invert_mouse_rotation_action)
        self.show_entity_labels_action = QAction("Show entity labels", self)
        self.show_entity_labels_action.setCheckable(True)
        self.show_entity_labels_action.setShortcut("L")
        self.show_entity_labels_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.show_entity_labels_action.setChecked(self.show_entity_labels)
        self.show_entity_labels_action.setToolTip("Show #entity labels for rendered points, edges, and faces")
        view_menu.addAction(self.show_entity_labels_action)
        label_content_menu = view_menu.addMenu("Label content")
        self.label_mode_group = QActionGroup(self)
        self.label_mode_group.setExclusive(True)
        self.line_index_labels_action = QAction("Line index (#ID)", self)
        self.line_index_labels_action.setCheckable(True)
        self.type_labels_action = QAction("Entity type", self)
        self.type_labels_action.setCheckable(True)
        self.label_mode_group.addAction(self.line_index_labels_action)
        self.label_mode_group.addAction(self.type_labels_action)
        label_content_menu.addAction(self.line_index_labels_action)
        label_content_menu.addAction(self.type_labels_action)
        self.line_index_labels_action.setChecked(self.label_mode == "index")
        self.type_labels_action.setChecked(self.label_mode == "type")

    def _load_invert_mouse_rotation(self) -> bool:
        if not self.settings.contains("invert_mouse_rotation"):
            return self.config.invert_mouse_rotation
        return bool(self.settings.value("invert_mouse_rotation", False, type=bool))

    def _load_playback_tick_rate(self) -> int:
        value = self.settings.value("playback_tick_rate", 10, type=int)
        return max(1, min(60, int(value)))

    def _load_show_entity_labels(self) -> bool:
        if not self.settings.contains("show_entity_labels"):
            return self.config.show_entity_labels
        return bool(self.settings.value("show_entity_labels", False, type=bool))

    def _load_label_mode(self) -> str:
        if not self.settings.contains("label_mode"):
            return self.config.label_mode
        value = str(self.settings.value("label_mode", "index"))
        return value if value in {"index", "type"} else "index"

    def _playback_interval(self) -> int:
        return max(1, round(1000 / self.playback_tick_rate))

    def _invert_mouse_rotation_changed(self, enabled: bool):
        self.invert_mouse_rotation = enabled
        self.settings.setValue("invert_mouse_rotation", enabled)
        self.settings.sync()
        self.viewport.set_invert_mouse_rotation(enabled)

    def _show_entity_labels_changed(self, enabled: bool):
        self.show_entity_labels = enabled
        self.settings.setValue("show_entity_labels", enabled)
        self.settings.sync()
        # Rebuild the current snapshot so enabling labels also refreshes the
        # type-name lookup that is intentionally skipped while labels are off.
        self._refresh_viewport()

    def _label_mode_changed(self, mode: str):
        self.label_mode = mode
        self.settings.setValue("label_mode", mode)
        self.settings.sync()
        self._refresh_viewport()

    def _label_texts(self) -> dict[int, str]:
        if not self.document or not self.show_entity_labels:
            return {}
        return {entity.entity_id: _label_for_entity_type(entity.type_name) for entity in self.document.entities}

    def _label_orders(self) -> dict[int, int]:
        if not self.document or not self.show_entity_labels:
            return {}
        return {entity.entity_id: entity.order for entity in self.document.entities}

    def _refresh_viewport(self):
        if not self.document or not self.document.entities:
            return
        builder = self.geometry_builder or GeometryBuilder(self.document)
        snapshot = builder.build(self.discovered_order)
        self.viewport.show_snapshot(
            snapshot,
            selected_id=self.current_id,
            labels=self.show_entity_labels,
            label_mode=self.label_mode,
            label_texts=self._label_texts(),
            label_orders=self._label_orders(),
            label_time=self.discovered_order,
        )

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

        playback_panel = QWidget()
        playback_layout = QVBoxLayout(playback_panel)
        playback_layout.setContentsMargins(8, 6, 8, 6)
        playback_controls = QWidget()
        playback_controls_layout = QHBoxLayout(playback_controls)
        playback_controls_layout.setContentsMargins(0, 0, 0, 0)
        playback_controls_layout.addWidget(self.play_button)
        playback_controls_layout.addWidget(self.step_backward_button)
        playback_controls_layout.addWidget(self.step_forward_button)
        playback_controls_layout.addWidget(self.playback_progress, 1)
        playback_controls_layout.addWidget(QLabel("Tick rate:"))
        playback_controls_layout.addWidget(self.playback_tick_rate_spin)
        playback_controls_layout.addWidget(self.playback_frame_label)
        playback_layout.addWidget(playback_controls)
        playback_layout.addWidget(self.hotkey_legend)

        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(splitter, 1)
        central_layout.addWidget(playback_panel)
        self.setCentralWidget(central_widget)
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
        self.invert_mouse_rotation_action.toggled.connect(self._invert_mouse_rotation_changed)
        self.show_entity_labels_action.toggled.connect(self._show_entity_labels_changed)
        self.line_index_labels_action.triggered.connect(lambda: self._label_mode_changed("index"))
        self.type_labels_action.triggered.connect(lambda: self._label_mode_changed("type"))
        self.play_button.toggled.connect(self._playback_toggled)
        self.step_backward_button.clicked.connect(lambda: self.step_playback(-1))
        self.step_forward_button.clicked.connect(lambda: self.step_playback(1))
        self.playback_progress.valueChanged.connect(self._playback_frame_changed)
        self.playback_tick_rate_spin.valueChanged.connect(self._playback_tick_rate_changed)
        self._update_playback_controls()

        # QVTKRenderWindowInteractor consumes key events for its own camera
        # controls, so bridge the application hotkeys at the Qt widget level.
        self.viewport.installEventFilter(self)
        vtk_widget = getattr(self.viewport, "widget", None)
        if vtk_widget is not None:
            vtk_widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        viewport_widget = getattr(self.viewport, "widget", None)
        if watched in {self.viewport, viewport_widget} and event.type() == QEvent.Type.KeyPress:
            if event.isAutoRepeat() or event.modifiers() & (
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.AltModifier
                | Qt.KeyboardModifier.MetaModifier
            ):
                return super().eventFilter(watched, event)
            if event.key() == Qt.Key.Key_Space:
                self.play_button.setChecked(not self.play_button.isChecked())
                event.accept()
                return True
            if event.key() == Qt.Key.Key_L:
                self.show_entity_labels_action.trigger()
                event.accept()
                return True
            if event.key() == Qt.Key.Key_T:
                action = self.line_index_labels_action if self.label_mode == "type" else self.type_labels_action
                action.trigger()
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def _update_playback_controls(self):
        has_entities = bool(self.document and self.document.entities)
        self.play_button.setEnabled(has_entities)
        self.step_backward_button.setEnabled(has_entities and self.playback_order > 0)
        self.step_forward_button.setEnabled(
            has_entities and self.document is not None and self.playback_order < len(self.document.entities) - 1
        )
        self.playback_progress.setEnabled(has_entities)
        total = len(self.document.entities) if self.document else 0
        self.playback_frame_label.setText(f"{self.playback_order + 1 if has_entities else 0} / {total}")

    def _playback_toggled(self, playing: bool):
        if not playing:
            self.playback_timer.stop()
            self.play_button.setText("Play")
            return
        if not self.document or not self.document.entities:
            self.play_button.setChecked(False)
            return
        if self.playback_order >= len(self.document.entities) - 1:
            self._set_playback_order(0)
        self.playback_timer.start()
        self.play_button.setText("Pause")

    def _playback_tick(self):
        if not self.document or self.playback_order >= len(self.document.entities) - 1:
            self.play_button.setChecked(False)
            return
        self._set_playback_order(self.playback_order + 1)
        if self.playback_order >= len(self.document.entities) - 1:
            self.play_button.setChecked(False)

    def _playback_frame_changed(self, order: int):
        if self.document and self.document.entities and order != self.playback_order:
            self._set_playback_order(order)

    def _set_playback_order(self, order: int):
        if not self.document or not self.document.entities:
            return
        self.playback_order = max(0, min(len(self.document.entities) - 1, order))
        self.playback_progress.blockSignals(True)
        self.playback_progress.setValue(self.playback_order)
        self.playback_progress.blockSignals(False)
        entity = self.document.entities[self.playback_order]
        self.discovered_order = self.playback_order
        builder = self.geometry_builder or GeometryBuilder(self.document)
        self.viewport.show_snapshot(
            builder.build(self.playback_order),
            selected_id=entity.entity_id,
            labels=self.show_entity_labels,
            label_mode=self.label_mode,
            label_texts=self._label_texts(),
            label_orders=self._label_orders(),
            label_time=self.discovered_order,
        )
        self.status.setText(
            f"Playback: #{entity.entity_id} {entity.type_name} · "
            f"{self.playback_order + 1}/{len(self.document.entities)}"
        )
        self._update_playback_controls()

    def step_playback(self, delta: int):
        if not self.document or not self.document.entities:
            return
        self.play_button.setChecked(False)
        self._set_playback_order(self.playback_order + delta)

    def _playback_tick_rate_changed(self, value: int):
        self.playback_tick_rate = value
        self.playback_timer.setInterval(self._playback_interval())
        self.settings.setValue("playback_tick_rate", value)
        self.settings.sync()

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open STEP file", "", "STEP files (*.step *.stp *.STEP *.STP);;All files (*)")
        if path:
            self.open_path(path)

    def open_path(self, path: str):
        self.play_button.setChecked(False)
        try:
            self.document = StepDocument.from_file(path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not parse STEP file", str(exc))
            return
        self._add_recent_file(path)
        self.geometry_builder = GeometryBuilder(self.document)
        self.playback_order = 0
        self.playback_progress.setRange(0, max(0, len(self.document.entities) - 1))
        self.playback_progress.setValue(0)
        self._update_playback_controls()
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
        self.play_button.setChecked(False)
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
        self.playback_order = self.discovered_order
        self.playback_progress.blockSignals(True)
        self.playback_progress.setValue(self.playback_order)
        self.playback_progress.blockSignals(False)
        snapshot = (self.geometry_builder or GeometryBuilder(self.document)).build(self.discovered_order)
        self.viewport.show_snapshot(
            snapshot,
            selected_id=entity_id,
            labels=self.show_entity_labels,
            label_mode=self.label_mode,
            label_texts=self._label_texts(),
            label_orders=self._label_orders(),
            label_time=self.discovered_order,
        )
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
