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
