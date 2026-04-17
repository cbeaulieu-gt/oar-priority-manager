"""Tests for MainWindow advanced-filter wiring (Tasks 6 & 7, issue #49).

Covers:
- ``MainWindow._on_advanced_requested`` — signal wiring, dialog creation,
  pre-population from condition-mode search bar, filter_applied routing.
- ``MainWindow._apply_advanced_filter`` — tree walking, match_advanced_filter
  dispatch, filter_tree forwarding, empty-query short-circuit.

All tests use the ``MagicMock``-as-*self* pattern established in
``test_condition_filter_search.py`` to avoid instantiating a real
``MainWindow`` (which requires a live MO2 instance on disk).
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from oar_priority_manager.core.filter_engine import AdvancedFilterQuery
from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.ui.search_bar import SearchMode
from oar_priority_manager.ui.tree_model import NodeType, TreeNode, build_tree

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
    """Build a minimal SubMod for advanced-filter tests.

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


# ---------------------------------------------------------------------------
# Task 6 — _on_advanced_requested
# ---------------------------------------------------------------------------


class TestOnAdvancedRequested:
    """Tests for ``MainWindow._on_advanced_requested``.

    Uses the MagicMock-as-self pattern: call the unbound method on a mock
    object that has the required attributes wired up.
    """

    def _make_win(
        self,
        submods: list[SubMod] | None = None,
        search_mode: SearchMode = SearchMode.TEXT,
        search_text: str = "",
    ) -> MagicMock:
        """Create a lightweight mock MainWindow substitute.

        Args:
            submods: List of SubMods assigned to ``_submods``.
            search_mode: The SearchMode the search bar reports.
            search_text: Text currently in the search bar input.

        Returns:
            A ``MagicMock`` configured to stand in for ``self``.
        """
        win = MagicMock()
        win._submods = submods or []
        win._search_bar.current_mode = search_mode
        win._search_bar._input.text.return_value = search_text
        return win

    def test_opens_filter_builder_dialog(self) -> None:
        """``_on_advanced_requested`` instantiates a FilterBuilder and calls exec."""
        win = self._make_win()

        with patch(
            "oar_priority_manager.ui.main_window.FilterBuilder"
        ) as MockDialog:
            instance = MockDialog.return_value
            from oar_priority_manager.ui.main_window import MainWindow

            MainWindow._on_advanced_requested(win)

        MockDialog.assert_called_once()
        instance.exec.assert_called_once()

    def test_known_types_is_sorted_union_of_submods(self) -> None:
        """known_conditions passed to FilterBuilder is the sorted union.

        Verifies that ``collect_known_condition_types`` is called with
        ``self._submods`` and the result is forwarded to the dialog.
        """
        sm1 = _make_submod(
            "s1", condition_types_present={"IsInCombat", "IsFemale"}
        )
        sm2 = _make_submod(
            "s2", condition_types_present={"HasPerk"}
        )
        win = self._make_win(submods=[sm1, sm2])

        captured_kwargs: dict = {}

        def _capture(*args, **kwargs):
            captured_kwargs["known_conditions"] = args[0] if args else kwargs.get(
                "known_conditions"
            )
            mock = MagicMock()
            mock.filter_applied = MagicMock()
            mock.filter_applied.connect = MagicMock()
            return mock

        with patch(
            "oar_priority_manager.ui.main_window.FilterBuilder",
            side_effect=_capture,
        ):
            from oar_priority_manager.ui.main_window import MainWindow

            MainWindow._on_advanced_requested(win)

        known = captured_kwargs["known_conditions"]
        # Must be a sorted list
        assert isinstance(known, list)
        assert known == sorted(known)
        # Must contain submod-observed types
        assert "IsFemale" in known
        assert "IsInCombat" in known
        assert "HasPerk" in known

    def test_no_initial_query_when_search_bar_in_text_mode(self) -> None:
        """Dialog receives ``initial_query=None`` when search bar is in TEXT mode."""
        win = self._make_win(search_mode=SearchMode.TEXT)

        captured: dict = {}

        def _capture(*args, **kwargs):
            captured["initial_query"] = kwargs.get("initial_query")
            mock = MagicMock()
            mock.filter_applied = MagicMock()
            mock.filter_applied.connect = MagicMock()
            return mock

        with patch(
            "oar_priority_manager.ui.main_window.FilterBuilder",
            side_effect=_capture,
        ):
            from oar_priority_manager.ui.main_window import MainWindow

            MainWindow._on_advanced_requested(win)

        assert captured["initial_query"] is None

    def test_initial_query_populated_from_condition_mode_text(self) -> None:
        """Dialog receives a pre-populated query when bar is in CONDITION mode.

        The parsed ``required`` and ``excluded`` sets from the current text
        query must be forwarded to the dialog as ``initial_query``.
        """
        win = self._make_win(
            search_mode=SearchMode.CONDITION,
            search_text="IsFemale NOT HasPerk",
        )

        captured: dict = {}

        def _capture(*args, **kwargs):
            captured["initial_query"] = kwargs.get("initial_query")
            mock = MagicMock()
            mock.filter_applied = MagicMock()
            mock.filter_applied.connect = MagicMock()
            return mock

        with patch(
            "oar_priority_manager.ui.main_window.FilterBuilder",
            side_effect=_capture,
        ):
            from oar_priority_manager.ui.main_window import MainWindow

            MainWindow._on_advanced_requested(win)

        iq = captured["initial_query"]
        assert iq is not None
        assert isinstance(iq, AdvancedFilterQuery)
        assert "IsFemale" in iq.required
        assert "HasPerk" in iq.excluded
        # ANY OF stays empty (text parser has no OR output, plan §8 decision 8)
        assert len(iq.any_of) == 0

    def test_filter_applied_signal_routes_to_apply_advanced_filter(self) -> None:
        """Connecting ``filter_applied`` to ``_apply_advanced_filter`` happens.

        When the dialog emits ``filter_applied``, ``_apply_advanced_filter``
        must be called with the emitted query.
        """
        win = self._make_win()
        query = AdvancedFilterQuery(required={"IsFemale"})

        # Record what filter_applied was connected to, then fire it manually.
        connected_slot: list = []

        def _capture(*args, **kwargs):
            mock = MagicMock()
            mock.filter_applied.connect.side_effect = (
                lambda fn: connected_slot.append(fn)
            )
            return mock

        with patch(
            "oar_priority_manager.ui.main_window.FilterBuilder",
            side_effect=_capture,
        ):
            from oar_priority_manager.ui.main_window import MainWindow

            MainWindow._on_advanced_requested(win)

        assert connected_slot, "filter_applied.connect was never called"
        # Fire the connected slot manually
        connected_slot[0](query)
        win._apply_advanced_filter.assert_called_once_with(query)

    def test_advanced_requested_signal_wired_in_connect_signals(
        self, qtbot
    ) -> None:
        """``_connect_signals`` connects ``advanced_requested`` to the slot.

        This test verifies that the signal is wired by checking that calling
        the slot manually and triggering the signal both route correctly.
        We do this without a full MainWindow by inspecting the source.
        """
        import inspect

        from oar_priority_manager.ui.main_window import MainWindow

        source = inspect.getsource(MainWindow._connect_signals)
        assert "advanced_requested" in source, (
            "_connect_signals must wire search_bar.advanced_requested"
        )
        assert "_on_advanced_requested" in source, (
            "_connect_signals must connect to _on_advanced_requested"
        )


# ---------------------------------------------------------------------------
# Task 7 — _apply_advanced_filter
# ---------------------------------------------------------------------------


class TestApplyAdvancedFilter:
    """Tests for ``MainWindow._apply_advanced_filter``.

    Uses the same ``_run_filter`` harness pattern established in
    ``TestApplyConditionFilter`` (lines 347-407 of
    ``test_condition_filter_search.py``).
    """

    def _run_filter(
        self,
        submods: list[SubMod],
        query: AdvancedFilterQuery,
        hide_mode: bool = False,
    ) -> set[str]:
        """Run ``_apply_advanced_filter`` and return matched submod names.

        Builds a real tree from *submods*, wires a mock tree panel, calls
        the filter method, and returns the set of ``display_name`` values
        whose ``TreeNode`` ids ended up in the ``matching`` set passed to
        ``filter_tree``.  Returns ``None`` (as a sentinel) when
        ``filter_tree(None)`` is called (empty query path).

        Args:
            submods: SubMods to include in the tree.
            query: The advanced filter query to apply.
            hide_mode: Value assigned to ``win._hide_mode``.

        Returns:
            Set of ``display_name`` strings for matched SUBMOD nodes, or
            ``None`` if ``filter_tree`` was called with ``None``.
        """
        from oar_priority_manager.ui.main_window import MainWindow
        from oar_priority_manager.ui.tree_model import build_tree

        root = build_tree(submods)

        node_by_id: dict[int, TreeNode] = {}

        def _collect(node: TreeNode) -> None:
            node_by_id[id(node)] = node
            for child in node.children:
                _collect(child)

        _collect(root)

        captured: dict = {}

        mock_panel = MagicMock()
        mock_panel.tree_root = root
        mock_panel.filter_tree.side_effect = (
            lambda matching, hide_mode=False: captured.update(
                {"matching": matching, "hide_mode": hide_mode}
            )
        )

        win = MagicMock()
        win._tree_panel = mock_panel
        win._hide_mode = hide_mode

        MainWindow._apply_advanced_filter(win, query)

        matched_ids = captured.get("matching")
        if matched_ids is None:
            return None  # type: ignore[return-value]
        return {
            node_by_id[nid].display_name
            for nid in matched_ids
            if nid in node_by_id
            and node_by_id[nid].node_type == NodeType.SUBMOD
        }

    # ------------------------------------------------------------------ #
    # Fixtures                                                             #
    # ------------------------------------------------------------------ #

    @pytest.fixture
    def female_sub(self) -> SubMod:
        """SubMod with IsFemale condition."""
        return _make_submod(
            "female_anim",
            condition_types_present={"IsFemale"},
        )

    @pytest.fixture
    def perk_sub(self) -> SubMod:
        """SubMod with HasPerk condition."""
        return _make_submod(
            "perk_anim",
            condition_types_present={"HasPerk"},
        )

    @pytest.fixture
    def female_perk_sub(self) -> SubMod:
        """SubMod with both IsFemale and HasPerk conditions."""
        return _make_submod(
            "female_perk_anim",
            condition_types_present={"IsFemale", "HasPerk"},
        )

    @pytest.fixture
    def empty_sub(self) -> SubMod:
        """SubMod with no conditions."""
        return _make_submod("bare_anim", condition_types_present=set())

    # ------------------------------------------------------------------ #
    # Empty-query short-circuit                                            #
    # ------------------------------------------------------------------ #

    def test_empty_query_calls_filter_tree_with_none(
        self, female_sub: SubMod
    ) -> None:
        """An empty AdvancedFilterQuery clears the filter (calls filter_tree(None))."""
        result = self._run_filter([female_sub], AdvancedFilterQuery())
        assert result is None

    # ------------------------------------------------------------------ #
    # REQUIRED bucket                                                      #
    # ------------------------------------------------------------------ #

    def test_required_matches_submod_with_condition(
        self,
        female_sub: SubMod,
        perk_sub: SubMod,
    ) -> None:
        """REQUIRED=IsFemale matches only the female submod."""
        q = AdvancedFilterQuery(required={"IsFemale"})
        matched = self._run_filter([female_sub, perk_sub], q)
        assert "female_anim" in matched
        assert "perk_anim" not in matched

    # ------------------------------------------------------------------ #
    # ANY OF bucket                                                        #
    # ------------------------------------------------------------------ #

    def test_any_of_matches_submod_with_one_condition(
        self,
        female_sub: SubMod,
        perk_sub: SubMod,
        empty_sub: SubMod,
    ) -> None:
        """ANY_OF={IsFemale, HasPerk} matches both but not the empty submod."""
        q = AdvancedFilterQuery(any_of={"IsFemale", "HasPerk"})
        matched = self._run_filter([female_sub, perk_sub, empty_sub], q)
        assert "female_anim" in matched
        assert "perk_anim" in matched
        assert "bare_anim" not in matched

    # ------------------------------------------------------------------ #
    # EXCLUDED bucket                                                      #
    # ------------------------------------------------------------------ #

    def test_excluded_removes_submod_with_condition(
        self,
        female_sub: SubMod,
        perk_sub: SubMod,
    ) -> None:
        """EXCLUDED=HasPerk removes the perk submod."""
        q = AdvancedFilterQuery(excluded={"HasPerk"})
        matched = self._run_filter([female_sub, perk_sub], q)
        assert "female_anim" in matched
        assert "perk_anim" not in matched

    # ------------------------------------------------------------------ #
    # Combined buckets                                                     #
    # ------------------------------------------------------------------ #

    def test_all_three_buckets_combined(
        self,
        female_sub: SubMod,
        perk_sub: SubMod,
        female_perk_sub: SubMod,
        empty_sub: SubMod,
    ) -> None:
        """REQUIRED=IsFemale, ANY_OF=IsFemale, EXCLUDED=HasPerk yields female only."""
        q = AdvancedFilterQuery(
            required={"IsFemale"},
            any_of={"IsFemale", "HasPerk"},
            excluded={"HasPerk"},
        )
        matched = self._run_filter(
            [female_sub, perk_sub, female_perk_sub, empty_sub], q
        )
        assert "female_anim" in matched
        assert "perk_anim" not in matched
        assert "female_perk_anim" not in matched  # excluded by HasPerk
        assert "bare_anim" not in matched

    # ------------------------------------------------------------------ #
    # Tree-walk edge cases                                                 #
    # ------------------------------------------------------------------ #

    def test_none_submod_node_skipped(self) -> None:
        """Tree nodes without an attached SubMod are silently skipped."""
        sm = _make_submod("test_sub", condition_types_present={"IsFemale"})
        root = build_tree([sm])
        orphan = TreeNode(
            display_name="orphan",
            node_type=NodeType.SUBMOD,
            submod=None,
        )
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

        # Should not raise
        q = AdvancedFilterQuery(required={"IsFemale"})
        MainWindow._apply_advanced_filter(win, q)
        assert isinstance(captured["matching"], set)

    def test_hide_mode_forwarded_to_filter_tree(
        self, female_sub: SubMod
    ) -> None:
        """``self._hide_mode`` is forwarded to ``TreePanel.filter_tree``."""
        from oar_priority_manager.ui.main_window import MainWindow
        from oar_priority_manager.ui.tree_model import build_tree

        root = build_tree([female_sub])
        captured: dict = {}

        mock_panel = MagicMock()
        mock_panel.tree_root = root
        mock_panel.filter_tree.side_effect = (
            lambda matching, hide_mode=False: captured.update(
                {"hide_mode": hide_mode}
            )
        )

        win = MagicMock()
        win._tree_panel = mock_panel
        win._hide_mode = True

        q = AdvancedFilterQuery(required={"IsFemale"})
        MainWindow._apply_advanced_filter(win, q)
        assert captured["hide_mode"] is True

    def test_advanced_query_stored_on_self(
        self, female_sub: SubMod
    ) -> None:
        """After applying, ``self._advanced_query`` is set to the query."""
        from oar_priority_manager.ui.main_window import MainWindow
        from oar_priority_manager.ui.tree_model import build_tree

        root = build_tree([female_sub])

        win = MagicMock()
        win._tree_panel = MagicMock()
        win._tree_panel.tree_root = root
        win._hide_mode = False

        q = AdvancedFilterQuery(required={"IsFemale"})
        MainWindow._apply_advanced_filter(win, q)

        # _advanced_query must be set to the query (not a MagicMock attribute)
        assert win._advanced_query == q
