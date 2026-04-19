"""Unified search bar — name search + condition filter mode.

See spec §7.2. Tier 2: condition filter mode (AND/OR/NOT), autocomplete.

When the user types AND/OR/NOT keywords (as whole words, case-insensitive)
or a ``condition:`` prefix, the bar switches automatically to condition
filter mode.  The ``condition_mode_changed`` signal notifies the main
window, which routes the query through ``parse_filter_query`` /
``match_filter`` instead of the regular ``SearchIndex``.
"""

from __future__ import annotations

import re
from enum import Enum, auto

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Whole-word regex that matches any of the boolean keywords
_KEYWORD_RE = re.compile(
    r"\b(AND|OR|NOT)\b",
    re.IGNORECASE,
)

_CONDITION_PREFIX = "condition:"

# Tooltip shown on the search input when condition mode is active
_CONDITION_MODE_TOOLTIP = (
    "Condition filter active — matches submods that have these "
    "condition types in their config.\n"
    "Use NOT <Type> to exclude a condition type.\n"
    "Example: IsFemale NOT HasPerk"
)


class SearchMode(Enum):
    """Tracks whether the search bar is in text or condition filter mode.

    Attributes:
        TEXT: Normal substring search using ``SearchIndex``.
        CONDITION: Condition-filter mode using ``parse_filter_query`` and
            ``match_filter`` from ``filter_engine``.
    """

    TEXT = auto()
    CONDITION = auto()


def detect_search_mode(text: str) -> SearchMode:
    """Determine whether *text* should activate condition filter mode.

    Condition mode is triggered when the text:

    * contains any of ``AND``, ``OR``, ``NOT`` as whole words
      (case-insensitive), **or**
    * starts with the prefix ``condition:`` (case-insensitive).

    This function is intentionally a module-level pure function so that
    it can be tested independently of the Qt widget.

    Args:
        text: The raw string currently in the search bar.

    Returns:
        :attr:`SearchMode.CONDITION` when a condition-mode trigger is
        detected; :attr:`SearchMode.TEXT` otherwise.
    """
    stripped = text.strip()
    if stripped.lower().startswith(_CONDITION_PREFIX):
        return SearchMode.CONDITION
    if _KEYWORD_RE.search(stripped):
        return SearchMode.CONDITION
    return SearchMode.TEXT


class SearchBar(QWidget):
    """Top-bar search input with condition-filter mode detection.

    Emits :attr:`search_changed` on every keystroke.  The main window
    reads :attr:`current_mode` to decide which search backend to use.

    Signals:
        search_changed: Emitted whenever the input text changes; carries
            the current text string.
        refresh_requested: Emitted when the Refresh button is clicked.
        advanced_requested: Emitted when the Advanced button is clicked.
        scan_issues_requested: Emitted when the Scan issues button is
            clicked. The button is only enabled when the issue count is
            greater than zero.
        filter_mode_changed: Emitted when the Hide/Dim toggle changes.
            Carries ``True`` when hide mode is active, ``False`` for dim.
        condition_mode_changed: Emitted when the search mode transitions
            between TEXT and CONDITION.  Carries the new
            :class:`SearchMode` value.
    """

    search_changed = Signal(str)
    refresh_requested = Signal()
    advanced_requested = Signal()
    scan_issues_requested = Signal()
    # Emitted when the hide/dim mode changes. True = hide mode, False = dim.
    filter_mode_changed = Signal(bool)
    # Emitted when the mode switches between TEXT and CONDITION.
    condition_mode_changed = Signal(object)  # carries SearchMode

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the search bar widget.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._mode: SearchMode = SearchMode.TEXT

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._input = QLineEdit()
        self._input.setPlaceholderText(
            "Search mods, submods, animations…  "
            "(use AND/OR/NOT or condition: for condition filter)"
        )
        # Object name + dynamic property drive the condition-mode border style
        # via QLineEdit#SearchBar_input[conditionMode="true"] in custom.qss.
        self._input.setObjectName("SearchBar_input")
        self._input.setProperty("conditionMode", "false")
        self._input.textChanged.connect(self._on_text_changed)
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

        self._scan_issues_btn = QPushButton("Scan issues (0)")
        self._scan_issues_btn.setObjectName("scan-issues-btn")
        self._scan_issues_btn.setToolTip(
            "Open the log pane listing parse and validation warnings"
            " found during scan."
        )
        self._scan_issues_btn.setEnabled(False)
        self._scan_issues_btn.clicked.connect(
            self.scan_issues_requested.emit
        )
        layout.addWidget(self._scan_issues_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(self._refresh_btn)

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_text_changed(self, text: str) -> None:
        """Handle keystroke in the search input.

        Detects mode switches, updates the visual indicator and tooltip,
        and forwards the text via :attr:`search_changed`.

        Args:
            text: Current content of the QLineEdit.
        """
        new_mode = detect_search_mode(text)
        if new_mode != self._mode:
            self._mode = new_mode
            self._apply_mode_style()
            self.condition_mode_changed.emit(new_mode)

        self.search_changed.emit(text)

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

    def _apply_mode_style(self) -> None:
        """Update QLineEdit style and tooltip to reflect the current mode.

        The visual indicator is driven by the ``conditionMode`` dynamic
        property on the input widget, which is targeted by
        ``QLineEdit#SearchBar_input[conditionMode="true"]`` in custom.qss.
        Qt requires an explicit unpolish/polish cycle after a dynamic
        property change for QSS attribute selectors to re-evaluate.
        """
        is_condition = self._mode == SearchMode.CONDITION
        self._input.setProperty(
            "conditionMode", "true" if is_condition else "false"
        )
        # Force Qt to re-evaluate the QSS property selector
        style = self._input.style()
        if style is not None:
            style.unpolish(self._input)
            style.polish(self._input)
        self._input.update()
        if is_condition:
            self._input.setToolTip(_CONDITION_MODE_TOOLTIP)
        else:
            self._input.setToolTip("")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def current_mode(self) -> SearchMode:
        """Return the current :class:`SearchMode`."""
        return self._mode

    @property
    def hide_mode(self) -> bool:
        """Return True when the Hide button is currently checked."""
        return self._hide_btn.isChecked()

    def focus_search(self) -> None:
        """Focus the search input and select all text."""
        self._input.setFocus()
        self._input.selectAll()

    def set_scan_issues_count(self, count: int) -> None:
        """Update the Scan issues button label and enabled state.

        Sets the button text to ``"Scan issues (N)"`` and enables the
        button when *count* is greater than zero.  Disables the button
        when *count* is zero.

        Args:
            count: Number of submods with warnings. The button is
                disabled when ``count == 0``.
        """
        self._scan_issues_btn.setText(f"Scan issues ({count})")
        self._scan_issues_btn.setEnabled(count > 0)
