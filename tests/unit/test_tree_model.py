"""Tests for ui/tree_model.py — hierarchy construction and search index.

See spec §6.2 (tree_model), §7.3 (tree sort order).
"""
from __future__ import annotations

from pathlib import Path

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.ui.tree_model import SearchIndex, build_tree


def _sm(
    name: str,
    mo2_mod: str = "ModA",
    replacer: str = "Rep",
    priority: int = 100,
    disabled: bool = False,
    animations: list[str] | None = None,
) -> SubMod:
    return SubMod(
        mo2_mod=mo2_mod,
        replacer=replacer,
        name=name,
        description="",
        priority=priority,
        source_priority=priority,
        disabled=disabled,
        config_path=Path(f"C:/mods/{mo2_mod}/{replacer}/{name}/config.json"),
        override_source=OverrideSource.SOURCE,
        override_is_ours=False,
        raw_dict={"name": name, "priority": priority},
        animations=animations or [],
        conditions={},
        warnings=[],
    )

class TestBuildTree:
    def test_single_submod(self):
        submods = [_sm("sub1", mo2_mod="ModA", replacer="Rep1")]
        root = build_tree(submods)
        assert len(root.children) == 1
        mod = root.children[0]
        assert mod.display_name == "ModA"
        assert len(mod.children) == 1
        rep = mod.children[0]
        assert rep.display_name == "Rep1"
        assert len(rep.children) == 1
        assert rep.children[0].display_name == "sub1"

    def test_mods_sorted_alphabetically(self):
        submods = [
            _sm("s1", mo2_mod="Zebra"),
            _sm("s2", mo2_mod="Alpha"),
            _sm("s3", mo2_mod="Middle"),
        ]
        root = build_tree(submods)
        names = [c.display_name for c in root.children]
        assert names == ["Alpha", "Middle", "Zebra"]

    def test_submods_sorted_by_priority_descending(self):
        submods = [
            _sm("low", mo2_mod="Mod", replacer="Rep", priority=100),
            _sm("high", mo2_mod="Mod", replacer="Rep", priority=500),
            _sm("mid", mo2_mod="Mod", replacer="Rep", priority=300),
        ]
        root = build_tree(submods)
        rep = root.children[0].children[0]
        priorities = [c.submod.priority for c in rep.children]
        assert priorities == [500, 300, 100]

    def test_multiple_replacers_under_mod(self):
        submods = [
            _sm("s1", mo2_mod="Mod", replacer="RepB"),
            _sm("s2", mo2_mod="Mod", replacer="RepA"),
        ]
        root = build_tree(submods)
        rep_names = [c.display_name for c in root.children[0].children]
        assert rep_names == ["RepA", "RepB"]

    def test_auto_expand_single_replacer(self):
        submods = [_sm("s1", mo2_mod="Mod", replacer="OnlyRep")]
        root = build_tree(submods)
        mod = root.children[0]
        assert len(mod.children) == 1
        assert mod.children[0].auto_expand is True

    def test_no_auto_expand_multiple_replacers(self):
        submods = [
            _sm("s1", mo2_mod="Mod", replacer="Rep1"),
            _sm("s2", mo2_mod="Mod", replacer="Rep2"),
        ]
        root = build_tree(submods)
        mod = root.children[0]
        assert not any(c.auto_expand for c in mod.children)

class TestSearchIndex:
    def test_indexes_mod_names(self):
        submods = [_sm("s1", mo2_mod="Female Combat Pack")]
        root = build_tree(submods)
        index = SearchIndex(root, {})
        results = index.search("Female")
        assert any("Female Combat Pack" in r.display_text for r in results)

    def test_indexes_submod_names(self):
        submods = [_sm("heavy", mo2_mod="Mod")]
        root = build_tree(submods)
        index = SearchIndex(root, {})
        results = index.search("heavy")
        assert any("heavy" in r.display_text for r in results)

    def test_indexes_animation_filenames(self):
        submods = [_sm("s1", animations=["mt_walkforward.hkx"])]
        conflict_map = {"mt_walkforward.hkx": submods}
        root = build_tree(submods)
        index = SearchIndex(root, conflict_map)
        results = index.search("walkforward")
        assert len(results) > 0

    def test_empty_query_returns_empty(self):
        submods = [_sm("s1")]
        root = build_tree(submods)
        index = SearchIndex(root, {})
        assert index.search("") == []

    def test_case_insensitive(self):
        submods = [_sm("Heavy", mo2_mod="Mod")]
        root = build_tree(submods)
        index = SearchIndex(root, {})
        results = index.search("heavy")
        assert len(results) > 0


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
