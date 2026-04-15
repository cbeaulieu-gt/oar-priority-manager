"""Unified search bar — name search + condition filter mode.

See spec §7.2. Tier 2: condition filter mode (AND/OR/NOT), autocomplete.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget


class SearchBar(QWidget):
    """Top-bar search input with Advanced button, Hide toggle, and Refresh button."""

    search_changed = Signal(str)
    refresh_requested = Signal()
    advanced_requested = Signal()
    # Emitted when the hide/dim mode changes. True = hide mode, False = dim mode.
    filter_mode_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Search mods, submods, animations...")
        self._input.textChanged.connect(self.search_changed.emit)
        layout.addWidget(self._input, stretch=1)

        # Hide/Dim toggle: unchecked = dim (default), checked = hide
        self._hide_btn = QPushButton("Hide")
        self._hide_btn.setCheckable(True)
        self._hide_btn.setChecked(False)
        self._hide_btn.setToolTip(
            "When checked, non-matching items are hidden entirely.\n"
            "When unchecked, non-matching items are dimmed (default)."
        )
        self._hide_btn.clicked.connect(self._on_filter_mode_changed)
        layout.addWidget(self._hide_btn)

        self._advanced_btn = QPushButton("Advanced...")
        self._advanced_btn.clicked.connect(self.advanced_requested.emit)
        layout.addWidget(self._advanced_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(self._refresh_btn)

    def _on_filter_mode_changed(self) -> None:
        """Handle the Hide toggle being clicked.

        Emits both ``filter_mode_changed`` (so the window can update state)
        and ``search_changed`` (so the active filter re-applies immediately
        with the new mode).
        """
        hide_mode = self._hide_btn.isChecked()
        self.filter_mode_changed.emit(hide_mode)
        # Re-emit the current query so the filter re-applies in the new mode.
        self.search_changed.emit(self._input.text())

    @property
    def hide_mode(self) -> bool:
        """Return True when the Hide button is currently checked."""
        return self._hide_btn.isChecked()

    def focus_search(self) -> None:
        """Focus the search input and select all text."""
        self._input.setFocus()
        self._input.selectAll()
