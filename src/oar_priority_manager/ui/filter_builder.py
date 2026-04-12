"""Advanced filter builder modal — three pill buckets.

See spec §7.7. Stub for now — Tier 2: three pill buckets with autocomplete.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout


class FilterBuilder(QDialog):
    """Modal dialog with REQUIRED / ANY OF / EXCLUDED pill buckets."""

    def __init__(self, known_types: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Advanced Condition Filter")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Advanced filter builder — coming soon"))
        self._known_types = known_types
