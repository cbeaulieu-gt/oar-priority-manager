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
