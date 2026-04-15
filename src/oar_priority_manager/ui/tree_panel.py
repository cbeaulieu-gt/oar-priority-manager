"""Left-column tree panel showing Mod → Replacer → Submod hierarchy.

See spec §7.3. Full implementation in Task 14.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QMenu,
    QPushButton,
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
    """Tree panel: Mod → Replacer → Submod hierarchy with status icons.

    A toolbar at the top provides a Name/Priority sort toggle (issue #45).
    """

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
        # False = sort by name (default), True = sort by priority
        self._sort_by_priority: bool = False
        self._setup_ui()
        self._populate()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # -- Sort toolbar (issue #45) --
        # Two checkable QPushButtons styled to match the segmented toggle
        # used in stacks_panel (issue #69 pattern).
        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(4, 4, 4, 2)
        toolbar_layout.setSpacing(0)

        _seg_checked = (
            "QPushButton:checked {"
            "  background: #3a3a5a;"
            "  font-weight: bold;"
            "  border: 1px solid #5a5a8a;"
            "}"
        )
        _seg_unchecked = (
            "QPushButton {"
            "  background: #2a2a2a;"
            "  border: 1px solid #444;"
            "  padding: 3px 10px;"
            "}"
            "QPushButton:hover { background: #333; }"
        )

        self._name_btn = QPushButton("Name")
        self._name_btn.setCheckable(True)
        self._name_btn.setChecked(True)
        self._name_btn.setToolTip("Sort mods alphabetically (default)")
        self._name_btn.setStyleSheet(
            _seg_unchecked + _seg_checked
            + "QPushButton { border-radius: 0px;"
            "  border-top-left-radius: 4px;"
            "  border-bottom-left-radius: 4px;"
            "  border-right: none; }"
        )

        self._priority_btn = QPushButton("Priority")
        self._priority_btn.setCheckable(True)
        self._priority_btn.setChecked(False)
        self._priority_btn.setToolTip(
            "Sort mods by their highest submod priority (descending)"
        )
        self._priority_btn.setStyleSheet(
            _seg_unchecked + _seg_checked
            + "QPushButton { border-radius: 0px;"
            "  border-top-right-radius: 4px;"
            "  border-bottom-right-radius: 4px; }"
        )

        # QButtonGroup enforces mutual exclusivity
        self._sort_group = QButtonGroup(self)
        self._sort_group.setExclusive(True)
        self._sort_group.addButton(self._name_btn)
        self._sort_group.addButton(self._priority_btn)

        self._name_btn.clicked.connect(lambda: self._set_sort(False))
        self._priority_btn.clicked.connect(lambda: self._set_sort(True))

        toolbar_layout.addWidget(self._name_btn)
        toolbar_layout.addWidget(self._priority_btn)
        toolbar_layout.addStretch()

        layout.addWidget(toolbar)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tag_delegate = TagDelegate(self._tree)
        self._tree.setItemDelegate(self._tag_delegate)
        self._tree.currentItemChanged.connect(self._on_selection)
        layout.addWidget(self._tree)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)

    def _set_sort(self, by_priority: bool) -> None:
        """Switch between name sort and priority sort and re-populate.

        Args:
            by_priority: True to sort mod nodes by their highest submod
                priority descending; False for the default alpha sort.
        """
        if self._sort_by_priority == by_priority:
            return
        self._sort_by_priority = by_priority
        self._populate()

    def _sorted_mod_nodes(self) -> list[TreeNode]:
        """Return mod-level children in the current sort order.

        Name mode: alphabetical by display_name (the order from build_tree).
        Priority mode: descending by the maximum submod priority across all
            replacers, so the "most important" mod floats to the top.
        """
        if not self._sort_by_priority:
            return list(self._root.children)

        def _max_priority(mod_node: TreeNode) -> int:
            best = 0
            for rep in mod_node.children:
                for sub in rep.children:
                    if sub.submod is not None and sub.submod.priority > best:
                        best = sub.submod.priority
            return best

        return sorted(self._root.children, key=_max_priority, reverse=True)

    def _populate(self) -> None:
        self._tree.clear()
        self._item_map: dict[int, TreeNode] = {}

        for mod_node in self._sorted_mod_nodes():
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

    def filter_tree(
        self, matching_nodes: set[int] | None, hide_mode: bool = False
    ) -> None:
        """Filter the tree to highlight or hide non-matching nodes.

        Args:
            matching_nodes: Set of ``id()`` values of matching TreeNodes,
                or None to clear any active filter and show all items normally.
            hide_mode: When False (default), non-matching items are dimmed
                (grey foreground). When True, non-matching items are hidden
                entirely and matching items plus their ancestors are shown.
        """
        normal_color = QApplication.palette().windowText().color()
        dim_color = QColor(160, 160, 160)

        if matching_nodes is None:
            # Clear filter — restore all items to the default palette color
            # and make sure nothing is hidden.
            self._unhide_all()
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

        # Walk every QTreeWidgetItem and apply visibility/color.
        def _apply(item: QTreeWidgetItem) -> None:
            node = self._item_map.get(id(item))
            is_visible = node is not None and id(node) in visible

            if hide_mode:
                item.setHidden(not is_visible)
            else:
                # Dim mode: ensure nothing is hidden (may have been set by a
                # prior hide-mode run), then tint non-matching items grey.
                item.setHidden(False)
                if is_visible:
                    item.setForeground(0, normal_color)
                    # Expand parents of matching items for visibility.
                    parent = item.parent()
                    if parent is not None:
                        parent.setExpanded(True)
                else:
                    item.setForeground(0, dim_color)

            for i in range(item.childCount()):
                _apply(item.child(i))

        for i in range(self._tree.topLevelItemCount()):
            _apply(self._tree.topLevelItem(i))

    def _unhide_all(self) -> None:
        """Recursively ensure every item is visible (clears hide-mode state)."""

        def _apply(item: QTreeWidgetItem) -> None:
            item.setHidden(False)
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

    def select_submod(self, submod: SubMod) -> None:
        """Select and scroll to a submod in the tree by identity (issue #60).

        Iterates ``_item_map`` looking for the ``QTreeWidgetItem`` whose
        associated ``TreeNode`` holds a reference to *submod* (identity
        check, not equality).  When found, the item is programmatically
        selected (which fires ``currentItemChanged`` → ``selection_changed``)
        and scrolled into view.  If the submod is not present in the current
        tree (e.g. the tree has been rebuilt since the stacks panel was last
        refreshed), this method is a no-op.

        Args:
            submod: The ``SubMod`` instance to navigate to.
        """
        for item_id, node in self._item_map.items():
            if node.submod is submod:
                # Locate the QTreeWidgetItem by its Python id key.
                # We must walk the tree to find the actual item object because
                # _item_map stores id(item) → node, not item → node.
                item = self._find_item_by_id(item_id)
                if item is not None:
                    self._tree.setCurrentItem(item)
                    self._tree.scrollToItem(
                        item,
                        QTreeWidget.ScrollHint.EnsureVisible,
                    )
                return

    def _find_item_by_id(
        self, target_id: int
    ) -> QTreeWidgetItem | None:
        """Return the ``QTreeWidgetItem`` whose ``id()`` equals *target_id*.

        Walks the full tree hierarchy depth-first.  Returns ``None`` if no
        item with the given id is found.

        Args:
            target_id: The ``id()`` value of the desired item.

        Returns:
            The matching ``QTreeWidgetItem``, or ``None``.
        """
        def _walk(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            if id(item) == target_id:
                return item
            for i in range(item.childCount()):
                result = _walk(item.child(i))
                if result is not None:
                    return result
            return None

        for i in range(self._tree.topLevelItemCount()):
            result = _walk(self._tree.topLevelItem(i))
            if result is not None:
                return result
        return None

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
