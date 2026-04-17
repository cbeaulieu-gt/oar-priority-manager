"""Labeled pill-bucket container for the Advanced Filter Builder.

A ``BucketWidget`` groups one "bucket" of condition-type pills under a
header label (e.g. "Required", "Any Of", "Excluded").  Pills are added
through an autocomplete ``QLineEdit`` and can be removed via each pill's
close button.

Public API
----------
BucketWidget
"""
from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QStringListModel, Qt, Signal
from PySide6.QtWidgets import (
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .filter_pill import PillWidget


class BucketWidget(QWidget):
    """Labeled pill-list with an input field and ``QCompleter``.

    Displays a header *label* above a scrollable row of ``PillWidget``
    instances and a line-edit + Add-button below for adding new entries.
    The widget owns an internal ``set[str]`` of selected condition names;
    consumers should read ``selections`` and react to ``selections_changed``.

    Signals:
        selections_changed: Emitted (with no arguments) after any add,
            remove, ``clear()``, or ``set_selections()`` call that modifies
            the internal state.

    Attributes:
        _selections: Internal set of selected condition-type names.
        _pill_row: Widget holding the horizontal pill layout.
        _pill_layout: ``QHBoxLayout`` that contains the pills.
        _line_edit: ``QLineEdit`` for entering new condition names.
        _add_btn: ``QPushButton`` that triggers an add.
        _completer: ``QCompleter`` attached to ``_line_edit``.
        _completer_model: ``QStringListModel`` backing ``_completer``.

    Example::

        bucket = BucketWidget("Required", ["IsFemale", "IsInCombat"])
        bucket.selections_changed.connect(on_change)
    """

    selections_changed = Signal()

    def __init__(
        self,
        label: str,
        known_conditions: list[str],
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the bucket.

        Args:
            label: Header text shown above the pill row
                (e.g. ``"Required"``).
            known_conditions: Initial list of condition-type names offered
                by the autocomplete completer.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._selections: set[str] = set()
        self._build_ui(label, known_conditions)

    # ------------------------------------------------------------------
    # Internal – UI construction
    # ------------------------------------------------------------------

    def _build_ui(self, label: str, known_conditions: list[str]) -> None:
        """Construct child widgets and layouts.

        Args:
            label: Header text for the bucket.
            known_conditions: Autocomplete source list.
        """
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # --- Header label -------------------------------------------
        header = QLabel(label)
        root.addWidget(header)

        # --- Pill row (scrollable) -----------------------------------
        self._pill_row = QWidget()
        self._pill_layout = QHBoxLayout(self._pill_row)
        self._pill_layout.setContentsMargins(0, 0, 0, 0)
        self._pill_layout.setSpacing(4)
        self._pill_layout.addStretch()  # keep pills left-aligned

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._pill_row)
        scroll.setFixedHeight(48)
        scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        root.addWidget(scroll)

        # --- Input row (line edit + Add button) ----------------------
        input_row = QHBoxLayout()
        input_row.setSpacing(4)

        self._line_edit = QLineEdit()
        self._line_edit.setPlaceholderText("Add condition…")
        self._line_edit.returnPressed.connect(self._on_submit)
        input_row.addWidget(self._line_edit)

        self._add_btn = QPushButton("Add")
        self._add_btn.clicked.connect(self._on_submit)
        input_row.addWidget(self._add_btn)

        root.addLayout(input_row)

        # --- Completer -----------------------------------------------
        self._completer_model = QStringListModel(known_conditions)
        self._completer = QCompleter(self._completer_model)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._line_edit.setCompleter(self._completer)

    # ------------------------------------------------------------------
    # Internal – event handlers
    # ------------------------------------------------------------------

    def _on_submit(self) -> None:
        """Handle Enter key or Add-button click.

        Reads the current text from ``_line_edit``.  If it is empty or
        only whitespace, or already present in ``_selections``, the call
        is a no-op.  Otherwise a new ``PillWidget`` is created, added to
        the pill row, and ``selections_changed`` is emitted once.
        """
        name = self._line_edit.text().strip()
        if not name:
            return
        if name in self._selections:
            return

        self._add_pill(name)
        self._line_edit.clear()
        self.selections_changed.emit()

    def _add_pill(self, name: str) -> None:
        """Create and insert a ``PillWidget`` for *name* (no signal).

        Args:
            name: The condition-type name to add.
        """
        self._selections.add(name)
        pill = PillWidget(name, parent=self._pill_row)
        pill.removed.connect(self._on_pill_removed)
        # Insert before the trailing stretch item
        count = self._pill_layout.count()
        self._pill_layout.insertWidget(count - 1, pill)

    def _on_pill_removed(self, name: str) -> None:
        """Handle ``PillWidget.removed`` — remove name and emit signal.

        Args:
            name: The condition-type name emitted by the pill.
        """
        self._selections.discard(name)

        # Find and schedule deletion of the pill with this name
        for pill in self._pill_row.findChildren(PillWidget):
            if pill.condition_name == name:
                self._pill_layout.removeWidget(pill)
                pill.deleteLater()
                break

        self.selections_changed.emit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def selections(self) -> set[str]:
        """Return a copy of the current selected condition-type names.

        Returns:
            A new ``set[str]`` — external mutation does not affect
            internal state.
        """
        return set(self._selections)

    def set_selections(self, values: Iterable[str]) -> None:
        """Replace all pills with *values* and emit ``selections_changed``.

        Clears all existing pills silently first, then adds each value in
        *values* without emitting per-add signals, and finally emits
        ``selections_changed`` exactly once.

        Args:
            values: The new collection of condition-type names.
        """
        # Clear existing pills without emitting
        self._clear_silent()

        for name in values:
            name = name.strip()
            if name and name not in self._selections:
                self._add_pill(name)

        self.selections_changed.emit()

    def clear(self) -> None:
        """Remove all pills and emit ``selections_changed`` once.

        If the bucket is already empty this still emits once (consistent
        with ``set_selections``).
        """
        self._clear_silent()
        self.selections_changed.emit()

    def set_known_conditions(self, known: list[str]) -> None:
        """Update the autocomplete source with a new list.

        Args:
            known: The replacement list of condition-type names for
                the completer.
        """
        self._completer_model.setStringList(known)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clear_silent(self) -> None:
        """Remove all pills and clear ``_selections`` without emitting."""
        self._selections.clear()
        for pill in list(self._pill_row.findChildren(PillWidget)):
            self._pill_layout.removeWidget(pill)
            pill.deleteLater()
