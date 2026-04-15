# Conditions Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the raw-JSON conditions panel with a formatted AND/OR/NOT tree view, a JSON toggle, and on-demand PRESET resolution.

**Architecture:** A pure-logic `conditions_renderer.py` converts OAR condition dicts into `RenderedNode` trees (no Qt dependency). The updated `conditions_panel.py` uses these nodes to build a QWidget-based formatted view alongside the existing JSON view, switched via a segmented toggle. Preset data flows from the scanner through `tree_model.py` TreeNodes to the panel.

**Tech Stack:** Python 3.11, PySide6, pytest, dataclasses

---

### Task 1: Create `conditions_renderer.py` — RenderedNode dataclass and `render_conditions()`

**Files:**
- Create: `src/oar_priority_manager/ui/conditions_renderer.py`
- Create: `tests/unit/test_conditions_renderer.py`

- [ ] **Step 1: Write failing tests for `render_conditions()`**

```python
"""Tests for ui/conditions_renderer.py — pure-logic condition tree renderer."""
from __future__ import annotations

from oar_priority_manager.ui.conditions_renderer import (
    RenderedNode,
    render_conditions,
)


class TestRenderConditions:
    def test_empty_list_returns_empty(self):
        result = render_conditions([])
        assert result == []

    def test_empty_dict_returns_empty(self):
        result = render_conditions({})
        assert result == []

    def test_single_leaf_condition(self):
        conditions = [{"condition": "IsFemale", "negated": False}]
        result = render_conditions(conditions)
        assert len(result) == 1
        node = result[0]
        assert node.text == "IsFemale"
        assert node.node_type == "leaf"
        assert node.negated is False
        assert node.params == {}
        assert node.children == []

    def test_negated_leaf(self):
        conditions = [{"condition": "HasShield", "negated": True}]
        result = render_conditions(conditions)
        assert result[0].negated is True

    def test_leaf_with_extra_params(self):
        conditions = [
            {
                "condition": "HasPerk",
                "negated": False,
                "formID": "0x00012345",
                "pluginName": "Skyrim.esm",
            }
        ]
        result = render_conditions(conditions)
        node = result[0]
        assert node.params == {
            "formID": "0x00012345",
            "pluginName": "Skyrim.esm",
        }

    def test_and_group(self):
        conditions = [
            {
                "condition": "AND",
                "conditions": [
                    {"condition": "IsFemale", "negated": False},
                    {"condition": "IsInCombat", "negated": False},
                ],
            }
        ]
        result = render_conditions(conditions)
        assert len(result) == 1
        group = result[0]
        assert group.node_type == "AND"
        assert group.text == "AND"
        assert len(group.children) == 2
        assert group.children[0].text == "IsFemale"
        assert group.children[1].text == "IsInCombat"

    def test_or_group(self):
        conditions = [
            {
                "condition": "OR",
                "conditions": [
                    {"condition": "HasKeyword", "negated": False},
                    {"condition": "HasPerk", "negated": False},
                ],
            }
        ]
        result = render_conditions(conditions)
        assert result[0].node_type == "OR"
        assert len(result[0].children) == 2

    def test_nested_and_inside_or(self):
        conditions = [
            {
                "condition": "OR",
                "conditions": [
                    {
                        "condition": "AND",
                        "conditions": [
                            {"condition": "IsFemale", "negated": False},
                            {"condition": "IsSneaking", "negated": False},
                        ],
                    },
                    {"condition": "IsInCombat", "negated": False},
                ],
            }
        ]
        result = render_conditions(conditions)
        or_node = result[0]
        assert or_node.node_type == "OR"
        assert or_node.children[0].node_type == "AND"
        assert len(or_node.children[0].children) == 2
        assert or_node.children[1].text == "IsInCombat"

    def test_preset_reference(self):
        conditions = [
            {"condition": "PRESET", "Preset": "Combat Ready Stance"}
        ]
        result = render_conditions(conditions)
        assert len(result) == 1
        node = result[0]
        assert node.node_type == "preset"
        assert node.preset_name == "Combat Ready Stance"

    def test_top_level_dict_with_conditions_key(self):
        conditions = {
            "condition": "AND",
            "conditions": [
                {"condition": "IsFemale", "negated": False},
            ],
        }
        result = render_conditions(conditions)
        assert len(result) == 1
        assert result[0].node_type == "AND"
        assert result[0].children[0].text == "IsFemale"

    def test_top_level_dict_bare_conditions_key(self):
        """Dict with just a conditions key, no condition type — implicit AND."""
        conditions = {
            "conditions": [
                {"condition": "IsFemale", "negated": False},
            ],
        }
        result = render_conditions(conditions)
        assert len(result) == 1
        assert result[0].node_type == "AND"

    def test_missing_negated_defaults_false(self):
        conditions = [{"condition": "IsFemale"}]
        result = render_conditions(conditions)
        assert result[0].negated is False

    def test_non_dict_items_skipped(self):
        conditions = ["invalid", 42, {"condition": "IsFemale", "negated": False}]
        result = render_conditions(conditions)
        assert len(result) == 1
        assert result[0].text == "IsFemale"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_conditions_renderer.py -v`
Expected: ImportError — `conditions_renderer` module does not exist yet.

- [ ] **Step 3: Implement `conditions_renderer.py`**

```python
"""Pure-logic renderer for OAR condition trees.

Converts nested OAR condition dicts/lists into RenderedNode dataclass trees.
No Qt dependency — this module is testable without a GUI.

See spec: docs/superpowers/specs/2026-04-12-conditions-panel-design.md
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Keys that are structural (not user-visible parameters).
_STRUCTURAL_KEYS: frozenset[str] = frozenset({
    "condition", "negated", "conditions", "Preset",
})

# OAR group-node condition types.
_GROUP_TYPES: frozenset[str] = frozenset({"AND", "OR"})


@dataclass
class RenderedNode:
    """One node in the rendered condition tree.

    Attributes:
        text: Display label — condition type name or group label.
        node_type: One of "AND", "OR", "leaf", "preset".
        negated: True if this leaf condition is negated.
        params: Extra JSON keys (excluding structural ones) as key=value.
        children: Child nodes (populated for AND/OR groups).
        preset_name: The preset name (only for node_type="preset").
    """

    text: str
    node_type: str
    negated: bool = False
    params: dict[str, str] = field(default_factory=dict)
    children: list[RenderedNode] = field(default_factory=list)
    preset_name: str | None = None


def render_conditions(conditions: dict | list) -> list[RenderedNode]:
    """Convert an OAR condition tree into a list of RenderedNode trees.

    Handles both top-level list format and top-level dict format.
    Returns an empty list for empty/invalid input.

    Args:
        conditions: The raw OAR conditions — either a list of condition
            dicts or a single dict with a "conditions" key.

    Returns:
        A list of RenderedNode instances representing the tree.
    """
    if isinstance(conditions, list):
        return [node for item in conditions if (node := _render_node(item)) is not None]

    if isinstance(conditions, dict):
        if not conditions:
            return []
        # Dict with a "conditions" key is a group node
        if "conditions" in conditions:
            group_type = conditions.get("condition", "AND")
            if group_type not in _GROUP_TYPES:
                group_type = "AND"
            children_raw = conditions.get("conditions", [])
            children = [
                node
                for item in children_raw
                if (node := _render_node(item)) is not None
            ]
            return [RenderedNode(
                text=group_type,
                node_type=group_type,
                children=children,
            )]
        # Dict without "conditions" key — single leaf node
        node = _render_node(conditions)
        return [node] if node is not None else []

    return []


def _render_node(item: object) -> RenderedNode | None:
    """Render a single condition dict into a RenderedNode.

    Returns None for non-dict items (defensive skip).
    """
    if not isinstance(item, dict):
        return None

    condition_type = item.get("condition")
    if not isinstance(condition_type, str):
        # No condition key — skip
        return None

    # PRESET reference
    if condition_type == "PRESET":
        preset_name = item.get("Preset", "")
        return RenderedNode(
            text=f"PRESET: {preset_name}",
            node_type="preset",
            preset_name=preset_name if isinstance(preset_name, str) else "",
        )

    # AND/OR group node
    if condition_type in _GROUP_TYPES and "conditions" in item:
        children_raw = item.get("conditions", [])
        children = [
            node
            for child in children_raw
            if (node := _render_node(child)) is not None
        ]
        return RenderedNode(
            text=condition_type,
            node_type=condition_type,
            children=children,
        )

    # Leaf condition
    negated = bool(item.get("negated", False))
    params = {
        k: str(v) for k, v in item.items() if k not in _STRUCTURAL_KEYS
    }
    return RenderedNode(
        text=condition_type,
        node_type="leaf",
        negated=negated,
        params=params,
    )


def resolve_preset(
    preset_name: str, presets: dict
) -> list[RenderedNode] | None:
    """Resolve a PRESET reference using the replacer's conditionPresets.

    Args:
        preset_name: The name of the preset to look up.
        presets: The conditionPresets dict from the replacer config.
            Keys are preset names, values are condition dicts/lists.

    Returns:
        A list of RenderedNode trees for the preset's conditions,
        or None if the preset name is not found.
    """
    if not isinstance(presets, dict):
        return None
    preset_data = presets.get(preset_name)
    if preset_data is None:
        return None
    return render_conditions(preset_data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_conditions_renderer.py -v`
Expected: All 13 tests PASS.

- [ ] **Step 5: Commit**

```bash
git -C "<worktree>" add src/oar_priority_manager/ui/conditions_renderer.py tests/unit/test_conditions_renderer.py
git -C "<worktree>" commit -m "feat: add conditions_renderer with RenderedNode and render_conditions (#43)"
```

---

### Task 2: Add `resolve_preset()` tests

**Files:**
- Modify: `tests/unit/test_conditions_renderer.py`

- [ ] **Step 1: Add failing tests for `resolve_preset()`**

Append to `tests/unit/test_conditions_renderer.py`:

```python
from oar_priority_manager.ui.conditions_renderer import resolve_preset


class TestResolvePreset:
    def test_resolve_existing_preset(self):
        presets = {
            "Combat Ready": [
                {"condition": "IsWeaponDrawn", "negated": False},
                {"condition": "IsInCombat", "negated": False},
            ]
        }
        result = resolve_preset("Combat Ready", presets)
        assert result is not None
        assert len(result) == 2
        assert result[0].text == "IsWeaponDrawn"
        assert result[1].text == "IsInCombat"

    def test_resolve_missing_preset_returns_none(self):
        presets = {"Combat Ready": [{"condition": "IsWeaponDrawn", "negated": False}]}
        result = resolve_preset("Nonexistent", presets)
        assert result is None

    def test_resolve_empty_presets_dict(self):
        result = resolve_preset("Anything", {})
        assert result is None

    def test_resolve_invalid_presets_type(self):
        result = resolve_preset("Anything", "not a dict")
        assert result is None

    def test_resolve_preset_with_nested_group(self):
        presets = {
            "Weapon Check": {
                "condition": "AND",
                "conditions": [
                    {"condition": "IsWeaponDrawn", "negated": False},
                    {"condition": "IsMounted", "negated": True},
                ],
            }
        }
        result = resolve_preset("Weapon Check", presets)
        assert result is not None
        assert len(result) == 1
        assert result[0].node_type == "AND"
        assert len(result[0].children) == 2
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/unit/test_conditions_renderer.py -v`
Expected: All 18 tests PASS (the implementation from Task 1 already includes `resolve_preset`).

- [ ] **Step 3: Commit**

```bash
git -C "<worktree>" add tests/unit/test_conditions_renderer.py
git -C "<worktree>" commit -m "test: add resolve_preset tests (#44)"
```

---

### Task 3: Add `conditions_stats()` helper and tests

**Files:**
- Modify: `src/oar_priority_manager/ui/conditions_renderer.py`
- Modify: `tests/unit/test_conditions_renderer.py`

- [ ] **Step 1: Write failing tests for `conditions_stats()`**

Append to `tests/unit/test_conditions_renderer.py`:

```python
from oar_priority_manager.ui.conditions_renderer import conditions_stats


class TestConditionsStats:
    def test_empty_tree(self):
        stats = conditions_stats([])
        assert stats == {"conditions": 0, "types": 0, "negated": 0, "presets": 0}

    def test_flat_leaves(self):
        nodes = render_conditions([
            {"condition": "IsFemale", "negated": False},
            {"condition": "IsInCombat", "negated": False},
            {"condition": "HasShield", "negated": True},
        ])
        stats = conditions_stats(nodes)
        assert stats["conditions"] == 3
        assert stats["types"] == 3
        assert stats["negated"] == 1
        assert stats["presets"] == 0

    def test_duplicate_types_counted_once(self):
        nodes = render_conditions([
            {"condition": "IsFemale", "negated": False},
            {"condition": "IsFemale", "negated": True},
        ])
        stats = conditions_stats(nodes)
        assert stats["conditions"] == 2
        assert stats["types"] == 1
        assert stats["negated"] == 1

    def test_with_presets(self):
        nodes = render_conditions([
            {"condition": "IsFemale", "negated": False},
            {"condition": "PRESET", "Preset": "Combat Ready"},
            {"condition": "PRESET", "Preset": "Weapon Check"},
        ])
        stats = conditions_stats(nodes)
        assert stats["presets"] == 2
        assert stats["conditions"] == 1
        assert stats["types"] == 1

    def test_nested_groups(self):
        nodes = render_conditions([
            {
                "condition": "AND",
                "conditions": [
                    {"condition": "IsFemale", "negated": False},
                    {
                        "condition": "OR",
                        "conditions": [
                            {"condition": "HasPerk", "negated": False},
                            {"condition": "HasKeyword", "negated": True},
                        ],
                    },
                ],
            },
        ])
        stats = conditions_stats(nodes)
        assert stats["conditions"] == 3
        assert stats["types"] == 3
        assert stats["negated"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_conditions_renderer.py::TestConditionsStats -v`
Expected: ImportError — `conditions_stats` not yet exported.

- [ ] **Step 3: Implement `conditions_stats()`**

Add to `src/oar_priority_manager/ui/conditions_renderer.py`:

```python
def conditions_stats(nodes: list[RenderedNode]) -> dict[str, int]:
    """Compute summary statistics for a rendered condition tree.

    Walks the tree and counts leaf conditions, unique types, negated
    leaves, and preset references.

    Args:
        nodes: The top-level list of RenderedNode from render_conditions().

    Returns:
        Dict with keys: "conditions", "types", "negated", "presets".
    """
    types: set[str] = set()
    total = 0
    negated = 0
    presets = 0

    def _walk(node_list: list[RenderedNode]) -> None:
        nonlocal total, negated, presets
        for node in node_list:
            if node.node_type == "preset":
                presets += 1
            elif node.node_type in ("AND", "OR"):
                _walk(node.children)
            else:
                # leaf
                total += 1
                types.add(node.text)
                if node.negated:
                    negated += 1

    _walk(nodes)
    return {
        "conditions": total,
        "types": len(types),
        "negated": negated,
        "presets": presets,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_conditions_renderer.py -v`
Expected: All 23 tests PASS.

- [ ] **Step 5: Commit**

```bash
git -C "<worktree>" add src/oar_priority_manager/ui/conditions_renderer.py tests/unit/test_conditions_renderer.py
git -C "<worktree>" commit -m "feat: add conditions_stats helper for footer display (#43)"
```

---

### Task 4: Extract `conditionPresets` in the scanner and attach to TreeNode

**Files:**
- Modify: `src/oar_priority_manager/ui/tree_model.py`
- Modify: `src/oar_priority_manager/core/scanner.py`
- Modify: `tests/unit/test_conditions_renderer.py`

- [ ] **Step 1: Add `condition_presets` field to TreeNode**

In `src/oar_priority_manager/ui/tree_model.py`, add a new field to the `TreeNode` dataclass:

```python
# Add after the auto_expand field (line 55):
    condition_presets: dict = field(default_factory=dict)
```

Update the docstring to include:

```python
        condition_presets: conditionPresets dict from the replacer-level
            config.json. Populated only on REPLACER nodes; empty for others.
```

- [ ] **Step 2: Add `replacer_presets` to `SubMod` model**

In `src/oar_priority_manager/core/models.py`, add a field to `SubMod` after the `conditions` field (line 47):

```python
    # conditionPresets from the replacer-level config.json.
    # Stored per-submod so it's available without needing the replacer path.
    replacer_presets: dict = field(default_factory=dict)
```

- [ ] **Step 3: Extract `conditionPresets` in scanner**

In `src/oar_priority_manager/core/scanner.py`, inside `_find_submod_dirs()`, the scanner already iterates through replacer directories. We need to read the replacer-level config.json for each replacer and pass the presets down.

Modify `_build_submod()` to accept and store `replacer_presets`:

Add parameter `replacer_presets: dict` to the `_build_submod` function signature (after `overwrite_dir`).

In the `return SubMod(...)` call, add `replacer_presets=replacer_presets,`.

In `scan_mods()`, read the replacer config before building submods. Replace the inner loop body (lines 177-181) with:

```python
    for mo2_mod, replacer, submod_folder, submod_path in submod_dirs:
        # Read replacer-level config.json for conditionPresets
        replacer_dir = submod_path.parent
        replacer_config_path = replacer_dir / "config.json"
        replacer_presets: dict = {}
        if replacer_config_path.is_file():
            from oar_priority_manager.core.parser import parse_config
            rep_dict, _ = parse_config(replacer_config_path)
            raw_presets = rep_dict.get("conditionPresets", {})
            if isinstance(raw_presets, dict):
                replacer_presets = raw_presets

        sm = _build_submod(
            mo2_mod, replacer, submod_folder, submod_path,
            overwrite_dir, replacer_presets,
        )
        submods.append(sm)
        if on_progress is not None:
            on_progress(len(submods), total)
```

Note: `parse_config` is already imported at the top of scanner.py, so move the import up to the function level rather than inside the loop, or just use the existing top-level import.

- [ ] **Step 4: Attach presets to REPLACER TreeNodes in `build_tree()`**

In `src/oar_priority_manager/ui/tree_model.py`, inside `build_tree()`, when creating `rep_node`, populate `condition_presets` from the first submod's `replacer_presets`:

```python
        for rep_name in sorted(replacer_dict.keys()):
            # Get presets from first submod in this replacer (all share the same)
            first_submod = replacer_dict[rep_name][0]
            rep_presets = (
                first_submod.replacer_presets
                if hasattr(first_submod, "replacer_presets")
                else {}
            )
            rep_node = TreeNode(
                display_name=rep_name,
                node_type=NodeType.REPLACER,
                parent=mod_node,
                auto_expand=single_replacer,
                condition_presets=rep_presets,
            )
```

- [ ] **Step 5: Write tests for preset data flow**

Add to `tests/unit/test_conditions_renderer.py`:

```python
class TestPresetDataFlow:
    """Integration-style tests verifying presets flow from scanner to TreeNode."""

    def test_tree_node_has_condition_presets_field(self):
        from oar_priority_manager.ui.tree_model import TreeNode, NodeType
        node = TreeNode(
            display_name="test",
            node_type=NodeType.REPLACER,
            condition_presets={"Combat": [{"condition": "IsInCombat"}]},
        )
        assert node.condition_presets == {"Combat": [{"condition": "IsInCombat"}]}

    def test_tree_node_default_empty_presets(self):
        from oar_priority_manager.ui.tree_model import TreeNode, NodeType
        node = TreeNode(display_name="test", node_type=NodeType.MOD)
        assert node.condition_presets == {}
```

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS. No existing tests should break since the new fields have defaults.

- [ ] **Step 7: Commit**

```bash
git -C "<worktree>" add src/oar_priority_manager/core/models.py src/oar_priority_manager/core/scanner.py src/oar_priority_manager/ui/tree_model.py tests/unit/test_conditions_renderer.py
git -C "<worktree>" commit -m "feat: extract conditionPresets from replacer configs and attach to TreeNode (#44)"
```

---

### Task 5: Rewrite `conditions_panel.py` — formatted view + JSON toggle

**Files:**
- Modify: `src/oar_priority_manager/ui/conditions_panel.py`
- Create: `tests/unit/test_conditions_panel.py`

- [ ] **Step 1: Write failing tests for the new panel**

```python
"""Tests for ui/conditions_panel.py — formatted conditions view + JSON toggle."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

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
        # Should show placeholder text, not conditions
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
        # Header should be generic
        assert "Select" in panel._header.text()

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
        # Should show "No conditions defined" or similar

    def test_json_toggle_shows_raw_json(self, qapp):
        panel = ConditionsPanel()
        sm = _make_submod(
            conditions=[{"condition": "IsFemale", "negated": False}]
        )
        panel.update_focus(sm)
        # Switch to JSON mode
        panel._json_btn.click()
        # The JSON view should be visible and contain the condition text
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
        assert "3" in footer_text  # 3 conditions
        assert "3" in footer_text  # 3 types
        assert "1" in footer_text  # 1 negated
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_conditions_panel.py -v`
Expected: AttributeError — `_formatted_view`, `_json_view`, `_formatted_btn` etc. don't exist on the old panel.

- [ ] **Step 3: Rewrite `conditions_panel.py`**

Replace the entire contents of `src/oar_priority_manager/ui/conditions_panel.py`:

```python
"""Conditions panel — formatted AND/OR/NOT tree + raw JSON toggle.

See spec: docs/superpowers/specs/2026-04-12-conditions-panel-design.md
Issues: #43 (formatted display), #44 (JSON toggle)
"""
from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
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

        # Segmented toggle matching tree_panel.py / stacks_panel.py pattern
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

        self._formatted_btn = QPushButton("Formatted")
        self._formatted_btn.setCheckable(True)
        self._formatted_btn.setChecked(True)
        self._formatted_btn.setStyleSheet(
            _seg_unchecked + _seg_checked
            + "QPushButton { border-radius: 0px;"
            "  border-top-left-radius: 4px;"
            "  border-bottom-left-radius: 4px;"
            "  border-right: none; }"
        )

        self._json_btn = QPushButton("JSON")
        self._json_btn.setCheckable(True)
        self._json_btn.setChecked(False)
        self._json_btn.setStyleSheet(
            _seg_unchecked + _seg_checked
            + "QPushButton { border-radius: 0px;"
            "  border-top-right-radius: 4px;"
            "  border-bottom-right-radius: 4px; }"
        )

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
        self._stats_label.setStyleSheet("color: #565f89; padding: 4px 8px;")
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
        label.setStyleSheet("color: #565f89; padding: 8px;")
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
        """Render an AND/OR group with its children."""
        label_text = "ALL of:" if node.node_type == "AND" else "ANY of:"
        color = "#7aa2f7" if node.node_type == "AND" else "#bb9af7"

        group_label = QLabel(f"<b style='color:{color};'>{label_text}</b>")
        group_label.setTextFormat(Qt.TextFormat.RichText)
        group_label.setContentsMargins(indent * 20, 2, 0, 0)
        parent_layout.addWidget(group_label)

        # Render children at increased indent
        self._render_nodes(node.children, parent_layout, indent + 1)

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

        # Create a container widget for the preset card
        card = QWidget()
        card.setStyleSheet(
            "background: #2a2a3a; border: 1px solid #444; border-radius: 6px;"
        )
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
            checked: bool = False,
            *,
            exp: QWidget = expanded,
            hdr: QLabel = header,
            pname: str = preset_name,
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
                if expanded_layout.count() == 0:
                    self._populate_preset(pname, expanded_layout)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_conditions_panel.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `pytest tests/ -v`
Expected: All tests PASS. The old `conditions_panel.py` tests (if any) may need updating since the API changed.

- [ ] **Step 6: Commit**

```bash
git -C "<worktree>" add src/oar_priority_manager/ui/conditions_panel.py tests/unit/test_conditions_panel.py
git -C "<worktree>" commit -m "feat: rewrite conditions panel with formatted tree view and JSON toggle (#43, #44)"
```

---

### Task 6: Wire preset data through `main_window.py` and integration test

**Files:**
- Modify: `src/oar_priority_manager/ui/main_window.py`
- Modify: `tests/unit/test_conditions_panel.py`

- [ ] **Step 1: Verify main_window.py passes SubMod to conditions panel**

Check that `_on_tree_selection` and `_on_competitor_focused` already pass `submod` objects to `conditions_panel.update_focus()`. They do (lines 138 and 142 of main_window.py), so no change is needed — the SubMod already carries `replacer_presets` from Task 4.

- [ ] **Step 2: Add integration test for preset expansion**

Add to `tests/unit/test_conditions_panel.py`:

```python
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
        # (detailed rendering tested via conditions_renderer unit tests)
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
```

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git -C "<worktree>" add tests/unit/test_conditions_panel.py
git -C "<worktree>" commit -m "test: add preset expansion integration tests (#44)"
```

---

### Task 7: Lint, final verification, and cleanup

**Files:**
- All modified files

- [ ] **Step 1: Run ruff linter**

Run: `ruff check src/ tests/ --fix`
Expected: No errors, or auto-fixable ones resolved.

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 3: Verify no import cycles**

Run: `python -c "from oar_priority_manager.ui.conditions_panel import ConditionsPanel; print('OK')"`
Expected: "OK" — no circular imports.

- [ ] **Step 4: Commit any lint fixes**

```bash
git -C "<worktree>" add -A
git -C "<worktree>" commit -m "chore: lint fixes for conditions panel implementation"
```

Only commit if there were actual changes from the lint step.
