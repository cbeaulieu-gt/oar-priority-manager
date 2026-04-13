"""Tests for ui/conditions_renderer.py — pure-logic condition tree renderer."""
from __future__ import annotations

from oar_priority_manager.ui.conditions_renderer import (
    conditions_stats,
    render_conditions,
    resolve_preset,
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

    def test_and_group_capital_conditions_key(self):
        """Real OAR data uses capital-C 'Conditions' in AND/OR groups."""
        conditions = [
            {
                "condition": "AND",
                "requiredVersion": "1.0.0.0",
                "Conditions": [
                    {"condition": "IsFemale", "requiredVersion": "1.0.0.0"},
                    {"condition": "IsInCombat", "requiredVersion": "1.0.0.0"},
                ],
            }
        ]
        result = render_conditions(conditions)
        assert len(result) == 1
        group = result[0]
        assert group.node_type == "AND"
        assert len(group.children) == 2
        assert group.children[0].text == "IsFemale"
        assert group.children[1].text == "IsInCombat"

    def test_or_group_capital_conditions_key(self):
        """Real OAR OR groups also use capital-C 'Conditions'."""
        conditions = [
            {
                "condition": "OR",
                "requiredVersion": "1.0.0.0",
                "Conditions": [
                    {"condition": "IsFemale", "requiredVersion": "1.0.0.0"},
                    {"condition": "IsInCombat", "requiredVersion": "1.0.0.0"},
                ],
            }
        ]
        result = render_conditions(conditions)
        assert result[0].node_type == "OR"
        assert len(result[0].children) == 2

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

    def test_nested_real_oar_format(self):
        """Nested AND/OR with capital-C Conditions and requiredVersion throughout."""
        conditions = [
            {
                "condition": "OR",
                "requiredVersion": "1.0.0.0",
                "Conditions": [
                    {
                        "condition": "AND",
                        "requiredVersion": "1.0.0.0",
                        "Conditions": [
                            {"condition": "IsFemale", "requiredVersion": "1.0.0.0"},
                            {"condition": "IsSneaking", "requiredVersion": "1.0.0.0"},
                        ],
                    },
                    {"condition": "IsInCombat", "requiredVersion": "1.0.0.0"},
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

    def test_top_level_dict_with_capital_conditions_key(self):
        """Top-level dict using capital-C 'Conditions' (real OAR format)."""
        conditions = {
            "condition": "OR",
            "requiredVersion": "1.0.0.0",
            "Conditions": [
                {"condition": "IsFemale", "requiredVersion": "1.0.0.0"},
                {"condition": "IsInCombat", "requiredVersion": "1.0.0.0"},
            ],
        }
        result = render_conditions(conditions)
        assert len(result) == 1
        assert result[0].node_type == "OR"
        assert len(result[0].children) == 2
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

    def test_required_version_filtered_from_leaf_params(self):
        """requiredVersion is structural noise and must not appear in params."""
        conditions = [
            {
                "condition": "IsFemale",
                "requiredVersion": "1.0.0.0",
                "negated": False,
            }
        ]
        result = render_conditions(conditions)
        assert "requiredVersion" not in result[0].params

    def test_disabled_filtered_from_leaf_params(self):
        """disabled is OAR metadata and must not appear in params."""
        conditions = [
            {
                "condition": "IsInCombat",
                "requiredVersion": "1.0.0.0",
                "disabled": True,
            }
        ]
        result = render_conditions(conditions)
        assert "disabled" not in result[0].params
        assert "requiredVersion" not in result[0].params

    def test_user_meaningful_params_still_visible(self):
        """formID and pluginName are user-meaningful and must still appear."""
        conditions = [
            {
                "condition": "HasPerk",
                "requiredVersion": "1.0.0.0",
                "negated": False,
                "formID": "0x00012345",
                "pluginName": "Skyrim.esm",
            }
        ]
        result = render_conditions(conditions)
        assert result[0].params == {"formID": "0x00012345", "pluginName": "Skyrim.esm"}

    def test_missing_negated_defaults_false(self):
        conditions = [{"condition": "IsFemale"}]
        result = render_conditions(conditions)
        assert result[0].negated is False

    def test_non_dict_items_skipped(self):
        conditions = ["invalid", 42, {"condition": "IsFemale", "negated": False}]
        result = render_conditions(conditions)
        assert len(result) == 1
        assert result[0].text == "IsFemale"


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


class TestPresetDataFlow:
    """Integration-style tests verifying presets flow from scanner to TreeNode."""

    def test_tree_node_has_condition_presets_field(self):
        from oar_priority_manager.ui.tree_model import NodeType, TreeNode
        node = TreeNode(
            display_name="test",
            node_type=NodeType.REPLACER,
            condition_presets={"Combat": [{"condition": "IsInCombat"}]},
        )
        assert node.condition_presets == {"Combat": [{"condition": "IsInCombat"}]}

    def test_tree_node_default_empty_presets(self):
        from oar_priority_manager.ui.tree_model import NodeType, TreeNode
        node = TreeNode(display_name="test", node_type=NodeType.MOD)
        assert node.condition_presets == {}
