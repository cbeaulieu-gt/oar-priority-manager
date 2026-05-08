"""Tests for ui/scan_progress_dialog.py — splash-style scan progress dialog.

Covers AC from issue #96:
- Progress signal updates bar value and labels correctly.
- Stage weighting maps scan_mods at 50% to overall ~32.5%.
- finished() auto-dismisses the dialog after ~1 s via QTimer.
- failed() closes the dialog immediately (no timer).
- cancelled() closes the dialog immediately.
- Cancel button click emits cancellation_requested signal.
"""

from __future__ import annotations

import os

import pytest
from PySide6.QtWidgets import QApplication

from oar_priority_manager.ui.scan_progress_dialog import ScanProgressDialog

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp_session():
    """Session-scoped QApplication for dialog tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# Progress signal updates
# ---------------------------------------------------------------------------


class TestProgressUpdates:
    """on_progress() updates the bar value and labels."""

    def test_progress_updates_bar(self, qapp_session, qtbot):
        """Emitting on_progress updates the overall bar and per-item label.

        Calls on_progress for the scan_mods stage and asserts that the
        progress bar value and per-item label text are updated.
        """
        dialog = ScanProgressDialog(mode="refresh")
        qtbot.addWidget(dialog)

        dialog.on_progress("scan_mods", 10, 100, "SomeSubMod")

        assert dialog._bar.value() > 0
        assert "SomeSubMod" in dialog._item_label.text()

    def test_stage_label_updates_on_progress(self, qapp_session, qtbot):
        """Emitting on_progress with a known stage updates the stage label."""
        dialog = ScanProgressDialog(mode="refresh")
        qtbot.addWidget(dialog)

        dialog.on_progress("detect", 0, 0, "")

        assert "Detect" in dialog._stage_label.text() or \
            dialog._stage_label.text() != ""

    def test_stage_weighting(self, qapp_session, qtbot):
        """scan_mods at 50% yields overall value near 32 (5 + 55*0.5 = 32.5).

        Stage weights: detect=5, scan_mods=55, scan_animations=30,
        build_conflict_map=5, build_stacks=5.
        start offset for scan_mods = 5%.
        overall = 5 + 55 * (50/100) = 32.5 → bar value 32 or 33.
        """
        dialog = ScanProgressDialog(mode="refresh")
        qtbot.addWidget(dialog)

        dialog.on_progress("scan_mods", 50, 100, "SomeMod")

        bar_val = dialog._bar.value()
        assert 32 <= bar_val <= 33, (
            f"Expected bar value ~32-33 for scan_mods 50%, got {bar_val}"
        )


# ---------------------------------------------------------------------------
# finished() auto-dismiss
# ---------------------------------------------------------------------------


class TestFinishedAutoDismiss:
    """on_finished() causes the dialog to close after ~1 second."""

    def test_finished_auto_dismisses(self, qapp_session, qtbot):
        """Dialog closes within 1.5 s after on_finished() is called.

        The dialog uses QTimer.singleShot(1000, self.accept) internally,
        so we allow 1.5 s total (1 s timer + 500 ms slack).
        """
        dialog = ScanProgressDialog(mode="refresh")
        qtbot.addWidget(dialog)
        dialog.show()

        # on_finished receives the scan result tuple
        fake_result = ([], {}, [])
        with qtbot.waitSignal(dialog.finished, timeout=1500):
            dialog.on_finished(fake_result)


# ---------------------------------------------------------------------------
# failed() closes immediately
# ---------------------------------------------------------------------------


class TestFailedClosesImmediately:
    """on_failed() closes the dialog without a timer."""

    def test_failed_closes_immediately(self, qapp_session, qtbot):
        """Dialog closes within 200 ms after on_failed() is called.

        No QTimer is involved — the dialog hides immediately so the caller
        can show an error dialog in its place.
        """
        dialog = ScanProgressDialog(mode="refresh")
        qtbot.addWidget(dialog)
        dialog.show()

        exc = RuntimeError("scan failed")
        with qtbot.waitSignal(dialog.finished, timeout=200):
            dialog.on_failed(exc)


# ---------------------------------------------------------------------------
# cancelled() closes immediately
# ---------------------------------------------------------------------------


class TestCancelledClosesImmediately:
    """on_cancelled() closes the dialog without a timer."""

    def test_cancelled_closes_immediately(self, qapp_session, qtbot):
        """Dialog closes within 200 ms after on_cancelled() is called.

        No QTimer — cancelled is a user-initiated action, so the dialog
        dismisses synchronously rather than briefly showing a "done" state.
        """
        dialog = ScanProgressDialog(mode="refresh")
        qtbot.addWidget(dialog)
        dialog.show()

        with qtbot.waitSignal(dialog.finished, timeout=200):
            dialog.on_cancelled()


# ---------------------------------------------------------------------------
# Cancel button emits cancellation_requested
# ---------------------------------------------------------------------------


class TestCancelButton:
    """Clicking the cancel button emits cancellation_requested."""

    def test_cancel_button_emits_cancellation_requested(
        self, qapp_session, qtbot
    ):
        """Clicking the cancel button fires the cancellation_requested signal.

        The caller wires this signal to QThread.requestInterruption() so the
        worker stops cleanly.  The dialog itself does not call requestInterruption
        directly — it stays UI-agnostic w.r.t. the scan pipeline.
        """
        dialog = ScanProgressDialog(mode="refresh")
        qtbot.addWidget(dialog)
        dialog.show()

        with qtbot.waitSignal(dialog.cancellation_requested, timeout=500):
            dialog._cancel_btn.click()


# ---------------------------------------------------------------------------
# Mode differences
# ---------------------------------------------------------------------------


class TestModeConstruction:
    """ScanProgressDialog constructs correctly for startup and refresh modes."""

    def test_startup_mode_constructs(self, qapp_session, qtbot):
        """ScanProgressDialog(mode='startup') constructs without error."""
        dialog = ScanProgressDialog(mode="startup")
        qtbot.addWidget(dialog)
        assert dialog is not None

    def test_refresh_mode_constructs(self, qapp_session, qtbot):
        """ScanProgressDialog(mode='refresh') constructs without error."""
        dialog = ScanProgressDialog(mode="refresh")
        qtbot.addWidget(dialog)
        assert dialog is not None
