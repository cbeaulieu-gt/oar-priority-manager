"""Left-column tree panel showing Mod → Replacer → Submod hierarchy.

See spec §7.3. Full implementation in Task 14.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from oar_priority_manager.core.models import SubMod
from oar_priority_manager.ui.tree_model import NodeType, TreeNode, build_tree


class TreePanel(QWidget):
    """Tree panel: Mod → Replacer → Submod hierarchy with status icons."""

    # Emitted when a tree node is selected: (node_type, submod_or_None)
    selection_changed = Signal(object, object)

    def __init__(self, submods: list[SubMod], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._submods = submods
        self._root = build_tree(submods)
        self._setup_ui()
        self._populate()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.currentItemChanged.connect(self._on_selection)
        layout.addWidget(self._tree)

    def _populate(self) -> None:
        self._tree.clear()
        self._item_map: dict[int, TreeNode] = {}

        for mod_node in self._root.children:
            mod_item = QTreeWidgetItem([mod_node.display_name])
            self._item_map[id(mod_item)] = mod_node

            for rep_node in mod_node.children:
                rep_item = QTreeWidgetItem([rep_node.display_name])
                self._item_map[id(rep_item)] = rep_node

                for sub_node in rep_node.children:
                    sm = sub_node.submod
                    icon = "⚠" if (sm and sm.has_warnings) else ("✗" if (sm and sm.disabled) else "✓")
                    sub_item = QTreeWidgetItem([f"{icon} {sub_node.display_name}"])
                    self._item_map[id(sub_item)] = sub_node
                    rep_item.addChild(sub_item)

                mod_item.addChild(rep_item)
                if rep_node.auto_expand:
                    rep_item.setExpanded(True)

            self._tree.addTopLevelItem(mod_item)

    def _on_selection(self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None) -> None:
        if current is None:
            self.selection_changed.emit(None, None)
            return
        node = self._item_map.get(id(current))
        if node:
            self.selection_changed.emit(node.node_type, node.submod)

    def refresh(self, submods: list[SubMod]) -> None:
        """Refresh tree from new submod data."""
        self._submods = submods
        self._root = build_tree(submods)
        self._populate()
