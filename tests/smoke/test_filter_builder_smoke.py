"""End-to-end smoke test for the advanced filter builder (issue #49, Task 8).

Scenario (plan §5, Task 8 checkboxes):
- Two submods on disk — one with an IsFemale condition, one without.
- Launch a real MainWindow with the synthetic instance.
- Programmatically trigger _on_advanced_requested, obtain the open
  FilterBuilder, add "IsFemale" to the Required bucket, click Apply.
- Assert the tree panel has exactly one SUBMOD node in the matching set.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from oar_priority_manager.app.config import AppConfig
from oar_priority_manager.core.anim_scanner import build_conflict_map, scan_animations
from oar_priority_manager.core.filter_engine import extract_condition_types
from oar_priority_manager.core.priority_resolver import build_stacks
from oar_priority_manager.core.scanner import scan_mods
from oar_priority_manager.ui.filter_builder import FilterBuilder
from oar_priority_manager.ui.main_window import MainWindow
from oar_priority_manager.ui.tree_model import NodeType
from tests.conftest import make_config_json, make_submod_dir

# ---------------------------------------------------------------------------
# Condition dict helpers
# ---------------------------------------------------------------------------

_ISFEMALE_CONDITION = {
    "condition": "IsFemale",
    "negated": False,
}


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def filtered_instance(tmp_path: Path) -> Path:
    """Create a MO2 instance with exactly two submods.

    - ``female_sub``: config includes an IsFemale condition.
    - ``neutral_sub``: config has no conditions.

    Args:
        tmp_path: pytest temporary directory.

    Returns:
        The instance root Path.
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
        "female_sub",
        config=make_config_json(
            name="female_sub",
            priority=200,
            conditions=[_ISFEMALE_CONDITION],
        ),
        animations=["mt_idle.hkx"],
    )
    make_submod_dir(
        mods,
        "TestMod",
        "REP",
        "neutral_sub",
        config=make_config_json(
            name="neutral_sub",
            priority=100,
            conditions=[],
        ),
        animations=["mt_walk.hkx"],
    )
    return instance


@pytest.fixture
def main_window(qtbot, filtered_instance: Path) -> MainWindow:
    """Construct a MainWindow with the synthetic two-submod instance.

    Populates ``condition_types_present`` on each submod the same way
    ``app/main.py`` does, so the advanced filter has real data to work with.

    Args:
        qtbot: pytest-qt bot fixture.
        filtered_instance: Path to the synthetic MO2 instance.

    Returns:
        A fully-initialised :class:`MainWindow`.
    """
    mods_dir = filtered_instance / "mods"
    overwrite_dir = filtered_instance / "overwrite"

    submods = scan_mods(mods_dir, overwrite_dir)
    scan_animations(submods)
    # Populate condition_types_present (mirrors app/main.py startup sequence)
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
        instance_root=filtered_instance,
    )
    qtbot.addWidget(window)
    window.show()
    return window


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


def test_advanced_filter_isfemale_required_matches_one_submod(
    qtbot, main_window: MainWindow
) -> None:
    """Applying REQUIRED=IsFemale leaves exactly one SUBMOD node matched.

    Flow:
    1. Patch ``FilterBuilder.exec`` so the dialog does not block.
    2. Trigger ``_on_advanced_requested`` — this creates the dialog.
    3. Add "IsFemale" to the Required bucket.
    4. Click Apply programmatically.
    5. Assert ``filter_tree`` was called with a set containing exactly one
       SUBMOD node id — the ``female_sub`` node.

    Args:
        qtbot: pytest-qt bot fixture.
        main_window: The fully-initialised test window.
    """
    captured: dict = {}
    original_filter_tree = main_window._tree_panel.filter_tree

    def _spy_filter_tree(matching, hide_mode=False):
        """Record what was passed to filter_tree and forward normally."""
        captured["matching"] = matching
        captured["hide_mode"] = hide_mode
        original_filter_tree(matching, hide_mode=hide_mode)

    main_window._tree_panel.filter_tree = _spy_filter_tree  # type: ignore[method-assign]

    # Patch exec() so the dialog doesn't block (no event loop needed).
    # We drive the dialog manually after it's constructed.
    dialog_holder: list[FilterBuilder] = []

    def _capture_exec(self_dialog):
        """Intercept exec so we can drive the dialog in the test."""
        dialog_holder.append(self_dialog)
        # Do NOT call the real exec — that would block.

    with patch.object(FilterBuilder, "exec", _capture_exec):
        main_window._on_advanced_requested()

    assert dialog_holder, "FilterBuilder was never instantiated"
    dialog = dialog_holder[0]

    # Programmatically add "IsFemale" to the Required bucket.
    # _required_bucket is the first BucketWidget in the dialog.
    dialog._required_bucket._line_edit.setText("IsFemale")
    dialog._required_bucket._on_submit()

    # Click Apply — emits filter_applied and calls accept().
    dialog._on_apply()

    # The spy should have been called
    assert "matching" in captured, (
        "filter_tree was not called after Apply"
    )
    matching_ids = captured["matching"]

    # Collect SUBMOD node ids from the tree to cross-reference
    root = main_window._tree_panel.tree_root
    submod_nodes: dict[str, int] = {}
    for mod_node in root.children:
        for rep_node in mod_node.children:
            for sub_node in rep_node.children:
                if sub_node.node_type == NodeType.SUBMOD and sub_node.submod:
                    submod_nodes[sub_node.submod.name] = id(sub_node)

    assert "female_sub" in submod_nodes, (
        "female_sub not found in tree"
    )
    assert "neutral_sub" in submod_nodes, (
        "neutral_sub not found in tree"
    )

    # Exactly the female_sub node should be in the matching set
    assert submod_nodes["female_sub"] in matching_ids, (
        "female_sub node not in matching set"
    )
    assert submod_nodes["neutral_sub"] not in matching_ids, (
        "neutral_sub incorrectly included in matching set"
    )
    assert len(matching_ids) == 1, (
        f"Expected exactly 1 matching SUBMOD node, got {len(matching_ids)}"
    )
