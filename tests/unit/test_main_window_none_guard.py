"""Tests for MainWindow None-submod guards (issue #100).

Covers:
- ``MainWindow._on_action`` — early-return when ``submod`` is ``None``.
- ``StacksPanel.update_selection(None)`` — action buttons are disabled
  when no submod is selected.
- ``StacksPanel.update_selection(submod)`` — action buttons are re-enabled
  when a valid submod is provided.

The ``_on_action`` tests use the MagicMock-as-self pattern from
``test_main_window_scan_issues.py`` to avoid pulling in a live MO2
instance.  The ``StacksPanel`` tests instantiate the real widget under
``QT_QPA_PLATFORM=offscreen``.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.ui.main_window import MainWindow  # noqa: E402
from oar_priority_manager.ui.stacks_panel import StacksPanel  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_submod(
    name: str = "sub",
    priority: int = 100,
    mo2_mod: str = "TestMod",
    replacer: str = "rep",
    animations: list[str] | None = None,
) -> SubMod:
    """Build a minimal SubMod for None-guard tests.

    Args:
        name: Submod name.
        priority: Priority integer.
        mo2_mod: MO2 mod name.
        replacer: Replacer name.
        animations: Animation filenames.

    Returns:
        A fully constructed SubMod instance with no warnings.
    """
    return SubMod(
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
        animations=animations or ["mt_idle.hkx"],
        conditions={},
        warnings=[],
    )


# ---------------------------------------------------------------------------
# _on_action None-submod guard
# ---------------------------------------------------------------------------


class TestOnActionNoneSubmod:
    """``_on_action`` must return immediately when ``submod`` is ``None``.

    The early return prevents ``_confirm_action`` from reaching
    ``move_to_top(None, …)`` and raising
    ``AttributeError: 'NoneType' object has no attribute 'animations'``.
    """

    def _make_win(self) -> MagicMock:
        """Build a minimal mock MainWindow substitute.

        Returns:
            MagicMock configured with the attributes ``_on_action`` reads.
        """
        mock_self = MagicMock()
        return mock_self

    def test_move_to_top_none_submod_does_not_raise(self) -> None:
        """``_on_action('move_to_top', None, None)`` must not raise."""
        mock_self = self._make_win()
        # Should return without calling _confirm_action or write_override
        MainWindow._on_action(mock_self, "move_to_top", None, None)
        mock_self._confirm_action.assert_not_called()

    def test_move_to_top_replacer_none_submod_does_not_raise(self) -> None:
        """``_on_action('move_to_top_replacer', None, None)`` must not raise."""
        mock_self = self._make_win()
        MainWindow._on_action(mock_self, "move_to_top_replacer", None, None)
        mock_self._confirm_action.assert_not_called()

    def test_move_to_top_mod_none_submod_does_not_raise(self) -> None:
        """``_on_action('move_to_top_mod', None, None)`` must not raise."""
        mock_self = self._make_win()
        MainWindow._on_action(mock_self, "move_to_top_mod", None, None)
        mock_self._confirm_action.assert_not_called()

    def test_no_state_mutation_when_submod_is_none(self) -> None:
        """No write_override calls must occur when ``submod`` is ``None``.

        ``write_override`` is imported inside ``_on_action``'s body, so we
        patch it at its definition site in ``override_manager``.
        """
        mock_self = self._make_win()
        with patch(
            "oar_priority_manager.core.override_manager.write_override"
        ) as mock_write:
            # The None guard should return before write_override is ever reached.
            MainWindow._on_action(mock_self, "move_to_top", None, None)
            mock_write.assert_not_called()


# ---------------------------------------------------------------------------
# StacksPanel button gating on selection state
# ---------------------------------------------------------------------------


class TestStacksPanelButtonGating:
    """Action buttons must be disabled with no selection, enabled otherwise.

    Uses a real ``StacksPanel`` under ``QT_QPA_PLATFORM=offscreen`` so
    the ``QWidget.isEnabled()`` contract is exercised without a live MO2
    instance.
    """

    @pytest.fixture()
    def panel(self, qapp) -> StacksPanel:  # type: ignore[no-untyped-def]
        """Instantiate a real StacksPanel with an empty conflict map.

        Args:
            qapp: pytest-qt fixture that ensures a ``QApplication`` exists.

        Returns:
            A ``StacksPanel`` ready for button-state assertions.
        """
        return StacksPanel(conflict_map={})

    def _action_buttons(self, panel: StacksPanel) -> list:
        """Return the action buttons that must track selection state.

        Args:
            panel: The StacksPanel under test.

        Returns:
            List of QPushButton instances for move-to-top variants.
        """
        return [
            panel._move_to_top_btn,
            panel._move_rep_btn,
            panel._move_mod_btn,
        ]

    def test_buttons_disabled_with_no_selection(
        self, panel: StacksPanel
    ) -> None:
        """Action buttons are disabled when ``update_selection(None)`` is called."""
        panel.update_selection(None)
        for btn in self._action_buttons(panel):
            assert not btn.isEnabled(), (
                f"{btn.text()!r} should be disabled with no selection"
            )

    def test_buttons_enabled_after_valid_selection(
        self, panel: StacksPanel
    ) -> None:
        """Action buttons are enabled when a valid submod (no warnings) is selected."""
        sm = _make_submod()
        panel.update_selection(sm)
        for btn in self._action_buttons(panel):
            assert btn.isEnabled(), (
                f"{btn.text()!r} should be enabled after selecting a submod"
            )

    def test_buttons_re_disabled_after_selection_cleared(
        self, panel: StacksPanel
    ) -> None:
        """Selecting then clearing re-disables all action buttons."""
        sm = _make_submod()
        panel.update_selection(sm)
        panel.update_selection(None)
        for btn in self._action_buttons(panel):
            assert not btn.isEnabled(), (
                f"{btn.text()!r} should be disabled after selection cleared"
            )
