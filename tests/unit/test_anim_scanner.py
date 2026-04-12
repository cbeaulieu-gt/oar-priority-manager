"""Tests for core/anim_scanner.py — animation file discovery and conflict map.

See spec §6.2 (anim_scanner responsibilities).
"""

from __future__ import annotations

from pathlib import Path

from oar_priority_manager.core.anim_scanner import (
    _discover_variant_folders,
    _extract_replaced_animations,
    build_conflict_map,
    scan_animations,
)
from oar_priority_manager.core.models import OverrideSource, SubMod


def _make_submod(
    name: str = "sub1",
    mo2_mod: str = "ModA",
    replacer: str = "Rep",
    priority: int = 100,
    config_path: Path | None = None,
    animations: list[str] | None = None,
    raw_dict: dict | None = None,
) -> SubMod:
    return SubMod(
        mo2_mod=mo2_mod,
        replacer=replacer,
        name=name,
        description="",
        priority=priority,
        source_priority=priority,
        disabled=False,
        config_path=config_path or Path("C:/fake/config.json"),
        override_source=OverrideSource.SOURCE,
        override_is_ours=False,
        raw_dict=raw_dict or {"name": name, "priority": priority},
        animations=animations or [],
        conditions={},
        warnings=[],
    )


class TestScanAnimations:
    """scan_animations populates each SubMod's animations list."""

    def test_discovers_hkx_files(self, tmp_path: Path):
        submod_dir = tmp_path / "sub1"
        submod_dir.mkdir()
        (submod_dir / "mt_idle.hkx").touch()
        (submod_dir / "mt_walkforward.hkx").touch()
        (submod_dir / "not_an_anim.txt").touch()

        sm = _make_submod(config_path=submod_dir / "config.json")
        scan_animations([sm])
        assert sorted(sm.animations) == ["mt_idle.hkx", "mt_walkforward.hkx"]

    def test_case_insensitive_lowercase(self, tmp_path: Path):
        """Animation filenames are normalized to lowercase (spec §4)."""
        submod_dir = tmp_path / "sub1"
        submod_dir.mkdir()
        (submod_dir / "MT_Idle.HKX").touch()

        sm = _make_submod(config_path=submod_dir / "config.json")
        scan_animations([sm])
        assert sm.animations == ["mt_idle.hkx"]

    def test_override_animations_folder(self, tmp_path: Path):
        """overrideAnimationsFolder resolves relative to PARENT of submod dir (replacer dir)."""
        replacer_dir = tmp_path / "ReplacerA"
        submod_dir = replacer_dir / "sub1"
        submod_dir.mkdir(parents=True)
        (submod_dir / "config.json").touch()

        # Shared animations folder next to the submod (sibling under replacer)
        shared = replacer_dir / "shared_anims"
        shared.mkdir()
        (shared / "mt_idle.hkx").touch()

        sm = _make_submod(
            config_path=submod_dir / "config.json",
            raw_dict={"name": "sub1", "priority": 100, "overrideAnimationsFolder": "shared_anims"},
        )
        scan_animations([sm])
        assert "mt_idle.hkx" in sm.animations

    def test_no_hkx_files_empty_list(self, tmp_path: Path):
        submod_dir = tmp_path / "sub1"
        submod_dir.mkdir()
        (submod_dir / "config.json").touch()

        sm = _make_submod(config_path=submod_dir / "config.json")
        scan_animations([sm])
        assert sm.animations == []

    def test_discovers_replacement_anim_data_from_path(
        self, tmp_path: Path
    ):
        """Animations in replacementAnimDatas are discovered from the path field
        even with no .hkx files on the filesystem."""
        submod_dir = tmp_path / "sub1"
        submod_dir.mkdir()

        raw = {
            "name": "sub1",
            "priority": 100,
            "replacementAnimDatas": [
                {
                    "projectName": "DefaultMale",
                    "path": "data\\meshes\\actors\\character\\animations\\OAR\\mod\\_variants_sneakmtidle",
                    "variants": [
                        {"filename": "replacement1.hkx", "weight": 0.5},
                        {"filename": "replacement2.hkx", "disabled": True},
                    ],
                }
            ],
        }
        sm = _make_submod(
            config_path=submod_dir / "config.json", raw_dict=raw
        )
        scan_animations([sm])
        # Derived from path last segment "_variants_sneakmtidle" → sneakmtidle.hkx
        assert sm.animations == ["sneakmtidle.hkx"]

    def test_replacement_anim_data_merged_with_filesystem(
        self, tmp_path: Path
    ):
        """Filesystem .hkx files and replacementAnimDatas path-derived names
        are merged and deduplicated."""
        submod_dir = tmp_path / "sub1"
        submod_dir.mkdir()
        # mt_idle.hkx exists both on disk and is also the target of a
        # replacementAnimDatas entry — should appear once.
        (submod_dir / "mt_idle.hkx").touch()
        (submod_dir / "mt_walkforward.hkx").touch()

        raw = {
            "name": "sub1",
            "priority": 100,
            "replacementAnimDatas": [
                {
                    "projectName": "DefaultMale",
                    "path": "data\\meshes\\actors\\character\\animations\\OAR\\mod\\_variants_mt_idle",
                    "variants": [{"filename": "replacement.hkx"}],
                },
                {
                    "projectName": "DefaultMale",
                    "path": "data\\meshes\\actors\\character\\animations\\OAR\\mod\\_variants_config_only",
                    "variants": [{"filename": "replacement.hkx"}],
                },
            ],
        }
        sm = _make_submod(
            config_path=submod_dir / "config.json", raw_dict=raw
        )
        scan_animations([sm])
        assert sm.animations == [
            "config_only.hkx",
            "mt_idle.hkx",
            "mt_walkforward.hkx",
        ]

    def test_replacement_anim_data_case_insensitive(
        self, tmp_path: Path
    ):
        """Vanilla animation names derived from path are normalised to lowercase."""
        submod_dir = tmp_path / "sub1"
        submod_dir.mkdir()

        raw = {
            "name": "sub1",
            "priority": 100,
            "replacementAnimDatas": [
                {
                    "projectName": "DefaultMale",
                    "path": "data\\meshes\\actors\\character\\animations\\OAR\\mod\\_variants_RELAX10",
                    "variants": [{"filename": "replacement.hkx"}],
                },
                {
                    "projectName": "DefaultMale",
                    "path": "data\\meshes\\actors\\character\\animations\\OAR\\mod\\_variants_MT_Idle",
                    "variants": [{"filename": "replacement.hkx"}],
                },
            ],
        }
        sm = _make_submod(
            config_path=submod_dir / "config.json", raw_dict=raw
        )
        scan_animations([sm])
        assert sm.animations == ["mt_idle.hkx", "relax10.hkx"]

    def test_replacement_anim_data_malformed_graceful(
        self, tmp_path: Path
    ):
        """Missing or invalid path values do not raise; result is empty."""
        submod_dir = tmp_path / "sub1"
        submod_dir.mkdir()

        raw = {
            "name": "sub1",
            "priority": 100,
            "replacementAnimDatas": [
                # Entry with no 'path' key
                {"projectName": "DefaultMale", "variants": []},
                # Entry with a non-string path
                {"projectName": "DefaultFemale", "path": 42},
                # Entry with an empty string path
                {"projectName": "DefaultFemale", "path": ""},
                # Completely non-dict entry
                "not_a_dict",
            ],
        }
        sm = _make_submod(
            config_path=submod_dir / "config.json", raw_dict=raw
        )
        # Should not raise and should produce no animations.
        scan_animations([sm])
        assert sm.animations == []

    def test_replacement_anim_data_multiple_projects_deduplicated(
        self, tmp_path: Path
    ):
        """Same vanilla animation slot targeted by both DefaultMale and
        DefaultFemale entries is deduplicated to a single entry."""
        submod_dir = tmp_path / "sub1"
        submod_dir.mkdir()

        raw = {
            "name": "sub1",
            "priority": 100,
            "replacementAnimDatas": [
                {
                    "projectName": "DefaultMale",
                    "path": "data\\meshes\\actors\\character\\animations\\OAR\\mod\\_variants_relax10",
                    "variants": [{"filename": "male_replacement.hkx"}],
                },
                {
                    "projectName": "DefaultMale",
                    "path": "data\\meshes\\actors\\character\\animations\\OAR\\mod\\_variants_unique_male",
                    "variants": [{"filename": "replacement.hkx"}],
                },
                {
                    "projectName": "DefaultFemale",
                    "path": "data\\meshes\\actors\\character\\animations\\OAR\\mod\\_variants_relax10",
                    "variants": [{"filename": "female_replacement.hkx"}],
                },
                {
                    "projectName": "DefaultFemale",
                    "path": "data\\meshes\\actors\\character\\animations\\OAR\\mod\\_variants_unique_female",
                    "variants": [{"filename": "replacement.hkx"}],
                },
            ],
        }
        sm = _make_submod(
            config_path=submod_dir / "config.json", raw_dict=raw
        )
        scan_animations([sm])
        assert sm.animations == [
            "relax10.hkx",
            "unique_female.hkx",
            "unique_male.hkx",
        ]

    def test_discovers_implicit_variant_folders(self, tmp_path: Path):
        """Subdirectories starting with _variants_ are discovered without any
        replacementAnimDatas entry in config — the stripped, lowercased name
        plus .hkx is added to the animations list."""
        submod_dir = tmp_path / "relax_sneak_melee_right_dagger"
        submod_dir.mkdir()
        (submod_dir / "_variants_sneakmtidle").mkdir()
        (submod_dir / "_variants_1hm_idle").mkdir()

        sm = _make_submod(config_path=submod_dir / "config.json")
        scan_animations([sm])
        assert sorted(sm.animations) == ["1hm_idle.hkx", "sneakmtidle.hkx"]

    def test_variant_folders_merged_with_replacement_anim_data(
        self, tmp_path: Path
    ):
        """When a submod has both implicit _variants_* folders AND
        replacementAnimDatas entries, the results are merged and deduplicated
        via set union — an animation found via both paths appears only once."""
        submod_dir = tmp_path / "sub1"
        submod_dir.mkdir()
        # sneakmtidle appears via both routes; config_only appears only in config.
        (submod_dir / "_variants_sneakmtidle").mkdir()
        (submod_dir / "_variants_filesystem_only").mkdir()

        raw = {
            "name": "sub1",
            "priority": 100,
            "replacementAnimDatas": [
                {
                    "projectName": "DefaultMale",
                    "path": "data\\meshes\\OAR\\mod\\_variants_sneakmtidle",
                    "variants": [{"filename": "replacement.hkx"}],
                },
                {
                    "projectName": "DefaultMale",
                    "path": "data\\meshes\\OAR\\mod\\_variants_config_only",
                    "variants": [{"filename": "replacement.hkx"}],
                },
            ],
        }
        sm = _make_submod(config_path=submod_dir / "config.json", raw_dict=raw)
        scan_animations([sm])
        assert sm.animations == [
            "config_only.hkx",
            "filesystem_only.hkx",
            "sneakmtidle.hkx",
        ]

    def test_variant_folders_case_insensitive(self, tmp_path: Path):
        """Folder names like _variants_Tor_1HMPose are lowercased to
        tor_1hmpose.hkx."""
        submod_dir = tmp_path / "sub1"
        submod_dir.mkdir()
        (submod_dir / "_variants_Tor_1HMPose").mkdir()

        sm = _make_submod(config_path=submod_dir / "config.json")
        scan_animations([sm])
        assert sm.animations == ["tor_1hmpose.hkx"]

    def test_non_variant_folders_ignored(self, tmp_path: Path):
        """Subdirectories that do NOT start with _variants_ are not included."""
        submod_dir = tmp_path / "sub1"
        submod_dir.mkdir()
        (submod_dir / "some_other_folder").mkdir()
        (submod_dir / "meshes").mkdir()
        (submod_dir / "_not_variants_idle").mkdir()
        # Only this one should be discovered.
        (submod_dir / "_variants_sneakmtidle").mkdir()

        sm = _make_submod(config_path=submod_dir / "config.json")
        scan_animations([sm])
        assert sm.animations == ["sneakmtidle.hkx"]


class TestDiscoverVariantFolders:
    """Unit tests for the _discover_variant_folders helper."""

    def test_returns_empty_set_for_nonexistent_dir(self, tmp_path: Path):
        """OSError from a missing directory is caught; empty set returned."""
        result = _discover_variant_folders(tmp_path / "does_not_exist")
        assert result == set()

    def test_empty_dir_returns_empty_set(self, tmp_path: Path):
        assert _discover_variant_folders(tmp_path) == set()

    def test_strips_prefix_and_appends_hkx(self, tmp_path: Path):
        (tmp_path / "_variants_sneakmtidle").mkdir()
        assert _discover_variant_folders(tmp_path) == {"sneakmtidle.hkx"}

    def test_lowercases_name(self, tmp_path: Path):
        (tmp_path / "_variants_MT_Idle").mkdir()
        assert _discover_variant_folders(tmp_path) == {"mt_idle.hkx"}

    def test_ignores_files_not_dirs(self, tmp_path: Path):
        """A file named _variants_foo is not a variant folder and is ignored."""
        (tmp_path / "_variants_sneakmtidle").touch()
        assert _discover_variant_folders(tmp_path) == set()

    def test_ignores_non_matching_dirs(self, tmp_path: Path):
        (tmp_path / "meshes").mkdir()
        (tmp_path / "_not_variants_idle").mkdir()
        assert _discover_variant_folders(tmp_path) == set()

    def test_multiple_variant_folders(self, tmp_path: Path):
        (tmp_path / "_variants_sneakmtidle").mkdir()
        (tmp_path / "_variants_1hm_idle").mkdir()
        (tmp_path / "_variants_Tor_1HMPose").mkdir()
        assert _discover_variant_folders(tmp_path) == {
            "sneakmtidle.hkx",
            "1hm_idle.hkx",
            "tor_1hmpose.hkx",
        }


class TestExtractReplacedAnimations:
    """Unit tests for the _extract_replaced_animations helper."""

    def test_empty_dict_returns_empty_set(self):
        assert _extract_replaced_animations({}) == set()

    def test_key_absent_returns_empty_set(self):
        assert _extract_replaced_animations({"name": "sub1"}) == set()

    def test_non_list_value_returns_empty_set(self):
        """replacementAnimDatas that is not a list is ignored gracefully."""
        assert _extract_replaced_animations(
            {"replacementAnimDatas": "oops"}
        ) == set()

    def test_extracts_name_from_variants_prefix(self):
        """Last path segment starting with _variants_ yields the stripped name."""
        raw = {
            "replacementAnimDatas": [
                {
                    "path": "data\\meshes\\actors\\character\\animations\\OAR\\mod\\_variants_sneakmtidle",
                    "variants": [{"filename": "replacement.hkx"}],
                }
            ]
        }
        assert _extract_replaced_animations(raw) == {"sneakmtidle.hkx"}

    def test_appends_hkx_extension(self):
        """Derived name without .hkx gets the extension appended."""
        raw = {
            "replacementAnimDatas": [
                {
                    "path": "data\\meshes\\actors\\character\\animations\\OAR\\mod\\_variants_1hm_idle",
                    "variants": [],
                }
            ]
        }
        assert _extract_replaced_animations(raw) == {"1hm_idle.hkx"}

    def test_no_variants_prefix_uses_segment_as_is(self):
        """Last path segment without _variants_ prefix is used directly."""
        raw = {
            "replacementAnimDatas": [
                {
                    "path": "data\\meshes\\actors\\character\\animations\\OAR\\mod\\mt_idle",
                    "variants": [],
                }
            ]
        }
        assert _extract_replaced_animations(raw) == {"mt_idle.hkx"}

    def test_multiple_entries_one_animation_per_entry(self):
        """Each entry contributes exactly one animation regardless of how many
        variant filenames it contains."""
        raw = {
            "replacementAnimDatas": [
                {
                    "path": "data\\meshes\\OAR\\mod\\_variants_sneakmtidle",
                    "variants": [
                        {"filename": "replacement.hkx"},
                        {"filename": "replacement.hkx"},
                    ],
                },
                {
                    "path": "data\\meshes\\OAR\\mod\\_variants_1hm_idle",
                    "variants": [{"filename": "replacement.hkx"}],
                },
            ]
        }
        assert _extract_replaced_animations(raw) == {
            "sneakmtidle.hkx",
            "1hm_idle.hkx",
        }

    def test_missing_path_key_skipped(self):
        """Entry without a 'path' key is skipped without error."""
        raw = {
            "replacementAnimDatas": [
                {"projectName": "DefaultMale", "variants": []},
            ]
        }
        assert _extract_replaced_animations(raw) == set()

    def test_non_string_path_skipped(self):
        """Entry with a non-string path value is skipped without error."""
        raw = {
            "replacementAnimDatas": [
                {"path": 99, "variants": []},
            ]
        }
        assert _extract_replaced_animations(raw) == set()

    def test_empty_string_path_skipped(self):
        """Entry with an empty string path is skipped without error."""
        raw = {
            "replacementAnimDatas": [
                {"path": "", "variants": []},
            ]
        }
        assert _extract_replaced_animations(raw) == set()

    def test_case_normalised_to_lowercase(self):
        """Derived animation names are lowercased."""
        raw = {
            "replacementAnimDatas": [
                {
                    "path": "data\\meshes\\OAR\\mod\\_variants_Shd_BlockIdle",
                    "variants": [],
                }
            ]
        }
        assert _extract_replaced_animations(raw) == {"shd_blockidle.hkx"}

    def test_replacement_anim_data_extracts_from_path_not_variants(self):
        """Each replacementAnimDatas entry = one vanilla animation derived from path."""
        raw = {
            "replacementAnimDatas": [
                {
                    "projectName": "DefaultMale",
                    "path": "data\\meshes\\...\\submod\\_variants_sneakmtidle",
                    "variants": [{"filename": "replacement.hkx"}],
                },
                {
                    "projectName": "DefaultMale",
                    "path": "data\\meshes\\...\\submod\\_variants_1hm_idle",
                    "variants": [{"filename": "replacement.hkx"}],
                },
            ]
        }
        # Should extract sneakmtidle.hkx and 1hm_idle.hkx, NOT replacement.hkx
        result = _extract_replaced_animations(raw)
        assert result == {"sneakmtidle.hkx", "1hm_idle.hkx"}
        assert "replacement.hkx" not in result


class TestBuildConflictMap:
    """build_conflict_map groups submods by shared animation filename."""

    def test_two_submods_sharing_animation(self):
        sm1 = _make_submod(name="sub1", priority=100, animations=["mt_idle.hkx"])
        sm2 = _make_submod(name="sub2", mo2_mod="ModB", priority=200, animations=["mt_idle.hkx"])
        cmap = build_conflict_map([sm1, sm2])
        assert "mt_idle.hkx" in cmap
        assert len(cmap["mt_idle.hkx"]) == 2

    def test_no_overlap_separate_entries(self):
        sm1 = _make_submod(name="sub1", animations=["mt_idle.hkx"])
        sm2 = _make_submod(name="sub2", animations=["mt_walkforward.hkx"])
        cmap = build_conflict_map([sm1, sm2])
        assert len(cmap["mt_idle.hkx"]) == 1
        assert len(cmap["mt_walkforward.hkx"]) == 1

    def test_sorted_by_priority_descending(self):
        sm1 = _make_submod(name="low", priority=100, animations=["mt_idle.hkx"])
        sm2 = _make_submod(name="high", priority=500, animations=["mt_idle.hkx"])
        sm3 = _make_submod(name="mid", priority=300, animations=["mt_idle.hkx"])
        cmap = build_conflict_map([sm1, sm2, sm3])
        priorities = [s.priority for s in cmap["mt_idle.hkx"]]
        assert priorities == [500, 300, 100]

    def test_empty_input(self):
        cmap = build_conflict_map([])
        assert cmap == {}
