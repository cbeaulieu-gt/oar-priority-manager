"""End-to-end smoke test for the Scan Issues log pane (issue #51, Task 6).

Scenario:
- Two submods on disk: one valid, one with an invalid JSON config.json.
- Launch a real MainWindow.
- Assert the Scan issues button label shows "Scan issues (1)" and is enabled.
- Open the pane via _on_scan_issues_requested().
- Assert the pane's table has exactly one row referencing the broken submod.
- Double-click the row, assert the tree currentItem becomes the broken submod.
- Assert the DetailsPanel switches to the parse-error view (contains the
  "WARNING — parse errors prevent normal display" banner, does NOT contain
  "Priority:" or "Animations:").
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from oar_priority_manager.app.config import AppConfig
from oar_priority_manager.core.anim_scanner import build_conflict_map, scan_animations
from oar_priority_manager.core.filter_engine import extract_condition_types
from oar_priority_manager.core.priority_resolver import build_stacks
from oar_priority_manager.core.scanner import scan_mods
from oar_priority_manager.ui.main_window import MainWindow
from oar_priority_manager.ui.tree_model import NodeType
from tests.conftest import make_config_json, make_submod_dir


@pytest.fixture
def warning_instance(tmp_path: Path) -> Path:
    """Create an MO2 instance with one valid and one broken submod.

    ``valid_sub`` has a normal config.json; ``broken_sub`` has config.json
    that fails to parse after trailing-comma repair (mismatched bracket).
    """
    instance = tmp_path
    mods = instance / "mods"
    mods.mkdir()
    (instance / "overwrite").mkdir()
    (instance / "ModOrganizer.ini").touch()

    make_submod_dir(
        mods,
        "TestMod",
        "REP",
        "valid_sub",
        config=make_config_json(name="valid_sub", priority=100),
        animations=["mt_walk.hkx"],
    )
    # Write a config.json that will not parse even after comma repair.
    broken_dir = (
        mods / "TestMod" / "meshes" / "actors" / "character"
        / "animations" / "OpenAnimationReplacer" / "REP" / "broken_sub"
    )
    broken_dir.mkdir(parents=True)
    (broken_dir / "config.json").write_text(
        "{\"name\": \"broken_sub\", \"priority\": 50,\n\"conditions\": [",
        encoding="utf-8",
    )
    # Drop a stub .hkx so the scanner considers it a submod.
    (broken_dir / "stub.hkx").write_text("", encoding="utf-8")
    return instance


@pytest.fixture
def main_window(qtbot, warning_instance: Path) -> MainWindow:
    """Build a real MainWindow instance backed by the warning_instance fixture."""
    mods_dir = warning_instance / "mods"
    overwrite_dir = warning_instance / "overwrite"
    submods = scan_mods(mods_dir, overwrite_dir)
    scan_animations(submods)
    for sm in submods:
        present, negated = extract_condition_types(sm.conditions)
        sm.condition_types_present = present
        sm.condition_types_negated = negated

    conflict_map = build_conflict_map(submods)
    stacks = build_stacks(conflict_map)

    window = MainWindow(
        submods=submods,
        conflict_map=conflict_map,
        stacks=stacks,
        app_config=AppConfig(),
        instance_root=warning_instance,
    )
    qtbot.addWidget(window)
    window.show()
    return window


def test_scan_issues_button_shows_count(main_window: MainWindow) -> None:
    """The Scan issues button label reflects 1 warning submod."""
    btn = main_window._search_bar._scan_issues_btn
    assert btn.isEnabled()
    assert btn.text() == "Scan issues (1)"


def test_scan_issues_pane_lists_broken_submod(
    qtbot, main_window: MainWindow
) -> None:
    """Opening the pane shows exactly one row for broken_sub."""
    main_window._on_scan_issues_requested()
    pane = main_window._scan_issues_pane
    assert pane is not None
    qtbot.waitUntil(lambda: pane.isVisible(), timeout=500)
    assert pane._table.rowCount() == 1
    row_submod = pane._table.item(0, 1).text()
    assert "broken_sub" in row_submod


def test_double_click_navigates_and_details_panel_switches_view(
    qtbot, main_window: MainWindow
) -> None:
    """Double-click on a log row selects the tree node and shows parse errors."""
    main_window._on_scan_issues_requested()
    pane = main_window._scan_issues_pane
    assert pane is not None
    qtbot.waitUntil(lambda: pane._table.rowCount() == 1, timeout=500)

    # Simulate double-click on column 1 (Submod column).
    item = pane._table.item(0, 1)
    pane._table.itemDoubleClicked.emit(item)

    # Tree selection should now be the broken_sub SUBMOD node.
    current = main_window._tree_panel._tree.currentItem()
    assert current is not None
    node = main_window._tree_panel._item_map.get(id(current))
    assert node is not None
    assert node.node_type == NodeType.SUBMOD
    assert node.submod is not None
    assert node.submod.name == "broken_sub"

    # Details panel rendered the parse-error view.
    html = main_window._details_panel._label.text()
    assert "WARNING" in html
    assert "parse errors" in html
    assert "Priority:" not in html
    assert "Animations:" not in html
