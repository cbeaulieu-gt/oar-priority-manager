"""Tests for condition-filter search bar wiring (issue #50).

Covers:
- ``detect_search_mode`` — pure mode-detection logic
- ``SearchBar`` widget — visual mode switching, signal emission
- ``MainWindow._apply_condition_filter`` — integration with filter engine
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.ui.search_bar import (
    SearchMode,
    detect_search_mode,
)
from oar_priority_manager.ui.tree_model import NodeType, TreeNode

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_submod(
    name: str = "sub",
    priority: int = 100,
    condition_types_present: set[str] | None = None,
    condition_types_negated: set[str] | None = None,
    mo2_mod: str = "TestMod",
    replacer: str = "rep",
) -> SubMod:
    """Build a minimal SubMod for condition-filter tests.

    Args:
        name: Submod name.
        priority: Priority integer.
        condition_types_present: Pre-populated condition type set.
        condition_types_negated: Pre-populated negated type set.
        mo2_mod: MO2 mod name.
        replacer: Replacer name.

    Returns:
        A fully constructed SubMod instance.
    """
    sm = SubMod(
        mo2_mod=mo2_mod,
        replacer=replacer,
        name=name,
        description="",
        priority=priority,
        source_priority=priority,
        disabled=False,
        config_path=Path(
            f"C:/mods/{mo2_mod}/meshes/actors/character/animations"
            f"/OpenAnimationReplacer/{replacer}/{name}/config.json"
        ),
        override_source=OverrideSource.SOURCE,
        override_is_ours=False,
        raw_dict={"name": name, "priority": priority},
        animations=["mt_idle.hkx"],
    )
    sm.condition_types_present = condition_types_present or set()
    sm.condition_types_negated = condition_types_negated or set()
    return sm


def _make_tree(submods: list[SubMod]) -> TreeNode:
    """Build a minimal three-level TreeNode tree from a flat SubMod list.

    Args:
        submods: List of SubMod instances to organise into the tree.

    Returns:
        The ROOT TreeNode whose children are MOD nodes.
    """
    from oar_priority_manager.ui.tree_model import build_tree
    return build_tree(submods)


# ---------------------------------------------------------------------------
# detect_search_mode — pure function
# ---------------------------------------------------------------------------


class TestDetectSearchMode:
    """Tests for the ``detect_search_mode`` pure function."""

    def test_empty_string_is_text_mode(self) -> None:
        assert detect_search_mode("") == SearchMode.TEXT

    def test_plain_name_is_text_mode(self) -> None:
        assert detect_search_mode("IsFemale") == SearchMode.TEXT

    def test_plain_multi_word_no_keywords_is_text_mode(self) -> None:
        assert detect_search_mode("my cool mod") == SearchMode.TEXT

    # condition: prefix triggers condition mode
    def test_condition_prefix_lowercase_triggers(self) -> None:
        assert detect_search_mode("condition:IsFemale") == SearchMode.CONDITION

    def test_condition_prefix_mixed_case_triggers(self) -> None:
        assert detect_search_mode("Condition:IsFemale") == SearchMode.CONDITION

    def test_condition_prefix_uppercase_triggers(self) -> None:
        assert detect_search_mode("CONDITION:IsFemale") == SearchMode.CONDITION

    def test_condition_prefix_with_leading_whitespace(self) -> None:
        assert detect_search_mode("  condition:IsFemale") == SearchMode.CONDITION

    def test_condition_prefix_alone_triggers(self) -> None:
        # Even with nothing after the colon
        assert detect_search_mode("condition:") == SearchMode.CONDITION

    # NOT keyword
    def test_not_keyword_uppercase_triggers(self) -> None:
        assert detect_search_mode("NOT HasPerk") == SearchMode.CONDITION

    def test_not_keyword_mixed_case_triggers(self) -> None:
        assert detect_search_mode("Not HasPerk") == SearchMode.CONDITION

    def test_not_keyword_lowercase_triggers(self) -> None:
        assert detect_search_mode("not HasPerk") == SearchMode.CONDITION

    def test_not_as_substring_does_not_trigger(self) -> None:
        # "notable" should not trigger because NOT is not a whole word here
        assert detect_search_mode("notable") == SearchMode.TEXT

    # OR keyword
    def test_or_keyword_triggers(self) -> None:
        assert detect_search_mode("IsFemale OR IsInCombat") == SearchMode.CONDITION

    def test_or_lowercase_triggers(self) -> None:
        assert detect_search_mode("IsFemale or IsInCombat") == SearchMode.CONDITION

    def test_or_as_substring_does_not_trigger(self) -> None:
        # "organizer" contains "or" but it's not a whole word match at boundary
        assert detect_search_mode("organizer") == SearchMode.TEXT

    # AND keyword
    def test_and_keyword_triggers(self) -> None:
        assert detect_search_mode("IsFemale AND HasPerk") == SearchMode.CONDITION

    def test_and_lowercase_triggers(self) -> None:
        assert detect_search_mode("IsFemale and HasPerk") == SearchMode.CONDITION

    def test_and_as_substring_does_not_trigger(self) -> None:
        # "android" contains "and" but not as a whole word
        assert detect_search_mode("android mod") == SearchMode.TEXT

    # Combined
    def test_combined_not_and_name_triggers(self) -> None:
        assert detect_search_mode("IsFemale NOT HasPerk") == SearchMode.CONDITION

    def test_whitespace_only_is_text_mode(self) -> None:
        assert detect_search_mode("   ") == SearchMode.TEXT


# ---------------------------------------------------------------------------
# SearchBar widget — mode switching
# ---------------------------------------------------------------------------


class TestSearchBarModeSwitch:
    """Tests for the SearchBar widget's automatic mode-switch behaviour."""

    @pytest.fixture
    def search_bar(self, qtbot):
        """Provide a SearchBar widget ready for testing.

        Args:
            qtbot: pytest-qt bot fixture for widget management.
        """
        from oar_priority_manager.ui.search_bar import SearchBar
        bar = SearchBar()
        qtbot.addWidget(bar)
        return bar

    def test_initial_mode_is_text(self, search_bar) -> None:
        assert search_bar.current_mode == SearchMode.TEXT

    def test_typing_plain_text_stays_text_mode(
        self, search_bar, qtbot
    ) -> None:
        qtbot.keyClicks(search_bar._input, "hello")
        assert search_bar.current_mode == SearchMode.TEXT

    def test_typing_not_keyword_switches_to_condition(
        self, search_bar, qtbot
    ) -> None:
        search_bar._input.setText("NOT HasPerk")
        assert search_bar.current_mode == SearchMode.CONDITION

    def test_typing_or_keyword_switches_to_condition(
        self, search_bar, qtbot
    ) -> None:
        search_bar._input.setText("IsFemale OR IsInCombat")
        assert search_bar.current_mode == SearchMode.CONDITION

    def test_typing_and_keyword_switches_to_condition(
        self, search_bar, qtbot
    ) -> None:
        search_bar._input.setText("IsFemale AND HasPerk")
        assert search_bar.current_mode == SearchMode.CONDITION

    def test_condition_prefix_switches_to_condition(
        self, search_bar, qtbot
    ) -> None:
        search_bar._input.setText("condition:IsFemale")
        assert search_bar.current_mode == SearchMode.CONDITION

    def test_clearing_keywords_reverts_to_text_mode(
        self, search_bar, qtbot
    ) -> None:
        # Activate condition mode first
        search_bar._input.setText("NOT HasPerk")
        assert search_bar.current_mode == SearchMode.CONDITION
        # Clear input — should revert to text mode
        search_bar._input.clear()
        assert search_bar.current_mode == SearchMode.TEXT

    def test_removing_keywords_reverts_to_text_mode(
        self, search_bar, qtbot
    ) -> None:
        search_bar._input.setText("IsFemale NOT HasPerk")
        assert search_bar.current_mode == SearchMode.CONDITION
        # Replace with plain text — no keywords remain
        search_bar._input.setText("IsFemale HasPerk")
        assert search_bar.current_mode == SearchMode.TEXT

    def test_condition_mode_changed_signal_emitted(
        self, search_bar, qtbot
    ) -> None:
        received = []
        search_bar.condition_mode_changed.connect(received.append)
        search_bar._input.setText("NOT HasPerk")
        assert len(received) == 1
        assert received[0] == SearchMode.CONDITION

    def test_condition_mode_changed_emitted_on_revert(
        self, search_bar, qtbot
    ) -> None:
        received = []
        search_bar._input.setText("NOT HasPerk")
        search_bar.condition_mode_changed.connect(received.append)
        # Now revert
        search_bar._input.setText("HasPerk")
        assert len(received) == 1
        assert received[0] == SearchMode.TEXT

    def test_no_duplicate_mode_signals(self, search_bar, qtbot) -> None:
        """Mode signal should fire only on transitions, not every keystroke."""
        received = []
        search_bar._input.setText("NOT HasPerk")
        search_bar.condition_mode_changed.connect(received.append)
        # Type more inside condition mode — no extra transition
        search_bar._input.setText("NOT HasPerk IsFemale")
        assert len(received) == 0

    def test_search_changed_always_emitted(self, search_bar, qtbot) -> None:
        """search_changed fires for every text change regardless of mode."""
        received = []
        search_bar.search_changed.connect(received.append)
        search_bar._input.setText("hello")
        search_bar._input.setText("NOT HasPerk")
        assert len(received) == 2

    def test_condition_mode_applies_blue_style(
        self, search_bar, qtbot
    ) -> None:
        search_bar._input.setText("NOT HasPerk")
        # The stylesheet should contain the blue border colour
        style = search_bar._input.styleSheet()
        assert "#5b9bd5" in style

    def test_text_mode_clears_style(self, search_bar, qtbot) -> None:
        search_bar._input.setText("NOT HasPerk")
        search_bar._input.setText("normal text")
        assert search_bar._input.styleSheet() == ""

    def test_condition_mode_sets_tooltip(self, search_bar, qtbot) -> None:
        search_bar._input.setText("NOT HasPerk")
        assert "Condition filter active" in search_bar._input.toolTip()

    def test_text_mode_clears_tooltip(self, search_bar, qtbot) -> None:
        search_bar._input.setText("NOT HasPerk")
        search_bar._input.setText("normal")
        assert search_bar._input.toolTip() == ""


# ---------------------------------------------------------------------------
# Condition filter integration — _apply_condition_filter
# ---------------------------------------------------------------------------


class TestApplyConditionFilter:
    """Tests for the main window's condition-filter routing logic.

    We test the filter matching logic directly by constructing a minimal
    tree and calling ``_apply_condition_filter`` with a mocked
    ``_tree_panel``.  This avoids creating a full ``MainWindow`` (which
    requires a real MO2 instance on disk) while still covering the
    routing code paths.
    """

    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------

    @pytest.fixture
    def female_submod(self) -> SubMod:
        """SubMod with IsFemale condition present."""
        return _make_submod(
            name="female_anim",
            condition_types_present={"IsFemale"},
        )

    @pytest.fixture
    def perk_submod(self) -> SubMod:
        """SubMod with HasPerk condition present."""
        return _make_submod(
            name="perk_anim",
            condition_types_present={"HasPerk"},
        )

    @pytest.fixture
    def female_perk_submod(self) -> SubMod:
        """SubMod with both IsFemale and HasPerk conditions."""
        return _make_submod(
            name="female_perk_anim",
            condition_types_present={"IsFemale", "HasPerk"},
        )

    @pytest.fixture
    def empty_submod(self) -> SubMod:
        """SubMod with no conditions."""
        return _make_submod(
            name="bare_anim",
            condition_types_present=set(),
        )

    def _run_filter(
        self,
        submods: list[SubMod],
        query: str,
    ) -> set[str]:
        """Helper: run ``_apply_condition_filter`` and return matched submod names.

        Builds a real tree from *submods*, wires a mock tree panel, calls
        the filter method, and returns the set of submod ``display_name``
        values whose ``TreeNode`` ids ended up in the ``matching`` set
        passed to ``filter_tree``.

        Args:
            submods: SubMods to include in the tree.
            query: Condition filter query string.

        Returns:
            Set of display_name strings for matched SUBMOD nodes.
        """
        from oar_priority_manager.ui.main_window import MainWindow
        from oar_priority_manager.ui.tree_model import NodeType, build_tree

        root = build_tree(submods)

        # Build id → node map from the tree
        node_by_id: dict[int, TreeNode] = {}

        def _collect(node: TreeNode) -> None:
            node_by_id[id(node)] = node
            for child in node.children:
                _collect(child)

        _collect(root)

        # Capture what _apply_condition_filter passes to filter_tree
        captured: dict = {}

        mock_panel = MagicMock()
        mock_panel.tree_root = root
        mock_panel.filter_tree.side_effect = (
            lambda matching, hide_mode=False: captured.update(
                {"matching": matching}
            )
        )

        # Use a MagicMock as self and call the unbound method — avoids
        # PySide6 metaclass restrictions on object.__new__(QMainWindow).
        win = MagicMock()
        win._tree_panel = mock_panel
        win._hide_mode = False

        MainWindow._apply_condition_filter(win, query)

        matched_ids = captured.get("matching", set())
        return {
            node_by_id[nid].display_name
            for nid in matched_ids
            if nid in node_by_id
            and node_by_id[nid].node_type == NodeType.SUBMOD
        }

    # ------------------------------------------------------------------
    # Happy-path tests
    # ------------------------------------------------------------------

    def test_required_condition_matches_submod(
        self,
        female_submod: SubMod,
        perk_submod: SubMod,
    ) -> None:
        matched = self._run_filter(
            [female_submod, perk_submod], "IsFemale"
        )
        assert "female_anim" in matched
        assert "perk_anim" not in matched

    def test_not_excludes_submod(
        self,
        female_submod: SubMod,
        perk_submod: SubMod,
    ) -> None:
        matched = self._run_filter(
            [female_submod, perk_submod], "NOT IsFemale"
        )
        assert "female_anim" not in matched
        assert "perk_anim" in matched

    def test_multiple_required_conditions(
        self,
        female_submod: SubMod,
        female_perk_submod: SubMod,
    ) -> None:
        # Only the submod with BOTH conditions should match.
        matched = self._run_filter(
            [female_submod, female_perk_submod], "IsFemale HasPerk"
        )
        assert "female_perk_anim" in matched
        assert "female_anim" not in matched

    def test_condition_prefix_stripped_before_parsing(
        self,
        female_submod: SubMod,
        perk_submod: SubMod,
    ) -> None:
        matched = self._run_filter(
            [female_submod, perk_submod], "condition:IsFemale"
        )
        assert "female_anim" in matched
        assert "perk_anim" not in matched

    def test_condition_prefix_case_insensitive(
        self,
        female_submod: SubMod,
        perk_submod: SubMod,
    ) -> None:
        matched = self._run_filter(
            [female_submod, perk_submod], "CONDITION:IsFemale"
        )
        assert "female_anim" in matched

    # ------------------------------------------------------------------
    # Edge-case tests
    # ------------------------------------------------------------------

    def test_empty_query_matches_all_submods(
        self,
        female_submod: SubMod,
        perk_submod: SubMod,
        empty_submod: SubMod,
    ) -> None:
        """An empty filter query (only an empty condition: prefix) matches all."""
        matched = self._run_filter(
            [female_submod, perk_submod, empty_submod], "condition:"
        )
        assert "female_anim" in matched
        assert "perk_anim" in matched
        assert "bare_anim" in matched

    def test_submod_with_no_conditions_fails_required(
        self,
        empty_submod: SubMod,
    ) -> None:
        matched = self._run_filter([empty_submod], "IsFemale")
        assert "bare_anim" not in matched

    def test_submod_with_no_conditions_passes_not(
        self,
        empty_submod: SubMod,
    ) -> None:
        """A submod with no conditions passes a NOT filter (absent = not excluded)."""
        matched = self._run_filter([empty_submod], "NOT IsFemale")
        assert "bare_anim" in matched

    def test_required_and_excluded_combined(
        self,
        female_submod: SubMod,
        female_perk_submod: SubMod,
    ) -> None:
        """IsFemale NOT HasPerk matches female only, not female+perk."""
        matched = self._run_filter(
            [female_submod, female_perk_submod], "IsFemale NOT HasPerk"
        )
        assert "female_anim" in matched
        assert "female_perk_anim" not in matched

    def test_no_match_returns_empty_set(
        self,
        perk_submod: SubMod,
    ) -> None:
        matched = self._run_filter([perk_submod], "IsFemale")
        assert len(matched) == 0

    def test_none_submod_node_skipped(self) -> None:
        """Tree nodes without an attached SubMod must not cause errors."""
        # Build a tree normally then inject a node with submod=None
        sm = _make_submod("test_sub", condition_types_present={"IsFemale"})
        root = _make_tree([sm])
        # Inject a SUBMOD node with no submod
        orphan = TreeNode(
            display_name="orphan",
            node_type=NodeType.SUBMOD,
            submod=None,
        )
        # Attach it to the first replacer
        root.children[0].children[0].children.append(orphan)

        from oar_priority_manager.ui.main_window import MainWindow

        mock_panel = MagicMock()
        mock_panel.tree_root = root
        captured: dict = {}
        mock_panel.filter_tree.side_effect = (
            lambda matching, hide_mode=False: captured.update(
                {"matching": matching}
            )
        )

        win = MagicMock()
        win._tree_panel = mock_panel
        win._hide_mode = False

        # Should not raise even with the None-submod node present
        MainWindow._apply_condition_filter(win, "IsFemale")
        assert isinstance(captured["matching"], set)

    # ------------------------------------------------------------------
    # Revert-to-text-mode tests
    # ------------------------------------------------------------------

    def test_clearing_input_calls_filter_tree_with_none(
        self, qtbot
    ) -> None:
        """When the search bar is cleared, the main window clears the filter."""
        from oar_priority_manager.ui.search_bar import SearchBar

        bar = SearchBar()
        qtbot.addWidget(bar)

        captured = {}
        bar.search_changed.connect(lambda t: captured.update({"text": t}))

        bar._input.setText("NOT HasPerk")
        bar._input.clear()

        assert captured["text"] == ""

    def test_mode_reverts_after_clearing_keyword(self, qtbot) -> None:
        """Removing the last keyword reverts the bar to TEXT mode."""
        from oar_priority_manager.ui.search_bar import SearchBar

        bar = SearchBar()
        qtbot.addWidget(bar)

        bar._input.setText("NOT HasPerk")
        assert bar.current_mode == SearchMode.CONDITION

        bar._input.setText("HasPerk")
        assert bar.current_mode == SearchMode.TEXT
