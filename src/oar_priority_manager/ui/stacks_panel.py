"""Priority stacks panel — shows animation competition for the selected submod.

See spec §7.4. Center pane of the main layout.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from oar_priority_manager.core.models import SubMod


class StacksPanel(QWidget):
    """Center pane: priority stacks for the selected submod's animations."""

    # Emitted when user clicks a competitor row: (submod,)
    competitor_focused = Signal(object)
    # Emitted when user triggers a priority action: (action_name, submod, value)
    action_triggered = Signal(str, object, object)

    def __init__(
        self,
        conflict_map: dict[str, list[SubMod]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._conflict_map = conflict_map
        self._current_submod: SubMod | None = None
        self._relative_mode = True
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._header = QLabel("Select a submod to see priority stacks.")
        layout.addWidget(self._header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll)

        # Action buttons (spec §7.4)
        layout.addWidget(self._build_action_bar())

    def update_selection(self, submod: SubMod | None) -> None:
        """Update stacks display for the selected submod."""
        self._current_submod = submod
        self._refresh_display()

    def _refresh_display(self) -> None:
        # Clear existing content
        while self._content_layout.count():
            child = self._content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        sm = self._current_submod
        if sm is None:
            self._header.setText("Select a submod to see priority stacks.")
            return

        self._header.setText(f"<b>Priority Stacks</b> · <code>{sm.name}</code>")

        for anim in sm.animations:
            competitors = self._conflict_map.get(anim, [])
            section = self._build_stack_section(anim, competitors, sm)
            self._content_layout.addWidget(section)

        self._content_layout.addStretch()

    def _build_stack_section(
        self, anim: str, competitors: list[SubMod], selected: SubMod,
    ) -> QWidget:
        """Build one expandable stack section for an animation."""
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(4, 4, 4, 4)

        # Header
        rank = next((i for i, c in enumerate(competitors) if c is selected), -1)
        if rank == 0:
            status = "<span style='color:#4a9'>you're #1</span>"
        elif rank > 0 and competitors:
            delta = competitors[0].priority - selected.priority
            target = competitors[0].priority + 1
            status = f"<span style='color:#e66'>losing by {delta} · set to {target:,} to win</span>"
        else:
            status = ""

        # Check for ties
        priorities = [c.priority for c in competitors]
        has_ties = len(priorities) != len(set(priorities))
        if has_ties and rank >= 0:
            tied_with = [
                c for c in competitors
                if c.priority == selected.priority and c is not selected
            ]
            if tied_with:
                status += " <span style='color:#aa4'>⚠ TIED</span>"

        header = QLabel(f"▾ <b>{anim}</b> · {len(competitors)} competitors · {status}")
        header.setTextFormat(1)  # RichText
        layout.addWidget(header)

        # Competitor rows
        for i, comp in enumerate(competitors):
            is_you = comp is selected
            rank_num = i + 1
            if self._relative_mode:
                delta = comp.priority - competitors[0].priority if competitors else 0
                val_text = f"+{delta}" if delta >= 0 else str(delta)
            else:
                val_text = f"{comp.priority:,}"

            you_marker = " <b>(you)</b>" if is_you else ""
            row_text = f"  #{rank_num} {val_text}  {comp.mo2_mod} / {comp.name}{you_marker}"
            row = QLabel(row_text)
            layout.addWidget(row)

        return section

    def _build_action_bar(self) -> QWidget:
        """Build Move to Top / Set Exact action buttons."""
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 4, 4, 4)

        self._move_to_top_btn = QPushButton("Move to Top")
        self._move_to_top_btn.clicked.connect(
            lambda: self.action_triggered.emit("move_to_top", self._current_submod, None)
        )
        layout.addWidget(self._move_to_top_btn)

        self._set_exact_btn = QPushButton("Set Exact…")
        self._set_exact_btn.clicked.connect(self._on_set_exact)
        layout.addWidget(self._set_exact_btn)

        layout.addStretch()
        return bar

    def _on_set_exact(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        if self._current_submod is None:
            return
        value, ok = QInputDialog.getInt(
            self, "Set Exact Priority",
            f"New priority for {self._current_submod.name}:",
            value=self._current_submod.priority,
            min=-2_147_483_648, max=2_147_483_647,
        )
        if ok:
            self.action_triggered.emit("set_exact", self._current_submod, value)

    def set_relative_mode(self, relative: bool) -> None:
        """Switch between relative (delta) and absolute priority display."""
        self._relative_mode = relative
        self._refresh_display()

    def refresh(self, conflict_map: dict[str, list[SubMod]]) -> None:
        """Refresh display using updated conflict map."""
        self._conflict_map = conflict_map
        self._refresh_display()
