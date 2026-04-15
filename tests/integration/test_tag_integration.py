"""Integration tests for category tags end-to-end.

Tests the full pipeline: scan → extract conditions → compute tags → apply overrides.
"""
from __future__ import annotations

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
