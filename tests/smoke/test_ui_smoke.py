"""UI smoke tests — verify panels construct and basic interactions don't crash.

See spec §11.1 (smoke tests).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from oar_priority_manager.app.config import AppConfig
from oar_priority_manager.core.anim_scanner import build_conflict_map, scan_animations
from oar_priority_manager.core.models import PriorityStack
from oar_priority_manager.core.priority_resolver import build_stacks
from oar_priority_manager.core.scanner import scan_mods
from oar_priority_manager.ui.main_window import MainWindow
from tests.conftest import make_config_json, make_submod_dir


@pytest.fixture
def populated_instance(tmp_path: Path) -> Path:
    """Create a tmp MO2 instance with a few OAR mods."""
    instance = tmp_path
    mods = instance / "mods"
    mods.mkdir()
    (instance / "overwrite").mkdir()
    (instance / "ModOrganizer.ini").touch()

    make_submod_dir(
        mods, "Female Combat Pack", "AMA", "heavy",
        config=make_config_json(name="heavy", priority=500),
        animations=["mt_idle.hkx", "mt_walkforward.hkx"],
    )
    make_submod_dir(
        mods, "Female Combat Pack", "AMA", "light",
        config=make_config_json(name="light", priority=400),
        animations=["mt_idle.hkx"],
    )
    make_submod_dir(
        mods, "Vanilla Tweaks", "VT", "idle",
        config=make_config_json(name="idle", priority=200),
        animations=["mt_idle.hkx", "mt_walkforward.hkx"],
    )
    return instance


@pytest.fixture
def main_window(qtbot, populated_instance: Path) -> MainWindow:
    mods_dir = populated_instance / "mods"
    overwrite_dir = populated_instance / "overwrite"

    submods = scan_mods(mods_dir, overwrite_dir)
    scan_animations(submods)
    conflict_map = build_conflict_map(submods)
    stacks = build_stacks(conflict_map)

    window = MainWindow(
        submods=submods,
        conflict_map=conflict_map,
        stacks=stacks,
        app_config=AppConfig(),
        instance_root=populated_instance,
    )
    qtbot.addWidget(window)
    window.show()
    return window


def test_main_window_constructs(main_window: MainWindow):
    """Main window constructs without crashing."""
    assert main_window.isVisible()


def test_window_has_three_panes(main_window: MainWindow):
    """Window has the expected panel structure."""
    assert main_window._tree_panel is not None
    assert main_window._stacks_panel is not None
    assert main_window._conditions_panel is not None
    assert main_window._details_panel is not None


def test_tree_has_items(main_window: MainWindow):
    """Tree is populated with mod data."""
    tree = main_window._tree_panel._tree
    assert tree.topLevelItemCount() > 0
