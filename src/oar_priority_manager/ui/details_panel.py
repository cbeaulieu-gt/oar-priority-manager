"""Details panel — read-only metadata for the currently selected tree node.

See spec §7.3. Shows different content for mod/replacer/submod selection levels.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from oar_priority_manager.core.models import SubMod
from oar_priority_manager.ui.tree_model import NodeType


class DetailsPanel(QWidget):
    """Bottom section of left column — read-only metadata."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self._label = QLabel("Select an item in the tree to see details.")
        self._label.setWordWrap(True)
        layout.addWidget(self._label)

    def update_selection(self, node_type: NodeType | None, submod: SubMod | None) -> None:
        """Update display based on tree selection."""
        if node_type is None or (node_type == NodeType.SUBMOD and submod is None):
            self._label.setText("Select an item in the tree to see details.")
            return

        if node_type == NodeType.SUBMOD and submod is not None:
            lines = [
                f"<b>{submod.name}</b>",
                f"<span style='color:gray'>{submod.display_path}</span>",
                f"Priority: <b>{submod.priority:,}</b>",
            ]
            if submod.is_overridden:
                lines.append(f"<span style='color:#aa4'>was {submod.source_priority:,}</span>")
            lines.append(f"MO2 source: <code>{submod.mo2_mod}</code>")
            lines.append(f"Animations: {len(submod.animations)} files")
            self._label.setText("<br>".join(lines))
        elif node_type == NodeType.MOD:
            self._label.setText("<b>Mod</b> — select a submod for details")
        elif node_type == NodeType.REPLACER:
            self._label.setText("<b>Replacer</b> — select a submod for details")
