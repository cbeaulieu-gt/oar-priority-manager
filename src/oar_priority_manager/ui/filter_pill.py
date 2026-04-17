"""Reusable condition-name chip widget for the Advanced Filter Builder.

A ``PillWidget`` displays a single condition-type name alongside a close
button.  It is the basic building block used inside ``BucketWidget`` (Task 4)
and ultimately inside the ``FilterBuilder`` dialog (Task 5).

Public API
----------
PillWidget
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QToolButton,
    QWidget,
)


class PillWidget(QWidget):
    """Condition-name chip with a close button.

    Displays *condition_name* as a label with a ``×`` close button to its
    right.  When the close button is clicked the ``removed`` signal is
    emitted with the condition name as its payload; the widget itself is
    **not** hidden or deleted — the parent bucket is responsible for
    removing it from the layout.

    The widget is styled with a light rounded background that uses palette
    roles so it adapts to both light and dark themes.

    Signals:
        removed: Emitted with the condition name when the close button is
            clicked.

    Example::

        pill = PillWidget("IsFemale")
        pill.removed.connect(lambda name: print(f"Remove {name}"))
    """

    removed = Signal(str)

    def __init__(
        self,
        condition_name: str,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the pill.

        Args:
            condition_name: The condition-type name displayed on the chip
                (e.g. ``"IsFemale"``).  Immutable after construction.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._condition_name = condition_name

        self._build_ui()
        self._apply_style()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construct child widgets and layout."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._label = QLabel(self._condition_name)
        layout.addWidget(self._label)

        self._close_btn = QToolButton()
        self._close_btn.setText("\u00d7")  # multiplication sign ×
        self._close_btn.setAutoRaise(True)
        self._close_btn.setToolTip("Remove")
        self._close_btn.clicked.connect(self._on_close_clicked)
        layout.addWidget(self._close_btn)

    def _apply_style(self) -> None:
        """Apply a minimal rounded-border stylesheet to the container."""
        self.setStyleSheet(
            "PillWidget {"
            "  border: 1px solid palette(mid);"
            "  border-radius: 8px;"
            "  padding: 2px 6px;"
            "  background: palette(button);"
            "}"
        )

    def _on_close_clicked(self) -> None:
        """Emit ``removed`` with the condition name when the button fires."""
        self.removed.emit(self._condition_name)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def condition_name(self) -> str:
        """Return the immutable condition-type name for this pill.

        Returns:
            The condition name supplied at construction time.
        """
        return self._condition_name
