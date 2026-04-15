"""Tests for core/tag_engine.py — category tag auto-detection.

See design spec docs/superpowers/specs/2026-04-14-category-tags-design.md.
"""
from __future__ import annotations

from pathlib import Path

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.core.tag_engine import TagCategory, apply_overrides, compute_tags


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
