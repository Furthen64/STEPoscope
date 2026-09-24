from __future__ import annotations

from .colors import category_for_type, color_for_depth

try:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem
except ImportError:  # pragma: no cover - exercised only without GUI extras
    QTreeWidget = object  # type: ignore[misc,assignment]


class EntityTree(QTreeWidget):
    """Entity tree supporting file, semantic, and playback listings."""

    selected_entity = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Entity", "Type"])
        self.itemClicked.connect(self._clicked)
        self.document = None

    def set_document(self, document, mode: str = "File order", geometry_only: bool = False) -> None:
        self.document = document
        self.clear()
        self.setHeaderLabels(["Line", "STEP source"] if mode == "Playback" else ["Entity", "Type"])
        self.semantic_coloring = mode == "Semantic"
        self.geometry_only = geometry_only
        self.visible_entity_ids: list[int] = []
        self.playback_items: dict[int, QTreeWidgetItem] = {}
        if mode == "Semantic":
            roots = [entity for entity in document.entities if not document.incoming.get(entity.entity_id)]
            if not roots:
                roots = document.entities[:1]
            for entity in roots:
                self._add_semantic(self.invisibleRootItem(), entity.entity_id, set(), 0)
        else:
            for entity in document.entities:
                if mode != "Playback" and not self._is_visible(entity):
                    continue
                if mode == "Playback":
                    source = entity.raw.replace("\r", " ").replace("\n", " ").strip()
                    item = QTreeWidgetItem([str(entity.span.line), source])
                    item.setData(0, Qt.ItemDataRole.UserRole, entity.entity_id)
                    item.setToolTip(1, entity.raw)
                    self.playback_items[entity.entity_id] = item
                else:
                    item = self._item_for(entity)
                self.addTopLevelItem(item)
                self.visible_entity_ids.append(entity.entity_id)
        self.expandToDepth(1)

    def focus_playback_entity(self, entity_id: int) -> None:
        item = self.playback_items.get(entity_id)
        if item is not None:
            self.setCurrentItem(item)
            self.scrollToItem(item)

    def _add_semantic(self, parent, entity_id: int, path: set[int], depth: int) -> None:
        entity = self.document.entity(entity_id)
        if entity is None or entity_id in path:
            return
        next_path = path | {entity_id}
        if not self._is_visible(entity):
            # Keep semantic traversal useful when an organizational entity is
            # between the root and the actual shape topology.
            for child_id in self.document.outgoing.get(entity_id, ()):
                self._add_semantic(parent, child_id, next_path, depth)
            return
        item = self._item_for(entity, depth)
        parent.addChild(item)
        self.visible_entity_ids.append(entity_id)
        for child_id in self.document.outgoing.get(entity_id, ()):
            self._add_semantic(item, child_id, next_path, depth + 1)

    def _is_visible(self, entity) -> bool:
        return not self.geometry_only or category_for_type(entity.type_name) in {"Geometry", "Topology"}

    def _item_for(self, entity, depth: int = 0):
        item = QTreeWidgetItem([f"#{entity.entity_id}", entity.type_name])
        item.setData(0, Qt.ItemDataRole.UserRole, entity.entity_id)
        if self.semantic_coloring:
            category = category_for_type(entity.type_name)
            red, green, blue = color_for_depth(category, depth)
            color = QColor.fromRgbF(red, green, blue)
            item.setForeground(0, color)
            item.setForeground(1, color)
        return item

    def _clicked(self, item, _column) -> None:
        entity_id = item.data(0, Qt.ItemDataRole.UserRole)
        if entity_id is not None:
            self.selected_entity.emit(int(entity_id))
