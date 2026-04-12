"""Priority stacks panel — shows animation competition for the selected submod.

See spec §7.4. Center pane of the main layout.

Issues addressed:
  #33 — Relative/Absolute mode toolbar toggle
  #34 — Rank badge colours (green for #1, grey for rest; red bg for losing rows)
  #35 — Expand/collapse animation sections
  #36 — Clickable competitor rows emitting competitor_focused signal
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from oar_priority_manager.core.models import SubMod


# ---------------------------------------------------------------------------
# Helper widget: collapsible stack section (issue #35)
# ---------------------------------------------------------------------------

class _StackSection(QWidget):
    """A single animation's priority stack — collapsible via header click."""

    def __init__(self, header_html: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._expanded = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Flat button acts as a toggle header (issue #35)
        self._header_btn = QPushButton()
        self._header_btn.setFlat(True)
        self._header_btn.setStyleSheet("text-align: left; padding: 2px 6px;")
        self._header_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._header_btn.clicked.connect(self._toggle)
        outer.addWidget(self._header_btn)

        # Separator line for visual grouping
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        outer.addWidget(line)

        # Collapsible content area
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(8, 2, 4, 4)
        self._content_layout.setSpacing(1)
        outer.addWidget(self._content)

        # Store the base header text (without arrow prefix) so we can rebuild it
        self._header_html = header_html
        self._update_header()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def add_row(self, row_widget: QWidget) -> None:
        """Append a competitor row to the content area."""
        self._content_layout.addWidget(row_widget)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._update_header()

    def _update_header(self) -> None:
        arrow = "▾" if self._expanded else "▸"
        self._header_btn.setText(f"{arrow} {self._header_html}")


# ---------------------------------------------------------------------------
# Helper: styled competitor row (issues #34, #36)
# ---------------------------------------------------------------------------

def _make_competitor_row(
    rank_num: int,
    val_text: str,
    comp: SubMod,
    is_you: bool,
    is_losing_row: bool,
    relative_mode: bool,
    on_click,
) -> QWidget:
    """Build a single clickable competitor row with rank badge + name columns.

    Args:
        rank_num: 1-based rank position.
        val_text: Formatted priority value (delta or absolute).
        comp: The competitor SubMod.
        is_you: Whether this row represents the currently selected submod.
        is_losing_row: True when this row is the winner that the selected
            submod is losing to (used for red background tint).
        relative_mode: Controls priority column width.
        on_click: Callable invoked when the row is clicked.

    Returns:
        A QWidget containing the full row layout.
    """
    # Outer button so the whole row is clickable (issue #36)
    btn = QPushButton()
    btn.setFlat(True)

    # Red background for the row we are losing to (issue #34 spec §7.4)
    bg = "background: #4a2020;" if is_losing_row else ""
    btn.setStyleSheet(
        f"QPushButton {{ text-align: left; padding: 1px 2px; {bg} }}"
        "QPushButton:hover { background: rgba(255,255,255,0.05); }"
    )

    row_layout = QHBoxLayout(btn)
    row_layout.setContentsMargins(2, 1, 2, 1)
    row_layout.setSpacing(4)

    # -- Rank badge (issue #34) --
    badge_color = "#4a9" if rank_num == 1 else "#888"
    badge = QLabel(f"<span style='color:{badge_color}'><b>#{rank_num}</b></span>")
    badge.setTextFormat(Qt.TextFormat.RichText)
    badge.setFixedWidth(36)
    badge.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    row_layout.addWidget(badge)

    # -- Priority value column (issue #34 — fixed width per spec) --
    prio_width = 80 if relative_mode else 140
    prio_lbl = QLabel(val_text)
    prio_lbl.setFixedWidth(prio_width)
    prio_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    prio_lbl.setStyleSheet("color: #aaa;")
    row_layout.addWidget(prio_lbl)

    # -- Owner / name --
    name_text = f"{comp.mo2_mod} / {comp.name}"
    if is_you:
        name_text = f"<b>{name_text}  (you)</b>"
    name_lbl = QLabel(name_text)
    name_lbl.setTextFormat(Qt.TextFormat.RichText)
    name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    row_layout.addWidget(name_lbl)

    # Wire click signal (issue #36)
    btn.clicked.connect(on_click)

    return btn


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

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
        self._collapsed: dict[str, bool] = {}  # anim -> collapsed state (issue #35)
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ---- Toolbar: Relative / Absolute toggle (issue #33) ----
        toolbar_widget = QWidget()
        toolbar = QHBoxLayout(toolbar_widget)
        toolbar.setContentsMargins(4, 4, 4, 2)

        self._rel_btn = QPushButton("Relative")
        self._abs_btn = QPushButton("Absolute")
        self._rel_btn.setCheckable(True)
        self._abs_btn.setCheckable(True)
        self._rel_btn.setChecked(True)   # default: relative mode
        self._abs_btn.setChecked(False)
        self._rel_btn.clicked.connect(lambda: self._set_mode(True))
        self._abs_btn.clicked.connect(lambda: self._set_mode(False))
        toolbar.addWidget(self._rel_btn)
        toolbar.addWidget(self._abs_btn)
        toolbar.addStretch()
        layout.addWidget(toolbar_widget)

        # ---- Header label ----
        self._header = QLabel("Select a submod to see priority stacks.")
        self._header.setContentsMargins(4, 0, 4, 4)
        layout.addWidget(self._header)

        # ---- Scroll area for stack sections ----
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(4, 4, 4, 4)
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll)

        # ---- Action buttons ----
        layout.addWidget(self._build_action_bar())

    # ------------------------------------------------------------------
    # Public API (preserved from original)
    # ------------------------------------------------------------------

    def update_selection(self, submod: SubMod | None) -> None:
        """Update stacks display for the selected submod."""
        self._current_submod = submod
        self._refresh_display()

    def set_relative_mode(self, relative: bool) -> None:
        """Switch between relative (delta) and absolute priority display."""
        self._relative_mode = relative
        self._rel_btn.setChecked(relative)
        self._abs_btn.setChecked(not relative)
        self._refresh_display()

    def refresh(self, conflict_map: dict[str, list[SubMod]]) -> None:
        """Refresh display using updated conflict map."""
        self._conflict_map = conflict_map
        self._refresh_display()

    # ------------------------------------------------------------------
    # Internal: mode toggle
    # ------------------------------------------------------------------

    def _set_mode(self, relative: bool) -> None:
        """Called by toolbar buttons — update state and refresh."""
        self._relative_mode = relative
        self._rel_btn.setChecked(relative)
        self._abs_btn.setChecked(not relative)
        self._refresh_display()

    # ------------------------------------------------------------------
    # Internal: display refresh
    # ------------------------------------------------------------------

    def _refresh_display(self) -> None:
        # Clear existing content widgets
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
    ) -> _StackSection:
        """Build one collapsible stack section for a single animation.

        Args:
            anim: Animation filename (e.g. ``mt_idle.hkx``).
            competitors: Ordered list of competing SubMods for this animation.
            selected: The currently selected SubMod.

        Returns:
            A ``_StackSection`` widget ready for insertion into the scroll area.
        """
        rank = next((i for i, c in enumerate(competitors) if c is selected), -1)

        # Build status HTML
        if rank == 0:
            status = "<span style='color:#4a9'>you're #1</span>"
        elif rank > 0 and competitors:
            delta = competitors[0].priority - selected.priority
            target = competitors[0].priority + 1
            status = (
                f"<span style='color:#e66'>"
                f"losing by {delta} · set to {target:,} to win"
                f"</span>"
            )
        else:
            status = ""

        # Tie detection
        priorities = [c.priority for c in competitors]
        has_ties = len(priorities) != len(set(priorities))
        if has_ties and rank >= 0:
            tied_with = [
                c for c in competitors
                if c.priority == selected.priority and c is not selected
            ]
            if tied_with:
                status += " <span style='color:#aa4'>⚠ TIED</span>"

        header_html = (
            f"<b>{anim}</b> · {len(competitors)} competitors · {status}"
        )
        section = _StackSection(header_html)

        # Restore collapsed state (issue #35)
        if self._collapsed.get(anim, False):
            # Simulate collapse without extra toggle machinery
            section._expanded = False
            section._content.setVisible(False)
            section._update_header()

        # Track collapses: wire into header button post-construction
        _anim = anim  # capture for closure
        _orig_toggle = section._toggle

        def _patched_toggle(s=section, a=_anim, orig=_orig_toggle):
            orig()
            self._collapsed[a] = not s._expanded

        section._header_btn.clicked.disconnect()
        section._header_btn.clicked.connect(_patched_toggle)

        # Competitor rows
        for i, comp in enumerate(competitors):
            is_you = comp is selected
            rank_num = i + 1

            if self._relative_mode:
                delta = comp.priority - competitors[0].priority if competitors else 0
                val_text = f"+{delta}" if delta >= 0 else str(delta)
            else:
                val_text = f"{comp.priority:,}"

            # "Losing row" = the winning competitor when we are not #1 (issue #34)
            is_losing_row = (not is_you) and (rank > 0) and (rank_num == 1)

            # Capture comp for the click closure (issue #36)
            _comp = comp
            row = _make_competitor_row(
                rank_num=rank_num,
                val_text=val_text,
                comp=comp,
                is_you=is_you,
                is_losing_row=is_losing_row,
                relative_mode=self._relative_mode,
                on_click=lambda checked=False, c=_comp: self.competitor_focused.emit(c),
            )
            section.add_row(row)

        return section

    # ------------------------------------------------------------------
    # Action bar
    # ------------------------------------------------------------------

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
