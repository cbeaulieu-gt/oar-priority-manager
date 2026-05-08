"""Splash-style modal progress dialog for the OAR scan pipeline.

Displays overall scan progress with per-stage weighting, a per-item label
showing the current submod name, and a cancel button.  Used in two modes:

- ``"startup"`` — ``ApplicationModal``, no parent; shown during initial
  startup scan before the main window exists.
- ``"refresh"`` — ``WindowModal`` with a ``MainWindow`` parent; shown during
  a user-triggered re-scan.  Blocks input to the parent window only, so
  other applications remain responsive.

The dialog is UI-agnostic: it reads worker signals and emits
``cancellation_requested`` for the caller to wire to
``QThread.requestInterruption()``.  It does not call into the scan pipeline
directly.

See issue #96 and docs/scan-worker.md for design rationale.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Stage weighting constants
# ---------------------------------------------------------------------------

# Maps stage name → (start_pct, weight_pct).
# The five weights must sum to 100.
_STAGE_WEIGHTS: dict[str, tuple[int, int]] = {
    "detect":            (0,  5),
    "scan_mods":         (5,  55),
    "scan_animations":   (60, 30),
    "build_conflict_map": (90, 5),
    "build_stacks":      (95, 5),
}

# Human-readable label shown in the stage label widget.
_STAGE_LABELS: dict[str, str] = {
    "detect":            "Detecting instance…",
    "scan_mods":         "Scanning mods…",
    "scan_animations":   "Scanning animations…",
    "build_conflict_map": "Building conflict map…",
    "build_stacks":      "Resolving priorities…",
}


class ScanProgressDialog(QDialog):
    """Splash-style modal dialog showing scan pipeline progress.

    Attributes:
        mode: Either ``"startup"`` or ``"refresh"``.  Controls window
            modality and flags.
    """

    cancellation_requested: Signal = Signal()
    """Emitted when the user clicks the Cancel button.

    The caller should wire this to ``thread.requestInterruption()`` so the
    worker stops cleanly after the current submod finishes.
    """

    def __init__(
        self, mode: str, parent: QWidget | None = None
    ) -> None:
        """Initialise the dialog.

        Args:
            mode: ``"startup"`` or ``"refresh"``.  Determines window
                modality and chrome style.
            parent: Optional parent widget.  Should be the ``MainWindow``
                instance when ``mode="refresh"``; ``None`` for startup.
        """
        super().__init__(parent)
        self.mode = mode
        self._setup_window_flags()
        self._build_layout()

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _setup_window_flags(self) -> None:
        """Apply window flags and modality based on the dialog mode.

        Startup: ApplicationModal (no parent); uses SplashScreen-style
            frameless chrome so it appears before any window is shown.
        Refresh: WindowModal with parent; uses minimal title-bar chrome
            so the user can still see which window is blocked.
        """
        if self.mode == "startup":
            self.setWindowFlags(
                Qt.WindowType.Dialog
                | Qt.WindowType.FramelessWindowHint
            )
            self.setWindowModality(Qt.WindowModality.ApplicationModal)
        else:
            self.setWindowFlags(
                Qt.WindowType.Dialog
                | Qt.WindowType.WindowTitleHint
                | Qt.WindowType.CustomizeWindowHint
            )
            self.setWindowModality(Qt.WindowModality.WindowModal)

        self.setWindowTitle("OAR Priority Manager — Scanning")
        self.setMinimumWidth(420)

    def _build_layout(self) -> None:
        """Construct all child widgets and the layout.

        Layout (top to bottom):
            1. Title label
            2. Stage label (current pipeline stage)
            3. Overall progress bar (0–100)
            4. Per-item label (current submod name, elided)
            5. Cancel button (right-aligned)
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        # Title
        title = QLabel("OAR Priority Manager — Scanning")
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        # Stage label
        self._stage_label = QLabel("Initialising…")
        layout.addWidget(self._stage_label)

        # Overall progress bar
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        layout.addWidget(self._bar)

        # Per-item label (elided with Qt.ElideMiddle via stylesheet is not
        # directly available on QLabel, so we truncate manually in the slot).
        self._item_label = QLabel("")
        self._item_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self._item_label)

        # Cancel button (right-aligned)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        btn_row.addWidget(self._cancel_btn)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _elide_middle(self, text: str, max_chars: int = 55) -> str:
        """Truncate ``text`` to ``max_chars`` using middle-elision.

        Args:
            text: The string to shorten.
            max_chars: Maximum character count before elision is applied.

        Returns:
            The original string if short enough, otherwise a version
            with ``…`` inserted in the middle.
        """
        if len(text) <= max_chars:
            return text
        half = (max_chars - 1) // 2
        return text[:half] + "…" + text[-(max_chars - half - 1):]

    def _compute_overall(
        self, stage: str, current: int, total: int
    ) -> int:
        """Compute the overall progress percentage for a stage update.

        Args:
            stage: One of the ``_STAGE_WEIGHTS`` keys.
            current: Items processed so far in this stage.
            total: Total items in this stage (0 means indeterminate).

        Returns:
            Integer percentage 0–100 for the overall bar.
        """
        if stage not in _STAGE_WEIGHTS:
            return self._bar.value()

        start_pct, weight = _STAGE_WEIGHTS[stage]
        within = weight * current / total if total > 0 else 0.0
        return round(start_pct + within)

    # ------------------------------------------------------------------
    # Slots wired to ScanWorker signals
    # ------------------------------------------------------------------

    def on_progress(
        self, stage: str, current: int, total: int, label: str
    ) -> None:
        """Update bar value, stage label, and per-item label.

        Designed to be connected directly to ``ScanWorker.progress_updated``.

        Args:
            stage: Pipeline stage name (one of the ``_STAGES`` constants).
            current: Items processed so far in this stage.
            total: Total items expected in this stage (0 if unknown).
            label: Submod display name or empty string for stage boundaries.
        """
        stage_text = _STAGE_LABELS.get(stage, stage)
        self._stage_label.setText(stage_text)

        overall = self._compute_overall(stage, current, total)
        self._bar.setValue(overall)

        if label:
            self._item_label.setText(self._elide_middle(label))
        else:
            self._item_label.setText("")

    def on_finished(self, result: Any) -> None:
        """Handle scan completion — show a brief "done" state then dismiss.

        The dialog shows the final 100% state for ~1 second before calling
        ``accept()`` so the user can see the scan completed before the UI
        updates.

        Designed to be connected to ``ScanWorker.finished``.

        Args:
            result: The ``(submods, conflict_map, stacks)`` tuple from the
                worker.  Used to display a count in the stage label.
        """
        submods = result[0] if isinstance(result, tuple) and result else []
        n = len(submods) if isinstance(submods, list) else 0

        self._bar.setValue(100)
        self._stage_label.setText(f"Done — {n} mods loaded")
        self._item_label.setText("")
        self._cancel_btn.setEnabled(False)

        QTimer.singleShot(1000, self.accept)

    def on_failed(self, exc: Exception) -> None:  # noqa: ARG002
        """Close the dialog immediately when the scan fails.

        Does not display the error — that is the caller's responsibility
        (e.g. a QMessageBox after the dialog closes).

        Designed to be connected to ``ScanWorker.failed``.

        Args:
            exc: The exception captured by the worker.  Not displayed here;
                the caller handles error presentation.
        """
        self.reject()

    def on_cancelled(self) -> None:
        """Close the dialog immediately when the scan is cancelled.

        Called after the worker emits ``cancelled``.  The dialog dismisses
        without a timer because cancellation is synchronous from the user's
        perspective.

        Designed to be connected to ``ScanWorker.cancelled``.
        """
        self.reject()

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_cancel_clicked(self) -> None:
        """Emit ``cancellation_requested`` when the Cancel button is clicked.

        The dialog does NOT close itself here.  It waits for the worker to
        emit ``cancelled`` (via ``on_cancelled``), which then calls
        ``reject()``.  This keeps the user informed that cancellation is
        in progress rather than appearing to hang.
        """
        self._cancel_btn.setEnabled(False)
        self._stage_label.setText("Cancelling…")
        self.cancellation_requested.emit()
