"""Advanced filter builder modal dialog for OAR Priority Manager.

Composes three :class:`~oar_priority_manager.ui.filter_bucket.BucketWidget`
instances (Required, Any Of, Excluded) and exposes the combined selection as
an :class:`~oar_priority_manager.core.filter_engine.AdvancedFilterQuery`.

Public API
----------
FilterBuilder
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QVBoxLayout,
    QWidget,
)

from ..core.filter_engine import AdvancedFilterQuery
from .filter_bucket import BucketWidget


class FilterBuilder(QDialog):
    """Three-bucket advanced filter dialog.

    Presents three :class:`BucketWidget` instances — Required, Any Of, and
    Excluded — and an Apply / Cancel / Clear button row.  The dialog emits
    :attr:`filter_applied` carrying an :class:`AdvancedFilterQuery` when the
    user clicks either **Apply** or **Clear**, then accepts.  **Cancel**
    silently rejects the dialog without emitting.

    Signals:
        filter_applied: Emitted with an :class:`AdvancedFilterQuery` when
            Apply or Clear is clicked.  Carries an empty query on Clear.

    Attributes:
        _required_bucket: ``BucketWidget`` for the Required bucket.
        _any_of_bucket: ``BucketWidget`` for the Any Of bucket.
        _excluded_bucket: ``BucketWidget`` for the Excluded bucket.
        _button_box: The ``QDialogButtonBox`` holding Apply/Cancel/Clear.
        _clear_btn: The ``QPushButton`` added with ``ResetRole``.

    Example::

        builder = FilterBuilder(
            known_conditions=["IsFemale", "IsInCombat"],
            initial_query=AdvancedFilterQuery(required={"IsFemale"}),
        )
        builder.filter_applied.connect(on_filter_applied)
        builder.exec()
    """

    filter_applied = Signal(object)  # carries AdvancedFilterQuery

    def __init__(
        self,
        known_conditions: list[str],
        initial_query: AdvancedFilterQuery | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the dialog and optionally pre-populate buckets.

        Initial population (when *initial_query* is provided) is performed
        before any signals are wired, so the ``filter_applied`` signal is
        never emitted during construction.

        Args:
            known_conditions: List of condition-type names offered by the
                autocomplete completers inside each bucket widget.
            initial_query: If provided, pre-populates the three bucket
                widgets from the query's ``required``, ``any_of``, and
                ``excluded`` sets.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Advanced Filter")

        self._build_ui(known_conditions)

        # Populate buckets BEFORE connecting any filter_applied signals so
        # that set_selections() calls during init cannot trigger the dialog-
        # level signal.
        if initial_query is not None:
            self._required_bucket.set_selections(initial_query.required)
            self._any_of_bucket.set_selections(initial_query.any_of)
            self._excluded_bucket.set_selections(initial_query.excluded)

        self._connect_signals()

    # ------------------------------------------------------------------
    # Internal – UI construction
    # ------------------------------------------------------------------

    def _build_ui(self, known_conditions: list[str]) -> None:
        """Construct child widgets and layouts.

        Args:
            known_conditions: Autocomplete source list passed to each bucket.
        """
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Three pill buckets
        self._required_bucket = BucketWidget("Required", known_conditions)
        self._any_of_bucket = BucketWidget("Any Of", known_conditions)
        self._excluded_bucket = BucketWidget("Excluded", known_conditions)

        root.addWidget(self._required_bucket)
        root.addWidget(self._any_of_bucket)
        root.addWidget(self._excluded_bucket)

        # Button box: Apply + Cancel as standard buttons; Clear via addButton
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._clear_btn = self._button_box.addButton(
            "Clear", QDialogButtonBox.ButtonRole.ResetRole
        )

        root.addWidget(self._button_box)

    # ------------------------------------------------------------------
    # Internal – signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        """Wire button-box signals to private slots.

        ``button_box.accepted`` is deliberately NOT connected — we only want
        Apply to emit the signal, not the default OK-equivalent path.
        """
        self._button_box.rejected.connect(self.reject)
        self._button_box.button(
            QDialogButtonBox.StandardButton.Apply
        ).clicked.connect(self._on_apply)
        self._clear_btn.clicked.connect(self._on_clear)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def current_query(self) -> AdvancedFilterQuery:
        """Build an :class:`AdvancedFilterQuery` from current bucket selections.

        Returns:
            An :class:`AdvancedFilterQuery` whose ``required``, ``any_of``,
            and ``excluded`` sets mirror the current contents of the three
            bucket widgets.
        """
        return AdvancedFilterQuery(
            required=set(self._required_bucket.selections),
            any_of=set(self._any_of_bucket.selections),
            excluded=set(self._excluded_bucket.selections),
        )

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _on_apply(self) -> None:
        """Emit ``filter_applied`` with the current query and accept.

        Connected to the Apply button's ``clicked`` signal.
        """
        self.filter_applied.emit(self.current_query())
        self.accept()

    def _on_clear(self) -> None:
        """Clear all buckets, emit an empty query, and accept.

        Connected to the Clear button's ``clicked`` signal.  Always emits
        an empty :class:`AdvancedFilterQuery` regardless of prior state.
        """
        self._required_bucket.clear()
        self._any_of_bucket.clear()
        self._excluded_bucket.clear()
        self.filter_applied.emit(AdvancedFilterQuery())
        self.accept()
