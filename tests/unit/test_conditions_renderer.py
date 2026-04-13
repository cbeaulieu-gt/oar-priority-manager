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
