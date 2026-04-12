"""Unified search bar — name search + condition filter mode.

See spec §7.2. Tier 2: condition filter mode (AND/OR/NOT), autocomplete.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget


class SearchBar(QWidget):
    """Top-bar search input with Advanced button and Refresh button."""

    search_changed = Signal(str)
    refresh_requested = Signal()
    advanced_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Search mods, submods, animations...")
        self._input.textChanged.connect(self.search_changed.emit)
        layout.addWidget(self._input, stretch=1)

        self._advanced_btn = QPushButton("Advanced...")
        self._advanced_btn.clicked.connect(self.advanced_requested.emit)
        layout.addWidget(self._advanced_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(self._refresh_btn)

    def focus_search(self) -> None:
        """Focus the search input and select all text."""
        self._input.setFocus()
        self._input.selectAll()
