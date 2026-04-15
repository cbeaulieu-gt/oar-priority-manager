"""Dialog for manually editing category tags on a mod or submod.

Displays checkboxes for each TagCategory with colored pill previews.
Provides a "Reset to Auto" button to clear manual overrides.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from oar_priority_manager.core.tag_engine import TagCategory
from oar_priority_manager.ui.tag_delegate import sorted_tags


def _pill_html(tag: TagCategory) -> str:
    """Render a single tag as an HTML pill span."""
    return (
        f'<span style="'
        f"background:{tag.color_bg};"
        f"color:{tag.color_fg};"
        f"border:1px solid {tag.color_border};"
        f"border-radius:6px;"
        f"padding:1px 6px;"
        f"font-size:10px;"
        f"font-weight:bold;"
        f'">{tag.label}</span>'
    )


class TagEditDialog(QDialog):
    """Modal dialog for editing tags on a tree node.

    Args:
        current_tags: The currently active tags (auto or override).
        is_override: Whether the current tags are a manual override.
        parent: Parent widget.
    """

    def __init__(
        self,
        current_tags: set[TagCategory],
        is_override: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Tags")
        self.setMinimumWidth(300)
        self._reset_requested = False

        layout = QVBoxLayout(self)

        # Info label
        if is_override:
            info = QLabel(
                '<span style="color:#888">These tags are manually set. '
                'Click "Reset to Auto" to revert to auto-detected tags.</span>'
            )
        else:
            info = QLabel(
                '<span style="color:#888">Check/uncheck tags to override '
                "auto-detection for this item.</span>"
            )
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setWordWrap(True)
        layout.addWidget(info)

        # Checkboxes — one per tag category
        self._checkboxes: dict[TagCategory, QCheckBox] = {}
        for tag in sorted_tags(set(TagCategory)):
            row = QHBoxLayout()
            cb = QCheckBox()
            cb.setChecked(tag in current_tags)
            self._checkboxes[tag] = cb
            row.addWidget(cb)

            pill_label = QLabel(_pill_html(tag))
            pill_label.setTextFormat(Qt.TextFormat.RichText)
            row.addWidget(pill_label)

            row.addStretch()
            layout.addLayout(row)

        # Reset button
        reset_btn = QPushButton("Reset to Auto")
        reset_btn.setToolTip("Clear manual override and revert to auto-detected tags")
        reset_btn.clicked.connect(self._on_reset)
        layout.addWidget(reset_btn)

        # OK / Cancel
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_reset(self) -> None:
        """Handle Reset to Auto button click."""
        self._reset_requested = True
        self.accept()

    @property
    def reset_requested(self) -> bool:
        """True if user clicked Reset to Auto instead of OK."""
        return self._reset_requested

    def selected_tags(self) -> set[TagCategory]:
        """Return the set of checked tag categories."""
        return {tag for tag, cb in self._checkboxes.items() if cb.isChecked()}
