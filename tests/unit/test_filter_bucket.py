"""Tests for BucketWidget — labeled pill container (issue #49, Task 4).

Covers:
  - Construction and empty initial state
  - Adding a pill via the line-edit submit (Enter key)
  - ``selections_changed`` signal emitted on add
  - Duplicate add is a no-op (no duplicate pill, no second signal)
  - Empty/whitespace submit is a no-op
  - Removing a pill via its close button
  - ``clear()`` removes all pills and emits exactly once
  - ``set_selections()`` replaces all pills and emits exactly once
  - ``selections`` returns a copy (external mutation safe)
  - ``set_known_conditions()`` updates the completer model
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QPushButton, QToolButton

from oar_priority_manager.ui.filter_bucket import BucketWidget
from oar_priority_manager.ui.filter_pill import PillWidget

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

KNOWN = ["IsFemale", "IsInCombat", "HasMagicEffect"]


# ---------------------------------------------------------------------------
# TestBucketWidget
# ---------------------------------------------------------------------------


class TestBucketWidget:
    """Unit tests for ``BucketWidget``."""

    @pytest.fixture
    def bucket(self, qtbot) -> BucketWidget:
        """Return a BucketWidget("Required", KNOWN) registered with qtbot."""
        w = BucketWidget("Required", KNOWN)
        qtbot.addWidget(w)
        return w

    # ------------------------------------------------------------------
    # 1. Construction
    # ------------------------------------------------------------------

    def test_construction_succeeds(self, bucket: BucketWidget) -> None:
        """BucketWidget constructs without error."""
        assert bucket is not None

    def test_initial_selections_empty(self, bucket: BucketWidget) -> None:
        """``selections`` is an empty set after construction."""
        assert bucket.selections == set()

    # ------------------------------------------------------------------
    # 2. Add via line-edit Enter key
    # ------------------------------------------------------------------

    def test_add_via_enter_updates_selections(
        self, bucket: BucketWidget, qtbot
    ) -> None:
        """Typing a name and pressing Enter adds it to selections."""
        line_edit = bucket.findChild(QLineEdit)
        assert line_edit is not None, "No QLineEdit child found"

        line_edit.setText("IsFemale")
        qtbot.keyPress(line_edit, Qt.Key.Key_Return)

        assert bucket.selections == {"IsFemale"}

    def test_add_creates_pill_widget(
        self, bucket: BucketWidget, qtbot
    ) -> None:
        """Adding a condition creates exactly one PillWidget child."""
        line_edit = bucket.findChild(QLineEdit)
        assert line_edit is not None

        line_edit.setText("IsFemale")
        qtbot.keyPress(line_edit, Qt.Key.Key_Return)

        pills = bucket.findChildren(PillWidget)
        assert len(pills) == 1
        assert pills[0].condition_name == "IsFemale"

    def test_add_clears_line_edit(
        self, bucket: BucketWidget, qtbot
    ) -> None:
        """After a successful add the line edit is cleared."""
        line_edit = bucket.findChild(QLineEdit)
        assert line_edit is not None

        line_edit.setText("IsFemale")
        qtbot.keyPress(line_edit, Qt.Key.Key_Return)

        assert line_edit.text() == ""

    # ------------------------------------------------------------------
    # 3. selections_changed signal fires on add
    # ------------------------------------------------------------------

    def test_selections_changed_emitted_on_add(
        self, bucket: BucketWidget, qtbot
    ) -> None:
        """``selections_changed`` is emitted when a new pill is added."""
        line_edit = bucket.findChild(QLineEdit)
        assert line_edit is not None

        line_edit.setText("IsFemale")
        with qtbot.waitSignal(bucket.selections_changed, timeout=1000):
            qtbot.keyPress(line_edit, Qt.Key.Key_Return)

    # ------------------------------------------------------------------
    # 4. Duplicate add is a no-op
    # ------------------------------------------------------------------

    def test_duplicate_add_no_new_pill(
        self, bucket: BucketWidget, qtbot
    ) -> None:
        """Adding the same name twice keeps only one pill."""
        line_edit = bucket.findChild(QLineEdit)
        assert line_edit is not None

        line_edit.setText("IsFemale")
        qtbot.keyPress(line_edit, Qt.Key.Key_Return)
        line_edit.setText("IsFemale")
        qtbot.keyPress(line_edit, Qt.Key.Key_Return)

        assert len(bucket.selections) == 1
        pills = bucket.findChildren(PillWidget)
        assert len(pills) == 1

    def test_duplicate_add_no_second_signal(
        self, bucket: BucketWidget, qtbot
    ) -> None:
        """The second duplicate add must NOT emit ``selections_changed``."""
        line_edit = bucket.findChild(QLineEdit)
        assert line_edit is not None

        # First add — must emit
        line_edit.setText("IsFemale")
        with qtbot.waitSignal(bucket.selections_changed, timeout=1000):
            qtbot.keyPress(line_edit, Qt.Key.Key_Return)

        # Second add of same name — must NOT emit
        signal_count: list[int] = [0]
        bucket.selections_changed.connect(lambda: signal_count.__setitem__(0, signal_count[0] + 1))

        line_edit.setText("IsFemale")
        qtbot.keyPress(line_edit, Qt.Key.Key_Return)

        assert signal_count[0] == 0, (
            "selections_changed should not fire for duplicate add"
        )

    # ------------------------------------------------------------------
    # 5. Empty / whitespace submit is a no-op
    # ------------------------------------------------------------------

    def test_empty_submit_is_noop(
        self, bucket: BucketWidget, qtbot
    ) -> None:
        """Pressing Enter on an empty line edit does nothing."""
        line_edit = bucket.findChild(QLineEdit)
        assert line_edit is not None

        signal_count: list[int] = [0]
        bucket.selections_changed.connect(
            lambda: signal_count.__setitem__(0, signal_count[0] + 1)
        )

        line_edit.setText("")
        qtbot.keyPress(line_edit, Qt.Key.Key_Return)

        assert bucket.selections == set()
        assert signal_count[0] == 0

    def test_whitespace_submit_is_noop(
        self, bucket: BucketWidget, qtbot
    ) -> None:
        """Pressing Enter on whitespace-only text does nothing."""
        line_edit = bucket.findChild(QLineEdit)
        assert line_edit is not None

        signal_count: list[int] = [0]
        bucket.selections_changed.connect(
            lambda: signal_count.__setitem__(0, signal_count[0] + 1)
        )

        line_edit.setText("   ")
        qtbot.keyPress(line_edit, Qt.Key.Key_Return)

        assert bucket.selections == set()
        assert signal_count[0] == 0

    # ------------------------------------------------------------------
    # 6. Remove via pill close button
    # ------------------------------------------------------------------

    def test_remove_via_close_button_updates_selections(
        self, bucket: BucketWidget, qtbot
    ) -> None:
        """Clicking a pill's close button removes it from selections."""
        line_edit = bucket.findChild(QLineEdit)
        assert line_edit is not None

        line_edit.setText("IsFemale")
        qtbot.keyPress(line_edit, Qt.Key.Key_Return)
        assert "IsFemale" in bucket.selections

        pills = bucket.findChildren(PillWidget)
        assert pills, "Expected a PillWidget after add"
        close_btn = pills[0].findChild(QToolButton)
        assert close_btn is not None

        with qtbot.waitSignal(bucket.selections_changed, timeout=1000):
            close_btn.click()

        assert "IsFemale" not in bucket.selections

    def test_remove_deletes_pill_from_layout(
        self, bucket: BucketWidget, qtbot
    ) -> None:
        """After removal the PillWidget is scheduled for deletion."""
        line_edit = bucket.findChild(QLineEdit)
        assert line_edit is not None

        line_edit.setText("IsFemale")
        qtbot.keyPress(line_edit, Qt.Key.Key_Return)

        pills = bucket.findChildren(PillWidget)
        close_btn = pills[0].findChild(QToolButton)
        close_btn.click()

        # Process deferred deletions
        qtbot.waitSignal(bucket.selections_changed, timeout=100,
                         raising=False)
        # After deletion selections should be empty
        assert bucket.selections == set()

    # ------------------------------------------------------------------
    # 7. clear() removes all pills and emits exactly once
    # ------------------------------------------------------------------

    def test_clear_empties_selections(
        self, bucket: BucketWidget, qtbot
    ) -> None:
        """``clear()`` empties selections."""
        line_edit = bucket.findChild(QLineEdit)
        assert line_edit is not None

        for name in ("IsFemale", "IsInCombat"):
            line_edit.setText(name)
            qtbot.keyPress(line_edit, Qt.Key.Key_Return)

        bucket.clear()
        assert bucket.selections == set()

    def test_clear_emits_selections_changed_once(
        self, bucket: BucketWidget, qtbot
    ) -> None:
        """``clear()`` emits ``selections_changed`` exactly once."""
        line_edit = bucket.findChild(QLineEdit)
        assert line_edit is not None

        for name in ("IsFemale", "IsInCombat"):
            line_edit.setText(name)
            qtbot.keyPress(line_edit, Qt.Key.Key_Return)

        # Reset counter after the two adds
        signal_count: list[int] = [0]
        bucket.selections_changed.connect(
            lambda: signal_count.__setitem__(0, signal_count[0] + 1)
        )

        bucket.clear()

        assert signal_count[0] == 1, (
            f"Expected 1 emission from clear(), got {signal_count[0]}"
        )

    # ------------------------------------------------------------------
    # 8. set_selections() replaces all and emits once
    # ------------------------------------------------------------------

    def test_set_selections_replaces_all(
        self, bucket: BucketWidget, qtbot
    ) -> None:
        """``set_selections()`` replaces existing pills with the new set."""
        line_edit = bucket.findChild(QLineEdit)
        assert line_edit is not None

        line_edit.setText("IsFemale")
        qtbot.keyPress(line_edit, Qt.Key.Key_Return)

        bucket.set_selections({"IsInCombat", "HasMagicEffect"})

        assert bucket.selections == {"IsInCombat", "HasMagicEffect"}

    def test_set_selections_emits_once(
        self, bucket: BucketWidget, qtbot
    ) -> None:
        """``set_selections()`` emits ``selections_changed`` exactly once."""
        line_edit = bucket.findChild(QLineEdit)
        assert line_edit is not None

        line_edit.setText("IsFemale")
        qtbot.keyPress(line_edit, Qt.Key.Key_Return)

        signal_count: list[int] = [0]
        bucket.selections_changed.connect(
            lambda: signal_count.__setitem__(0, signal_count[0] + 1)
        )

        bucket.set_selections({"IsInCombat", "HasMagicEffect"})

        assert signal_count[0] == 1, (
            f"Expected 1 emission from set_selections(), got {signal_count[0]}"
        )

    # ------------------------------------------------------------------
    # 9. selections returns a copy
    # ------------------------------------------------------------------

    def test_selections_returns_copy(
        self, bucket: BucketWidget, qtbot
    ) -> None:
        """Mutating the returned set does not affect internal state."""
        line_edit = bucket.findChild(QLineEdit)
        assert line_edit is not None

        line_edit.setText("IsFemale")
        qtbot.keyPress(line_edit, Qt.Key.Key_Return)

        copy = bucket.selections
        copy.add("ShouldNotAppear")
        copy.discard("IsFemale")

        assert bucket.selections == {"IsFemale"}, (
            "Internal selections should not be affected by external mutation"
        )

    # ------------------------------------------------------------------
    # 10. set_known_conditions() updates the completer model
    # ------------------------------------------------------------------

    def test_set_known_conditions_updates_completer(
        self, bucket: BucketWidget
    ) -> None:
        """``set_known_conditions()`` replaces the completer's string list."""
        new_conditions = ["NewConditionA", "NewConditionB"]
        bucket.set_known_conditions(new_conditions)

        completer = bucket._completer  # access internal for verification
        model = completer.model()
        # QStringListModel exposes stringList()
        assert model.stringList() == new_conditions

    # ------------------------------------------------------------------
    # Bonus: Add via QPushButton click
    # ------------------------------------------------------------------

    def test_add_via_button_click(
        self, bucket: BucketWidget, qtbot
    ) -> None:
        """Clicking the Add button adds a pill just like pressing Enter."""
        line_edit = bucket.findChild(QLineEdit)
        assert line_edit is not None
        add_btn = bucket.findChild(QPushButton)
        assert add_btn is not None, "No QPushButton child found"

        line_edit.setText("IsFemale")
        with qtbot.waitSignal(bucket.selections_changed, timeout=1000):
            add_btn.click()

        assert bucket.selections == {"IsFemale"}
