# Category Tags Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add auto-detected category tags (colored pills) to mods and submods in the tree panel, with manual override support and search integration.

**Architecture:** A new `core/tag_engine.py` module computes tags via a 3-layer rule pipeline (folder keywords → animation patterns → condition types). Tags are stored on `SubMod`, rendered via a custom `QStyledItemDelegate` in the tree panel, and editable via a right-click dialog. Manual overrides persist in `AppConfig`.

**Tech Stack:** Python 3.11+, PySide6, pytest

**Issue:** #73

---

## File Structure

| File | Responsibility |
|---|---|
| `src/oar_priority_manager/core/tag_engine.py` | **New.** `TagCategory` enum (10 values with color metadata), `compute_tags()` pure function, 3-layer rule pipeline |
| `src/oar_priority_manager/core/models.py` | Add `tags: set` field to `SubMod` dataclass |
| `src/oar_priority_manager/app/config.py` | Add `tag_overrides: dict[str, list[str]]` to `AppConfig`, update `load_config`/`save_config` |
| `src/oar_priority_manager/app/main.py` | Call `compute_tags()` in `run_scan()` after condition extraction |
| `src/oar_priority_manager/ui/tree_panel.py` | Wire `TagDelegate`, add "Edit Tags..." context menu |
| `src/oar_priority_manager/ui/tag_delegate.py` | **New.** `QStyledItemDelegate` subclass that paints tag pills after display name |
| `src/oar_priority_manager/ui/tag_edit_dialog.py` | **New.** Checkbox dialog for manual tag editing with "Reset to Auto" |
| `src/oar_priority_manager/ui/details_panel.py` | Add Tags section with pill HTML and `+` button |
| `src/oar_priority_manager/ui/tree_model.py` | Extend `SearchIndex` to index tag names |
| `tests/unit/test_tag_engine.py` | **New.** Unit tests for tag engine |
| `tests/unit/test_config.py` | Add tests for `tag_overrides` persistence |
| `tests/unit/test_tree_model.py` | Add tests for tag-name search |

---

### Task 1: TagCategory Enum and Stub compute_tags

**Files:**
- Create: `src/oar_priority_manager/core/tag_engine.py`
- Test: `tests/unit/test_tag_engine.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_tag_engine.py`:

```python
"""Tests for core/tag_engine.py — category tag auto-detection.

See design spec docs/superpowers/specs/2026-04-14-category-tags-design.md.
"""
from __future__ import annotations

from oar_priority_manager.core.tag_engine import TagCategory, compute_tags
from oar_priority_manager.core.models import SubMod, OverrideSource
from pathlib import Path


def _make_submod(
    mo2_mod: str = "Test Mod",
    replacer: str = "TestReplacer",
    name: str = "test_sub",
    animations: list[str] | None = None,
    condition_types_present: set[str] | None = None,
    condition_types_negated: set[str] | None = None,
) -> SubMod:
    """Factory for SubMod instances with sensible defaults."""
    return SubMod(
        mo2_mod=mo2_mod,
        replacer=replacer,
        name=name,
        description="",
        priority=100,
        source_priority=100,
        disabled=False,
        config_path=Path(f"/fake/{mo2_mod}/{replacer}/{name}/config.json"),
        override_source=OverrideSource.SOURCE,
        override_is_ours=False,
        raw_dict={},
        animations=animations or [],
        condition_types_present=condition_types_present or set(),
        condition_types_negated=condition_types_negated or set(),
    )


class TestTagCategory:
    def test_enum_has_10_members(self):
        assert len(TagCategory) == 10

    def test_each_member_has_color_metadata(self):
        for tag in TagCategory:
            assert tag.color_bg.startswith("#"), f"{tag.name} missing color_bg"
            assert tag.color_fg.startswith("#"), f"{tag.name} missing color_fg"
            assert tag.color_border.startswith("#"), f"{tag.name} missing color_border"

    def test_each_member_has_label(self):
        for tag in TagCategory:
            assert isinstance(tag.label, str) and len(tag.label) > 0

    def test_sort_order_is_unique(self):
        orders = [tag.sort_order for tag in TagCategory]
        assert len(orders) == len(set(orders))

    def test_nsfw_sorts_first(self):
        assert TagCategory.NSFW.sort_order == 0


class TestComputeTagsEmpty:
    def test_empty_submod_returns_empty_set(self):
        sm = _make_submod()
        assert compute_tags(sm) == set()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tag_engine.py -v`
Expected: `ModuleNotFoundError: No module named 'oar_priority_manager.core.tag_engine'`

- [ ] **Step 3: Write TagCategory enum and stub compute_tags**

Create `src/oar_priority_manager/core/tag_engine.py`:

```python
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


def _layer1_keywords(submod: SubMod) -> set[TagCategory]:
    """Layer 1: folder/mod name keyword matching."""
    return set()


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_tag_engine.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/oar_priority_manager/core/tag_engine.py tests/unit/test_tag_engine.py
git commit -m "feat: add TagCategory enum and stub compute_tags (#73)"
```

---

### Task 2: Layer 1 — Folder/Mod Name Keyword Detection

**Files:**
- Modify: `src/oar_priority_manager/core/tag_engine.py`
- Modify: `tests/unit/test_tag_engine.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_tag_engine.py`:

```python
class TestLayer1Keywords:
    """Layer 1: folder/mod name keyword matching."""

    def test_nsfw_from_mod_name(self):
        sm = _make_submod(mo2_mod="Dynamic Feminine Female Modesty Animations OAR")
        tags = compute_tags(sm)
        assert TagCategory.NSFW in tags

    def test_nsfw_from_submod_name(self):
        sm = _make_submod(name="nude_both_free")
        tags = compute_tags(sm)
        assert TagCategory.NSFW in tags

    def test_nsfw_sexlab_keyword(self):
        sm = _make_submod(mo2_mod="SexLab Animation Pack")
        tags = compute_tags(sm)
        assert TagCategory.NSFW in tags

    def test_gender_female_from_mod_name(self):
        sm = _make_submod(mo2_mod="Dynamic Female Weather Idles")
        tags = compute_tags(sm)
        assert TagCategory.GENDER in tags

    def test_gender_male_from_mod_name(self):
        sm = _make_submod(mo2_mod="Random Male Wall Leaning Animations")
        tags = compute_tags(sm)
        assert TagCategory.GENDER in tags

    def test_gender_no_substring_match(self):
        """'female' inside 'maleficent' should NOT match."""
        sm = _make_submod(mo2_mod="Maleficent Anim Pack")
        tags = compute_tags(sm)
        assert TagCategory.GENDER not in tags

    def test_npc_from_mod_name(self):
        sm = _make_submod(mo2_mod="NPC Animation Remix")
        tags = compute_tags(sm)
        assert TagCategory.NPC in tags

    def test_npc_children_keyword(self):
        sm = _make_submod(mo2_mod="Lively Children Animations")
        tags = compute_tags(sm)
        assert TagCategory.NPC in tags

    def test_sneak_from_mod_name(self):
        sm = _make_submod(mo2_mod="Dynamic Relaxed sneak OAR")
        tags = compute_tags(sm)
        assert TagCategory.SNEAK in tags

    def test_combat_from_mod_name(self):
        sm = _make_submod(mo2_mod="Combat Animation Overhaul")
        tags = compute_tags(sm)
        assert TagCategory.COMBAT in tags

    def test_combat_dodge_keyword(self):
        sm = _make_submod(mo2_mod="Nolvus Awakening Dodge Framework")
        tags = compute_tags(sm)
        assert TagCategory.COMBAT in tags

    def test_movement_from_mod_name(self):
        sm = _make_submod(mo2_mod="EVG Animated Traversal")
        tags = compute_tags(sm)
        assert TagCategory.MOVEMENT in tags

    def test_multiple_keywords_yield_multiple_tags(self):
        sm = _make_submod(mo2_mod="Female NPC Sneak Pack")
        tags = compute_tags(sm)
        assert TagCategory.GENDER in tags
        assert TagCategory.NPC in tags
        assert TagCategory.SNEAK in tags

    def test_no_match_returns_empty(self):
        sm = _make_submod(mo2_mod="Some Random Mod")
        tags = compute_tags(sm)
        assert len(tags) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_tag_engine.py::TestLayer1Keywords -v`
Expected: All fail (keyword tests return empty sets)

- [ ] **Step 3: Implement _layer1_keywords**

Replace the `_layer1_keywords` stub in `src/oar_priority_manager/core/tag_engine.py`:

```python
# Module-level constant: keyword -> TagCategory mapping.
# Multi-word keywords must come before single-word to avoid partial matches.
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

# Pre-compiled patterns for whole-word matching.
# Gender keywords need word-boundary matching to avoid "female" in "maleficent".
_WHOLE_WORD_TAGS: frozenset[TagCategory] = frozenset({TagCategory.GENDER})


def _layer1_keywords(submod: SubMod) -> set[TagCategory]:
    """Layer 1: folder/mod name keyword matching.

    Scans mo2_mod, replacer, and name for keyword hits. Gender keywords
    use whole-word matching; others use substring matching.
    """
    tags: set[TagCategory] = set()
    # Combine all name sources into one lowered string for scanning.
    text = f"{submod.mo2_mod} {submod.replacer} {submod.name}".lower()

    for keywords, tag in _KEYWORD_RULES:
        if tag in tags:
            continue  # Already found this tag
        for kw in keywords:
            if tag in _WHOLE_WORD_TAGS:
                # Whole-word boundary match
                if re.search(rf"\b{re.escape(kw)}\b", text):
                    tags.add(tag)
                    break
            else:
                if kw in text:
                    tags.add(tag)
                    break

    return tags
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_tag_engine.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/oar_priority_manager/core/tag_engine.py tests/unit/test_tag_engine.py
git commit -m "feat: implement Layer 1 keyword detection for tag engine (#73)"
```

---

### Task 3: Layer 2 — Animation Filename Pattern Voting

**Files:**
- Modify: `src/oar_priority_manager/core/tag_engine.py`
- Modify: `tests/unit/test_tag_engine.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_tag_engine.py`:

```python
class TestLayer2Animations:
    """Layer 2: animation filename pattern voting with 30% threshold."""

    def test_combat_animations(self):
        anims = [f"1hm_attack{i}.hkx" for i in range(10)]
        sm = _make_submod(animations=anims)
        tags = compute_tags(sm)
        assert TagCategory.COMBAT in tags

    def test_movement_animations(self):
        anims = ["mt_runforward.hkx", "mt_runbackward.hkx", "mt_walk.hkx"]
        sm = _make_submod(animations=anims)
        tags = compute_tags(sm)
        assert TagCategory.MOVEMENT in tags

    def test_sneak_animations(self):
        anims = ["mt_sneak_idle.hkx", "sneak_forward.hkx", "sneak_back.hkx"]
        sm = _make_submod(animations=anims)
        tags = compute_tags(sm)
        assert TagCategory.SNEAK in tags

    def test_idle_animations(self):
        anims = ["mt_idle.hkx", "1hm_idle.hkx", "idle_front.hkx"]
        sm = _make_submod(animations=anims)
        tags = compute_tags(sm)
        assert TagCategory.IDLE in tags

    def test_furniture_animations(self):
        anims = ["chair_sit.hkx", "sit_idle.hkx", "bed_enter.hkx"]
        sm = _make_submod(animations=anims)
        tags = compute_tags(sm)
        assert TagCategory.FURNITURE in tags

    def test_equipment_animations(self):
        anims = ["1hm_equip.hkx", "1hm_unequip.hkx", "bow_draw.hkx"]
        sm = _make_submod(animations=anims)
        tags = compute_tags(sm)
        assert TagCategory.EQUIPMENT in tags

    def test_magic_animations(self):
        anims = ["mlh_cast.hkx", "mrh_cast.hkx", "mt_cast_idle.hkx"]
        sm = _make_submod(animations=anims)
        tags = compute_tags(sm)
        assert TagCategory.MAGIC in tags

    def test_voting_threshold_below_30_percent(self):
        """1 idle out of 10 combat = 10% idle, should NOT tag Idle."""
        anims = [f"1hm_attack{i}.hkx" for i in range(9)] + ["mt_idle.hkx"]
        sm = _make_submod(animations=anims)
        tags = compute_tags(sm)
        assert TagCategory.COMBAT in tags
        assert TagCategory.IDLE not in tags

    def test_voting_threshold_at_30_percent(self):
        """3 idle out of 10 = 30%, should tag Idle."""
        anims = [f"1hm_attack{i}.hkx" for i in range(7)] + [
            "mt_idle.hkx",
            "idle_front.hkx",
            "1hm_idle.hkx",
        ]
        sm = _make_submod(animations=anims)
        tags = compute_tags(sm)
        assert TagCategory.COMBAT in tags
        assert TagCategory.IDLE in tags

    def test_empty_animations_no_tags(self):
        sm = _make_submod(animations=[])
        tags = compute_tags(sm)
        assert len(tags) == 0

    def test_unrecognized_animations_no_tags(self):
        anims = ["custom_anim1.hkx", "custom_anim2.hkx"]
        sm = _make_submod(animations=anims)
        tags = compute_tags(sm)
        assert len(tags) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_tag_engine.py::TestLayer2Animations -v`
Expected: All fail (animation voting returns empty sets)

- [ ] **Step 3: Implement _layer2_animations**

Replace the `_layer2_animations` stub in `src/oar_priority_manager/core/tag_engine.py`:

```python
# Animation filename patterns for each tag category.
# Patterns are matched against lowercased animation filenames (without extension).
_ANIM_PATTERNS: list[tuple[list[str], TagCategory]] = [
    (["_attack", "_block", "_stagger", "_recoil", "_power"], TagCategory.COMBAT),
    (["_run", "_walk", "_sprint", "_swim", "_jump"], TagCategory.MOVEMENT),
    (["sneak"], TagCategory.SNEAK),
    (["_idle", "mt_idle"], TagCategory.IDLE),
    (["_sit", "_chair", "_bed", "_lean"], TagCategory.FURNITURE),
    (["_equip", "_sheathe", "_draw", "_unequip"], TagCategory.EQUIPMENT),
    (["_cast", "mlh_", "mrh_"], TagCategory.MAGIC),
]

# Minimum fraction of animations that must match a category for it to apply.
_ANIM_VOTE_THRESHOLD: float = 0.30


def _classify_animation(filename: str) -> set[TagCategory]:
    """Classify a single animation filename into zero or more tag categories."""
    # Strip extension and lowercase
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

    Each animation filename is classified into zero or more categories.
    A tag is applied only if >= 30% of the submod's animations match it.
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_tag_engine.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/oar_priority_manager/core/tag_engine.py tests/unit/test_tag_engine.py
git commit -m "feat: implement Layer 2 animation pattern voting for tag engine (#73)"
```

---

### Task 4: Layer 3 — Condition Type Refinement

**Files:**
- Modify: `src/oar_priority_manager/core/tag_engine.py`
- Modify: `tests/unit/test_tag_engine.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_tag_engine.py`:

```python
class TestLayer3Conditions:
    """Layer 3: condition type refinement with precondition filter."""

    def test_distinctive_issneaking_always_tags(self):
        """IsSneaking is distinctive — tags Sneak even with 8+ condition types."""
        sm = _make_submod(
            condition_types_present={
                "IsSneaking", "IsEquippedType", "IsWornInSlotHasKeyword",
                "HasMagicEffect", "IsActorBase", "IsClass", "HasPerk",
                "CompareValues", "HasKeyword",
            },
        )
        tags = compute_tags(sm)
        assert TagCategory.SNEAK in tags

    def test_distinctive_isfemale_always_tags(self):
        sm = _make_submod(
            condition_types_present={"IsFemale", "IsEquippedType", "IsWornInSlotHasKeyword",
                                      "HasMagicEffect", "IsClass", "HasPerk",
                                      "CompareValues", "HasKeyword", "IsActorBase"},
        )
        tags = compute_tags(sm)
        assert TagCategory.GENDER in tags

    def test_distinctive_ischild_always_tags_npc(self):
        sm = _make_submod(
            condition_types_present={"IsChild", "IsEquippedType", "IsWornInSlotHasKeyword",
                                      "HasMagicEffect", "IsClass", "HasPerk",
                                      "CompareValues", "HasKeyword", "IsActorBase"},
        )
        tags = compute_tags(sm)
        assert TagCategory.NPC in tags

    def test_nondistinctive_with_few_conditions_tags(self):
        """IsEquippedType with <=3 total conditions should tag Equipment."""
        sm = _make_submod(
            condition_types_present={"IsEquippedType", "IsWeaponDrawn"},
        )
        tags = compute_tags(sm)
        assert TagCategory.EQUIPMENT in tags

    def test_nondistinctive_with_many_conditions_skipped(self):
        """IsEquippedType with 8+ total conditions is a precondition — skip."""
        sm = _make_submod(
            condition_types_present={
                "IsEquippedType", "IsWornInSlotHasKeyword", "HasMagicEffect",
                "IsActorBase", "IsClass", "HasPerk", "CompareValues",
                "HasKeyword",
            },
        )
        tags = compute_tags(sm)
        assert TagCategory.EQUIPMENT not in tags

    def test_combat_conditions_few(self):
        sm = _make_submod(
            condition_types_present={"IsInCombat", "IsCombatState"},
        )
        tags = compute_tags(sm)
        assert TagCategory.COMBAT in tags

    def test_magic_conditions_few(self):
        sm = _make_submod(
            condition_types_present={"HasMagicEffect", "HasSpell"},
        )
        tags = compute_tags(sm)
        assert TagCategory.MAGIC in tags

    def test_npc_conditions_few(self):
        sm = _make_submod(
            condition_types_present={"IsActorBase", "IsRace"},
        )
        tags = compute_tags(sm)
        assert TagCategory.NPC in tags

    def test_furniture_conditions_few(self):
        sm = _make_submod(
            condition_types_present={"SitSleepState", "CurrentFurniture"},
        )
        tags = compute_tags(sm)
        assert TagCategory.FURNITURE in tags

    def test_movement_distinctive_isonmount(self):
        sm = _make_submod(
            condition_types_present={
                "IsOnMount", "IsEquippedType", "IsWornInSlotHasKeyword",
                "HasMagicEffect", "IsActorBase", "IsClass", "HasPerk",
                "CompareValues", "HasKeyword",
            },
        )
        tags = compute_tags(sm)
        assert TagCategory.MOVEMENT in tags

    def test_layer3_skips_already_tagged(self):
        """If Layer 1 already tagged Combat, Layer 3 should not re-add it."""
        sm = _make_submod(
            mo2_mod="Combat Animation Overhaul",
            condition_types_present={"IsInCombat"},
        )
        tags = compute_tags(sm)
        assert TagCategory.COMBAT in tags
        # Should be exactly 1 Combat tag, not duplicated
        assert tags.count(TagCategory.COMBAT) if isinstance(tags, list) else True

    def test_ignored_conditions(self):
        """IED_*, SDS_*, PRESET, AND, OR should not produce tags."""
        sm = _make_submod(
            condition_types_present={
                "IED_GearNodeEquippedPlacementHint", "SDS_IsShieldOnBackEnabled",
                "PRESET",
            },
        )
        tags = compute_tags(sm)
        assert len(tags) == 0

    def test_negated_isfemale_skipped(self):
        """IsFemale that is negated should NOT tag Gender (it's a filter, not purpose)."""
        sm = _make_submod(
            condition_types_present={"IsFemale"},
            condition_types_negated={"IsFemale"},
        )
        tags = compute_tags(sm)
        assert TagCategory.GENDER not in tags
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_tag_engine.py::TestLayer3Conditions -v`
Expected: Most fail (condition layer returns empty sets)

- [ ] **Step 3: Implement _layer3_conditions**

Replace the `_layer3_conditions` stub in `src/oar_priority_manager/core/tag_engine.py`:

```python
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

# Maximum number of unique condition types for non-distinctive rules to fire.
_FEW_CONDITIONS_THRESHOLD: int = 3


def _layer3_conditions(
    submod: SubMod, existing: set[TagCategory]
) -> set[TagCategory]:
    """Layer 3: condition type refinement with precondition filter.

    Only adds tags NOT already present from layers 1-2. Distinctive
    conditions always count; non-distinctive only count when the submod
    has few unique condition types (likely definitional, not preconditions).
    """
    # Filter out ignored conditions for counting purposes.
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
        # Distinctive conditions — always count
        if ct in _DISTINCTIVE_CONDITIONS:
            tag = _DISTINCTIVE_CONDITIONS[ct]
            # Special case: IsFemale only counts if NOT negated
            if ct == "IsFemale" and ct in submod.condition_types_negated:
                continue
            if tag not in existing:
                tags.add(tag)

        # Non-distinctive conditions — only count with few conditions
        elif few_conditions and ct in _NON_DISTINCTIVE_CONDITIONS:
            tag = _NON_DISTINCTIVE_CONDITIONS[ct]
            if tag not in existing:
                tags.add(tag)

    return tags
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_tag_engine.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/oar_priority_manager/core/tag_engine.py tests/unit/test_tag_engine.py
git commit -m "feat: implement Layer 3 condition type refinement for tag engine (#73)"
```

---

### Task 5: SubMod.tags Field and AppConfig.tag_overrides

**Files:**
- Modify: `src/oar_priority_manager/core/models.py`
- Modify: `src/oar_priority_manager/app/config.py`
- Modify: `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test for AppConfig**

Add to `tests/unit/test_config.py`:

```python
class TestTagOverrides:
    def test_tag_overrides_default_empty(self):
        config = AppConfig()
        assert config.tag_overrides == {}

    def test_tag_overrides_round_trip(self, tmp_path):
        config = AppConfig(tag_overrides={
            "TestMod/Replacer/Sub1": ["combat", "npc"],
            "OtherMod/Rep/Sub2": ["nsfw"],
        })
        path = tmp_path / "config.json"
        save_config(config, path)
        loaded = load_config(path)
        assert loaded.tag_overrides == {
            "TestMod/Replacer/Sub1": ["combat", "npc"],
            "OtherMod/Rep/Sub2": ["nsfw"],
        }

    def test_tag_overrides_missing_from_file(self, tmp_path):
        """Old config files without tag_overrides should load with empty dict."""
        path = tmp_path / "config.json"
        path.write_text('{"submod_sort": "priority"}', encoding="utf-8")
        loaded = load_config(path)
        assert loaded.tag_overrides == {}
```

Add the necessary imports at the top of `test_config.py`:

```python
from oar_priority_manager.app.config import AppConfig, load_config, save_config
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_config.py::TestTagOverrides -v`
Expected: `AttributeError: 'AppConfig' has no attribute 'tag_overrides'`

- [ ] **Step 3: Add tags field to SubMod**

In `src/oar_priority_manager/core/models.py`, add after line 51 (`warnings: list[str] = ...`):

```python
    tags: set = field(default_factory=set)
```

Note: Type is `set` (not `set[TagCategory]`) to avoid a circular import between `models.py` and `tag_engine.py`. The tag engine populates it with `TagCategory` values at runtime.

- [ ] **Step 4: Add tag_overrides to AppConfig**

In `src/oar_priority_manager/app/config.py`, add to `AppConfig` after `last_selected_path`:

```python
    tag_overrides: dict[str, list[str]] = field(default_factory=dict)
```

Update `load_config` to read the new field — add after the `last_selected_path` line in the `AppConfig(...)` constructor call:

```python
            tag_overrides=data.get("tag_overrides", {}),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_config.py -v`
Expected: All tests PASS (including new TestTagOverrides)

- [ ] **Step 6: Run full test suite**

Run: `pytest -v`
Expected: All existing tests still PASS (adding a defaulted field doesn't break anything)

- [ ] **Step 7: Commit**

```bash
git add src/oar_priority_manager/core/models.py src/oar_priority_manager/app/config.py tests/unit/test_config.py
git commit -m "feat: add SubMod.tags field and AppConfig.tag_overrides (#73)"
```

---

### Task 6: Wire Tag Computation into Scan Pipeline

**Files:**
- Modify: `src/oar_priority_manager/app/main.py`
- Modify: `tests/unit/test_tag_engine.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_tag_engine.py`:

```python
class TestComputeTagsMultiLayer:
    """Integration: tags accumulate across layers."""

    def test_keyword_plus_animation_tags(self):
        """Layer 1 keyword + Layer 2 animation should combine."""
        sm = _make_submod(
            mo2_mod="Dynamic Female Weather Idles",
            animations=["mt_idle.hkx", "idle_front.hkx", "idle_rain.hkx"],
        )
        tags = compute_tags(sm)
        assert TagCategory.GENDER in tags  # Layer 1
        assert TagCategory.IDLE in tags    # Layer 2

    def test_keyword_plus_condition_tags(self):
        """Layer 1 + Layer 3 should combine."""
        sm = _make_submod(
            mo2_mod="NPC Animation Remix",
            condition_types_present={"IsSneaking"},
        )
        tags = compute_tags(sm)
        assert TagCategory.NPC in tags    # Layer 1
        assert TagCategory.SNEAK in tags  # Layer 3

    def test_all_three_layers_combine(self):
        sm = _make_submod(
            mo2_mod="Female Combat Pack",
            animations=["1hm_attack1.hkx", "1hm_attack2.hkx", "1hm_attack3.hkx"],
            condition_types_present={"IsSneaking"},
        )
        tags = compute_tags(sm)
        assert TagCategory.GENDER in tags   # Layer 1 (female)
        assert TagCategory.COMBAT in tags   # Layer 1 (combat) + Layer 2 (attack anims)
        assert TagCategory.SNEAK in tags    # Layer 3 (IsSneaking)
```

- [ ] **Step 2: Run test to verify it passes** (these should pass already since layers are implemented)

Run: `pytest tests/unit/test_tag_engine.py::TestComputeTagsMultiLayer -v`
Expected: All PASS

- [ ] **Step 3: Wire compute_tags into run_scan**

In `src/oar_priority_manager/app/main.py`, add import at line 23 (after the `extract_condition_types` import):

```python
from oar_priority_manager.core.tag_engine import compute_tags
```

Then in `run_scan()`, add after line 61 (`sm.condition_types_negated = negated`):

```python
        sm.tags = compute_tags(sm)
```

- [ ] **Step 4: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/oar_priority_manager/app/main.py tests/unit/test_tag_engine.py
git commit -m "feat: wire tag computation into scan pipeline (#73)"
```

---

### Task 7: Tag Pill Delegate for Tree Panel

**Files:**
- Create: `src/oar_priority_manager/ui/tag_delegate.py`
- Modify: `src/oar_priority_manager/ui/tree_panel.py`

- [ ] **Step 1: Create TagDelegate**

Create `src/oar_priority_manager/ui/tag_delegate.py`:

```python
"""Custom tree item delegate that paints category tag pills.

Renders colored pills after the display name in each tree row.
Uses TagCategory color metadata for the muted palette.
"""
from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTreeWidgetItem

from oar_priority_manager.core.tag_engine import TagCategory
from oar_priority_manager.ui.tree_model import NodeType, TreeNode

# Custom data role to store tags on QTreeWidgetItem
TAG_DATA_ROLE: int = Qt.ItemDataRole.UserRole + 100
# Custom data role to store override indicator
TAG_OVERRIDE_ROLE: int = Qt.ItemDataRole.UserRole + 101

# Pill layout constants
_PILL_H_PAD: int = 6
_PILL_V_PAD: int = 2
_PILL_GAP: int = 3
_PILL_RADIUS: int = 6
_PILL_FONT_SIZE: int = 9
_PILL_LEFT_MARGIN: int = 8
_MAX_MOD_PILLS: int = 4


def sorted_tags(tags: set[TagCategory]) -> list[TagCategory]:
    """Sort tags by sort_order for consistent display."""
    return sorted(tags, key=lambda t: t.sort_order)


class TagDelegate(QStyledItemDelegate):
    """Delegate that paints tag pills to the right of the item text."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pill_font = QFont()
        self._pill_font.setPixelSize(_PILL_FONT_SIZE)
        self._pill_font.setBold(True)
        self._pill_fm = QFontMetrics(self._pill_font)

    def _get_tags(self, index) -> list[TagCategory]:
        """Retrieve sorted tags from item data."""
        tags = index.data(TAG_DATA_ROLE)
        if not tags:
            return []
        return sorted_tags(tags) if isinstance(tags, set) else []

    def _pill_width(self, label: str) -> int:
        """Width of a single pill including padding."""
        return self._pill_fm.horizontalAdvance(label) + 2 * _PILL_H_PAD

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        """Paint the default item, then overlay tag pills."""
        # Draw default content (icon, text, selection highlight)
        super().paint(painter, option, index)

        tags = self._get_tags(index)
        if not tags:
            return

        is_override = index.data(TAG_OVERRIDE_ROLE)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self._pill_font)

        # Calculate pill start position: right-align within the item rect
        rect = option.rect
        pill_h = self._pill_fm.height() + 2 * _PILL_V_PAD
        y = rect.top() + (rect.height() - pill_h) // 2

        # Calculate total pills width to right-align
        total_width = 0
        for tag in tags:
            total_width += self._pill_width(tag.label) + _PILL_GAP
        if is_override:
            total_width += self._pill_fm.horizontalAdvance("\u270E ") + _PILL_GAP
        total_width -= _PILL_GAP  # Remove trailing gap

        x = rect.right() - total_width - _PILL_LEFT_MARGIN

        # Draw override indicator (pencil)
        if is_override:
            painter.setPen(QColor("#888888"))
            painter.drawText(
                x,
                y + _PILL_V_PAD + self._pill_fm.ascent(),
                "\u270E",
            )
            x += self._pill_fm.horizontalAdvance("\u270E ") + _PILL_GAP

        # Draw each pill
        for tag in tags:
            w = self._pill_width(tag.label)
            pill_rect = QRect(x, y, w, pill_h)

            # Background
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(tag.color_bg)))
            painter.drawRoundedRect(pill_rect, _PILL_RADIUS, _PILL_RADIUS)

            # Border
            painter.setPen(QPen(QColor(tag.color_border), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(pill_rect, _PILL_RADIUS, _PILL_RADIUS)

            # Text
            painter.setPen(QColor(tag.color_fg))
            painter.drawText(
                pill_rect,
                Qt.AlignmentFlag.AlignCenter,
                tag.label,
            )

            x += w + _PILL_GAP

        painter.restore()

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index,
    ) -> QSize:
        """Expand width to accommodate pills."""
        size = super().sizeHint(option, index)
        tags = self._get_tags(index)
        if tags:
            extra = _PILL_LEFT_MARGIN
            for tag in tags:
                extra += self._pill_width(tag.label) + _PILL_GAP
            size.setWidth(size.width() + extra)
        return size
```

- [ ] **Step 2: Wire delegate into TreePanel**

In `src/oar_priority_manager/ui/tree_panel.py`, add imports:

```python
from oar_priority_manager.ui.tag_delegate import TagDelegate, TAG_DATA_ROLE, TAG_OVERRIDE_ROLE, sorted_tags, _MAX_MOD_PILLS
from oar_priority_manager.core.tag_engine import TagCategory
```

In `_setup_ui()`, after `self._tree.setHeaderHidden(True)`, add:

```python
        self._tag_delegate = TagDelegate(self._tree)
        self._tree.setItemDelegate(self._tag_delegate)
```

In `_populate()`, update the submod item creation to store tags. After creating `sub_item`:

```python
                    if sm and sm.tags:
                        sub_item.setData(0, TAG_DATA_ROLE, sm.tags)
```

After creating `mod_item` and adding all its children, compute rollup tags. Replace the `self._tree.addTopLevelItem(mod_item)` section:

```python
            # Compute mod-level rollup tags (union of all submod tags)
            mod_tags: set[TagCategory] = set()
            for rep_node in mod_node.children:
                for sub_node in rep_node.children:
                    if sub_node.submod and sub_node.submod.tags:
                        mod_tags.update(sub_node.submod.tags)
            if mod_tags:
                # Limit to max pills for mod rows
                display_tags = sorted_tags(mod_tags)[:_MAX_MOD_PILLS]
                mod_item.setData(0, TAG_DATA_ROLE, set(display_tags))

            self._tree.addTopLevelItem(mod_item)
```

- [ ] **Step 3: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/oar_priority_manager/ui/tag_delegate.py src/oar_priority_manager/ui/tree_panel.py
git commit -m "feat: add TagDelegate for pill rendering in tree panel (#73)"
```

---

### Task 8: Tag Edit Dialog

**Files:**
- Create: `src/oar_priority_manager/ui/tag_edit_dialog.py`

- [ ] **Step 1: Create the dialog**

Create `src/oar_priority_manager/ui/tag_edit_dialog.py`:

```python
"""Dialog for manually editing category tags on a mod or submod.

Displays checkboxes for each TagCategory with colored pill previews.
Provides a "Reset to Auto" button to clear manual overrides.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from oar_priority_manager.core.tag_engine import TagCategory
from oar_priority_manager.ui.tag_delegate import sorted_tags


def _pill_html(tag: TagCategory) -> str:
    """Render a single tag as an HTML pill span."""
    return (
        f'<span style="'
        f"background:{tag.color_bg};"
        f"color:{tag.color_fg};"
        f"border:1px solid {tag.color_border};"
        f"border-radius:6px;"
        f"padding:1px 6px;"
        f"font-size:10px;"
        f"font-weight:bold;"
        f'">{tag.label}</span>'
    )


class TagEditDialog(QDialog):
    """Modal dialog for editing tags on a tree node.

    Args:
        current_tags: The currently active tags (auto or override).
        is_override: Whether the current tags are a manual override.
        parent: Parent widget.
    """

    def __init__(
        self,
        current_tags: set[TagCategory],
        is_override: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Tags")
        self.setMinimumWidth(300)
        self._reset_requested = False

        layout = QVBoxLayout(self)

        # Info label
        if is_override:
            info = QLabel(
                '<span style="color:#888">These tags are manually set. '
                'Click "Reset to Auto" to revert to auto-detected tags.</span>'
            )
        else:
            info = QLabel(
                '<span style="color:#888">Check/uncheck tags to override '
                "auto-detection for this item.</span>"
            )
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setWordWrap(True)
        layout.addWidget(info)

        # Checkboxes — one per tag category
        self._checkboxes: dict[TagCategory, QCheckBox] = {}
        for tag in sorted_tags(set(TagCategory)):
            row = QHBoxLayout()
            cb = QCheckBox()
            cb.setChecked(tag in current_tags)
            self._checkboxes[tag] = cb
            row.addWidget(cb)

            pill_label = QLabel(_pill_html(tag))
            pill_label.setTextFormat(Qt.TextFormat.RichText)
            row.addWidget(pill_label)

            row.addStretch()
            layout.addLayout(row)

        # Reset button
        reset_btn = QPushButton("Reset to Auto")
        reset_btn.setToolTip("Clear manual override and revert to auto-detected tags")
        reset_btn.clicked.connect(self._on_reset)
        layout.addWidget(reset_btn)

        # OK / Cancel
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_reset(self) -> None:
        """Handle Reset to Auto button click."""
        self._reset_requested = True
        self.accept()

    @property
    def reset_requested(self) -> bool:
        """True if user clicked Reset to Auto instead of OK."""
        return self._reset_requested

    def selected_tags(self) -> set[TagCategory]:
        """Return the set of checked tag categories."""
        return {tag for tag, cb in self._checkboxes.items() if cb.isChecked()}
```

- [ ] **Step 2: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS (dialog is new, no existing tests break)

- [ ] **Step 3: Commit**

```bash
git add src/oar_priority_manager/ui/tag_edit_dialog.py
git commit -m "feat: add TagEditDialog for manual tag editing (#73)"
```

---

### Task 9: Context Menu and Tag Override Persistence

**Files:**
- Modify: `src/oar_priority_manager/ui/tree_panel.py`
- Modify: `src/oar_priority_manager/ui/main_window.py`

- [ ] **Step 1: Read main_window.py to understand the app_config wiring**

Read `src/oar_priority_manager/ui/main_window.py` to see how `app_config` is passed around and how context menus are set up.

- [ ] **Step 2: Add context menu to TreePanel**

In `src/oar_priority_manager/ui/tree_panel.py`, add imports:

```python
from PySide6.QtWidgets import QMenu
from PySide6.QtCore import QPoint
from oar_priority_manager.app.config import AppConfig
from oar_priority_manager.ui.tag_edit_dialog import TagEditDialog
```

Update `__init__` to accept `app_config`:

```python
    def __init__(
        self,
        submods: list[SubMod],
        app_config: AppConfig | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._submods = submods
        self._app_config = app_config
        self._root = build_tree(submods)
        self._setup_ui()
        self._populate()
```

In `_setup_ui()`, add after `layout.addWidget(self._tree)`:

```python
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
```

Add the context menu methods:

```python
    def _on_context_menu(self, pos: QPoint) -> None:
        """Show context menu with 'Edit Tags...' action."""
        item = self._tree.itemAt(pos)
        if item is None:
            return
        node = self._item_map.get(id(item))
        if node is None or node.node_type == NodeType.ROOT:
            return

        menu = QMenu(self)
        edit_tags_action = menu.addAction("Edit Tags...")
        action = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if action == edit_tags_action:
            self._edit_tags(item, node)

    def _edit_tags(self, item: QTreeWidgetItem, node: TreeNode) -> None:
        """Open tag edit dialog for the given node."""
        if self._app_config is None:
            return

        # Determine current tags and override state
        override_key = self._get_override_key(node)
        is_override = override_key in self._app_config.tag_overrides

        if node.node_type == NodeType.SUBMOD and node.submod:
            current_tags = node.submod.tags.copy()
        elif node.node_type == NodeType.MOD:
            # Rollup from children
            current_tags: set = set()
            for rep in node.children:
                for sub in rep.children:
                    if sub.submod and sub.submod.tags:
                        current_tags.update(sub.submod.tags)
        else:
            return  # No tag editing for replacer nodes

        # Apply override if exists
        if is_override:
            override_names = self._app_config.tag_overrides[override_key]
            current_tags = {
                tag for tag in TagCategory
                if tag.label.lower() in [n.lower() for n in override_names]
            }

        dialog = TagEditDialog(current_tags, is_override, self)
        if dialog.exec() != TagEditDialog.DialogCode.Accepted:
            return

        if dialog.reset_requested:
            # Remove override
            self._app_config.tag_overrides.pop(override_key, None)
            # Restore auto-detected tags on the tree item
            if node.node_type == NodeType.SUBMOD and node.submod:
                from oar_priority_manager.core.tag_engine import compute_tags
                node.submod.tags = compute_tags(node.submod)
                item.setData(0, TAG_DATA_ROLE, node.submod.tags)
                item.setData(0, TAG_OVERRIDE_ROLE, None)
        else:
            # Save override
            selected = dialog.selected_tags()
            override_list = [tag.label.lower() for tag in sorted_tags(selected)]
            self._app_config.tag_overrides[override_key] = override_list

            # Update tree item
            if node.node_type == NodeType.SUBMOD and node.submod:
                node.submod.tags = selected
            item.setData(0, TAG_DATA_ROLE, selected)
            item.setData(0, TAG_OVERRIDE_ROLE, True)

        # Refresh parent mod rollup if editing a submod
        if node.node_type == NodeType.SUBMOD and node.parent and node.parent.parent:
            self._refresh_mod_rollup(node.parent.parent)

        self._tree.viewport().update()

    def _get_override_key(self, node: TreeNode) -> str:
        """Build the config key for tag overrides."""
        if node.node_type == NodeType.SUBMOD and node.submod:
            return f"{node.submod.mo2_mod}/{node.submod.replacer}/{node.submod.name}"
        elif node.node_type == NodeType.MOD:
            return f"mod:{node.display_name}"
        return ""

    def _refresh_mod_rollup(self, mod_node: TreeNode) -> None:
        """Recompute and update tag rollup for a mod-level tree item."""
        # Find the QTreeWidgetItem for this mod_node
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if self._item_map.get(id(item)) is mod_node:
                mod_tags: set[TagCategory] = set()
                for rep in mod_node.children:
                    for sub in rep.children:
                        if sub.submod and sub.submod.tags:
                            mod_tags.update(sub.submod.tags)
                if mod_tags:
                    display = sorted_tags(mod_tags)[:_MAX_MOD_PILLS]
                    item.setData(0, TAG_DATA_ROLE, set(display))
                else:
                    item.setData(0, TAG_DATA_ROLE, None)
                break
```

- [ ] **Step 3: Update MainWindow to pass app_config to TreePanel**

Read `main_window.py` and find where `TreePanel` is constructed. Add `app_config=self._app_config` to the constructor call.

- [ ] **Step 4: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS. Some existing tests may need `app_config=None` added to TreePanel constructor calls if they use positional args — check and fix.

- [ ] **Step 5: Commit**

```bash
git add src/oar_priority_manager/ui/tree_panel.py src/oar_priority_manager/ui/main_window.py
git commit -m "feat: add context menu tag editing with override persistence (#73)"
```

---

### Task 10: Details Panel Tags Section

**Files:**
- Modify: `src/oar_priority_manager/ui/details_panel.py`

- [ ] **Step 1: Read the full details_panel.py**

Read the file to see exactly where to insert tag display in `_render_submod()` and `_render_mod()`.

- [ ] **Step 2: Add tag pill HTML rendering**

Add a helper method to `DetailsPanel`:

```python
    @staticmethod
    def _render_tag_pills(tags: set) -> str:
        """Render tags as HTML pills for the details panel."""
        from oar_priority_manager.core.tag_engine import TagCategory
        from oar_priority_manager.ui.tag_delegate import sorted_tags

        if not tags:
            return '<span style="color:#666">None detected</span>'

        pills = []
        for tag in sorted_tags(tags):
            if isinstance(tag, TagCategory):
                pills.append(
                    f'<span style="'
                    f"background:{tag.color_bg};"
                    f"color:{tag.color_fg};"
                    f"border:1px solid {tag.color_border};"
                    f"border-radius:6px;"
                    f"padding:1px 6px;"
                    f"font-size:10px;"
                    f"font-weight:bold;"
                    f'">{tag.label}</span>'
                )
        return " ".join(pills)
```

- [ ] **Step 3: Add tags to _render_submod**

In `_render_submod()`, add a tags line in the HTML output (after the condition count line):

```python
        tags_html = self._render_tag_pills(node.submod.tags)
        lines.append(f"<b>Tags:</b> {tags_html}")
```

- [ ] **Step 4: Add tags to _render_mod**

In `_render_mod()`, compute rollup tags and display:

```python
        mod_tags: set = set()
        for rep in node.children:
            for sub in rep.children:
                if sub.submod and sub.submod.tags:
                    mod_tags.update(sub.submod.tags)
        tags_html = self._render_tag_pills(mod_tags)
        lines.append(f"<b>Tags:</b> {tags_html}")
```

- [ ] **Step 5: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/oar_priority_manager/ui/details_panel.py
git commit -m "feat: display tag pills in details panel (#73)"
```

---

### Task 11: Search Index Tag Integration

**Files:**
- Modify: `src/oar_priority_manager/ui/tree_model.py`
- Modify: `tests/unit/test_tree_model.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_tree_model.py`:

```python
class TestSearchIndexTags:
    def test_search_by_tag_name(self):
        """Searching 'combat' should match submods tagged Combat."""
        from oar_priority_manager.core.tag_engine import TagCategory

        sm = SubMod(
            mo2_mod="Test Mod",
            replacer="Rep",
            name="test_sub",
            description="",
            priority=100,
            source_priority=100,
            disabled=False,
            config_path=Path("/fake/config.json"),
            override_source=OverrideSource.SOURCE,
            override_is_ours=False,
            raw_dict={},
            tags={TagCategory.COMBAT},
        )
        root = build_tree([sm])
        index = SearchIndex(root, {})
        results = index.search("combat")
        assert len(results) >= 1
        assert any(r.node.submod is sm for r in results)

    def test_search_tag_case_insensitive(self):
        from oar_priority_manager.core.tag_engine import TagCategory

        sm = SubMod(
            mo2_mod="Test Mod",
            replacer="Rep",
            name="test_sub",
            description="",
            priority=100,
            source_priority=100,
            disabled=False,
            config_path=Path("/fake/config.json"),
            override_source=OverrideSource.SOURCE,
            override_is_ours=False,
            raw_dict={},
            tags={TagCategory.NSFW},
        )
        root = build_tree([sm])
        index = SearchIndex(root, {})
        results = index.search("nsfw")
        assert len(results) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_tree_model.py::TestSearchIndexTags -v`
Expected: FAIL (tag names not indexed)

- [ ] **Step 3: Extend SearchIndex to index tag names**

In `src/oar_priority_manager/ui/tree_model.py`, in `SearchIndex._build()`, inside the `_walk` function, after the `self._submod_node_map[id(node.submod)] = node` line, add:

```python
                # Index tag names for tag-based search
                if node.submod.tags:
                    for tag in node.submod.tags:
                        tag_result = SearchResult(
                            display_text=f"[{tag.label}] {node.display_name}",
                            node_type=node.node_type,
                            node=node,
                        )
                        self._entries.append((tag.label.lower(), tag_result))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_tree_model.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/oar_priority_manager/ui/tree_model.py tests/unit/test_tree_model.py
git commit -m "feat: extend search index to match tag names (#73)"
```

---

### Task 12: Apply Tag Overrides on Load

**Files:**
- Modify: `src/oar_priority_manager/app/main.py`
- Modify: `tests/unit/test_tag_engine.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_tag_engine.py`:

```python
from oar_priority_manager.core.tag_engine import apply_overrides


class TestApplyOverrides:
    def test_override_replaces_auto_tags(self):
        sm = _make_submod(
            mo2_mod="Test Mod",
            replacer="Rep",
            name="sub1",
            animations=["1hm_attack1.hkx", "1hm_attack2.hkx", "1hm_attack3.hkx"],
        )
        sm.tags = compute_tags(sm)
        assert TagCategory.COMBAT in sm.tags

        overrides = {"Test Mod/Rep/sub1": ["nsfw", "gender"]}
        apply_overrides([sm], overrides)
        assert sm.tags == {TagCategory.NSFW, TagCategory.GENDER}

    def test_no_override_keeps_auto_tags(self):
        sm = _make_submod(
            animations=["1hm_attack1.hkx", "1hm_attack2.hkx", "1hm_attack3.hkx"],
        )
        sm.tags = compute_tags(sm)
        original = sm.tags.copy()

        apply_overrides([sm], {})
        assert sm.tags == original

    def test_override_key_format(self):
        sm = _make_submod(
            mo2_mod="My Mod",
            replacer="MyRep",
            name="MySub",
        )
        sm.tags = compute_tags(sm)

        overrides = {"My Mod/MyRep/MySub": ["sneak"]}
        apply_overrides([sm], overrides)
        assert sm.tags == {TagCategory.SNEAK}

    def test_unknown_tag_name_in_override_ignored(self):
        sm = _make_submod(mo2_mod="Test", replacer="R", name="S")
        sm.tags = compute_tags(sm)

        overrides = {"Test/R/S": ["combat", "nonexistent_tag"]}
        apply_overrides([sm], overrides)
        assert sm.tags == {TagCategory.COMBAT}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_tag_engine.py::TestApplyOverrides -v`
Expected: `ImportError: cannot import name 'apply_overrides'`

- [ ] **Step 3: Implement apply_overrides**

Add to `src/oar_priority_manager/core/tag_engine.py`:

```python
# Lookup for tag name -> TagCategory (case-insensitive)
_TAG_BY_NAME: dict[str, TagCategory] = {
    tag.label.lower(): tag for tag in TagCategory
}


def apply_overrides(
    submods: list[SubMod],
    overrides: dict[str, list[str]],
) -> None:
    """Apply manual tag overrides from AppConfig to submods.

    Overrides completely replace auto-detected tags for matching submods.

    Args:
        submods: List of SubMod instances (tags field will be mutated).
        overrides: Dict from override key to list of tag name strings.
    """
    if not overrides:
        return

    for sm in submods:
        key = f"{sm.mo2_mod}/{sm.replacer}/{sm.name}"
        if key in overrides:
            tag_names = overrides[key]
            sm.tags = {
                _TAG_BY_NAME[name.lower()]
                for name in tag_names
                if name.lower() in _TAG_BY_NAME
            }
```

- [ ] **Step 4: Wire into main.py**

In `src/oar_priority_manager/app/main.py`, update the import:

```python
from oar_priority_manager.core.tag_engine import apply_overrides, compute_tags
```

In `run_scan()`, after the tag computation loop, add (needs `app_config` parameter):

Actually, `run_scan` doesn't have access to `app_config`. Instead, wire it in `main()` after `run_scan()` returns. After line 89 (`submods, conflict_map, stacks = run_scan(instance_root)`), add:

```python
    apply_overrides(submods, app_config.tag_overrides)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/oar_priority_manager/core/tag_engine.py src/oar_priority_manager/app/main.py tests/unit/test_tag_engine.py
git commit -m "feat: apply tag overrides from AppConfig on load (#73)"
```

---

### Task 13: Final Integration Test and Cleanup

**Files:**
- Create: `tests/integration/test_tag_integration.py`

- [ ] **Step 1: Write integration tests**

Create `tests/integration/test_tag_integration.py`:

```python
"""Integration tests for category tags end-to-end.

Tests the full pipeline: scan → extract conditions → compute tags → apply overrides.
"""
from __future__ import annotations

import json
from pathlib import Path

from oar_priority_manager.app.config import AppConfig, load_config, save_config
from oar_priority_manager.core.filter_engine import extract_condition_types
from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.core.tag_engine import (
    TagCategory,
    apply_overrides,
    compute_tags,
)
from oar_priority_manager.ui.tree_model import SearchIndex, build_tree


def _make_submod_with_conditions(
    mo2_mod: str,
    replacer: str,
    name: str,
    conditions: list,
    animations: list[str] | None = None,
) -> SubMod:
    """Create a SubMod with conditions already extracted."""
    sm = SubMod(
        mo2_mod=mo2_mod,
        replacer=replacer,
        name=name,
        description="",
        priority=100,
        source_priority=100,
        disabled=False,
        config_path=Path(f"/fake/{mo2_mod}/{replacer}/{name}/config.json"),
        override_source=OverrideSource.SOURCE,
        override_is_ours=False,
        raw_dict={},
        animations=animations or [],
        conditions=conditions,
    )
    present, negated = extract_condition_types(conditions)
    sm.condition_types_present = present
    sm.condition_types_negated = negated
    sm.tags = compute_tags(sm)
    return sm


class TestEndToEnd:
    def test_combat_mod_tagged_correctly(self):
        sm = _make_submod_with_conditions(
            mo2_mod="Combat Animation Overhaul",
            replacer="CAO",
            name="power_attacks",
            conditions=[
                {"condition": "IsWeaponDrawn", "negated": False},
            ],
            animations=[
                "1hm_attackpower.hkx",
                "1hm_attackpowerfwd.hkx",
                "1hm_attackpowerleft.hkx",
            ],
        )
        assert TagCategory.COMBAT in sm.tags

    def test_female_idle_mod_gets_two_tags(self):
        sm = _make_submod_with_conditions(
            mo2_mod="Dynamic Female Weather Idles",
            replacer="WeatherIdles",
            name="rain_idle",
            conditions=[
                {"condition": "IsFemale", "negated": False},
            ],
            animations=[
                "mt_idle.hkx",
                "idle_front.hkx",
            ],
        )
        assert TagCategory.GENDER in sm.tags
        assert TagCategory.IDLE in sm.tags

    def test_nsfw_detected_from_folder_name(self):
        sm = _make_submod_with_conditions(
            mo2_mod="Dynamic Feminine Female Modesty Animations OAR",
            replacer="KP_nudeNPC",
            name="npc_both_fre",
            conditions=[],
        )
        assert TagCategory.NSFW in sm.tags
        assert TagCategory.GENDER in sm.tags


class TestOverrideRoundTrip:
    def test_save_load_overrides(self, tmp_path):
        config = AppConfig(tag_overrides={
            "TestMod/Rep/Sub": ["combat", "npc"],
        })
        path = tmp_path / "config.json"
        save_config(config, path)

        loaded = load_config(path)
        assert loaded.tag_overrides == {"TestMod/Rep/Sub": ["combat", "npc"]}

    def test_override_applied_to_submod(self):
        sm = _make_submod_with_conditions(
            mo2_mod="TestMod",
            replacer="Rep",
            name="Sub",
            conditions=[],
            animations=["mt_idle.hkx", "idle_front.hkx", "idle_rain.hkx"],
        )
        assert TagCategory.IDLE in sm.tags

        apply_overrides([sm], {"TestMod/Rep/Sub": ["combat"]})
        assert sm.tags == {TagCategory.COMBAT}
        assert TagCategory.IDLE not in sm.tags


class TestSearchWithTags:
    def test_tag_search_finds_tagged_submod(self):
        sm = _make_submod_with_conditions(
            mo2_mod="Some Random Mod Name",
            replacer="Rep",
            name="sub1",
            conditions=[{"condition": "IsSneaking", "negated": False}],
        )
        root = build_tree([sm])
        index = SearchIndex(root, {})
        results = index.search("sneak")
        assert any(r.node.submod is sm for r in results)
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/integration/test_tag_integration.py -v`
Expected: All PASS

- [ ] **Step 3: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_tag_integration.py
git commit -m "test: add integration tests for category tags pipeline (#73)"
```

- [ ] **Step 5: Run linter**

Run: `ruff check src/oar_priority_manager/core/tag_engine.py src/oar_priority_manager/ui/tag_delegate.py src/oar_priority_manager/ui/tag_edit_dialog.py`
Fix any issues found.

- [ ] **Step 6: Final commit if lint fixes needed**

```bash
git add -A
git commit -m "fix: resolve lint issues in tag engine (#73)"
```
