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


# Animation filename patterns for each tag category.
_ANIM_PATTERNS: list[tuple[list[str], TagCategory]] = [
    (["_attack", "_block", "_stagger", "_recoil", "_power"], TagCategory.COMBAT),
    (["_run", "_walk", "_sprint", "_swim", "_jump"], TagCategory.MOVEMENT),
    (["sneak"], TagCategory.SNEAK),
    (["_idle", "mt_idle", "idle_"], TagCategory.IDLE),
    (["_sit", "_chair", "_bed", "_lean"], TagCategory.FURNITURE),
    (["_equip", "_sheathe", "_draw", "_unequip"], TagCategory.EQUIPMENT),
    (["_cast", "mlh_", "mrh_"], TagCategory.MAGIC),
]

_ANIM_VOTE_THRESHOLD: float = 0.30


def _classify_animation(filename: str) -> set[TagCategory]:
    """Classify a single animation filename into zero or more tag categories.

    Args:
        filename: Animation filename (with or without extension).

    Returns:
        Set of matching TagCategory values (may be empty).
    """
    name = filename.rsplit(".", 1)[0].lower() if "." in filename else filename.lower()
    matched: set[TagCategory] = set()
    for patterns, tag in _ANIM_PATTERNS:
        for pattern in patterns:
            if pattern in name:
                matched.add(tag)
                break
    return matched


def _layer2_animations(
    submod: SubMod, existing: set[TagCategory]
) -> set[TagCategory]:
    """Layer 2: animation filename pattern voting.

    Each animation is classified, then a tag applies only if >= 30% match.

    Args:
        submod: The SubMod whose animations list will be examined.
        existing: Tags already assigned by earlier layers (unused here but
            present for pipeline signature consistency).

    Returns:
        Set of TagCategory values that met the voting threshold.
    """
    if not submod.animations:
        return set()

    total = len(submod.animations)
    votes: dict[TagCategory, int] = {}

    for anim in submod.animations:
        for tag in _classify_animation(anim):
            votes[tag] = votes.get(tag, 0) + 1

    tags: set[TagCategory] = set()
    for tag, count in votes.items():
        if count / total >= _ANIM_VOTE_THRESHOLD:
            tags.add(tag)

    return tags


# Conditions ignored during tag computation (non-standard plugins, structural).
_IGNORED_CONDITION_PREFIXES: tuple[str, ...] = ("IED_", "SDS_")
_IGNORED_CONDITIONS: frozenset[str] = frozenset({"AND", "OR", "PRESET"})

# Distinctive conditions — always count regardless of total condition count.
_DISTINCTIVE_CONDITIONS: dict[str, TagCategory] = {
    "IsSneaking": TagCategory.SNEAK,
    "IsFemale": TagCategory.GENDER,
    "IsChild": TagCategory.NPC,
    "IsOnMount": TagCategory.MOVEMENT,
}

# Non-distinctive conditions — only count if submod has <= 3 unique condition types.
_NON_DISTINCTIVE_CONDITIONS: dict[str, TagCategory] = {
    "IsEquippedType": TagCategory.EQUIPMENT,
    "IsWornInSlotHasKeyword": TagCategory.EQUIPMENT,
    "IsInCombat": TagCategory.COMBAT,
    "IsCombatState": TagCategory.COMBAT,
    "IsAttacking": TagCategory.COMBAT,
    "IsBlocking": TagCategory.COMBAT,
    "IsRunning": TagCategory.MOVEMENT,
    "IsSprinting": TagCategory.MOVEMENT,
    "HasMagicEffect": TagCategory.MAGIC,
    "HasSpell": TagCategory.MAGIC,
    "IsActorBase": TagCategory.NPC,
    "IsRace": TagCategory.NPC,
    "IsClass": TagCategory.NPC,
    "IsVoiceType": TagCategory.NPC,
    "SitSleepState": TagCategory.FURNITURE,
    "CurrentFurniture": TagCategory.FURNITURE,
    "CurrentFurnitureHasKeyword": TagCategory.FURNITURE,
}

_FEW_CONDITIONS_THRESHOLD: int = 3


def _layer3_conditions(
    submod: SubMod, existing: set[TagCategory]
) -> set[TagCategory]:
    """Layer 3: condition type refinement with precondition filter.

    Only adds tags NOT already present from layers 1-2. Distinctive
    conditions always count; non-distinctive only count when the submod
    has few unique condition types (likely definitional, not preconditions).

    Args:
        submod: The SubMod whose condition_types_present will be examined.
        existing: Tags already assigned by layers 1-2.

    Returns:
        Set of new TagCategory values not already in existing.
    """
    relevant = {
        ct for ct in submod.condition_types_present
        if ct not in _IGNORED_CONDITIONS
        and not any(ct.startswith(p) for p in _IGNORED_CONDITION_PREFIXES)
    }

    if not relevant:
        return set()

    tags: set[TagCategory] = set()
    few_conditions = len(relevant) <= _FEW_CONDITIONS_THRESHOLD

    for ct in relevant:
        if ct in _DISTINCTIVE_CONDITIONS:
            tag = _DISTINCTIVE_CONDITIONS[ct]
            if ct == "IsFemale" and ct in submod.condition_types_negated:
                continue
            if tag not in existing:
                tags.add(tag)
        elif few_conditions and ct in _NON_DISTINCTIVE_CONDITIONS:
            tag = _NON_DISTINCTIVE_CONDITIONS[ct]
            if tag not in existing:
                tags.add(tag)

    return tags
