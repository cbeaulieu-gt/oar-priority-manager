"""Left-column tree panel showing Mod → Replacer → Submod hierarchy.

See spec §7.3. Full implementation in Task 14.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from oar_priority_manager.app.config import AppConfig
from oar_priority_manager.core.models import SubMod
from oar_priority_manager.core.tag_engine import TagCategory
from oar_priority_manager.ui.tag_delegate import (
    _MAX_MOD_PILLS,
    TAG_DATA_ROLE,
    TAG_OVERRIDE_ROLE,
    TagDelegate,
    sorted_tags,
)
from oar_priority_manager.ui.tag_edit_dialog import TagEditDialog
from oar_priority_manager.ui.tree_model import NodeType, TreeNode, build_tree


class TreePanel(QWidget):
    """Tree panel: Mod → Replacer → Submod hierarchy with status icons."""

    # Emitted when a tree node is selected: the TreeNode itself (or None)
    selection_changed = Signal(object)

    def __init__(
        self,
        submods: list[SubMod],
        app_config: AppConfig | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._submods = submods
        self._app_config = app_config
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
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)

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

    def _on_context_menu(self, pos: QPoint) -> None:
        """Show context menu with 'Edit Tags...' action."""
        item = self._tree.itemAt(pos)
        if item is None:
            return
        node = self._item_map.get(id(item))
        if node is None or node.node_type == NodeType.ROOT:
            return

        menu = QMenu(self)
        edit_tags_action = menu.addAction("Edit Tags...")
        action = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if action == edit_tags_action:
            self._edit_tags(item, node)

    def _edit_tags(self, item: QTreeWidgetItem, node: TreeNode) -> None:
        """Open tag edit dialog for the given node.

        Args:
            item: The QTreeWidgetItem that was right-clicked.
            node: The corresponding TreeNode.
        """
        if self._app_config is None:
            return

        override_key = self._get_override_key(node)
        is_override = override_key in self._app_config.tag_overrides

        if node.node_type == NodeType.SUBMOD and node.submod:
            current_tags = node.submod.tags.copy()
        elif node.node_type == NodeType.MOD:
            current_tags: set = set()
            for rep in node.children:
                for sub in rep.children:
                    if sub.submod and sub.submod.tags:
                        current_tags.update(sub.submod.tags)
        else:
            return  # No tag editing for replacer nodes

        if is_override:
            override_names = self._app_config.tag_overrides[override_key]
            current_tags = {
                tag for tag in TagCategory
                if tag.label.lower() in [n.lower() for n in override_names]
            }

        dialog = TagEditDialog(current_tags, is_override, self)
        if dialog.exec() != TagEditDialog.DialogCode.Accepted:
            return

        if dialog.reset_requested:
            self._app_config.tag_overrides.pop(override_key, None)
            if node.node_type == NodeType.SUBMOD and node.submod:
                from oar_priority_manager.core.tag_engine import compute_tags
                node.submod.tags = compute_tags(node.submod)
                item.setData(0, TAG_DATA_ROLE, node.submod.tags)
                item.setData(0, TAG_OVERRIDE_ROLE, None)
        else:
            selected = dialog.selected_tags()
            override_list = [tag.label.lower() for tag in sorted_tags(selected)]
            self._app_config.tag_overrides[override_key] = override_list

            if node.node_type == NodeType.SUBMOD and node.submod:
                node.submod.tags = selected
            item.setData(0, TAG_DATA_ROLE, selected)
            item.setData(0, TAG_OVERRIDE_ROLE, True)

        if node.node_type == NodeType.SUBMOD and node.parent and node.parent.parent:
            self._refresh_mod_rollup(node.parent.parent)

        self._tree.viewport().update()

    def _get_override_key(self, node: TreeNode) -> str:
        """Build the config key for tag overrides.

        Args:
            node: The tree node to derive a key for.

        Returns:
            A ``/``-separated key string suitable for use in
            ``AppConfig.tag_overrides``.
        """
        if node.node_type == NodeType.SUBMOD and node.submod:
            return f"{node.submod.mo2_mod}/{node.submod.replacer}/{node.submod.name}"
        elif node.node_type == NodeType.MOD:
            return f"mod:{node.display_name}"
        return ""

    def _refresh_mod_rollup(self, mod_node: TreeNode) -> None:
        """Recompute and update tag rollup for a mod-level tree item.

        Args:
            mod_node: The MOD-level TreeNode whose rollup should be refreshed.
        """
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if self._item_map.get(id(item)) is mod_node:
                mod_tags: set[TagCategory] = set()
                for rep in mod_node.children:
                    for sub in rep.children:
                        if sub.submod and sub.submod.tags:
                            mod_tags.update(sub.submod.tags)
                if mod_tags:
                    display = sorted_tags(mod_tags)[:_MAX_MOD_PILLS]
                    item.setData(0, TAG_DATA_ROLE, set(display))
                else:
                    item.setData(0, TAG_DATA_ROLE, None)
                break

    def refresh(self, submods: list[SubMod], app_config: AppConfig | None = None) -> None:
        """Refresh tree from new submod data.

        Args:
            submods: Updated list of SubMod objects to display.
            app_config: Optional updated config; replaces the stored reference
                if provided.
        """
        self._submods = submods
        if app_config is not None:
            self._app_config = app_config
        self._root = build_tree(submods)
        self._populate()
