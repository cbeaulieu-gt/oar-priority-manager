"""Tests for PillWidget — single condition-name chip (issue #49, Task 3).

Covers:
  - Construction and ``condition_name`` property
  - QLabel child displays the condition name
  - Close button emits ``removed`` signal with the condition name
  - Close button type and attributes
  - Multiple instances are independent
  - ``condition_name`` property is read-only
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QLabel, QToolButton

from oar_priority_manager.ui.filter_pill import PillWidget

# ---------------------------------------------------------------------------
# TestPillWidget
# ---------------------------------------------------------------------------


class TestPillWidget:
    """Unit tests for ``PillWidget``."""

    @pytest.fixture
    def pill(self, qtbot) -> PillWidget:
        """Return a PillWidget("IsFemale") registered with qtbot."""
        w = PillWidget("IsFemale")
        qtbot.addWidget(w)
        return w

    # ------------------------------------------------------------------
    # Construction / property
    # ------------------------------------------------------------------

    def test_construction_succeeds(self, pill: PillWidget) -> None:
        """PillWidget("IsFemale") constructs without error."""
        assert pill is not None

    def test_condition_name_property(self, pill: PillWidget) -> None:
        """``condition_name`` returns the string passed to the constructor."""
        assert pill.condition_name == "IsFemale"

    # ------------------------------------------------------------------
    # QLabel child
    # ------------------------------------------------------------------

    def test_label_shows_condition_name(self, pill: PillWidget) -> None:
        """A QLabel child must display the condition name exactly."""
        labels = pill.findChildren(QLabel)
        assert labels, "Expected at least one QLabel child"
        texts = [lbl.text() for lbl in labels]
        assert "IsFemale" in texts, (
            f"No QLabel with text 'IsFemale' found; got {texts!r}"
        )

    # ------------------------------------------------------------------
    # Close button
    # ------------------------------------------------------------------

    def test_close_button_is_qtoolbutton(self, pill: PillWidget) -> None:
        """The close button must be a QToolButton."""
        buttons = pill.findChildren(QToolButton)
        assert buttons, "Expected at least one QToolButton child"

    def test_close_button_has_remove_tooltip(self, pill: PillWidget) -> None:
        """The close button should have a tooltip containing 'Remove'."""
        buttons = pill.findChildren(QToolButton)
        assert buttons, "Expected at least one QToolButton child"
        tooltips = [btn.toolTip() for btn in buttons]
        assert any("Remove" in tip for tip in tooltips), (
            f"No QToolButton with 'Remove' in tooltip; got {tooltips!r}"
        )

    def test_close_button_emits_removed_signal(
        self, pill: PillWidget, qtbot
    ) -> None:
        """Clicking the close button emits ``removed`` with the condition name."""
        buttons = pill.findChildren(QToolButton)
        assert buttons, "Expected at least one QToolButton child"
        close_btn = buttons[0]

        received: list[str] = []
        pill.removed.connect(received.append)

        with qtbot.waitSignal(pill.removed, timeout=1000) as blocker:
            close_btn.click()

        assert blocker.args == ["IsFemale"]
        assert received == ["IsFemale"]

    # ------------------------------------------------------------------
    # Multiple instances are independent
    # ------------------------------------------------------------------

    def test_multiple_instances_do_not_interfere(self, qtbot) -> None:
        """Clicking pill A's close button must not emit from pill B."""
        pill_a = PillWidget("IsFemale")
        pill_b = PillWidget("IsInCombat")
        qtbot.addWidget(pill_a)
        qtbot.addWidget(pill_b)

        received: list[str] = []
        pill_a.removed.connect(received.append)
        pill_b.removed.connect(received.append)

        # Click only pill_a's close button
        btn_a = pill_a.findChildren(QToolButton)[0]
        with qtbot.waitSignal(pill_a.removed, timeout=1000):
            btn_a.click()

        assert received == ["IsFemale"], (
            f"Expected only 'IsFemale' to be received; got {received!r}"
        )

    # ------------------------------------------------------------------
    # Read-only property
    # ------------------------------------------------------------------

    def test_condition_name_is_read_only(self, pill: PillWidget) -> None:
        """Assigning to ``condition_name`` must raise ``AttributeError``."""
        with pytest.raises(AttributeError):
            pill.condition_name = "SomethingElse"  # type: ignore[misc]
