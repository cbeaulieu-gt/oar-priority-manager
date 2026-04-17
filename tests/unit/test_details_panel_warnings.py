"""Tests for DetailsPanel parse-error view (issue #51, Task 5, spec §7.8)."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.ui.details_panel import DetailsPanel
from oar_priority_manager.ui.tree_model import NodeType, TreeNode


def _sm(warnings: list[str]) -> SubMod:
    return SubMod(
        mo2_mod="ModA",
        replacer="Rep",
        name="broken",
        description="A broken submod",
        priority=100,
        source_priority=100,
        disabled=False,
        config_path=Path("C:/mods/ModA/Rep/broken/config.json"),
        override_source=OverrideSource.SOURCE,
        override_is_ours=False,
        raw_dict={},
        warnings=warnings,
    )


def _submod_node(sm: SubMod) -> TreeNode:
    return TreeNode(
        display_name=sm.name,
        node_type=NodeType.SUBMOD,
        submod=sm,
    )


class TestDetailsPanelWarnings:
    def test_clean_submod_renders_normal_view(self, qtbot) -> None:
        panel = DetailsPanel()
        qtbot.addWidget(panel)
        sm = _sm(warnings=[])
        panel.update_selection(_submod_node(sm))
        html = panel._label.text()
        # Normal view includes "Priority:" and "Animations:" labels.
        assert "Priority:" in html
        assert "Animations:" in html

    def test_warning_submod_hides_normal_metadata(self, qtbot) -> None:
        panel = DetailsPanel()
        qtbot.addWidget(panel)
        sm = _sm(warnings=["File not found: C:/x/user.json"])
        panel.update_selection(_submod_node(sm))
        html = panel._label.text()
        # Normal metadata sections must NOT appear on a warning submod.
        assert "Animations:" not in html
        assert "Conditions:" not in html
        assert "Override source:" not in html

    def test_warning_submod_shows_each_warning_bullet(self, qtbot) -> None:
        panel = DetailsPanel()
        qtbot.addWidget(panel)
        warnings = [
            "File not found: C:/x/user.json",
            "JSON parse error in C:/x/config.json: line 5 column 1",
        ]
        sm = _sm(warnings=warnings)
        panel.update_selection(_submod_node(sm))
        html = panel._label.text()
        assert "File not found: C:/x/user.json" in html
        assert "JSON parse error in C:/x/config.json" in html

    def test_warning_submod_shows_submod_name_and_path(self, qtbot) -> None:
        panel = DetailsPanel()
        qtbot.addWidget(panel)
        sm = _sm(warnings=["Empty file: C:/x/config.json"])
        panel.update_selection(_submod_node(sm))
        html = panel._label.text()
        assert sm.name in html
        assert str(sm.config_path.parent) in html

    def test_warning_banner_is_styled_red(self, qtbot) -> None:
        panel = DetailsPanel()
        qtbot.addWidget(panel)
        sm = _sm(warnings=["File not found: C:/x"])
        panel.update_selection(_submod_node(sm))
        html = panel._label.text()
        # The banner uses the same red hex (#e66) as the existing warnings span.
        assert "#e66" in html
