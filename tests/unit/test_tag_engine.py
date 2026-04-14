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
