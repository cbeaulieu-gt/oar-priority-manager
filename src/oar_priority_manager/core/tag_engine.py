"""Category tag auto-detection engine for OAR Priority Manager.

Computes category tags for submods based on a 3-layer rule pipeline:
  1. Folder/mod name keywords (highest confidence)
  2. Animation filename patterns (primary behavioral signal)
  3. Condition types (secondary refinement with precondition filter)

See design spec: docs/superpowers/specs/2026-04-14-category-tags-design.md
"""
from __future__ import annotations

import re
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from oar_priority_manager.core.models import SubMod


class TagCategory(Enum):
    """Category tag with display metadata.

    Each member is a tuple of (label, sort_order, color_bg, color_fg, color_border).
    """

    NSFW = ("NSFW", 0, "#5c2d4a", "#f0a0d0", "#8b446e")
    COMBAT = ("Combat", 1, "#5c2d2d", "#f0a0a0", "#8b4444")
    EQUIPMENT = ("Equipment", 2, "#3d3d3d", "#b0b0b0", "#5a5a5a")
    FURNITURE = ("Furniture", 3, "#5c4a2d", "#f0d0a0", "#8b6e44")
    GENDER = ("Gender", 4, "#5c5c2d", "#f0f0a0", "#8b8b44")
    IDLE = ("Idle", 5, "#2d5c4a", "#a0f0d0", "#448b6e")
    MAGIC = ("Magic", 6, "#4a2d5c", "#d0a0f0", "#6e448b")
    MOVEMENT = ("Movement", 7, "#2d3a5c", "#a0b8f0", "#44578b")
    NPC = ("NPC", 8, "#2d4a5c", "#a0d0f0", "#446e8b")
    SNEAK = ("Sneak", 9, "#3d2d5c", "#b8a0f0", "#5b448b")

    def __init__(
        self,
        label: str,
        sort_order: int,
        color_bg: str,
        color_fg: str,
        color_border: str,
    ) -> None:
        self.label = label
        self.sort_order = sort_order
        self.color_bg = color_bg
        self.color_fg = color_fg
        self.color_border = color_border


def compute_tags(submod: SubMod) -> set[TagCategory]:
    """Compute category tags for a submod using the 3-layer rule pipeline.

    Args:
        submod: The SubMod to tag.

    Returns:
        Set of matching TagCategory values (may be empty).
    """
    tags: set[TagCategory] = set()
    tags |= _layer1_keywords(submod)
    tags |= _layer2_animations(submod, tags)
    tags |= _layer3_conditions(submod, tags)
    return tags


# Module-level constant: keyword -> TagCategory mapping.
_KEYWORD_RULES: list[tuple[list[str], TagCategory]] = [
    # NSFW
    (
        [
            "modesty", "nude", "naked", "nsfw", "adult", "sexlab",
            "ostim", "pregnancy", "inflation", "flower girl", "billyy", "leito",
        ],
        TagCategory.NSFW,
    ),
    # Gender — whole-word only (handled by regex in _layer1_keywords)
    (["female", "male"], TagCategory.GENDER),
    # NPC — multi-word first
    (["cart driver", "npc", "children", "child"], TagCategory.NPC),
    # Sneak
    (["sneak"], TagCategory.SNEAK),
    # Combat — multi-word first
    (
        ["ashes of war", "boss fight", "combat", "stagger", "block", "dodge"],
        TagCategory.COMBAT,
    ),
    # Movement
    (["traversal", "clamber", "swimming", "jump"], TagCategory.MOVEMENT),
]

# Gender keywords need word-boundary matching to avoid "female" in "maleficent".
_WHOLE_WORD_TAGS: frozenset[TagCategory] = frozenset({TagCategory.GENDER})


def _layer1_keywords(submod: SubMod) -> set[TagCategory]:
    """Layer 1: folder/mod name keyword matching.

    Scans mo2_mod, replacer, and name for keyword hits. Gender keywords
    use whole-word matching; others use substring matching.
    """
    tags: set[TagCategory] = set()
    text = f"{submod.mo2_mod} {submod.replacer} {submod.name}".lower()

    for keywords, tag in _KEYWORD_RULES:
        if tag in tags:
            continue
        for kw in keywords:
            if tag in _WHOLE_WORD_TAGS:
                if re.search(rf"\b{re.escape(kw)}\b", text):
                    tags.add(tag)
                    break
            else:
                if kw in text:
                    tags.add(tag)
                    break

    return tags


def _layer2_animations(
    submod: SubMod, existing: set[TagCategory]
) -> set[TagCategory]:
    """Layer 2: animation filename pattern voting."""
    return set()


def _layer3_conditions(
    submod: SubMod, existing: set[TagCategory]
) -> set[TagCategory]:
    """Layer 3: condition type refinement with precondition filter."""
    return set()
