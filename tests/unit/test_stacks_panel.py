"""Unit tests for StacksPanel toolbar enhancements.

Covers the new controls added in issues #46, #47, #48, and #74:
  #46 — Shift… button and _on_shift dialog
  #47 — Animation filter QLineEdit
  #48 — Hide Winning checkable toggle
  #74 — Collapse same-mod competitor rows into a summary row
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.ui.stacks_panel import (
    StacksPanel,
    _ModGroupRow,
    _StackSection,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_submod(
    name: str = "sub",
    priority: int = 100,
    animations: list[str] | None = None,
    has_warnings: bool = False,
    mo2_mod: str = "Test Mod",
) -> SubMod:
    """Build a minimal SubMod for testing.

    Args:
        name: Submod name.
        priority: Priority integer.
        animations: List of animation filenames; defaults to
            ``["mt_idle.hkx"]``.
        has_warnings: When ``True``, adds a dummy warning string.
        mo2_mod: MO2 mod name used for same-mod grouping tests.

    Returns:
        A fully constructed SubMod.
    """
    return SubMod(
        mo2_mod=mo2_mod,
        replacer="rep",
        name=name,
        description="",
        priority=priority,
        source_priority=priority,
        disabled=False,
        config_path=Path(
            "C:/mods/Test/meshes/actors/character/animations"
            "/OpenAnimationReplacer/rep/sub/config.json"
        ),
        override_source=OverrideSource.SOURCE,
        override_is_ours=False,
        raw_dict={"name": name, "priority": priority},
        animations=animations if animations is not None else ["mt_idle.hkx"],
        conditions={},
        condition_types_present=set(),
        condition_types_negated=set(),
        warnings=["warn"] if has_warnings else [],
    )


def _make_panel(qtbot, conflict_map=None) -> StacksPanel:
    """Construct a StacksPanel and register it with qtbot.

    Args:
        qtbot: The pytest-qt bot fixture.
        conflict_map: Optional dict to pass as the conflict map; defaults
            to an empty dict.

    Returns:
        A visible StacksPanel widget.
    """
    panel = StacksPanel(conflict_map or {})
    qtbot.addWidget(panel)
    panel.show()
    return panel


def _iter_sections(panel: StacksPanel) -> list[_StackSection]:
    """Return all _StackSection widgets currently in the panel's scroll area.

    Args:
        panel: The StacksPanel to inspect.

    Returns:
        A list of _StackSection widgets (may be empty).
    """
    sections = []
    layout = panel._content_layout
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item and isinstance(item.widget(), _StackSection):
            sections.append(item.widget())
    return sections


# ---------------------------------------------------------------------------
# Issue #46 — Shift… button
# ---------------------------------------------------------------------------

class TestShiftButton:
    """Tests for the Shift… toolbar button (issue #46)."""

    def test_shift_btn_exists(self, qtbot):
        """StacksPanel exposes a _shift_btn attribute."""
        panel = _make_panel(qtbot)
        assert hasattr(panel, "_shift_btn")

    def test_shift_btn_disabled_with_no_selection(self, qtbot):
        """Shift button is disabled when no submod is selected."""
        panel = _make_panel(qtbot)
        panel.update_selection(None)
        assert not panel._shift_btn.isEnabled()

    def test_shift_btn_disabled_when_submod_has_warnings(self, qtbot):
        """Shift button is disabled when the selected submod has warnings."""
        sm = _make_submod(has_warnings=True)
        panel = _make_panel(qtbot)
        panel.update_selection(sm)
        assert not panel._shift_btn.isEnabled()

    def test_shift_btn_enabled_when_valid_submod(self, qtbot):
        """Shift button is enabled when a warning-free submod is selected."""
        sm = _make_submod()
        panel = _make_panel(qtbot, conflict_map={"mt_idle.hkx": [sm]})
        panel.update_selection(sm)
        assert panel._shift_btn.isEnabled()

    def test_shift_emits_action_on_ok(self, qtbot):
        """Clicking Shift and confirming the dialog emits action_triggered."""
        sm = _make_submod(priority=100)
        panel = _make_panel(qtbot, conflict_map={"mt_idle.hkx": [sm]})
        panel.update_selection(sm)

        received: list[tuple] = []
        panel.action_triggered.connect(
            lambda action, submod, val: received.append((action, submod, val))
        )

        with patch(
            "oar_priority_manager.ui.stacks_panel.QInputDialog.getInt",
            return_value=(50, True),
        ):
            panel._on_shift()

        assert len(received) == 1
        action, submod, value = received[0]
        assert action == "shift"
        assert submod is sm
        assert value == 50

    def test_shift_does_not_emit_on_cancel(self, qtbot):
        """Cancelling the Shift dialog does not emit action_triggered."""
        sm = _make_submod()
        panel = _make_panel(qtbot, conflict_map={"mt_idle.hkx": [sm]})
        panel.update_selection(sm)

        received: list[tuple] = []
        panel.action_triggered.connect(
            lambda action, submod, val: received.append((action, submod, val))
        )

        with patch(
            "oar_priority_manager.ui.stacks_panel.QInputDialog.getInt",
            return_value=(0, False),
        ):
            panel._on_shift()

        assert received == []

    def test_shift_does_nothing_when_no_submod(self, qtbot):
        """_on_shift is a no-op when _current_submod is None."""
        panel = _make_panel(qtbot)
        # Ensure no exception and no signal emission
        received: list = []
        panel.action_triggered.connect(lambda *a: received.append(a))
        panel._on_shift()
        assert received == []

    def test_shift_negative_value_emits_correctly(self, qtbot):
        """Negative shift delta is forwarded unchanged in the signal."""
        sm = _make_submod(priority=200)
        panel = _make_panel(qtbot, conflict_map={"mt_idle.hkx": [sm]})
        panel.update_selection(sm)

        received: list[tuple] = []
        panel.action_triggered.connect(
            lambda action, submod, val: received.append((action, submod, val))
        )

        with patch(
            "oar_priority_manager.ui.stacks_panel.QInputDialog.getInt",
            return_value=(-100, True),
        ):
            panel._on_shift()

        assert received[0][2] == -100


# ---------------------------------------------------------------------------
# Issue #47 — Animation filter input
# ---------------------------------------------------------------------------

class TestAnimFilter:
    """Tests for the animation filter QLineEdit (issue #47)."""

    def test_filter_widget_exists(self, qtbot):
        """StacksPanel exposes a _anim_filter attribute."""
        panel = _make_panel(qtbot)
        assert hasattr(panel, "_anim_filter")

    def test_filter_max_height(self, qtbot):
        """Filter input is compact — max height is at most 28px."""
        panel = _make_panel(qtbot)
        assert panel._anim_filter.maximumHeight() <= 28

    def test_filter_shows_all_when_empty(self, qtbot):
        """All sections are visible when the filter query is empty."""
        sm = _make_submod(animations=["mt_idle.hkx", "mt_run.hkx"])
        conflict_map = {
            "mt_idle.hkx": [sm],
            "mt_run.hkx": [sm],
        }
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        panel.update_selection(sm)

        panel._on_anim_filter("")

        sections = _iter_sections(panel)
        assert len(sections) == 2
        assert all(s.isVisible() for s in sections)

    def test_filter_hides_non_matching_sections(self, qtbot):
        """Sections whose anim_name does not contain the query are hidden."""
        sm = _make_submod(animations=["mt_idle.hkx", "mt_run.hkx"])
        conflict_map = {
            "mt_idle.hkx": [sm],
            "mt_run.hkx": [sm],
        }
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        panel.update_selection(sm)

        panel._on_anim_filter("idle")

        sections = _iter_sections(panel)
        visible = [s for s in sections if s.isVisible()]
        hidden = [s for s in sections if not s.isVisible()]
        assert len(visible) == 1
        assert visible[0].anim_name == "mt_idle.hkx"
        assert len(hidden) == 1
        assert hidden[0].anim_name == "mt_run.hkx"

    def test_filter_is_case_insensitive(self, qtbot):
        """Filter match is case-insensitive."""
        sm = _make_submod(animations=["mt_IDLE.hkx"])
        conflict_map = {"mt_IDLE.hkx": [sm]}
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        panel.update_selection(sm)

        panel._on_anim_filter("idle")

        sections = _iter_sections(panel)
        assert len(sections) == 1
        assert sections[0].isVisible()

    def test_filter_restores_all_on_clear(self, qtbot):
        """Clearing the filter after a query restores all sections."""
        sm = _make_submod(animations=["mt_idle.hkx", "mt_run.hkx"])
        conflict_map = {
            "mt_idle.hkx": [sm],
            "mt_run.hkx": [sm],
        }
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        panel.update_selection(sm)

        panel._on_anim_filter("idle")
        panel._on_anim_filter("")

        sections = _iter_sections(panel)
        assert all(s.isVisible() for s in sections)

    def test_anim_name_stored_on_section(self, qtbot):
        """Each built section has an anim_name attribute matching its animation."""
        sm = _make_submod(animations=["mt_idle.hkx", "mt_run.hkx"])
        conflict_map = {
            "mt_idle.hkx": [sm],
            "mt_run.hkx": [sm],
        }
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        panel.update_selection(sm)

        sections = _iter_sections(panel)
        anim_names = {s.anim_name for s in sections}
        assert anim_names == {"mt_idle.hkx", "mt_run.hkx"}


# ---------------------------------------------------------------------------
# Issue #48 — Collapse-winning toggle
# ---------------------------------------------------------------------------

class TestCollapseWinning:
    """Tests for the Hide Winning checkable button (issue #48)."""

    def test_collapse_winning_btn_exists(self, qtbot):
        """StacksPanel exposes a _collapse_winning_btn attribute."""
        panel = _make_panel(qtbot)
        assert hasattr(panel, "_collapse_winning_btn")

    def test_collapse_winning_btn_is_checkable(self, qtbot):
        """The Hide Winning button is a checkable toggle."""
        panel = _make_panel(qtbot)
        assert panel._collapse_winning_btn.isCheckable()

    def test_is_winning_stored_on_section(self, qtbot):
        """Sections where the selected submod is rank #1 have is_winning=True."""
        winner = _make_submod(name="winner", priority=500,
                              animations=["mt_idle.hkx"])
        loser = _make_submod(name="loser", priority=100,
                             animations=["mt_idle.hkx"])
        # winner is first → rank 0 for winner, rank 1 for loser
        conflict_map = {"mt_idle.hkx": [winner, loser]}
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        panel.update_selection(winner)

        sections = _iter_sections(panel)
        assert len(sections) == 1
        assert sections[0].is_winning is True

    def test_is_winning_false_when_losing(self, qtbot):
        """Sections where the selected submod is NOT rank #1 have is_winning=False."""
        winner = _make_submod(name="winner", priority=500,
                              animations=["mt_idle.hkx"])
        loser = _make_submod(name="loser", priority=100,
                             animations=["mt_idle.hkx"])
        conflict_map = {"mt_idle.hkx": [winner, loser]}
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        # Select the loser — it is NOT rank #1 in this stack
        panel.update_selection(loser)

        sections = _iter_sections(panel)
        assert len(sections) == 1
        assert sections[0].is_winning is False

    def test_collapse_winning_collapses_winning_sections(self, qtbot):
        """Enabling Hide Winning collapses sections where submod is #1."""
        winner = _make_submod(
            name="winner", priority=500,
            animations=["mt_idle.hkx", "mt_run.hkx"],
        )
        loser = _make_submod(
            name="loser", priority=100,
            animations=["mt_idle.hkx"],
        )
        # winner beats loser in mt_idle; winner is sole competitor in mt_run
        conflict_map = {
            "mt_idle.hkx": [winner, loser],
            "mt_run.hkx": [winner],
        }
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        panel.update_selection(winner)

        # All sections start expanded
        sections = _iter_sections(panel)
        assert all(s._expanded for s in sections)

        panel._on_collapse_winning(True)

        sections = _iter_sections(panel)
        for s in sections:
            if s.is_winning:
                assert not s._expanded, (
                    f"Section {s.anim_name} should be collapsed (winning)"
                )

    def test_collapse_winning_keeps_losing_sections_expanded(self, qtbot):
        """Enabling Hide Winning does NOT collapse losing/tied sections."""
        winner = _make_submod(
            name="winner", priority=500, animations=["mt_idle.hkx"]
        )
        loser = _make_submod(
            name="loser", priority=100, animations=["mt_idle.hkx"]
        )
        conflict_map = {"mt_idle.hkx": [winner, loser]}
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        # Select the loser — the section is NOT winning for loser
        panel.update_selection(loser)

        panel._on_collapse_winning(True)

        sections = _iter_sections(panel)
        assert len(sections) == 1
        assert sections[0]._expanded  # losing section stays expanded

    def test_unchecking_expands_all_sections(self, qtbot):
        """Unchecking Hide Winning restores all sections to expanded."""
        winner = _make_submod(
            name="winner", priority=500,
            animations=["mt_idle.hkx", "mt_run.hkx"],
        )
        loser = _make_submod(
            name="loser", priority=100, animations=["mt_idle.hkx"]
        )
        conflict_map = {
            "mt_idle.hkx": [winner, loser],
            "mt_run.hkx": [winner],
        }
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        panel.update_selection(winner)

        # Collapse first, then uncollapse
        panel._on_collapse_winning(True)
        panel._on_collapse_winning(False)

        sections = _iter_sections(panel)
        assert all(s._expanded for s in sections)


# ---------------------------------------------------------------------------
# Helpers for issue #74 tests
# ---------------------------------------------------------------------------

def _iter_section_children(section: _StackSection) -> list:
    """Return all direct child widgets of a _StackSection's content area.

    Args:
        section: The _StackSection to inspect.

    Returns:
        A list of direct child QWidget objects in the content layout.
    """
    layout = section._content_layout
    children = []
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item and item.widget():
            children.append(item.widget())
    return children


# ---------------------------------------------------------------------------
# Issue #74 — Collapse same-mod competitor rows
# ---------------------------------------------------------------------------

class TestCollapseCompetitors:
    """Tests for same-mod sibling collapsing in stacks panel (issue #74)."""

    def test_same_mod_siblings_create_group_row(self, qtbot):
        """Same-mod competitors produce a _ModGroupRow summary in the section."""
        selected = _make_submod(name="sub1", mo2_mod="SneakMod", priority=500,
                                animations=["mt_idle.hkx"])
        sibling = _make_submod(name="sub2", mo2_mod="SneakMod", priority=400,
                               animations=["mt_idle.hkx"])
        conflict_map = {"mt_idle.hkx": [selected, sibling]}
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        panel.update_selection(selected)

        sections = _iter_sections(panel)
        assert len(sections) == 1
        children = _iter_section_children(sections[0])

        group_rows = [c for c in children if isinstance(c, _ModGroupRow)]
        assert len(group_rows) == 1, "Expected exactly one _ModGroupRow for same-mod siblings"

    def test_group_row_label_shows_mod_name_and_count(self, qtbot):
        """The summary row label reflects the mod name and sibling count."""
        selected = _make_submod(name="sub1", mo2_mod="SneakMod", priority=500,
                                animations=["mt_idle.hkx"])
        sib2 = _make_submod(name="sub2", mo2_mod="SneakMod", priority=400,
                            animations=["mt_idle.hkx"])
        sib3 = _make_submod(name="sub3", mo2_mod="SneakMod", priority=300,
                            animations=["mt_idle.hkx"])
        conflict_map = {"mt_idle.hkx": [selected, sib2, sib3]}
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        panel.update_selection(selected)

        sections = _iter_sections(panel)
        children = _iter_section_children(sections[0])
        group_rows = [c for c in children if isinstance(c, _ModGroupRow)]
        assert len(group_rows) == 1
        label = group_rows[0]._btn.text()
        # Label should mention the mod name and sibling count (2 siblings)
        assert "SneakMod" in label
        assert "2" in label

    def test_cross_mod_competitors_are_individual_rows(self, qtbot):
        """Cross-mod competitors do NOT get grouped into a _ModGroupRow."""
        selected = _make_submod(name="sub1", mo2_mod="SneakMod", priority=500,
                                animations=["mt_idle.hkx"])
        other = _make_submod(name="other", mo2_mod="CombatMod", priority=300,
                             animations=["mt_idle.hkx"])
        conflict_map = {"mt_idle.hkx": [selected, other]}
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        panel.update_selection(selected)

        sections = _iter_sections(panel)
        children = _iter_section_children(sections[0])
        group_rows = [c for c in children if isinstance(c, _ModGroupRow)]
        assert len(group_rows) == 0, "Cross-mod competitor should NOT create a group row"

    def test_you_row_is_direct_section_child_not_in_group(self, qtbot):
        """'You' row is a direct child of the section — not inside _ModGroupRow."""
        selected = _make_submod(name="sub1", mo2_mod="SneakMod", priority=500,
                                animations=["mt_idle.hkx"])
        sibling = _make_submod(name="sub2", mo2_mod="SneakMod", priority=400,
                               animations=["mt_idle.hkx"])
        conflict_map = {"mt_idle.hkx": [selected, sibling]}
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        panel.update_selection(selected)

        sections = _iter_sections(panel)
        children = _iter_section_children(sections[0])

        # The group row exists but holds only the sibling — not the "you" row
        group_rows = [c for c in children if isinstance(c, _ModGroupRow)]
        assert len(group_rows) == 1
        # selected submod's row must NOT be inside the group's child rows
        assert len(group_rows[0]._child_rows) == 1

    def test_clicking_group_row_toggles_sibling_visibility(self, qtbot):
        """Clicking the _ModGroupRow summary button toggles the collapsed state and container."""
        selected = _make_submod(name="sub1", mo2_mod="SneakMod", priority=500,
                                animations=["mt_idle.hkx"])
        sibling = _make_submod(name="sub2", mo2_mod="SneakMod", priority=400,
                               animations=["mt_idle.hkx"])
        conflict_map = {"mt_idle.hkx": [selected, sibling]}
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        panel.update_selection(selected)

        sections = _iter_sections(panel)
        children = _iter_section_children(sections[0])
        group_rows = [c for c in children if isinstance(c, _ModGroupRow)]
        assert len(group_rows) == 1
        group = group_rows[0]

        # Groups start collapsed — container is explicitly hidden
        assert group.is_collapsed
        assert group._child_container.isHidden()

        # Click to expand — collapsed state flips, container no longer hidden
        group._btn.click()
        assert not group.is_collapsed
        assert not group._child_container.isHidden()

        # Click again to collapse — container hidden again
        group._btn.click()
        assert group.is_collapsed
        assert group._child_container.isHidden()

    def test_no_group_when_selected_is_only_submod_from_its_mod(self, qtbot):
        """No _ModGroupRow is created when no same-mod siblings exist."""
        selected = _make_submod(name="sub1", mo2_mod="SneakMod", priority=500,
                                animations=["mt_idle.hkx"])
        other = _make_submod(name="other", mo2_mod="CombatMod", priority=300,
                             animations=["mt_idle.hkx"])
        conflict_map = {"mt_idle.hkx": [selected, other]}
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        panel.update_selection(selected)

        sections = _iter_sections(panel)
        children = _iter_section_children(sections[0])
        group_rows = [c for c in children if isinstance(c, _ModGroupRow)]
        assert len(group_rows) == 0

    def test_group_state_persists_across_refresh(self, qtbot):
        """Expanding a group and calling _refresh_display preserves expanded state."""
        selected = _make_submod(name="sub1", mo2_mod="SneakMod", priority=500,
                                animations=["mt_idle.hkx"])
        sibling = _make_submod(name="sub2", mo2_mod="SneakMod", priority=400,
                               animations=["mt_idle.hkx"])
        conflict_map = {"mt_idle.hkx": [selected, sibling]}
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        panel.update_selection(selected)

        # Expand the group (it starts collapsed)
        sections = _iter_sections(panel)
        children = _iter_section_children(sections[0])
        group_rows = [c for c in children if isinstance(c, _ModGroupRow)]
        group_rows[0]._btn.click()  # expand

        # Trigger a refresh
        panel._refresh_display()

        # Group should still be expanded after refresh
        sections = _iter_sections(panel)
        children = _iter_section_children(sections[0])
        group_rows = [c for c in children if isinstance(c, _ModGroupRow)]
        assert len(group_rows) == 1
        assert not group_rows[0].is_collapsed

    def test_sibling_group_contains_correct_child_count(self, qtbot):
        """The group's _child_rows has exactly the same-mod sibling count."""
        selected = _make_submod(name="sub1", mo2_mod="SneakMod", priority=500,
                                animations=["mt_idle.hkx"])
        sib2 = _make_submod(name="sub2", mo2_mod="SneakMod", priority=400,
                            animations=["mt_idle.hkx"])
        sib3 = _make_submod(name="sub3", mo2_mod="SneakMod", priority=300,
                            animations=["mt_idle.hkx"])
        cross = _make_submod(name="cross", mo2_mod="CombatMod", priority=200,
                             animations=["mt_idle.hkx"])
        conflict_map = {"mt_idle.hkx": [selected, sib2, sib3, cross]}
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        panel.update_selection(selected)

        sections = _iter_sections(panel)
        children = _iter_section_children(sections[0])
        group_rows = [c for c in children if isinstance(c, _ModGroupRow)]
        assert len(group_rows) == 1
        # 2 siblings (sib2, sib3) — "you" (selected) is NOT in the group
        assert len(group_rows[0]._child_rows) == 2

    def test_rank_and_priority_labels_preserved_for_grouped_rows(self, qtbot):
        """Grouped sibling rows still carry rank badge and priority value labels."""
        from PySide6.QtWidgets import QLabel

        selected = _make_submod(name="sub1", mo2_mod="SneakMod", priority=500,
                                animations=["mt_idle.hkx"])
        sibling = _make_submod(name="sub2", mo2_mod="SneakMod", priority=400,
                               animations=["mt_idle.hkx"])
        conflict_map = {"mt_idle.hkx": [selected, sibling]}
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        panel.update_selection(selected)

        sections = _iter_sections(panel)
        children = _iter_section_children(sections[0])
        group_rows = [c for c in children if isinstance(c, _ModGroupRow)]
        assert len(group_rows) == 1

        sibling_row = group_rows[0]._child_rows[0]
        # Row should have QLabel children (rank badge + priority value + name)
        labels = sibling_row.findChildren(QLabel)
        assert len(labels) >= 2, "Grouped rows should still have rank badge and priority labels"

    def test_group_starts_collapsed_by_default(self, qtbot):
        """A freshly built mod group starts in the collapsed state."""
        selected = _make_submod(name="sub1", mo2_mod="SneakMod", priority=500,
                                animations=["mt_idle.hkx"])
        sibling = _make_submod(name="sub2", mo2_mod="SneakMod", priority=400,
                               animations=["mt_idle.hkx"])
        conflict_map = {"mt_idle.hkx": [selected, sibling]}
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        panel.update_selection(selected)

        sections = _iter_sections(panel)
        children = _iter_section_children(sections[0])
        group_rows = [c for c in children if isinstance(c, _ModGroupRow)]
        assert len(group_rows) == 1
        assert group_rows[0].is_collapsed
        assert group_rows[0]._child_container.isHidden()

    def test_mixed_same_and_cross_mod(self, qtbot):
        """Mixed scenario: same-mod siblings collapsed, cross-mod rows individual."""
        from PySide6.QtWidgets import QPushButton

        selected = _make_submod(name="sub1", mo2_mod="SneakMod", priority=500,
                                animations=["mt_idle.hkx"])
        sibling = _make_submod(name="sub2", mo2_mod="SneakMod", priority=400,
                               animations=["mt_idle.hkx"])
        cross = _make_submod(name="cross", mo2_mod="CombatMod", priority=300,
                             animations=["mt_idle.hkx"])
        conflict_map = {"mt_idle.hkx": [selected, sibling, cross]}
        panel = _make_panel(qtbot, conflict_map=conflict_map)
        panel.update_selection(selected)

        sections = _iter_sections(panel)
        children = _iter_section_children(sections[0])

        group_rows = [c for c in children if isinstance(c, _ModGroupRow)]
        direct_buttons = [c for c in children if isinstance(c, QPushButton)]

        # Exactly one group (same-mod sibling), one cross-mod individual button,
        # plus the "you" button
        assert len(group_rows) == 1, "Same-mod sibling must be in one group"
        assert len(direct_buttons) == 2, "Cross-mod + 'you' should be direct buttons"
