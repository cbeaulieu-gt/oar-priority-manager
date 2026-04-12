"""Main application window — three-pane layout with splitters.

See spec §7.1 (layout), §6.3 (data flow).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QSplitter, QVBoxLayout, QWidget

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

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # Top bar: search + advanced + refresh (fixed height, no stretch)
        self._search_bar = SearchBar()
        self._search_bar.setFixedHeight(40)
        main_layout.addWidget(self._search_bar, stretch=0)

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

    def _connect_signals(self) -> None:
        self._tree_panel.selection_changed.connect(self._on_tree_selection)
        self._search_bar.refresh_requested.connect(self._on_refresh)
        self._stacks_panel.action_triggered.connect(self._on_action)

    def _on_tree_selection(self, node_type, submod) -> None:
        self._details_panel.update_selection(node_type, submod)
        self._stacks_panel.update_selection(submod)
        if submod:
            self._conditions_panel.update_focus(submod)

    def _on_action(self, action: str, submod: SubMod, value: object) -> None:
        """Handle priority mutation actions from the stacks panel (spec §6.3 step 5)."""
        from oar_priority_manager.core.override_manager import write_override
        from oar_priority_manager.core.priority_resolver import (
            PriorityOverflowError,
            move_to_top,
            set_exact,
        )

        try:
            if action == "move_to_top":
                new_priorities = move_to_top(submod, self._conflict_map, scope="submod")
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

        except PriorityOverflowError as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Priority Overflow", str(e))

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
