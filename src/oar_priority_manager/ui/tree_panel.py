"""Left-column tree panel showing Mod → Replacer → Submod hierarchy.

See spec §7.3. Full implementation in Task 14.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from oar_priority_manager.core.models import SubMod
from oar_priority_manager.core.tag_engine import TagCategory
from oar_priority_manager.ui.tag_delegate import (
    TAG_DATA_ROLE,
    TAG_OVERRIDE_ROLE,
    TagDelegate,
    _MAX_MOD_PILLS,
    sorted_tags,
)
from oar_priority_manager.ui.tree_model import TreeNode, build_tree


class TreePanel(QWidget):
    """Tree panel: Mod → Replacer → Submod hierarchy with status icons."""

    # Emitted when a tree node is selected: the TreeNode itself (or None)
    selection_changed = Signal(object)

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
        self._tag_delegate = TagDelegate(self._tree)
        self._tree.setItemDelegate(self._tag_delegate)
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
                    if sm and sm.has_warnings:
                        icon = "⚠"
                    elif sm and sm.disabled:
                        icon = "✗"
                    else:
                        icon = "✓"
                    sub_item = QTreeWidgetItem([f"{icon} {sub_node.display_name}"])
                    self._item_map[id(sub_item)] = sub_node
                    if sm and sm.tags:
                        sub_item.setData(0, TAG_DATA_ROLE, sm.tags)
                    rep_item.addChild(sub_item)

                mod_item.addChild(rep_item)
                if rep_node.auto_expand:
                    rep_item.setExpanded(True)

            # Compute mod-level rollup tags (union of all submod tags)
            mod_tags: set[TagCategory] = set()
            for rep_node in mod_node.children:
                for sub_node in rep_node.children:
                    if sub_node.submod and sub_node.submod.tags:
                        mod_tags.update(sub_node.submod.tags)
            if mod_tags:
                display_tags = sorted_tags(mod_tags)[:_MAX_MOD_PILLS]
                mod_item.setData(0, TAG_DATA_ROLE, set(display_tags))

            self._tree.addTopLevelItem(mod_item)

    def _on_selection(
        self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None
    ) -> None:
        if current is None:
            self.selection_changed.emit(None)
            return
        node = self._item_map.get(id(current))
        if node:
            self.selection_changed.emit(node)

    @property
    def tree_root(self) -> TreeNode:
        """Return the root TreeNode for use by SearchIndex."""
        return self._root

    def filter_tree(self, matching_nodes: set[int] | None) -> None:
        """Filter the tree to highlight matching nodes.

        Args:
            matching_nodes: Set of ``id()`` values of matching TreeNodes,
                or None to clear any active filter and show all items normally.
        """
        normal_color = QApplication.palette().windowText().color()
        dim_color = QColor(160, 160, 160)

        if matching_nodes is None:
            # Clear filter — restore all items to the default palette color.
            self._set_all_colors(normal_color)
            return

        # Build the full "visible" set: matching nodes plus all their ancestors
        # and descendants so the tree context is preserved.
        visible: set[int] = set()

        def _add_ancestors(node: TreeNode) -> None:
            if node.parent is not None:
                visible.add(id(node.parent))
                _add_ancestors(node.parent)

        def _add_descendants(node: TreeNode) -> None:
            for child in node.children:
                visible.add(id(child))
                _add_descendants(child)

        for node in (n for item_id, n in self._item_map.items() if id(n) in matching_nodes):
            visible.add(id(node))
            _add_ancestors(node)
            _add_descendants(node)

        # Walk every QTreeWidgetItem and apply color + expand parents.
        def _apply(item: QTreeWidgetItem) -> None:
            node = self._item_map.get(id(item))
            if node is not None and id(node) in visible:
                item.setForeground(0, normal_color)
                # Ensure parents of matching items are expanded for visibility.
                parent = item.parent()
                if parent is not None:
                    parent.setExpanded(True)
            else:
                item.setForeground(0, dim_color)
            for i in range(item.childCount()):
                _apply(item.child(i))

        for i in range(self._tree.topLevelItemCount()):
            _apply(self._tree.topLevelItem(i))

    def _set_all_colors(self, color: QColor) -> None:
        """Recursively restore every item's foreground to *color*."""

        def _apply(item: QTreeWidgetItem) -> None:
            item.setForeground(0, color)
            for i in range(item.childCount()):
                _apply(item.child(i))

        for i in range(self._tree.topLevelItemCount()):
            _apply(self._tree.topLevelItem(i))

    def refresh(self, submods: list[SubMod]) -> None:
        """Refresh tree from new submod data."""
        self._submods = submods
        self._root = build_tree(submods)
        self._populate()
