"""Conditions panel — formatted AND/OR/NOT tree + raw JSON toggle.

See spec: docs/superpowers/specs/2026-04-12-conditions-panel-design.md
Issues: #43 (formatted display), #44 (JSON toggle)
"""
from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from oar_priority_manager.core.models import SubMod
from oar_priority_manager.ui.conditions_renderer import (
    RenderedNode,
    conditions_stats,
    render_conditions,
    resolve_preset,
)


class ConditionsPanel(QWidget):
    """Right pane: formatted condition tree with JSON toggle."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Object name targets QWidget#ConditionsPanel_root in custom.qss for
        # the pane-level border / background rule (issue #98).
        self.setObjectName("ConditionsPanel_root")
        # WA_StyledBackground is required so Qt actually paints the
        # background: rule from custom.qss.  Without it, Qt silently skips
        # background painting on plain QWidget subclasses — borders still
        # render (they go through a different drawing path) but the fill
        # colour is never applied.  This is the canonical fix for that
        # well-known Qt/PySide6 gotcha.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._current_submod: SubMod | None = None
        self._show_formatted: bool = True
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # -- Header row: label + Formatted/JSON toggle --
        header_row = QWidget()
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(4, 4, 4, 2)

        self._header = QLabel("Conditions")
        self._header.setTextFormat(Qt.TextFormat.RichText)
        header_layout.addWidget(self._header, stretch=1)

        # Segmented toggle matching tree_panel.py / stacks_panel.py pattern.
        # Object names match QPushButton#SegToggle_left / #SegToggle_right
        # in custom.qss.
        self._formatted_btn = QPushButton("Formatted")
        self._formatted_btn.setCheckable(True)
        self._formatted_btn.setChecked(True)
        self._formatted_btn.setObjectName("SegToggle_left")

        self._json_btn = QPushButton("JSON")
        self._json_btn.setCheckable(True)
        self._json_btn.setChecked(False)
        self._json_btn.setObjectName("SegToggle_right")

        self._toggle_group = QButtonGroup(self)
        self._toggle_group.setExclusive(True)
        self._toggle_group.addButton(self._formatted_btn)
        self._toggle_group.addButton(self._json_btn)

        self._formatted_btn.clicked.connect(lambda: self._set_mode(True))
        self._json_btn.clicked.connect(lambda: self._set_mode(False))

        header_layout.addWidget(self._formatted_btn)
        header_layout.addWidget(self._json_btn)

        layout.addWidget(header_row)

        # -- Formatted view (scroll area with rendered tree) --
        self._formatted_view = QScrollArea()
        self._formatted_view.setWidgetResizable(True)
        self._formatted_content = QWidget()
        self._formatted_layout = QVBoxLayout(self._formatted_content)
        self._formatted_layout.setContentsMargins(8, 8, 8, 8)
        self._formatted_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self._formatted_view.setWidget(self._formatted_content)
        layout.addWidget(self._formatted_view)

        # -- JSON view (existing QTextEdit, hidden by default) --
        self._json_view = QTextEdit()
        self._json_view.setReadOnly(True)
        self._json_view.hide()
        layout.addWidget(self._json_view)

        # -- Stats footer --
        self._stats_label = QLabel("")
        # Object name matches QLabel#ConditionsPanel_statsLabel in custom.qss
        self._stats_label.setObjectName("ConditionsPanel_statsLabel")
        layout.addWidget(self._stats_label)

    def _set_mode(self, formatted: bool) -> None:
        """Switch between formatted and JSON view modes."""
        if self._show_formatted == formatted:
            return
        self._show_formatted = formatted
        self._formatted_view.setVisible(formatted)
        self._json_view.setVisible(not formatted)

    def update_focus(self, submod: SubMod | None) -> None:
        """Update display for the focused competitor submod."""
        self._current_submod = submod

        if submod is None:
            self._header.setText("Conditions")
            self._clear_formatted()
            self._json_view.clear()
            self._stats_label.setText("")
            self._add_placeholder("Select a submod to view conditions.")
            return

        self._header.setText(
            f"<b>Conditions</b> · {submod.mo2_mod} / {submod.name}"
        )

        # JSON view (always updated, even if hidden)
        self._json_view.setPlainText(json.dumps(submod.conditions, indent=2))

        # Formatted view
        nodes = render_conditions(submod.conditions)
        self._clear_formatted()

        if not nodes:
            self._add_placeholder("No conditions defined.")
            self._stats_label.setText("")
            return

        self._render_nodes(nodes, self._formatted_layout, indent=0)

        # Stats footer
        stats = conditions_stats(nodes)
        parts = [
            f"{stats['conditions']} conditions",
            f"{stats['types']} types",
            f"{stats['negated']} negated",
        ]
        if stats["presets"] > 0:
            parts.append(f"{stats['presets']} presets")
        self._stats_label.setText(" · ".join(parts))

    def _clear_formatted(self) -> None:
        """Remove all widgets from the formatted view layout."""
        while self._formatted_layout.count():
            child = self._formatted_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _add_placeholder(self, text: str) -> None:
        """Add a placeholder label to the formatted view."""
        label = QLabel(text)
        # Object name matches QLabel#ConditionsPanel_placeholder in custom.qss
        label.setObjectName("ConditionsPanel_placeholder")
        self._formatted_layout.addWidget(label)

    def _render_nodes(
        self,
        nodes: list[RenderedNode],
        parent_layout: QVBoxLayout,
        indent: int,
    ) -> None:
        """Recursively render RenderedNode trees into QLabels."""
        for node in nodes:
            if node.node_type in ("AND", "OR"):
                self._render_group(node, parent_layout, indent)
            elif node.node_type == "preset":
                self._render_preset(node, parent_layout, indent)
            else:
                self._render_leaf(node, parent_layout, indent)

    def _render_group(
        self, node: RenderedNode, parent_layout: QVBoxLayout, indent: int
    ) -> None:
        """Render a collapsible AND/OR group with a clickable header.

        Groups start expanded by default so the full condition tree is
        visible on load.  Clicking the header toggles child visibility,
        and the arrow glyph (▾/▸) reflects the current state.

        Args:
            node: The AND/OR RenderedNode to render.
            parent_layout: The parent layout to add this group into.
            indent: Current indentation level (multiples of 20 px).
        """
        label_text = "ALL of:" if node.node_type == "AND" else "ANY of:"
        color = "#7aa2f7" if node.node_type == "AND" else "#bb9af7"
        child_count = len(node.children)

        def _expanded_html(
            lbl: str = label_text,
            clr: str = color,
            n: int = child_count,
        ) -> str:
            return (
                f"<b style='color:{clr};'>▾ {lbl}</b>"
                f" <span style='color:#565f89; font-size:11px;'>"
                f"({n})</span>"
            )

        def _collapsed_html(
            lbl: str = label_text,
            clr: str = color,
            n: int = child_count,
        ) -> str:
            return (
                f"<b style='color:{clr};'>▸ {lbl}</b>"
                f" <span style='color:#565f89; font-size:11px;'>"
                f"({n})</span>"
            )

        header = QLabel(_expanded_html())
        header.setTextFormat(Qt.TextFormat.RichText)
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header.setContentsMargins(indent * 20, 2, 0, 0)
        parent_layout.addWidget(header)

        # Children container — visible by default (expanded)
        children_widget = QWidget()
        children_layout = QVBoxLayout(children_widget)
        children_layout.setContentsMargins(0, 0, 0, 0)
        children_layout.setSpacing(0)
        parent_layout.addWidget(children_widget)

        # Render children into the container at increased indent
        self._render_nodes(node.children, children_layout, indent + 1)

        def _toggle(
            _event: object = None,
            *,
            cw: QWidget = children_widget,
            hdr: QLabel = header,
        ) -> None:
            # Use isHidden() rather than isVisible(): isVisible() returns
            # False for widgets that have never been shown in a top-level
            # window, so it cannot distinguish "explicitly hidden" from
            # "not yet displayed".  isHidden() reflects only explicit
            # hide()/show() calls, which is what we need here.
            if not cw.isHidden():
                cw.hide()
                hdr.setText(_collapsed_html())
            else:
                cw.show()
                hdr.setText(_expanded_html())

        header.mousePressEvent = _toggle

    def _render_leaf(
        self, node: RenderedNode, parent_layout: QVBoxLayout, indent: int
    ) -> None:
        """Render a single leaf condition with icon, name, and params."""
        if node.negated:
            icon = "<span style='color:#f7768e;'>✗</span>"
            name_html = (
                f"<span style='color:#c0caf5; text-decoration:line-through;"
                f" opacity:0.7;'>{node.text}</span>"
                f" <span style='background:#3a1a1a; color:#f7768e;"
                f" padding:1px 6px; border-radius:3px; font-size:11px;'>"
                f"NOT</span>"
            )
        else:
            icon = "<span style='color:#9ece6a;'>✓</span>"
            name_html = f"<span style='color:#c0caf5;'>{node.text}</span>"

        html = f"{icon} {name_html}"

        # Add parameters line if any
        if node.params:
            param_parts = [f'{k} = "{v}"' for k, v in node.params.items()]
            params_str = " · ".join(param_parts)
            html += (
                f"<br><span style='color:#565f89; font-size:11px;"
                f" margin-left:22px;'>{params_str}</span>"
            )

        label = QLabel(html)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setContentsMargins(indent * 20, 2, 0, 2)
        parent_layout.addWidget(label)

    def _render_preset(
        self, node: RenderedNode, parent_layout: QVBoxLayout, indent: int
    ) -> None:
        """Render a PRESET reference as a clickable expandable card."""
        preset_name = node.preset_name or "Unknown"

        # Create a container widget for the preset card.
        # Object name matches QWidget#ConditionsPanel_presetCard in custom.qss
        card = QWidget()
        card.setObjectName("ConditionsPanel_presetCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 8, 10, 8)

        # Header row
        header = QLabel(
            f"<span style='color:#e0af68;'>⚙</span>"
            f" <b style='color:#e0af68;'>PRESET:</b>"
            f" <span style='color:#c0caf5;'>{preset_name}</span>"
            f" <span style='color:#565f89; font-size:11px;'>"
            f"▸ expand</span>"
        )
        header.setTextFormat(Qt.TextFormat.RichText)
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        card_layout.addWidget(header)

        # Expanded content container (hidden initially)
        expanded = QWidget()
        expanded.hide()
        expanded_layout = QVBoxLayout(expanded)
        expanded_layout.setContentsMargins(8, 4, 0, 0)
        card_layout.addWidget(expanded)

        # Wire up click to toggle expand/collapse
        def _toggle_preset(
            _event: object = None,
            *,
            exp: QWidget = expanded,
            hdr: QLabel = header,
            pname: str = preset_name,
            exp_layout: QVBoxLayout = expanded_layout,
        ) -> None:
            if exp.isVisible():
                exp.hide()
                hdr.setText(
                    f"<span style='color:#e0af68;'>⚙</span>"
                    f" <b style='color:#e0af68;'>PRESET:</b>"
                    f" <span style='color:#c0caf5;'>{pname}</span>"
                    f" <span style='color:#565f89; font-size:11px;'>"
                    f"▸ expand</span>"
                )
            else:
                # Resolve preset on demand
                if exp_layout.count() == 0:
                    self._populate_preset(pname, exp_layout)
                exp.show()
                hdr.setText(
                    f"<span style='color:#e0af68;'>⚙</span>"
                    f" <b style='color:#e0af68;'>PRESET:</b>"
                    f" <span style='color:#c0caf5;'>{pname}</span>"
                    f" <span style='color:#565f89; font-size:11px;'>"
                    f"▾ collapse</span>"
                )

        header.mousePressEvent = _toggle_preset

        card.setContentsMargins(indent * 20, 4, 0, 4)
        parent_layout.addWidget(card)

    def _populate_preset(
        self, preset_name: str, layout: QVBoxLayout
    ) -> None:
        """Resolve and render a preset's conditions into the given layout."""
        presets = {}
        if self._current_submod is not None:
            presets = getattr(self._current_submod, "replacer_presets", {})

        nodes = resolve_preset(preset_name, presets)
        if nodes is None:
            warning = QLabel(
                f"<span style='color:#f7768e;'>Preset '{preset_name}'"
                f" not found in replacer config.</span>"
            )
            warning.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(warning)
            return

        self._render_nodes(nodes, layout, indent=0)
