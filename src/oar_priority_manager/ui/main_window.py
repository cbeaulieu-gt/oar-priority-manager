"""Main application window — three-pane layout with splitters.

See spec §7.1 (layout), §6.3 (data flow).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from oar_priority_manager.app.config import AppConfig
from oar_priority_manager.core.anim_scanner import build_conflict_map, scan_animations
from oar_priority_manager.core.filter_engine import extract_condition_types
from oar_priority_manager.core.models import PriorityStack, SubMod
from oar_priority_manager.core.priority_resolver import build_stacks
from oar_priority_manager.core.scanner import scan_mods
from oar_priority_manager.ui.conditions_panel import ConditionsPanel
from oar_priority_manager.ui.details_panel import DetailsPanel
from oar_priority_manager.ui.search_bar import SearchBar
from oar_priority_manager.ui.stacks_panel import StacksPanel
from oar_priority_manager.ui.tree_model import SearchIndex
from oar_priority_manager.ui.tree_panel import TreePanel


class MainWindow(QMainWindow):
    """Three-pane main window: (Tree+Details) | Stacks | Conditions."""

    def __init__(
        self,
        submods: list[SubMod],
        conflict_map: dict[str, list[SubMod]],
        stacks: list[PriorityStack],
        app_config: AppConfig,
        instance_root: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("OAR Priority Manager")
        self.resize(1400, 800)

        self._submods = submods
        self._conflict_map = conflict_map
        self._stacks = stacks
        self._config = app_config
        self._instance_root = instance_root
        # Tracks whether the search filter should hide non-matches (True)
        # or dim them (False, the default).  Updated via SearchBar.filter_mode_changed.
        self._hide_mode: bool = False

        self._setup_ui()
        self._connect_signals()
        self._apply_config()

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # Top bar: search bar + Clear Overrides button (fixed height, no stretch)
        self._search_bar = SearchBar()
        self._search_bar.setFixedHeight(40)

        self._clear_overrides_btn = QPushButton("Clear Overrides")
        self._clear_overrides_btn.setToolTip(
            "Delete all tool-written overrides for the selected mod"
            " (reverts to source priorities)"
        )
        self._clear_overrides_btn.clicked.connect(self._on_clear_overrides)

        top_bar = QWidget()
        top_bar.setFixedHeight(40)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(self._search_bar, stretch=1)
        top_layout.addWidget(self._clear_overrides_btn)

        main_layout.addWidget(top_bar, stretch=0)

        # Three-pane splitter (takes all remaining space)
        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left column: tree + details (vertical split)
        self._left_splitter = QSplitter(Qt.Orientation.Vertical)
        self._tree_panel = TreePanel(self._submods)
        self._details_panel = DetailsPanel()
        self._left_splitter.addWidget(self._tree_panel)
        self._left_splitter.addWidget(self._details_panel)
        self._left_splitter.setStretchFactor(0, 3)
        self._left_splitter.setStretchFactor(1, 1)

        # Center: priority stacks
        self._stacks_panel = StacksPanel(self._conflict_map)

        # Right: conditions
        self._conditions_panel = ConditionsPanel()

        self._main_splitter.addWidget(self._left_splitter)
        self._main_splitter.addWidget(self._stacks_panel)
        self._main_splitter.addWidget(self._conditions_panel)
        self._main_splitter.setStretchFactor(0, 1)
        self._main_splitter.setStretchFactor(1, 2)
        self._main_splitter.setStretchFactor(2, 1)

        main_layout.addWidget(self._main_splitter, stretch=1)

        # Ctrl+F shortcut to focus search
        shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut.activated.connect(self._search_bar.focus_search)

        # Search bar gets keyboard focus on launch (spec §7.2)
        self._search_bar.focus_search()

    def _connect_signals(self) -> None:
        self._tree_panel.selection_changed.connect(self._on_tree_selection)
        self._search_bar.search_changed.connect(self._on_search)
        self._search_bar.refresh_requested.connect(self._on_refresh)
        self._search_bar.filter_mode_changed.connect(self._on_filter_mode_changed)
        self._stacks_panel.action_triggered.connect(self._on_action)
        self._stacks_panel.competitor_focused.connect(self._on_competitor_focused)

    def _on_tree_selection(self, node) -> None:
        self._details_panel.update_selection(node)
        submod = node.submod if node else None
        if submod:
            self._stacks_panel.update_selection(submod)
            self._conditions_panel.update_focus(submod)

    def _on_competitor_focused(self, submod: SubMod) -> None:
        """Update conditions panel when a competitor row is clicked (spec §7.5)."""
        if submod:
            self._conditions_panel.update_focus(submod)

    def _on_filter_mode_changed(self, hide_mode: bool) -> None:
        """Update the stored hide/dim mode (issued by SearchBar.filter_mode_changed).

        The SearchBar also re-emits search_changed after this signal, so the
        active filter is automatically re-applied with the new mode.

        Args:
            hide_mode: True = hide non-matching items, False = dim them.
        """
        self._hide_mode = hide_mode

    def _on_search(self, query: str) -> None:
        """Filter tree based on search query (spec §7.2)."""
        if not query.strip():
            self._tree_panel.filter_tree(None)
            return

        # Build search index on each search (fast enough for typical mod counts)
        index = SearchIndex(self._tree_panel.tree_root, self._conflict_map)
        results = index.search(query)
        matching = {id(r.node) for r in results}
        self._tree_panel.filter_tree(matching, hide_mode=self._hide_mode)

    def _confirm_action(self, action: str, submod: SubMod, value: object) -> bool:
        """Show a preview dialog for the proposed priority change and return True if confirmed.

        Computes what the new priorities would be WITHOUT applying them, formats a
        human-readable summary with current → new values, and asks the user to
        confirm via QMessageBox.question.

        Args:
            action: One of "move_to_top", "move_to_top_replacer", "move_to_top_mod",
                    "set_exact", or "shift".
            submod: The target submod the action was triggered for.
            value:  Action-specific parameter (int priority for "set_exact",
                    int delta for "shift", None for move_to_top variants).

        Returns:
            True if the user clicked OK/Yes; False if they cancelled.
        """
        from oar_priority_manager.core.priority_resolver import (
            PriorityOverflowError,
            move_to_top,
            set_exact,
        )

        try:
            if action == "move_to_top":
                preview = move_to_top(submod, self._conflict_map, scope="submod")
                if not preview:
                    # Already winning — nothing to confirm; let _on_action handle gracefully.
                    return True
                new_p = preview[submod]
                msg = (
                    f"Move {submod.name} to top\n\n"
                    f"Current priority: {submod.priority}\n"
                    f"New priority:     {new_p}"
                )

            elif action == "move_to_top_replacer":
                preview = move_to_top(submod, self._conflict_map, scope="replacer")
                if not preview:
                    return True
                lines = [f"Move replacer '{submod.replacer}' to top\n"]
                lines.append(f"{'Submod':<30}  {'Current':>10}  {'New':>10}")
                lines.append("-" * 54)
                for sm, new_p in sorted(preview.items(), key=lambda kv: kv[0].name):
                    lines.append(f"{sm.name:<30}  {sm.priority:>10}  {new_p:>10}")
                lines.append(f"\n{len(preview)} submod(s) will be updated.")
                msg = "\n".join(lines)

            elif action == "move_to_top_mod":
                preview = move_to_top(submod, self._conflict_map, scope="mod")
                if not preview:
                    return True
                lines = [f"Move mod '{submod.mo2_mod}' to top\n"]
                lines.append(f"{'Submod':<30}  {'Current':>10}  {'New':>10}")
                lines.append("-" * 54)
                for sm, new_p in sorted(preview.items(), key=lambda kv: kv[0].name):
                    lines.append(f"{sm.name:<30}  {sm.priority:>10}  {new_p:>10}")
                lines.append(f"\n{len(preview)} submod(s) will be updated.")
                msg = "\n".join(lines)

            elif action == "set_exact" and isinstance(value, int):
                # set_exact is a pure function — call it only to validate range.
                set_exact(submod, value)
                msg = (
                    f"Set {submod.name} priority\n\n"
                    f"Current priority: {submod.priority}\n"
                    f"New priority:     {value}"
                )

            elif action == "shift" and isinstance(value, int):
                new_p = submod.priority + value
                direction = f"+{value}" if value >= 0 else str(value)
                msg = (
                    f"Shift {submod.name} priority by {direction}\n\n"
                    f"Current priority: {submod.priority}\n"
                    f"New priority:     {new_p}"
                )

            else:
                # Unknown action — pass through without a dialog.
                return True

        except PriorityOverflowError as e:
            # Surface overflow immediately so _on_action doesn't need to re-catch it.
            QMessageBox.warning(self, "Priority Overflow", str(e))
            return False

        reply = QMessageBox.question(
            self,
            "Confirm Priority Change",
            msg,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        return reply == QMessageBox.StandardButton.Ok

    def _on_action(self, action: str, submod: SubMod, value: object) -> None:
        """Handle priority mutation actions from the stacks panel (spec §6.3 step 5)."""
        from oar_priority_manager.core.override_manager import write_override
        from oar_priority_manager.core.priority_resolver import (
            PriorityOverflowError,
            move_to_top,
            set_exact,
        )

        if not self._confirm_action(action, submod, value):
            return

        try:
            if action == "move_to_top":
                new_priorities = move_to_top(submod, self._conflict_map, scope="submod")
            elif action == "move_to_top_replacer":
                new_priorities = move_to_top(submod, self._conflict_map, scope="replacer")
            elif action == "move_to_top_mod":
                new_priorities = move_to_top(submod, self._conflict_map, scope="mod")
            elif action == "set_exact" and isinstance(value, int):
                new_priorities = set_exact(submod, value)
            else:
                return

            overwrite_dir = self._instance_root / "overwrite"
            for sm, new_p in new_priorities.items():
                write_override(sm, new_p, overwrite_dir)

            # Refresh stacks display (in-memory, no re-scan)
            self._conflict_map = build_conflict_map(self._submods)
            self._stacks = build_stacks(self._conflict_map)
            self._stacks_panel.refresh(self._conflict_map)
            self._stacks_panel.update_selection(submod)
            self._tree_panel.refresh(self._submods)

            # Show toast notification (issue #37, spec §7.4)
            self._stacks_panel.show_toast(
                "Priority updated — you're now #1. Changes take effect the next time"
                " Skyrim loads this animation."
            )

        except PriorityOverflowError as e:
            QMessageBox.warning(self, "Priority Overflow", str(e))

    def _on_clear_overrides(self) -> None:
        """Clear all tool-written overrides for the selected mod (spec §8.2).

        Collects all submods in the current tree selection scope (submod,
        replacer, or mod), filters to those with an Overwrite-layer override,
        confirms with the user, deletes the override files, then refreshes.
        """
        from PySide6.QtWidgets import QMessageBox

        from oar_priority_manager.core.models import OverrideSource
        from oar_priority_manager.core.override_manager import clear_override
        from oar_priority_manager.ui.tree_model import NodeType

        current_item = self._tree_panel._tree.currentItem()
        if current_item is None:
            QMessageBox.information(
                self, "Clear Overrides", "Select a mod, replacer, or submod first."
            )
            return

        node = self._tree_panel._item_map.get(id(current_item))
        if node is None:
            return

        # Collect all submods in scope based on what level is selected
        submods_in_scope: list[SubMod] = []
        if node.node_type == NodeType.SUBMOD and node.submod:
            submods_in_scope = [node.submod]
        elif node.node_type == NodeType.REPLACER:
            submods_in_scope = [sn.submod for sn in node.children if sn.submod]
        elif node.node_type == NodeType.MOD:
            submods_in_scope = [
                sn.submod
                for rep in node.children
                for sn in rep.children
                if sn.submod
            ]

        # Filter to only those with an Overwrite-layer override present
        overridden = [
            sm for sm in submods_in_scope if sm.override_source == OverrideSource.OVERWRITE
        ]

        if not overridden:
            QMessageBox.information(
                self, "Clear Overrides", "No overrides to clear for this selection."
            )
            return

        reply = QMessageBox.question(
            self,
            "Clear Overrides",
            f"Remove {len(overridden)} override(s) for the selected scope? "
            "This will revert to source priorities.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        overwrite_dir = self._instance_root / "overwrite"
        for sm in overridden:
            clear_override(sm, overwrite_dir)

        self._on_refresh()

    def _on_refresh(self) -> None:
        """Re-scan the VFS and rebuild all models (spec §6.3 step 6)."""
        mods_dir = self._instance_root / "mods"
        overwrite_dir = self._instance_root / "overwrite"

        self._submods = scan_mods(mods_dir, overwrite_dir)
        scan_animations(self._submods)
        self._conflict_map = build_conflict_map(self._submods)
        self._stacks = build_stacks(self._conflict_map)

        for sm in self._submods:
            present, negated = extract_condition_types(sm.conditions)
            sm.condition_types_present = present
            sm.condition_types_negated = negated

        self._tree_panel.refresh(self._submods)
        self._stacks_panel.refresh(self._conflict_map)

    def _apply_config(self) -> None:
        """Apply persisted config values to UI widgets (spec §8.3)."""
        cfg = self._config

        # Relative/Absolute toggle
        if cfg.relative_or_absolute == "absolute":
            self._stacks_panel.set_relative_mode(False)

        # Window geometry
        if cfg.window_geometry:
            from PySide6.QtCore import QByteArray
            geo = QByteArray.fromBase64(cfg.window_geometry.encode())
            self.restoreGeometry(geo)

        # Splitter positions: [main0, main1, main2, left0, left1]
        if cfg.splitter_positions and len(cfg.splitter_positions) >= 3:
            main_sizes = cfg.splitter_positions[:3]
            self._main_splitter.setSizes(main_sizes)
        if cfg.splitter_positions and len(cfg.splitter_positions) >= 5:
            left_sizes = cfg.splitter_positions[3:5]
            self._left_splitter.setSizes(left_sizes)

    def capture_config(self) -> None:
        """Capture current UI state into the AppConfig (spec §8.3).

        Called before shutdown to persist user preferences.
        """
        cfg = self._config

        # Relative/Absolute mode
        cfg.relative_or_absolute = (
            "relative" if self._stacks_panel._relative_mode else "absolute"
        )

        # Window geometry (base64 encoded QByteArray)
        cfg.window_geometry = self.saveGeometry().toBase64().data().decode()

        # Splitter positions: [main0, main1, main2, left0, left1]
        cfg.splitter_positions = list(self._main_splitter.sizes()) + list(
            self._left_splitter.sizes()
        )
