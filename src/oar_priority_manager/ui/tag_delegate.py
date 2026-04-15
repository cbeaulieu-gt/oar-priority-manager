"""Custom tree item delegate that paints category tag pills.

Renders colored pills after the display name in each tree row.
Uses TagCategory color metadata for the muted palette.
"""
from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from oar_priority_manager.core.tag_engine import TagCategory

# Custom data role to store tags on QTreeWidgetItem
TAG_DATA_ROLE: int = Qt.ItemDataRole.UserRole + 100
# Custom data role to store override indicator
TAG_OVERRIDE_ROLE: int = Qt.ItemDataRole.UserRole + 101

# Pill layout constants
_PILL_H_PAD: int = 6
_PILL_V_PAD: int = 2
_PILL_GAP: int = 6
_PILL_RADIUS: int = 6
_PILL_FONT_SIZE: int = 9
_PILL_LEFT_MARGIN: int = 8
_MAX_MOD_PILLS: int = 4


def sorted_tags(tags: set[TagCategory]) -> list[TagCategory]:
    """Sort tags by sort_order for consistent display."""
    return sorted(tags, key=lambda t: t.sort_order)


class TagDelegate(QStyledItemDelegate):
    """Delegate that paints tag pills after the item text."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pill_font = QFont()
        self._pill_font.setPixelSize(_PILL_FONT_SIZE)
        self._pill_font.setBold(True)
        self._pill_fm = QFontMetrics(self._pill_font)

    def _get_tags(self, index) -> list[TagCategory]:
        """Retrieve sorted tags from item data."""
        tags = index.data(TAG_DATA_ROLE)
        if not tags:
            return []
        return sorted_tags(tags) if isinstance(tags, set) else []

    def _pill_width(self, label: str) -> int:
        """Width of a single pill including padding."""
        return self._pill_fm.horizontalAdvance(label) + 2 * _PILL_H_PAD

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        """Paint the default item, then overlay tag pills."""
        super().paint(painter, option, index)

        tags = self._get_tags(index)
        if not tags:
            return

        is_override = index.data(TAG_OVERRIDE_ROLE)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self._pill_font)

        rect = option.rect
        pill_h = self._pill_fm.height() + 2 * _PILL_V_PAD
        y = rect.top() + (rect.height() - pill_h) // 2

        # Left-align pills after the display text
        display_text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        text_fm = option.fontMetrics
        text_width = text_fm.horizontalAdvance(display_text)
        # Account for item indentation and icon space
        x = option.rect.left() + text_width + _PILL_LEFT_MARGIN

        # Draw override indicator (pencil)
        if is_override:
            painter.setPen(QColor("#888888"))
            painter.drawText(
                x,
                y + _PILL_V_PAD + self._pill_fm.ascent(),
                "\u270E",
            )
            x += self._pill_fm.horizontalAdvance("\u270E ") + _PILL_GAP

        # Draw each pill
        for tag in tags:
            w = self._pill_width(tag.label)
            pill_rect = QRect(x, y, w, pill_h)

            # Background
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(tag.color_bg)))
            painter.drawRoundedRect(pill_rect, _PILL_RADIUS, _PILL_RADIUS)

            # Border
            painter.setPen(QPen(QColor(tag.color_border), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(pill_rect, _PILL_RADIUS, _PILL_RADIUS)

            # Text
            painter.setPen(QColor(tag.color_fg))
            painter.drawText(
                pill_rect,
                Qt.AlignmentFlag.AlignCenter,
                tag.label,
            )

            x += w + _PILL_GAP

        painter.restore()

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index,
    ) -> QSize:
        """Expand width to accommodate pills."""
        size = super().sizeHint(option, index)
        tags = self._get_tags(index)
        if tags:
            extra = _PILL_LEFT_MARGIN
            for tag in tags:
                extra += self._pill_width(tag.label) + _PILL_GAP
            size.setWidth(size.width() + extra)
        return size
