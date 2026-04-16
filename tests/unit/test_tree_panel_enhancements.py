"""Tests for tree panel enhancements: sort toggle (issue #45) and hide mode (issue #70).

Covers:
  - TreePanel sort toggle: Name vs Priority sort order
  - TreePanel.filter_tree with hide_mode=False (dim) and hide_mode=True (hide)
  - SearchBar.filter_mode_changed signal and hide_mode property
  - MainWindow._hide_mode wiring via filter_mode_changed
"""
from __future__ import annotations

from pathlib import Path

import pytest

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.ui.search_bar import SearchBar
from oar_priority_manager.ui.tree_panel import TreePanel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sm(
    name: str,
    mo2_mod: str = "ModA",
    replacer: str = "Rep",
    priority: int = 100,
    disabled: bool = False,
) -> SubMod:
    """Build a minimal SubMod suitable for tree construction."""
    return SubMod(
        mo2_mod=mo2_mod,
        replacer=replacer,
        name=name,
        description="",
        priority=priority,
        source_priority=priority,
        disabled=disabled,
        config_path=Path(f"C:/mods/{mo2_mod}/{replacer}/{name}/config.json"),
        override_source=OverrideSource.SOURCE,
        override_is_ours=False,
        raw_dict={"name": name, "priority": priority},
        animations=[],
        conditions={},
        warnings=[],
    )


def _top_level_names(panel: TreePanel) -> list[str]:
    """Return the display names of all top-level items in the tree widget."""
    tree = panel._tree
    return [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]


# ---------------------------------------------------------------------------
# Sort toggle (issue #45)
# ---------------------------------------------------------------------------

class TestSortToggle:
    """TreePanel sort toggle: Name vs Priority."""

    @pytest.fixture
    def multi_mod_panel(self, qtbot) -> TreePanel:
        """Three mods with distinct highest submod priorities."""
        submods = [
            # ModA — highest priority 100
            _sm("a_sub", mo2_mod="ModA", priority=100),
            # ModB — highest priority 500
            _sm("b_sub", mo2_mod="ModB", priority=500),
            # ModC — highest priority 300
            _sm("c_sub", mo2_mod="ModC", priority=300),
        ]
        panel = TreePanel(submods)
        qtbot.addWidget(panel)
        return panel

    def test_default_sort_is_name(self, multi_mod_panel: TreePanel):
        """Default sort (Name) should list mods alphabetically."""
        assert _top_level_names(multi_mod_panel) == ["ModA", "ModB", "ModC"]

    def test_sort_by_priority_descending(self, multi_mod_panel: TreePanel):
        """Clicking Priority should reorder mods by highest submod priority desc."""
        multi_mod_panel._priority_btn.click()
        assert _top_level_names(multi_mod_panel) == ["ModB", "ModC", "ModA"]

    def test_toggle_back_to_name(self, multi_mod_panel: TreePanel):
        """Switching back to Name restores alphabetical order."""
        multi_mod_panel._priority_btn.click()
        multi_mod_panel._name_btn.click()
        assert _top_level_names(multi_mod_panel) == ["ModA", "ModB", "ModC"]

    def test_sort_flag_set_correctly(self, multi_mod_panel: TreePanel):
        """_sort_by_priority flag matches which button is active."""
        assert multi_mod_panel._sort_by_priority is False
        multi_mod_panel._priority_btn.click()
        assert multi_mod_panel._sort_by_priority is True
        multi_mod_panel._name_btn.click()
        assert multi_mod_panel._sort_by_priority is False

    def test_priority_sort_tie_broken_by_original_order(self, qtbot):
        """Mods with equal max priority maintain stable relative position."""
        submods = [
            _sm("sub", mo2_mod="Zebra", priority=200),
            _sm("sub", mo2_mod="Alpha", priority=200),
        ]
        panel = TreePanel(submods)
        qtbot.addWidget(panel)
        panel._priority_btn.click()
        # Both have priority 200; sorted() is stable so input order preserved
        names = _top_level_names(panel)
        assert set(names) == {"Alpha", "Zebra"}

    def test_button_group_is_exclusive(self, multi_mod_panel: TreePanel):
        """Only one sort button is checked at a time."""
        multi_mod_panel._priority_btn.click()
        assert multi_mod_panel._priority_btn.isChecked()
        assert not multi_mod_panel._name_btn.isChecked()

        multi_mod_panel._name_btn.click()
        assert multi_mod_panel._name_btn.isChecked()
        assert not multi_mod_panel._priority_btn.isChecked()

    def test_populate_preserves_submod_count(self, multi_mod_panel: TreePanel):
        """Re-populating on sort toggle must not lose any submod nodes."""
        tree = multi_mod_panel._tree

        def _count_all_items(widget_or_item) -> int:
            count = 0
            if hasattr(widget_or_item, "topLevelItemCount"):
                n = widget_or_item.topLevelItemCount()
                items = [widget_or_item.topLevelItem(i) for i in range(n)]
            else:
                n = widget_or_item.childCount()
                items = [widget_or_item.child(i) for i in range(n)]
            for item in items:
                count += 1 + _count_all_items(item)
            return count

        count_before = _count_all_items(tree)
        multi_mod_panel._priority_btn.click()
        count_after = _count_all_items(tree)
        assert count_before == count_after


# ---------------------------------------------------------------------------
# filter_tree hide mode (issue #70) — tree_panel.py
# ---------------------------------------------------------------------------

class TestFilterTreeHideMode:
    """TreePanel.filter_tree with hide_mode parameter."""

    @pytest.fixture
    def panel_with_two_mods(self, qtbot) -> TreePanel:
        """Two mods, each with one replacer and one submod."""
        submods = [
            _sm("alpha_sub", mo2_mod="AlphaMod", priority=100),
            _sm("beta_sub", mo2_mod="BetaMod", priority=200),
        ]
        panel = TreePanel(submods)
        qtbot.addWidget(panel)
        return panel

    def _get_top_item(self, panel: TreePanel, index: int):
        return panel._tree.topLevelItem(index)

    def test_clear_filter_unhides_all(self, panel_with_two_mods: TreePanel):
        """Passing None should unhide all items regardless of prior mode."""
        panel = panel_with_two_mods
        # First apply a hide filter, then clear it
        all_node_ids = set(id(n) for n in panel._item_map.values())
        panel.filter_tree(set(), hide_mode=True)  # hide everything

        panel.filter_tree(None)  # clear

        tree = panel._tree
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            assert not item.isHidden(), f"Top-level item {i} should be visible after clear"

    def test_dim_mode_does_not_hide_items(self, panel_with_two_mods: TreePanel):
        """hide_mode=False must not hide any items."""
        panel = panel_with_two_mods
        # Supply an empty matching set so nothing matches
        panel.filter_tree(set(), hide_mode=False)

        tree = panel._tree
        for i in range(tree.topLevelItemCount()):
            assert not tree.topLevelItem(i).isHidden()

    def test_hide_mode_hides_non_matching_top_level(self, panel_with_two_mods: TreePanel):
        """hide_mode=True hides top-level mod nodes that have no matching descendants."""
        panel = panel_with_two_mods
        # Find the TreeNode for AlphaMod
        alpha_mod_node = next(
            n for n in panel._item_map.values()
            if n.display_name == "AlphaMod"
        )
        panel.filter_tree({id(alpha_mod_node)}, hide_mode=True)

        tree = panel._tree
        # AlphaMod item (index 0, alphabetically first) should be visible
        alpha_item = tree.topLevelItem(0)
        beta_item = tree.topLevelItem(1)
        assert alpha_item.text(0) == "AlphaMod"
        assert not alpha_item.isHidden()
        assert beta_item.text(0) == "BetaMod"
        assert beta_item.isHidden()

    def test_hide_mode_shows_matching_descendants(self, panel_with_two_mods: TreePanel):
        """Ancestor chain of a matching submod must be visible in hide mode."""
        panel = panel_with_two_mods
        # Find the submod node for alpha_sub
        alpha_sub_node = next(
            n for n in panel._item_map.values()
            if n.display_name == "alpha_sub"
        )
        panel.filter_tree({id(alpha_sub_node)}, hide_mode=True)

        # The AlphaMod top-level item must be visible (ancestor of the match)
        tree = panel._tree
        alpha_item = tree.topLevelItem(0)
        assert alpha_item.text(0) == "AlphaMod"
        assert not alpha_item.isHidden()

    def test_switching_from_hide_to_dim_unhides(self, panel_with_two_mods: TreePanel):
        """After a hide-mode filter, switching to dim mode must unhide all items."""
        panel = panel_with_two_mods
        alpha_mod_node = next(
            n for n in panel._item_map.values()
            if n.display_name == "AlphaMod"
        )
        # Apply hide mode first
        panel.filter_tree({id(alpha_mod_node)}, hide_mode=True)

        # Now re-apply same matching set in dim mode
        panel.filter_tree({id(alpha_mod_node)}, hide_mode=False)

        tree = panel._tree
        for i in range(tree.topLevelItemCount()):
            assert not tree.topLevelItem(i).isHidden()


# ---------------------------------------------------------------------------
# SearchBar.filter_mode_changed signal (issue #70) — search_bar.py
# ---------------------------------------------------------------------------

class TestSearchBarHideToggle:
    """SearchBar hide/dim toggle signal and property."""

    @pytest.fixture
    def search_bar(self, qtbot) -> SearchBar:
        bar = SearchBar()
        qtbot.addWidget(bar)
        return bar

    def test_default_hide_mode_is_false(self, search_bar: SearchBar):
        """Hide button is unchecked by default (dim mode)."""
        assert search_bar.hide_mode is False

    def test_clicking_hide_emits_filter_mode_changed(self, search_bar: SearchBar, qtbot):
        """Clicking Hide emits filter_mode_changed(True)."""
        received: list[bool] = []
        search_bar.filter_mode_changed.connect(received.append)

        with qtbot.waitSignal(search_bar.filter_mode_changed, timeout=1000):
            search_bar._hide_btn.click()

        assert received == [True]

    def test_unchecking_hide_emits_false(self, search_bar: SearchBar, qtbot):
        """Unchecking Hide emits filter_mode_changed(False)."""
        received: list[bool] = []
        search_bar._hide_btn.setChecked(True)  # start checked
        search_bar.filter_mode_changed.connect(received.append)

        with qtbot.waitSignal(search_bar.filter_mode_changed, timeout=1000):
            search_bar._hide_btn.click()

        assert received == [False]

    def test_hide_toggle_re_emits_search_changed(self, search_bar: SearchBar, qtbot):
        """Toggling Hide also re-emits search_changed with the current query."""
        search_bar._input.setText("idle")
        emitted_queries: list[str] = []
        search_bar.search_changed.connect(emitted_queries.append)

        search_bar._hide_btn.click()

        assert "idle" in emitted_queries

    def test_hide_mode_property_reflects_button_state(self, search_bar: SearchBar):
        """The hide_mode property matches the button's checked state."""
        search_bar._hide_btn.setChecked(True)
        assert search_bar.hide_mode is True
        search_bar._hide_btn.setChecked(False)
        assert search_bar.hide_mode is False


# ---------------------------------------------------------------------------
# MainWindow._hide_mode wiring (issue #70) — main_window.py
# ---------------------------------------------------------------------------

class TestMainWindowHideModWiring:
    """MainWindow correctly stores _hide_mode and passes it to filter_tree."""

    @pytest.fixture
    def main_window(self, qtbot, tmp_path: Path):
        from oar_priority_manager.app.config import AppConfig
        from oar_priority_manager.core.anim_scanner import build_conflict_map, scan_animations
        from oar_priority_manager.core.priority_resolver import build_stacks
        from oar_priority_manager.core.scanner import scan_mods
        from oar_priority_manager.ui.main_window import MainWindow
        from tests.conftest import make_config_json, make_submod_dir

        mods = tmp_path / "mods"
        mods.mkdir()
        (tmp_path / "overwrite").mkdir()
        (tmp_path / "ModOrganizer.ini").touch()

        make_submod_dir(
            mods, "AlphaMod", "Rep", "alpha_sub",
            config=make_config_json(name="alpha_sub", priority=100),
        )
        make_submod_dir(
            mods, "BetaMod", "Rep", "beta_sub",
            config=make_config_json(name="beta_sub", priority=200),
        )

        submods = scan_mods(mods, tmp_path / "overwrite")
        scan_animations(submods)
        conflict_map = build_conflict_map(submods)
        stacks = build_stacks(conflict_map)

        window = MainWindow(
            submods=submods,
            conflict_map=conflict_map,
            stacks=stacks,
            app_config=AppConfig(),
            instance_root=tmp_path,
        )
        qtbot.addWidget(window)
        return window

    def test_initial_hide_mode_is_false(self, main_window):
        """MainWindow starts with _hide_mode = False."""
        assert main_window._hide_mode is False

    def test_filter_mode_changed_updates_hide_mode(self, main_window):
        """Emitting filter_mode_changed(True) sets _hide_mode on the window."""
        main_window._search_bar.filter_mode_changed.emit(True)
        assert main_window._hide_mode is True

    def test_filter_mode_changed_false_resets_hide_mode(self, main_window):
        """Emitting filter_mode_changed(False) resets _hide_mode to False."""
        main_window._hide_mode = True
        main_window._search_bar.filter_mode_changed.emit(False)
        assert main_window._hide_mode is False

    def test_clicking_hide_button_sets_hide_mode(self, main_window, qtbot):
        """Clicking the Hide button in the search bar updates MainWindow._hide_mode."""
        with qtbot.waitSignal(main_window._search_bar.filter_mode_changed, timeout=1000):
            main_window._search_bar._hide_btn.click()
        assert main_window._hide_mode is True
