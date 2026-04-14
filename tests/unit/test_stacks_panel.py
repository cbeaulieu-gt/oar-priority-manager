"""Unit tests for StacksPanel toolbar enhancements.

Covers the three new controls added in issues #46, #47, and #48:
  #46 — Shift… button and _on_shift dialog
  #47 — Animation filter QLineEdit
  #48 — Hide Winning checkable toggle
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.ui.stacks_panel import StacksPanel, _StackSection

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_submod(
    name: str = "sub",
    priority: int = 100,
    animations: list[str] | None = None,
    has_warnings: bool = False,
) -> SubMod:
    """Build a minimal SubMod for testing.

    Args:
        name: Submod name.
        priority: Priority integer.
        animations: List of animation filenames; defaults to
            ``["mt_idle.hkx"]``.
        has_warnings: When ``True``, adds a dummy warning string.

    Returns:
        A fully constructed SubMod.
    """
    return SubMod(
        mo2_mod="Test Mod",
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
