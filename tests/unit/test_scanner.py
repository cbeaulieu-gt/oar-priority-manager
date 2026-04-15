"""Tests for core/scanner.py — MO2 mod directory discovery and override precedence.

See spec §5.3 (override precedence), §6.2 (scanner), §4 (user.json data replacement).
"""

from __future__ import annotations

import json
from pathlib import Path

from oar_priority_manager.core.models import OverrideSource
from oar_priority_manager.core.scanner import scan_mods
from tests.conftest import OAR_REL, make_config_json, make_submod_dir


class TestDiscovery:
    """Scanner discovers submods across MO2 mod directories."""

    def test_single_submod(self, tmp_instance: Path):
        make_submod_dir(
            tmp_instance / "mods", "ModA", "ReplacerA", "sub1",
            config=make_config_json(name="sub1", priority=100),
            animations=["mt_idle.hkx"],
        )
        submods = scan_mods(tmp_instance / "mods", tmp_instance / "overwrite")
        assert len(submods) == 1
        assert submods[0].name == "sub1"
        assert submods[0].mo2_mod == "ModA"
        assert submods[0].replacer == "ReplacerA"
        assert submods[0].priority == 100

    def test_multiple_mods_and_submods(self, tmp_instance: Path):
        make_submod_dir(
            tmp_instance / "mods", "ModA", "Rep1", "sub1",
            config=make_config_json(name="sub1", priority=100),
        )
        make_submod_dir(
            tmp_instance / "mods", "ModA", "Rep1", "sub2",
            config=make_config_json(name="sub2", priority=200),
        )
        make_submod_dir(
            tmp_instance / "mods", "ModB", "Rep2", "sub3",
            config=make_config_json(name="sub3", priority=300),
        )
        submods = scan_mods(tmp_instance / "mods", tmp_instance / "overwrite")
        assert len(submods) == 3
        names = {s.name for s in submods}
        assert names == {"sub1", "sub2", "sub3"}

    def test_missing_config_json_produces_warning(self, tmp_instance: Path):
        """A submod-looking folder without config.json loads with a warning."""
        submod_dir = tmp_instance / "mods" / "ModA" / OAR_REL / "Rep" / "sub1"
        submod_dir.mkdir(parents=True)
        # No config.json created
        (submod_dir / "mt_idle.hkx").touch()
        submods = scan_mods(tmp_instance / "mods", tmp_instance / "overwrite")
        assert len(submods) == 1
        assert submods[0].has_warnings

    def test_no_oar_mods_returns_empty(self, tmp_instance: Path):
        """A mods/ dir with no OAR structure returns empty list."""
        (tmp_instance / "mods" / "SomeNonOARMod" / "textures").mkdir(parents=True)
        submods = scan_mods(tmp_instance / "mods", tmp_instance / "overwrite")
        assert submods == []

    def test_disabled_submod_has_disabled_flag(self, tmp_instance: Path):
        make_submod_dir(
            tmp_instance / "mods", "ModA", "Rep", "sub1",
            config=make_config_json(name="sub1", priority=100, disabled=True),
        )
        submods = scan_mods(tmp_instance / "mods", tmp_instance / "overwrite")
        assert submods[0].disabled is True


class TestOverridePrecedence:
    """Scanner reads raw_dict from the winning file in the precedence chain."""

    def test_config_json_only(self, tmp_instance: Path):
        """No overrides: SOURCE, raw_dict from config.json."""
        make_submod_dir(
            tmp_instance / "mods", "ModA", "Rep", "sub1",
            config=make_config_json(name="sub1", priority=100),
        )
        submods = scan_mods(tmp_instance / "mods", tmp_instance / "overwrite")
        assert submods[0].override_source == OverrideSource.SOURCE
        assert submods[0].priority == 100
        assert submods[0].source_priority == 100

    def test_source_user_json_overrides_config(self, tmp_instance: Path):
        """Source user.json wins over config.json. raw_dict comes from user.json.

        CRITICAL: user.json is a complete data replacement (spec §4).
        raw_dict MUST come from user.json, not config.json.
        """
        config = make_config_json(
            name="sub1", priority=100,
            conditions=[{"condition": "IsFemale"}],
        )
        user_data = {
            "priority": 200,
            "name": "sub1",
            "conditions": [{"condition": "IsInCombat"}],  # Different conditions!
        }
        make_submod_dir(
            tmp_instance / "mods", "ModA", "Rep", "sub1",
            config=config,
            user_json=user_data,
        )
        submods = scan_mods(tmp_instance / "mods", tmp_instance / "overwrite")
        sm = submods[0]
        assert sm.override_source == OverrideSource.USER_JSON
        assert sm.priority == 200
        assert sm.source_priority == 100
        # raw_dict must come from user.json, NOT config.json
        assert sm.raw_dict["conditions"] == [{"condition": "IsInCombat"}]

    def test_overwrite_user_json_wins_over_source(self, tmp_instance: Path):
        """Overwrite user.json wins over source user.json and config.json."""
        config = make_config_json(name="sub1", priority=100)
        source_user = {"priority": 200, "name": "sub1"}
        make_submod_dir(
            tmp_instance / "mods", "ModA", "Rep", "sub1",
            config=config,
            user_json=source_user,
        )
        # Write Overwrite user.json at mirrored path
        ow_path = (
            tmp_instance / "overwrite" / OAR_REL / "Rep" / "sub1" / "user.json"
        )
        ow_path.parent.mkdir(parents=True)
        ow_data = {
            "priority": 500,
            "name": "sub1",
            "_oarPriorityManager": {
                "toolVersion": "0.1.0",
                "writtenAt": "2026-04-11T00:00:00Z",
                "previousPriority": 200,
            },
        }
        ow_path.write_text(json.dumps(ow_data), encoding="utf-8")

        submods = scan_mods(tmp_instance / "mods", tmp_instance / "overwrite")
        sm = submods[0]
        assert sm.override_source == OverrideSource.OVERWRITE
        assert sm.priority == 500
        assert sm.override_is_ours is True

    def test_overwrite_without_metadata_is_external(self, tmp_instance: Path):
        """Overwrite user.json without _oarPriorityManager is an external override."""
        make_submod_dir(
            tmp_instance / "mods", "ModA", "Rep", "sub1",
            config=make_config_json(name="sub1", priority=100),
        )
        ow_path = (
            tmp_instance / "overwrite" / OAR_REL / "Rep" / "sub1" / "user.json"
        )
        ow_path.parent.mkdir(parents=True)
        ow_path.write_text(json.dumps({"priority": 300, "name": "sub1"}))

        submods = scan_mods(tmp_instance / "mods", tmp_instance / "overwrite")
        sm = submods[0]
        assert sm.override_source == OverrideSource.OVERWRITE
        assert sm.override_is_ours is False

    def test_raw_dict_from_user_json_not_config_json(self, tmp_instance: Path):
        """CRITICAL TEST (spec §11.1): When source user.json exists,
        raw_dict must come from user.json, and writing an override must
        preserve user.json's conditions, not config.json's conditions.
        """
        config = make_config_json(
            name="sub1", priority=100,
            conditions=[{"condition": "ConditionA"}],
            extra_fields={"interruptible": True},
        )
        user_data = {
            "priority": 200,
            "name": "sub1",
            "conditions": [{"condition": "ConditionB"}],
            "interruptible": False,
        }
        make_submod_dir(
            tmp_instance / "mods", "ModA", "Rep", "sub1",
            config=config,
            user_json=user_data,
        )
        submods = scan_mods(tmp_instance / "mods", tmp_instance / "overwrite")
        sm = submods[0]
        # raw_dict must be from user.json
        assert sm.raw_dict["conditions"] == [{"condition": "ConditionB"}]
        assert sm.raw_dict["interruptible"] is False
        # name still comes from config.json (kInfoOnly per OAR behavior)
        assert sm.name == "sub1"


class TestNameAndDescription:
    """Name and description always come from config.json (OAR kInfoOnly behavior)."""

    def test_name_from_config_even_when_user_json_exists(self, tmp_instance: Path):
        config = make_config_json(name="config_name", description="config_desc", priority=100)
        user_data = {"priority": 200, "name": "user_name"}
        make_submod_dir(
            tmp_instance / "mods", "ModA", "Rep", "sub1",
            config=config,
            user_json=user_data,
        )
        submods = scan_mods(tmp_instance / "mods", tmp_instance / "overwrite")
        # Name/description come from config.json per OAR §4
        assert submods[0].name == "config_name"
        assert submods[0].description == "config_desc"


class TestReplacerPresets:
    """Scanner converts conditionPresets to a dict keyed by name."""

    def test_presets_as_list_converted_to_dict(self, tmp_instance: Path):
        """Real OAR format: conditionPresets is a list of {name, conditions} objects."""
        replacer_dir = (
            tmp_instance / "mods" / "ModA" / OAR_REL / "ReplacerA"
        )
        replacer_dir.mkdir(parents=True)
        replacer_config = {
            "conditionPresets": [
                {
                    "name": "Malignis_Base",
                    "conditions": [{"condition": "IsFemale", "requiredVersion": "1.0.0.0"}],
                },
                {
                    "name": "Malignis_Dungeon",
                    "conditions": [{"condition": "IsInCombat", "requiredVersion": "1.0.0.0"}],
                },
            ]
        }
        (replacer_dir / "config.json").write_text(
            json.dumps(replacer_config), encoding="utf-8"
        )
        make_submod_dir(
            tmp_instance / "mods", "ModA", "ReplacerA", "sub1",
            config=make_config_json(name="sub1", priority=100),
        )
        submods = scan_mods(tmp_instance / "mods", tmp_instance / "overwrite")
        presets = submods[0].replacer_presets
        assert isinstance(presets, dict)
        assert set(presets.keys()) == {"Malignis_Base", "Malignis_Dungeon"}
        assert presets["Malignis_Base"] == [
            {"condition": "IsFemale", "requiredVersion": "1.0.0.0"}
        ]
        assert presets["Malignis_Dungeon"] == [
            {"condition": "IsInCombat", "requiredVersion": "1.0.0.0"}
        ]

    def test_presets_as_dict_kept_as_is(self, tmp_instance: Path):
        """Legacy/test-fixture format: conditionPresets already a dict — pass through."""
        replacer_dir = (
            tmp_instance / "mods" / "ModA" / OAR_REL / "ReplacerA"
        )
        replacer_dir.mkdir(parents=True)
        replacer_config = {
            "conditionPresets": {
                "MyPreset": [{"condition": "IsFemale"}],
            }
        }
        (replacer_dir / "config.json").write_text(
            json.dumps(replacer_config), encoding="utf-8"
        )
        make_submod_dir(
            tmp_instance / "mods", "ModA", "ReplacerA", "sub1",
            config=make_config_json(name="sub1", priority=100),
        )
        submods = scan_mods(tmp_instance / "mods", tmp_instance / "overwrite")
        assert submods[0].replacer_presets == {"MyPreset": [{"condition": "IsFemale"}]}

    def test_preset_list_entry_missing_conditions_skipped(self, tmp_instance: Path):
        """Malformed list entries (no 'conditions' or 'Conditions' key) are skipped."""
        replacer_dir = (
            tmp_instance / "mods" / "ModA" / OAR_REL / "ReplacerA"
        )
        replacer_dir.mkdir(parents=True)
        replacer_config = {
            "conditionPresets": [
                {"name": "Good", "conditions": [{"condition": "IsFemale"}]},
                {"name": "Bad"},   # no conditions key
                "not_a_dict",      # not a dict at all
            ]
        }
        (replacer_dir / "config.json").write_text(
            json.dumps(replacer_config), encoding="utf-8"
        )
        make_submod_dir(
            tmp_instance / "mods", "ModA", "ReplacerA", "sub1",
            config=make_config_json(name="sub1", priority=100),
        )
        submods = scan_mods(tmp_instance / "mods", tmp_instance / "overwrite")
        assert submods[0].replacer_presets == {
            "Good": [{"condition": "IsFemale"}]
        }

    def test_no_replacer_config_gives_empty_presets(self, tmp_instance: Path):
        """When there is no replacer-level config.json, presets are empty."""
        make_submod_dir(
            tmp_instance / "mods", "ModA", "ReplacerA", "sub1",
            config=make_config_json(name="sub1", priority=100),
        )
        submods = scan_mods(tmp_instance / "mods", tmp_instance / "overwrite")
        assert submods[0].replacer_presets == {}
