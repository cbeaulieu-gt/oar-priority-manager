"""Pure-logic renderer for OAR condition trees.

Converts nested OAR condition dicts/lists into RenderedNode dataclass trees.
No Qt dependency — this module is testable without a GUI.

See spec: docs/superpowers/specs/2026-04-12-conditions-panel-design.md
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Keys that are structural (not user-visible parameters).
# "Conditions" (capital-C) is the real OAR format for AND/OR child lists.
# "requiredVersion" and "disabled" appear on almost every real condition but
# carry no user-meaningful semantic — omit them from the params display.
_STRUCTURAL_KEYS: frozenset[str] = frozenset({
    "condition", "negated", "conditions", "Conditions", "Preset",
    "requiredVersion", "disabled",
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
        return [
            node for item in conditions if (node := _render_node(item)) is not None
        ]

    if isinstance(conditions, dict):
        if not conditions:
            return []
        # Dict with a "conditions"/"Conditions" key is a group node.
        # Real OAR data uses capital-C "Conditions"; support both.
        children_key = "Conditions" if "Conditions" in conditions else "conditions"
        if children_key in conditions:
            group_type = conditions.get("condition", "AND")
            if group_type not in _GROUP_TYPES:
                group_type = "AND"
            children_raw = conditions.get(children_key, [])
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
        # Dict without "conditions"/"Conditions" key — single leaf node
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
        return None

    # PRESET reference
    if condition_type == "PRESET":
        preset_name = item.get("Preset", "")
        return RenderedNode(
            text=f"PRESET: {preset_name}",
            node_type="preset",
            preset_name=preset_name if isinstance(preset_name, str) else "",
        )

    # AND/OR group node.
    # Real OAR uses capital-C "Conditions"; support both case variants.
    children_key = "Conditions" if "Conditions" in item else "conditions"
    if condition_type in _GROUP_TYPES and children_key in item:
        children_raw = item.get(children_key, [])
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
