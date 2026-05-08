"""Tests for core/scan_worker.py — QThread-backed scan pipeline worker.

Covers AC #6:
- Happy-path completion: worker runs, emits progress_updated (≥1 emission),
  emits finished with a valid ScanResult-shaped payload.
- Exception propagation: scan_mods raises → failed fires, finished does NOT.
- Cancellation: requestInterruption() → cancelled fires, finished does NOT.

Uses pytest-qt's qtbot.waitSignal / waitSignals for async signal assertion.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QCoreApplication, QThread

from oar_priority_manager.core.scan_worker import ScanWorker

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp():
    """Ensure a QCoreApplication exists for QThread-based tests.

    A QCoreApplication (no GUI) is sufficient for signal/slot testing.
    """
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


@pytest.fixture()
def tmp_instance(tmp_path: Path) -> Path:
    """Provide a minimal MO2 instance root with empty mods/ and overwrite/."""
    (tmp_path / "mods").mkdir()
    (tmp_path / "overwrite").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# Happy-path completion tests
# ---------------------------------------------------------------------------


class TestScanWorkerHappyPath:
    """ScanWorker runs to completion, emitting expected signals."""

    def test_finished_emits_with_scan_result(self, qapp, qtbot, tmp_instance):
        """Worker emits finished(result) with a 3-tuple payload on success.

        The payload is (submods, conflict_map, stacks) — the ScanResult
        returned by run_scan. An empty instance produces empty containers.
        """
        worker = ScanWorker(instance_root=tmp_instance)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        with qtbot.waitSignal(worker.finished, timeout=10_000) as blocker:
            thread.start()

        thread.quit()
        thread.wait()

        result = blocker.args[0]
        submods, conflict_map, stacks = result
        assert isinstance(submods, list)
        assert isinstance(conflict_map, dict)
        assert isinstance(stacks, list)

    def test_failed_does_not_emit_on_success(self, qapp, qtbot, tmp_instance):
        """Worker does NOT emit failed when scan completes successfully."""
        worker = ScanWorker(instance_root=tmp_instance)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        with (
            qtbot.waitSignal(worker.finished, timeout=10_000),
            qtbot.assertNotEmitted(worker.failed),
        ):
            thread.start()

        thread.quit()
        thread.wait()

    def test_progress_updated_emits_at_least_once(
        self, qapp, qtbot, tmp_instance
    ):
        """Worker emits ≥1 progress_updated signal during a scan.

        Even with zero submods, stage-transition progress events fire.
        We patch scan_mods to call on_progress at least once so the
        per-submod callback fires in addition to stage-boundary events.
        """
        from oar_priority_manager.core.models import OverrideSource, SubMod

        # Create one minimal submod so on_progress fires at least once.
        fake_submod = SubMod(
            mo2_mod="FakeMod",
            replacer="FakeReplacer",
            name="FakeSub",
            description="",
            priority=100,
            source_priority=100,
            disabled=False,
            config_path=tmp_instance / "mods" / "FakeMod" / "config.json",
            override_source=OverrideSource.SOURCE,
            override_is_ours=False,
            raw_dict={},
            conditions={},
        )

        progress_emissions: list[tuple] = []

        worker = ScanWorker(instance_root=tmp_instance)
        worker.progress_updated.connect(
            lambda stage, cur, total, label: progress_emissions.append(
                (stage, cur, total, label)
            )
        )

        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        def fake_scan_mods(mods_dir, overwrite_dir, on_progress=None):
            if on_progress is not None:
                on_progress(1, 1, "FakeSub")
            return [fake_submod]

        with (
            patch(
                "oar_priority_manager.core.scan_worker.scan_mods",
                side_effect=fake_scan_mods,
            ),
            qtbot.waitSignal(worker.finished, timeout=10_000),
        ):
            thread.start()

        thread.quit()
        thread.wait()

        assert len(progress_emissions) >= 1, (
            f"Expected ≥1 progress_updated emissions, got {progress_emissions}"
        )


# ---------------------------------------------------------------------------
# Exception propagation tests
# ---------------------------------------------------------------------------


class TestScanWorkerFailure:
    """ScanWorker emits failed and suppresses finished when an error occurs."""

    def test_failed_emits_on_scan_error(self, qapp, qtbot, tmp_instance):
        """Worker emits failed(exc) when scan_mods raises an exception."""
        boom = RuntimeError("synthetic scan failure")

        worker = ScanWorker(instance_root=tmp_instance)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        with (
            patch(
                "oar_priority_manager.core.scan_worker.scan_mods",
                side_effect=boom,
            ),
            qtbot.waitSignal(worker.failed, timeout=10_000) as blocker,
            qtbot.assertNotEmitted(worker.finished),
        ):
            thread.start()

        thread.quit()
        thread.wait()

        caught_exc = blocker.args[0]
        assert isinstance(caught_exc, RuntimeError)
        assert str(caught_exc) == "synthetic scan failure"

    def test_finished_does_not_emit_on_error(self, qapp, qtbot, tmp_instance):
        """Finished signal is NOT emitted when scan_mods raises."""
        worker = ScanWorker(instance_root=tmp_instance)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        with (
            patch(
                "oar_priority_manager.core.scan_worker.scan_mods",
                side_effect=ValueError("bad path"),
            ),
            qtbot.waitSignal(worker.failed, timeout=10_000),
            qtbot.assertNotEmitted(worker.finished),
        ):
            thread.start()

        thread.quit()
        thread.wait()


# ---------------------------------------------------------------------------
# Cancellation tests
# ---------------------------------------------------------------------------


class TestScanWorkerCancellation:
    """ScanWorker responds to requestInterruption() cleanly."""

    def test_cancelled_emits_when_interrupted(
        self, qapp, qtbot, tmp_instance
    ):
        """Calling QThread.requestInterruption() causes cancelled to emit.

        We request interruption from *within* the fake scan_mods body so
        there is no race between the ``started`` slot order.  The fake calls
        ``on_progress`` once (which checks for interruption after the flag
        is already set), causing ``_Cancelled`` to be raised and the worker
        to emit ``cancelled``.
        """
        worker = ScanWorker(instance_root=tmp_instance)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        def interruptible_scan_mods(mods_dir, overwrite_dir, on_progress=None):
            # Request interruption here — we are already on the worker thread.
            QThread.currentThread().requestInterruption()
            # The on_progress callback will detect the flag and raise _Cancelled.
            if on_progress is not None:
                on_progress(1, 1, "FakeSub")
            return []

        with (
            patch(
                "oar_priority_manager.core.scan_worker.scan_mods",
                side_effect=interruptible_scan_mods,
            ),
            qtbot.waitSignal(worker.cancelled, timeout=10_000),
            qtbot.assertNotEmitted(worker.finished),
        ):
            thread.start()

        thread.quit()
        thread.wait()

    def test_finished_does_not_emit_on_cancel(
        self, qapp, qtbot, tmp_instance
    ):
        """Finished is NOT emitted when the worker is cancelled."""
        worker = ScanWorker(instance_root=tmp_instance)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        def self_interrupting_scan(mods_dir, overwrite_dir, on_progress=None):
            # Request interruption from within the worker thread.
            QThread.currentThread().requestInterruption()
            if on_progress is not None:
                on_progress(1, 5, "FakeSub")
            return []

        with (
            patch(
                "oar_priority_manager.core.scan_worker.scan_mods",
                side_effect=self_interrupting_scan,
            ),
            qtbot.waitSignal(worker.cancelled, timeout=10_000),
            qtbot.assertNotEmitted(worker.finished),
        ):
            thread.start()

        thread.quit()
        thread.wait()
