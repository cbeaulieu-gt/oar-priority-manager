"""Priority stacks panel — shows animation competition for the selected submod.

See spec §7.4. Center pane of the main layout.

Issues addressed:
  #33 — Relative/Absolute mode toolbar toggle
  #34 — Rank badge colours (green for #1, grey for rest; red bg for losing rows)
  #35 — Expand/collapse animation sections
  #36 — Clickable competitor rows emitting competitor_focused signal
  #46 — Shift by N button
  #47 — Animation filter input
  #48 — Collapse-winning toggle button
  #60 — Right-click context menu "Go to in tree" on competitor rows
  #61 — Target badge label showing which submod action buttons apply to
  #66 — Loading indicator and caching for large priority stacks
  #68 — Action buttons moved to toolbar row
  #69 — Relative/Absolute replaced with segmented toggle control
  #74 — Collapse same-mod competitor rows into a single summary row
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
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

    def __init__(self, header_text: str, parent: QWidget | None = None) -> None:
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
        self._header_text = header_text
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
        self._header_btn.setText(f"{arrow} {self._header_text}")


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

    # Red background for losing row; blue tint for the "you" row (issues #34, #72)
    if is_losing_row:
        bg = "background: #4a2020;"
    elif is_you:
        bg = "background: #1a2a3a;"
    else:
        bg = ""
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
# Helper widget: collapsible same-mod sibling group (issue #74)
# ---------------------------------------------------------------------------

class _ModGroupRow(QWidget):
    """A clickable summary row that collapses/expands same-mod sibling rows.

    Rendered as a sub-header inside a ``_StackSection`` when more than one
    submod from the same MO2 mod appears in the competitor list.  Individual
    sibling rows are stored as children and toggled on click.

    Args:
        mod_name: The MO2 mod name used as the group label.
        sibling_count: Number of sibling submods in the group (excluding the
            "you" row, which is always visible outside the group).
        collapsed: Initial collapsed state.  Defaults to ``True`` so groups
            start collapsed and the panel stays compact.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        mod_name: str,
        sibling_count: int,
        collapsed: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._collapsed = collapsed
        self._mod_name = mod_name
        self._sibling_count = sibling_count
        self._child_rows: list[QWidget] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Summary button — acts as the toggle handle
        self._btn = QPushButton()
        self._btn.setFlat(True)
        self._btn.setStyleSheet(
            "QPushButton { text-align: left; padding: 2px 8px;"
            "  color: #8ab; font-style: italic; }"
            "QPushButton:hover { background: rgba(255,255,255,0.05); }"
        )
        self._btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._btn.clicked.connect(self._toggle)
        layout.addWidget(self._btn)

        # Container for child rows
        self._child_container = QWidget()
        self._child_layout = QVBoxLayout(self._child_container)
        self._child_layout.setContentsMargins(0, 0, 0, 0)
        self._child_layout.setSpacing(1)
        layout.addWidget(self._child_container)

        self._update_label()
        self._child_container.setVisible(not self._collapsed)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def add_child_row(self, row_widget: QWidget) -> None:
        """Append a sibling competitor row to this group's child container.

        Args:
            row_widget: The competitor row widget to add.
        """
        self._child_rows.append(row_widget)
        self._child_layout.addWidget(row_widget)

    @property
    def is_collapsed(self) -> bool:
        """Whether the group is currently collapsed."""
        return self._collapsed

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._child_container.setVisible(not self._collapsed)
        self._update_label()

    def _update_label(self) -> None:
        arrow = "▸" if self._collapsed else "▾"
        noun = "sibling" if self._sibling_count == 1 else "siblings"
        self._btn.setText(
            f"{arrow} {self._mod_name} ({self._sibling_count} {noun})"
        )


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

class StacksPanel(QWidget):
    """Center pane: priority stacks for the selected submod's animations."""

    # Emitted when user clicks a competitor row: (submod,)
    competitor_focused = Signal(object)
    # Emitted when user triggers a priority action: (action_name, submod, value)
    action_triggered = Signal(str, object, object)
    # Emitted when user right-clicks a competitor and chooses "Go to in tree"
    navigate_to_submod = Signal(object)  # issue #60

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
        # Keyed by f"{anim}:{mo2_mod}" — persists expand/collapse across refreshes
        self._mod_group_collapsed: dict[str, bool] = {}  # issue #74
        # Cache of built _StackSection widgets keyed by
        # (mo2_mod, replacer, name, relative_mode).  Populated on first
        # display_stack() call; invalidated via clear_cache() (issue #66).
        self._stack_cache: dict[
            tuple[str, str, str, bool], list[_StackSection]
        ] = {}
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the panel layout.

        Layout (top to bottom):
          1. Toolbar: segmented Relative|Absolute toggle, spacer, action buttons
          2. Toast label (hidden by default)
          3. Header label
          4. Scroll area with collapsible stack sections
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ---- Toolbar row (issues #33, #68, #69) ----
        toolbar_widget = QWidget()
        toolbar = QHBoxLayout(toolbar_widget)
        toolbar.setContentsMargins(4, 4, 4, 2)
        toolbar.setSpacing(4)

        # -- Segmented Relative | Absolute toggle (issue #69) --
        # Two checkable QPushButtons styled to sit flush with radius only on
        # outside corners, giving the appearance of a single segmented control.
        _seg_checked = (
            "QPushButton:checked {"
            "  background: #3a3a5a;"
            "  font-weight: bold;"
            "  border: 1px solid #5a5a8a;"
            "}"
        )
        _seg_unchecked = (
            "QPushButton {"
            "  background: #2a2a2a;"
            "  border: 1px solid #444;"
            "  padding: 3px 10px;"
            "}"
            "QPushButton:hover { background: #333; }"
        )

        self._rel_btn = QPushButton("Relative")
        self._rel_btn.setCheckable(True)
        self._rel_btn.setChecked(True)
        self._rel_btn.setStyleSheet(
            _seg_unchecked + _seg_checked
            + "QPushButton { border-radius: 0px;"
            "  border-top-left-radius: 4px;"
            "  border-bottom-left-radius: 4px;"
            "  border-right: none; }"
        )

        self._abs_btn = QPushButton("Absolute")
        self._abs_btn.setCheckable(True)
        self._abs_btn.setChecked(False)
        self._abs_btn.setStyleSheet(
            _seg_unchecked + _seg_checked
            + "QPushButton { border-radius: 0px;"
            "  border-top-right-radius: 4px;"
            "  border-bottom-right-radius: 4px; }"
        )

        # QButtonGroup enforces mutual exclusivity (issue #69)
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_group.addButton(self._rel_btn)
        self._mode_group.addButton(self._abs_btn)

        self._rel_btn.clicked.connect(lambda: self._set_mode(True))
        self._abs_btn.clicked.connect(lambda: self._set_mode(False))

        toolbar.addWidget(self._rel_btn)
        toolbar.addWidget(self._abs_btn)

        # Spacer between toggle and action buttons
        toolbar.addSpacing(12)

        # -- Target badge: shows which submod the action buttons apply to --
        # (issue #61) Prevents confusion when clicking competitor rows updates
        # the conditions panel but actions still target the tree selection.
        self._target_label = QLabel()
        self._target_label.setMaximumWidth(300)
        self._target_label.setWordWrap(False)
        self._target_label.setTextFormat(Qt.TextFormat.RichText)
        self._target_label.setToolTip(
            "The action buttons (Move to Top, Set Exact, etc.) apply to this"
            " submod, even when a competitor row is highlighted."
        )
        self._update_target_label(None)
        toolbar.addWidget(self._target_label)

        toolbar.addSpacing(8)

        # -- Action buttons inlined into toolbar (issue #68) --
        self._move_to_top_btn = QPushButton("Move to Top")
        self._move_to_top_btn.clicked.connect(
            lambda: self.action_triggered.emit(
                "move_to_top", self._current_submod, None
            )
        )
        toolbar.addWidget(self._move_to_top_btn)

        self._set_exact_btn = QPushButton("Set Exact…")
        self._set_exact_btn.clicked.connect(self._on_set_exact)
        toolbar.addWidget(self._set_exact_btn)

        self._move_rep_btn = QPushButton("Move Replacer to Top")
        self._move_rep_btn.clicked.connect(
            lambda: self.action_triggered.emit(
                "move_to_top_replacer", self._current_submod, None
            )
        )
        toolbar.addWidget(self._move_rep_btn)

        self._move_mod_btn = QPushButton("Move Mod to Top")
        self._move_mod_btn.clicked.connect(
            lambda: self.action_triggered.emit(
                "move_to_top_mod", self._current_submod, None
            )
        )
        toolbar.addWidget(self._move_mod_btn)

        # -- Shift by N button (issue #46) --
        self._shift_btn = QPushButton("Shift…")
        self._shift_btn.setToolTip("Shift priority by a relative amount")
        self._shift_btn.clicked.connect(self._on_shift)
        toolbar.addWidget(self._shift_btn)

        # -- Hide Winning toggle (issue #48) --
        self._collapse_winning_btn = QPushButton("Hide Winning")
        self._collapse_winning_btn.setCheckable(True)
        self._collapse_winning_btn.setToolTip(
            "Collapse sections where the selected submod is already #1"
        )
        self._collapse_winning_btn.toggled.connect(self._on_collapse_winning)
        toolbar.addWidget(self._collapse_winning_btn)

        # No trailing stretch — toolbar fills naturally; action btns are right
        # of the spacer and the segmented toggle anchors to the left.
        layout.addWidget(toolbar_widget)

        # ---- Animation filter input (issue #47) ----
        # Placed below the toolbar row, above the header label, so it targets
        # the scroll area content without cluttering the action-button row.
        self._anim_filter = QLineEdit()
        self._anim_filter.setPlaceholderText("Filter animations…")
        self._anim_filter.setMaximumHeight(28)
        self._anim_filter.setClearButtonEnabled(True)
        self._anim_filter.textChanged.connect(self._on_anim_filter)
        layout.addWidget(self._anim_filter)

        # ---- Toast notification (issue #37, spec §7.4) ----
        self._toast = QLabel()
        self._toast.setContentsMargins(8, 4, 8, 4)
        self._toast.setStyleSheet(
            "background: #1a3a1a; color: #4a9;"
            " padding: 4px 8px; border-radius: 4px;"
        )
        self._toast.setWordWrap(True)
        self._toast.hide()
        layout.addWidget(self._toast)

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

        # ---- Loading placeholder (issue #66) ----
        # Shown briefly while a large stack is being built from scratch
        # (i.e. on cache miss).  Hidden once the real content is in place.
        self._loading_label = QLabel("Loading\u2026")
        self._loading_label.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self._loading_label.setStyleSheet(
            "color: #888; font-style: italic; padding: 24px;"
        )
        self._loading_label.hide()
        # Insert it into the outer layout BEFORE the scroll area so it
        # overlays the header area — we instead add it into the content
        # layout and manage it there.
        self._content_layout.addWidget(self._loading_label)

    # ------------------------------------------------------------------
    # Public API (preserved from original)
    # ------------------------------------------------------------------

    def update_selection(self, submod: SubMod | None) -> None:
        """Update stacks display for the selected submod.

        Disables action buttons when the submod has warnings (spec §9) or
        when no submod is selected.  Also refreshes the target badge so
        the toolbar always shows which submod the action buttons apply to
        (issue #61).

        Args:
            submod: The newly selected SubMod, or ``None`` to clear.
        """
        self._current_submod = submod
        # Update target badge (issue #61)
        self._update_target_label(submod)
        # Disable action buttons when submod has warnings (spec §9)
        has_warnings = submod.has_warnings if submod else True
        enabled = not has_warnings and submod is not None
        self._move_to_top_btn.setEnabled(enabled)
        self._set_exact_btn.setEnabled(enabled)
        self._move_rep_btn.setEnabled(enabled)
        self._move_mod_btn.setEnabled(enabled)
        self._shift_btn.setEnabled(enabled)  # issue #46
        self._refresh_display()

    def show_toast(self, message: str) -> None:
        """Show a brief inline toast message that auto-dismisses after 5 seconds.

        Args:
            message: The text to display in the toast notification.
        """
        self._toast.setText(message)
        self._toast.show()
        QTimer.singleShot(5000, self._toast.hide)

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

    def clear_cache(self) -> None:
        """Invalidate the built-stack cache (issue #66).

        Must be called by the owning window whenever the underlying priority
        data changes (action applied, overrides cleared, full reload) so that
        the next ``update_selection`` call rebuilds from the new data rather
        than serving stale cached widgets.
        """
        self._stack_cache.clear()

    # ------------------------------------------------------------------
    # Internal: target label (issue #61)
    # ------------------------------------------------------------------

    def _update_target_label(self, submod: SubMod | None) -> None:
        """Update the toolbar target badge to reflect the action target.

        When a submod is selected the label reads
        ``"▸ Actions apply to: <b>SubModName</b>"`` in muted grey.
        When nothing is selected it shows ``"No submod selected"`` in
        dim grey so the badge is always present but visually quiet.

        Args:
            submod: The currently selected SubMod, or ``None`` when
                nothing is selected.
        """
        if submod is None:
            self._target_label.setText(
                "<span style='color:#666;'>No submod selected</span>"
            )
        else:
            # Elide long names to keep the toolbar compact.  Qt rich-text
            # labels do not support built-in elision, so we truncate the
            # raw name string before embedding it.
            name = submod.name
            if len(name) > 40:  # noqa: PLR2004
                name = name[:37] + "…"
            self._target_label.setText(
                f"<span style='color:#aaa;'>&#9656; Actions apply to:"
                f" <b>{name}</b></span>"
            )

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
        """Rebuild or restore the stacks scroll area for the current submod.

        Cache behaviour (issue #66):
          - On cache hit: sections are re-parented directly into the layout
            with no loading indicator.
          - On cache miss: a "Loading..." label is shown immediately and
            ``QApplication.processEvents()`` is called to paint it before
            the (potentially slow) build loop runs.  Results are cached
            under a key of ``(mo2_mod, replacer, name, relative_mode)``
            so re-selecting the same submod in the same display mode is
            instant.
        """
        # Collect all cached section widgets across every cache entry so we
        # can distinguish them from freshly-built or stale widgets during
        # the clear loop below.
        all_cached: set[int] = {
            id(sec)
            for sections in self._stack_cache.values()
            for sec in sections
        }

        # Clear existing content widgets from the layout.
        # - The loading label is always preserved (it is re-inserted at
        #   position 0 by insertWidget below).
        # - Cached _StackSection widgets are simply un-parented from the
        #   layout without deletion — they will be re-added on a cache hit.
        # - Any other widget (stretch spacers, config-only info labels, etc.)
        #   is deleted.
        while self._content_layout.count():
            child = self._content_layout.takeAt(0)
            w = child.widget()
            if w is None:
                # Layout spacer item — no widget to manage.
                continue
            if w is self._loading_label or id(w) in all_cached:
                # Keep: loading label stays owned by us; cached sections are
                # preserved so they can be re-inserted on a cache hit.
                w.setParent(None)  # type: ignore[call-overload]
            else:
                w.deleteLater()

        # Always re-add the loading label at position 0 so it can be shown
        # before the build starts on a cache miss.
        self._loading_label.hide()
        self._content_layout.insertWidget(0, self._loading_label)

        sm = self._current_submod
        if sm is None:
            self._header.setText("Select a submod to see priority stacks.")
            return

        self._header.setText(f"<b>Priority Stacks</b> · <code>{sm.name}</code>")

        # Config-only submods have no animations and don't compete in any
        # stack.  Show an explanatory message instead of an empty scroll area
        # so the user doesn't assume something is broken.
        if sm.is_config_only:
            info = QLabel(
                "This submod is a config-only toggle. It has no animations"
                " and does not compete in priority stacks. Other submods may"
                " reference it via IsReplacerEnabled conditions."
            )
            info.setWordWrap(True)
            info.setTextFormat(Qt.TextFormat.PlainText)
            info.setStyleSheet("color: #6af; padding: 8px;")
            self._content_layout.addWidget(info)
            self._content_layout.addStretch()
            return

        # --- Cache lookup (issue #66) ---
        cache_key = (sm.mo2_mod, sm.replacer, sm.name, self._relative_mode)
        cached = self._stack_cache.get(cache_key)

        if cached is not None:
            # Cache hit — restore sections directly, no loading label needed.
            for section in cached:
                self._content_layout.addWidget(section)
        else:
            # Cache miss — show "Loading…" immediately so the UI gives
            # visual feedback while the build loop runs.
            self._loading_label.show()
            QApplication.processEvents()

            sections: list[_StackSection] = []
            for anim in sm.animations:
                competitors = self._conflict_map.get(anim, [])
                section = self._build_stack_section(anim, competitors, sm)
                sections.append(section)
                self._content_layout.addWidget(section)

            # Hide the loading label now that content is in the layout.
            self._loading_label.hide()

            # Store in cache for future re-selections.
            self._stack_cache[cache_key] = sections

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

        # Build status text (plain text — QPushButton does not render rich text)
        if rank == 0:
            status = "you're #1"
        elif rank > 0 and competitors:
            delta = competitors[0].priority - selected.priority
            target = competitors[0].priority + 1
            status = f"losing by {delta:,} · set to {target:,} to win"
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
                status += " \u26a0 TIED"

        header_text = f"{anim} · {len(competitors)} competitors · {status}"
        section = _StackSection(header_text)

        # Store metadata needed by filter (issue #47) and hide-winning
        # (issue #48) without subclassing _StackSection.
        section.anim_name = anim  # type: ignore[attr-defined]
        section.is_winning = rank == 0  # type: ignore[attr-defined]

        # Restore collapsed state (issue #35)
        if self._collapsed.get(anim, False):
            # Simulate collapse without extra toggle machinery
            section._expanded = False
            section._content.setVisible(False)
            section._update_header()

        # Track collapses: wire into header button post-construction
        _anim = anim  # capture for closure
        _orig_toggle = section._toggle

        def _patched_toggle(checked=False, *, s=section, a=_anim, orig=_orig_toggle):
            orig()
            self._collapsed[a] = not s._expanded

        section._header_btn.clicked.disconnect()
        section._header_btn.clicked.connect(_patched_toggle)

        # ---- Competitor rows with same-mod grouping (issue #74) ----
        # Competitors from the same MO2 mod as the selected submod are grouped
        # into a collapsible _ModGroupRow.  Cross-mod competitors remain as
        # individual rows.  The "you" row is always rendered outside the group.
        selected_mod = selected.mo2_mod

        # Count how many competitors share the selected submod's MO2 mod
        # (excluding the selected submod itself) to decide whether to group.
        same_mod_siblings = [
            c for c in competitors if c.mo2_mod == selected_mod and c is not selected
        ]
        use_group = len(same_mod_siblings) > 0

        # Build the _ModGroupRow once if needed so sibling rows can be added to it.
        group_row: _ModGroupRow | None = None
        group_inserted = False  # track whether the group widget is in the section yet

        if use_group:
            state_key = f"{anim}:{selected_mod}"
            initial_collapsed = self._mod_group_collapsed.get(state_key, True)
            group_row = _ModGroupRow(
                mod_name=selected_mod,
                sibling_count=len(same_mod_siblings),
                collapsed=initial_collapsed,
            )

            # Persist state changes back to _mod_group_collapsed
            def _on_group_toggle(
                *,
                gr: _ModGroupRow = group_row,
                key: str = state_key,
            ) -> None:
                self._mod_group_collapsed[key] = gr.is_collapsed

            group_row._btn.clicked.connect(_on_group_toggle)

        for i, comp in enumerate(competitors):
            is_you = comp is selected
            rank_num = i + 1

            if self._relative_mode:
                delta = comp.priority - competitors[0].priority if competitors else 0
                val_text = f"+{delta:,}" if delta >= 0 else f"{delta:,}"
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

            # Right-click "Go to in tree" context menu (issue #60).
            # Context menu policy is set here (not inside _make_competitor_row)
            # because the module-level helper has no access to self or signals.
            row.setContextMenuPolicy(
                Qt.ContextMenuPolicy.CustomContextMenu
            )
            row.customContextMenuRequested.connect(
                lambda pos, c=_comp, r=row: self._show_competitor_context_menu(
                    r, pos, c
                )
            )

            # Route row into the correct container (issue #74):
            #   - "you" row: always goes directly into the section (always visible)
            #   - Same-mod sibling: routed into the group's child container
            #   - Cross-mod competitor: goes directly into the section
            if is_you:
                # The "you" row is always visible — never hidden inside the group
                section.add_row(row)
            elif use_group and comp.mo2_mod == selected_mod:
                # Same-mod sibling: insert group header before first sibling row,
                # then add this row as a child of the group.
                assert group_row is not None  # guaranteed by use_group
                if not group_inserted:
                    section.add_row(group_row)
                    group_inserted = True
                group_row.add_child_row(row)
            else:
                # Cross-mod competitor: individual row, no grouping
                section.add_row(row)

        return section

    # ------------------------------------------------------------------
    # Competitor context menu (issue #60)
    # ------------------------------------------------------------------

    def _show_competitor_context_menu(
        self,
        row: QPushButton,
        pos,
        comp: SubMod,
    ) -> None:
        """Show a right-click context menu on a competitor row.

        Presents a single "Go to in tree" action that emits
        ``navigate_to_submod`` so the main window can select the
        corresponding item in the tree panel.

        Args:
            row: The competitor row button the menu is anchored to.
            pos: The local position of the right-click (from
                ``customContextMenuRequested``).
            comp: The competitor ``SubMod`` this row represents.
        """
        menu = QMenu(row)
        action = menu.addAction("Go to in tree")
        action.triggered.connect(
            lambda: self.navigate_to_submod.emit(comp)
        )
        menu.exec(row.mapToGlobal(pos))

    # ------------------------------------------------------------------
    # Set Exact dialog
    # ------------------------------------------------------------------

    def _on_set_exact(self) -> None:
        """Open a dialog to set the selected submod's priority to an exact value."""
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

    # ------------------------------------------------------------------
    # Shift dialog (issue #46)
    # ------------------------------------------------------------------

    def _on_shift(self) -> None:
        """Open a dialog to shift the selected submod's priority by a delta.

        Prompts the user for a positive or negative integer offset, then
        emits ``action_triggered("shift", submod, delta)`` on confirmation.
        """
        if self._current_submod is None:
            return
        value, ok = QInputDialog.getInt(
            self, "Shift Priority",
            "Shift priority by:",
            value=0,
            min=-2_147_483_648, max=2_147_483_647,
        )
        if ok:
            self.action_triggered.emit("shift", self._current_submod, value)

    # ------------------------------------------------------------------
    # Animation filter (issue #47)
    # ------------------------------------------------------------------

    def _on_anim_filter(self, query: str) -> None:
        """Show only stack sections whose animation name contains *query*.

        Iterates every ``_StackSection`` widget currently in the scroll
        area's content layout and toggles visibility based on a
        case-insensitive substring match.  An empty query restores all
        sections.

        Args:
            query: The filter string typed by the user.
        """
        q = query.lower()
        for i in range(self._content_layout.count()):
            item = self._content_layout.itemAt(i)
            if item is None:
                continue
            widget = item.widget()
            if not isinstance(widget, _StackSection):
                continue
            anim_name: str = getattr(widget, "anim_name", "")
            visible = not q or q in anim_name.lower()
            widget.setVisible(visible)

    # ------------------------------------------------------------------
    # Collapse-winning toggle (issue #48)
    # ------------------------------------------------------------------

    def _on_collapse_winning(self, checked: bool) -> None:
        """Collapse or expand sections based on whether the submod is winning.

        When *checked* is ``True``, every section where the selected
        submod is rank #1 (``section.is_winning is True``) is collapsed
        so the user can focus on conflicting animations.  When *checked*
        is ``False``, all sections are expanded.

        Args:
            checked: ``True`` to hide winning sections, ``False`` to
                restore all.
        """
        for i in range(self._content_layout.count()):
            item = self._content_layout.itemAt(i)
            if item is None:
                continue
            widget = item.widget()
            if not isinstance(widget, _StackSection):
                continue
            is_winning: bool = getattr(widget, "is_winning", False)
            if checked and is_winning:
                # Collapse: force content hidden without toggling state
                # so the header arrow stays consistent.
                if widget._expanded:
                    widget._toggle()
            elif not checked and not widget._expanded:
                # Expand all sections back.
                widget._toggle()
