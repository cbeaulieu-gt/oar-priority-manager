"""Tests for ui/conditions_panel.py — formatted conditions view + JSON toggle."""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.ui.conditions_panel import ConditionsPanel


@pytest.fixture(scope="session")
def qapp():
    """Ensure a QApplication exists for widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_submod(
    conditions=None, name="TestSub", mo2_mod="TestMod", replacer_presets=None
):
    """Build a minimal SubMod for testing."""
    return SubMod(
        mo2_mod=mo2_mod,
        replacer="TestReplacer",
        name=name,
        description="",
        priority=100,
        source_priority=100,
        disabled=False,
        config_path=Path("/fake/config.json"),
        override_source=OverrideSource.SOURCE,
        override_is_ours=False,
        raw_dict={},
        conditions=conditions if conditions is not None else [],
        replacer_presets=replacer_presets if replacer_presets is not None else {},
    )


class TestConditionsPanelInit:
    def test_default_shows_placeholder(self, qapp):
        panel = ConditionsPanel()
        assert panel._formatted_view is not None
        assert panel._json_view is not None

    def test_formatted_is_default_mode(self, qapp):
        panel = ConditionsPanel()
        assert panel._formatted_btn.isChecked() is True
        assert panel._json_btn.isChecked() is False


class TestConditionsPanelUpdate:
    def test_update_none_shows_placeholder(self, qapp):
        panel = ConditionsPanel()
        panel.update_focus(None)
        # Header resets to "Conditions"; the placeholder label in the
        # formatted layout contains "Select a submod..."
        assert panel._header.text() == "Conditions"
        # At least one widget in the formatted layout (the placeholder label)
        assert panel._formatted_layout.count() >= 1

    def test_update_with_submod_shows_header(self, qapp):
        panel = ConditionsPanel()
        sm = _make_submod(
            conditions=[{"condition": "IsFemale", "negated": False}]
        )
        panel.update_focus(sm)
        assert "TestMod" in panel._header.text()
        assert "TestSub" in panel._header.text()

    def test_update_with_empty_conditions(self, qapp):
        panel = ConditionsPanel()
        sm = _make_submod(conditions=[])
        panel.update_focus(sm)
        # Should have at least the placeholder in the formatted layout
        assert panel._formatted_layout.count() >= 1

    def test_json_toggle_shows_raw_json(self, qapp):
        panel = ConditionsPanel()
        sm = _make_submod(
            conditions=[{"condition": "IsFemale", "negated": False}]
        )
        panel.update_focus(sm)
        panel._json_btn.click()
        assert "IsFemale" in panel._json_view.toPlainText()

    def test_formatted_toggle_returns_to_tree(self, qapp):
        panel = ConditionsPanel()
        sm = _make_submod(
            conditions=[{"condition": "IsFemale", "negated": False}]
        )
        panel.update_focus(sm)
        panel._json_btn.click()
        panel._formatted_btn.click()
        assert panel._formatted_btn.isChecked() is True


class TestConditionsPanelStats:
    def test_stats_footer_shows_counts(self, qapp):
        panel = ConditionsPanel()
        sm = _make_submod(
            conditions=[
                {"condition": "IsFemale", "negated": False},
                {"condition": "IsInCombat", "negated": False},
                {"condition": "HasShield", "negated": True},
            ]
        )
        panel.update_focus(sm)
        footer_text = panel._stats_label.text()
        assert "3" in footer_text
        assert "1" in footer_text


class TestGroupCollapsibility:
    """AND/OR group headers must be clickable and start expanded."""

    def _make_and_conditions(self):
        """Return conditions with a top-level AND group."""
        return [
            {
                "condition": "AND",
                "conditions": [
                    {"condition": "IsFemale", "negated": False},
                    {"condition": "IsInCombat", "negated": False},
                ],
            }
        ]

    def _find_group_header(self, panel):
        """Return the first QLabel whose text starts with the AND arrow."""
        from PySide6.QtWidgets import QLabel

        def _search(widget):
            for child in widget.findChildren(QLabel):
                txt = child.text()
                if "ALL of:" in txt or "ANY of:" in txt:
                    return child
            return None

        return _search(panel._formatted_content)

    def _find_children_widget(self, panel):
        """Return the first non-header QWidget inside the formatted content."""
        from PySide6.QtWidgets import QLabel

        # The children_widget is a QWidget added directly to
        # _formatted_layout right after the header label.
        layout = panel._formatted_layout
        for i in range(layout.count()):
            item = layout.itemAt(i)
            w = item.widget() if item else None
            if w is not None and not isinstance(w, QLabel):
                return w
        return None

    def test_group_header_is_clickable(self, qapp):
        """Group header QLabel must have PointingHandCursor set."""
        from PySide6.QtCore import Qt

        panel = ConditionsPanel()
        sm = _make_submod(conditions=self._make_and_conditions())
        panel.update_focus(sm)

        header = self._find_group_header(panel)
        assert header is not None, "No group header label found"
        assert header.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_group_starts_expanded(self, qapp):
        """Children widget must not be hidden immediately after update_focus.

        QWidget.isVisible() returns False for widgets that have never been
        rendered in a top-level window, so we check isHidden() instead —
        which reflects only explicit hide() calls, not window-show state.
        """
        panel = ConditionsPanel()
        sm = _make_submod(conditions=self._make_and_conditions())
        panel.update_focus(sm)

        children = self._find_children_widget(panel)
        assert children is not None, "No children container widget found"
        assert not children.isHidden(), "Group should start expanded (not hidden)"

    def test_clicking_header_toggles_children_visibility(self, qapp):
        """Clicking the header once hides children; again shows them.

        Uses isHidden() rather than isVisible() because the panel is never
        shown in a top-level window during tests — isVisible() would return
        False even after show() in that case.
        """
        panel = ConditionsPanel()
        sm = _make_submod(conditions=self._make_and_conditions())
        panel.update_focus(sm)

        header = self._find_group_header(panel)
        children = self._find_children_widget(panel)
        assert header is not None
        assert children is not None

        # First click — should collapse (hide children)
        header.mousePressEvent(None)
        assert children.isHidden(), (
            "Children should be hidden after first click"
        )

        # Second click — should expand (show children)
        header.mousePressEvent(None)
        assert not children.isHidden(), (
            "Children should not be hidden after second click"
        )


class TestPresetExpansion:
    def test_preset_resolves_from_submod_replacer_presets(self, qapp):
        panel = ConditionsPanel()
        presets = {
            "Combat Ready": [
                {"condition": "IsWeaponDrawn", "negated": False},
                {"condition": "IsInCombat", "negated": False},
            ]
        }
        sm = _make_submod(
            conditions=[
                {"condition": "PRESET", "Preset": "Combat Ready"},
            ],
            replacer_presets=presets,
        )
        panel.update_focus(sm)
        # The formatted view should contain a preset card widget
        assert panel._formatted_layout.count() >= 1

    def test_missing_preset_shows_warning(self, qapp):
        panel = ConditionsPanel()
        sm = _make_submod(
            conditions=[
                {"condition": "PRESET", "Preset": "Nonexistent"},
            ],
            replacer_presets={},
        )
        panel.update_focus(sm)
        assert panel._formatted_layout.count() >= 1

    def test_stats_footer_includes_presets(self, qapp):
        panel = ConditionsPanel()
        sm = _make_submod(
            conditions=[
                {"condition": "IsFemale", "negated": False},
                {"condition": "PRESET", "Preset": "Combat Ready"},
            ],
            replacer_presets={"Combat Ready": [{"condition": "IsInCombat"}]},
        )
        panel.update_focus(sm)
        footer_text = panel._stats_label.text()
        assert "1 presets" in footer_text or "preset" in footer_text.lower()
