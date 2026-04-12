"""Tests for core/anim_scanner.py — animation file discovery and conflict map.

See spec §6.2 (anim_scanner responsibilities).
"""

from __future__ import annotations

from pathlib import Path

from oar_priority_manager.core.anim_scanner import (
    _extract_replacement_anim_data_filenames,
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

    def test_discovers_replacement_anim_data_variants(
        self, tmp_path: Path
    ):
        """Animations in replacementAnimDatas are discovered even with no .hkx
        files on the filesystem."""
        submod_dir = tmp_path / "sub1"
        submod_dir.mkdir()

        raw = {
            "name": "sub1",
            "priority": 100,
            "replacementAnimDatas": [
                {
                    "projectName": "DefaultMale",
                    "path": "data\\meshes\\actors\\character",
                    "variants": [
                        {"filename": "relax10.hkx", "weight": 0.5},
                        {"filename": "hmmm.hkx", "disabled": True},
                    ],
                }
            ],
        }
        sm = _make_submod(
            config_path=submod_dir / "config.json", raw_dict=raw
        )
        scan_animations([sm])
        assert sm.animations == ["hmmm.hkx", "relax10.hkx"]

    def test_replacement_anim_data_merged_with_filesystem(
        self, tmp_path: Path
    ):
        """Filesystem .hkx files and replacementAnimDatas filenames are merged
        and deduplicated."""
        submod_dir = tmp_path / "sub1"
        submod_dir.mkdir()
        # relax10.hkx exists both on disk and in config — should appear once.
        (submod_dir / "relax10.hkx").touch()
        (submod_dir / "mt_idle.hkx").touch()

        raw = {
            "name": "sub1",
            "priority": 100,
            "replacementAnimDatas": [
                {
                    "projectName": "DefaultMale",
                    "variants": [
                        {"filename": "relax10.hkx"},
                        {"filename": "config_only.hkx"},
                    ],
                }
            ],
        }
        sm = _make_submod(
            config_path=submod_dir / "config.json", raw_dict=raw
        )
        scan_animations([sm])
        assert sm.animations == [
            "config_only.hkx",
            "mt_idle.hkx",
            "relax10.hkx",
        ]

    def test_replacement_anim_data_case_insensitive(
        self, tmp_path: Path
    ):
        """Variant filenames from config are normalised to lowercase."""
        submod_dir = tmp_path / "sub1"
        submod_dir.mkdir()

        raw = {
            "name": "sub1",
            "priority": 100,
            "replacementAnimDatas": [
                {
                    "projectName": "DefaultMale",
                    "variants": [
                        {"filename": "RELAX10.HKX"},
                        {"filename": "MT_Idle.hkx"},
                    ],
                }
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
        """Missing variants key or missing filename key does not raise; result
        is empty (or partial for valid entries)."""
        submod_dir = tmp_path / "sub1"
        submod_dir.mkdir()

        raw = {
            "name": "sub1",
            "priority": 100,
            "replacementAnimDatas": [
                # Entry with no 'variants' key
                {"projectName": "DefaultMale"},
                # Entry with variants but a variant missing 'filename'
                {
                    "projectName": "DefaultFemale",
                    "variants": [
                        {"weight": 0.5},  # no filename
                        None,             # not a dict
                    ],
                },
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
        """Same filename appearing in both DefaultMale and DefaultFemale
        entries is deduplicated to a single entry."""
        submod_dir = tmp_path / "sub1"
        submod_dir.mkdir()

        raw = {
            "name": "sub1",
            "priority": 100,
            "replacementAnimDatas": [
                {
                    "projectName": "DefaultMale",
                    "variants": [
                        {"filename": "relax10.hkx"},
                        {"filename": "unique_male.hkx"},
                    ],
                },
                {
                    "projectName": "DefaultFemale",
                    "variants": [
                        {"filename": "relax10.hkx"},
                        {"filename": "unique_female.hkx"},
                    ],
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


class TestExtractReplacementAnimDataFilenames:
    """Unit tests for the _extract_replacement_anim_data_filenames helper."""

    def test_empty_dict_returns_empty_set(self):
        assert _extract_replacement_anim_data_filenames({}) == set()

    def test_key_absent_returns_empty_set(self):
        assert _extract_replacement_anim_data_filenames(
            {"name": "sub1"}
        ) == set()

    def test_non_list_value_returns_empty_set(self):
        """replacementAnimDatas that is not a list is ignored gracefully."""
        assert _extract_replacement_anim_data_filenames(
            {"replacementAnimDatas": "oops"}
        ) == set()


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
