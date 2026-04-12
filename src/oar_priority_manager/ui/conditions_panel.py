"""Conditions panel — read-only display of a competitor's condition tree.

See spec §7.5. Right pane of the main layout.
"""

from __future__ import annotations

import json

from PySide6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget

from oar_priority_manager.core.models import SubMod


class ConditionsPanel(QWidget):
    """Right pane: conditions for the focused competitor."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._header = QLabel("Conditions")
        layout.addWidget(self._header)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        layout.addWidget(self._text)

    def update_focus(self, submod: SubMod | None) -> None:
        """Update conditions display for the focused competitor."""
        if submod is None:
            self._header.setText("Conditions")
            self._text.clear()
            return

        self._header.setText(f"<b>Conditions</b> · {submod.mo2_mod} / {submod.name}")
        # Raw JSON display (Tier 2: formatted REQUIRED/ONE OF/EXCLUDED view)
        self._text.setPlainText(json.dumps(submod.conditions, indent=2))
