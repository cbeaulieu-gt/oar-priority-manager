"""QThread-backed worker that runs the full scan pipeline off the GUI thread.

Architecture note: uses the QObject + moveToThread pattern rather than
subclassing QThread.  This keeps the worker composable (its signals are
ordinary QObject signals) and plays nicely with pytest-qt's qtbot helpers,
which assert signals directly against the worker object.

See docs/scan-worker.md for the full threading model and design rationale.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from oar_priority_manager.core.anim_scanner import build_conflict_map, scan_animations
from oar_priority_manager.core.filter_engine import extract_condition_types
from oar_priority_manager.core.priority_resolver import build_stacks
from oar_priority_manager.core.scanner import scan_mods
from oar_priority_manager.core.tag_engine import compute_tags

logger = logging.getLogger(__name__)

# Canonical stage names emitted with progress_updated.  The splash / progress
# UI consumes these string constants — keep them stable across releases.
_STAGES = (
    "detect",
    "scan_mods",
    "scan_animations",
    "build_conflict_map",
    "build_stacks",
)

# Type alias for the scan result 3-tuple returned by run_scan.
ScanResult = tuple[list, dict, list]


class _Cancelled(Exception):
    """Raised internally to unwind the scan pipeline on cancellation.

    Subclasses Exception so it is caught by the broad ``except Exception``
    guard in :py:meth:`ScanWorker.run`.  KeyboardInterrupt / SystemExit are
    NOT subclasses of Exception and therefore propagate normally.
    """


class ScanWorker(QObject):
    """Runs the OAR scan pipeline on a background QThread.

    Usage pattern::

        worker = ScanWorker(instance_root=path)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(on_done)
        worker.failed.connect(on_error)
        thread.start()

    To cancel a running scan call ``thread.requestInterruption()``.
    The worker checks for the interruption flag between submods (via the
    ``on_progress`` callback wired to :py:func:`scan_mods`) and between
    pipeline stages.  On cancellation ``cancelled`` is emitted and the
    thread returns cleanly with no partial result.

    Attributes:
        instance_root: Path to the MO2 instance root (contains mods/ and
            overwrite/ subdirectories).
    """

    # --- Signals -----------------------------------------------------------

    progress_updated: Signal = Signal(str, int, int, str)
    """Emitted at each pipeline stage boundary and per submod during scan_mods.

    Args:
        stage: One of the _STAGES constants (e.g. ``"scan_mods"``).
        current: Items processed so far in this stage.
        total: Total items expected in this stage (0 if unknown).
        label: Human-readable label for the current item (submod name or "").
    """

    finished: Signal = Signal(object)
    """Emitted on successful completion with the ScanResult 3-tuple.

    Args:
        result: ``(submods, conflict_map, stacks)`` — same shape as
            :py:func:`oar_priority_manager.app.main.run_scan`.
    """

    failed: Signal = Signal(object)
    """Emitted when an unexpected exception terminates the scan.

    Args:
        exception: The caught Exception instance.
    """

    cancelled: Signal = Signal()
    """Emitted when the scan is interrupted via QThread.requestInterruption()."""

    # -----------------------------------------------------------------------

    def __init__(
        self, instance_root: Path, parent: QObject | None = None
    ) -> None:
        """Initialize the worker.

        Args:
            instance_root: Path to the MO2 instance root.
            parent: Optional QObject parent.
        """
        super().__init__(parent)
        self.instance_root = instance_root

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_interruption(self) -> None:
        """Raise _Cancelled if the current thread has been interrupted.

        Args: (none)

        Raises:
            _Cancelled: If QThread.currentThread().isInterruptionRequested()
                returns True.
        """
        if QThread.currentThread().isInterruptionRequested():
            raise _Cancelled()

    def _make_progress_callback(self) -> Any:
        """Build the on_progress callable passed to scan_mods.

        The returned callable:
        1. Emits ``progress_updated`` with stage ``"scan_mods"``.
        2. Checks for a pending interruption after each submod; raises
           ``_Cancelled`` to unwind the pipeline when one is found.

        Returns:
            A callable accepting ``(current: int, total: int)`` that
            also receives the submod name via closure over the submods
            list.  Because ``scan_mods`` only provides ``(current, total)``
            the label is synthesised as ``f"submod {current}/{total}"``.
        """
        def on_progress(current: int, total: int) -> None:
            label = f"submod {current}/{total}"
            self.progress_updated.emit("scan_mods", current, total, label)
            self._check_interruption()

        return on_progress

    # ------------------------------------------------------------------
    # Main run slot
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Execute the full scan pipeline.

        This method is designed to be connected to ``QThread.started`` and
        runs entirely on the background thread.  It must not be called
        directly on the GUI thread.

        On completion  emits :py:attr:`finished`.
        On error       emits :py:attr:`failed`.
        On cancel      emits :py:attr:`cancelled`.

        Raises:
            (nothing — all exceptions are caught internally and forwarded
            via the ``failed`` signal, except _Cancelled which routes to
            ``cancelled``.)
        """
        try:
            result = self._run_pipeline()
        except _Cancelled:
            logger.debug("ScanWorker: scan cancelled by interruption request")
            self.cancelled.emit()
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("ScanWorker: scan failed with exception")
            self.failed.emit(exc)
            return

        self.finished.emit(result)

    def _run_pipeline(self) -> ScanResult:
        """Run all scan pipeline stages, emitting progress at each boundary.

        Checks for interruption at the top of each stage so cancellation
        has at most one-stage latency even when the scan_mods callback is
        not called (e.g. zero submods).

        Returns:
            A ``(submods, conflict_map, stacks)`` 3-tuple.

        Raises:
            _Cancelled: If QThread.currentThread().isInterruptionRequested()
                at any stage boundary or between submods.
            Exception: Any unhandled exception from the underlying scan
                functions propagates to the caller.
        """
        mods_dir = self.instance_root / "mods"
        overwrite_dir = self.instance_root / "overwrite"

        # Stage: detect
        self._check_interruption()
        self.progress_updated.emit("detect", 0, 0, "")

        # Stage: scan_mods
        self._check_interruption()
        self.progress_updated.emit("scan_mods", 0, 0, "")
        on_progress = self._make_progress_callback()
        submods = scan_mods(mods_dir, overwrite_dir, on_progress=on_progress)

        # Stage: scan_animations
        self._check_interruption()
        self.progress_updated.emit("scan_animations", 0, 0, "")
        scan_animations(submods)

        # Stage: build_conflict_map
        self._check_interruption()
        self.progress_updated.emit("build_conflict_map", 0, 0, "")
        conflict_map = build_conflict_map(submods)

        # Stage: build_stacks
        self._check_interruption()
        self.progress_updated.emit("build_stacks", 0, 0, "")
        stacks = build_stacks(conflict_map)

        # Post-processing: condition types and tags (no separate stage needed)
        self._check_interruption()
        for sm in submods:
            present, negated = extract_condition_types(sm.conditions)
            sm.condition_types_present = present
            sm.condition_types_negated = negated
            sm.tags = compute_tags(sm)

        logger.info(
            "ScanWorker: pipeline complete — %d submods, %d stacks",
            len(submods),
            len(stacks),
        )
        return submods, conflict_map, stacks
