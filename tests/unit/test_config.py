"""Tests for app/config.py — tool config and MO2 instance detection.

See spec §8.3 (tool config), §8.3.1 (instance detection chain).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from oar_priority_manager.app.config import (
    AppConfig,
    DetectionError,
    detect_instance_root,
    load_config,
    save_config,
)


class TestInstanceDetection:
    def test_mods_path_cli_arg(self, tmp_path: Path):
        mods = tmp_path / "mods"
        mods.mkdir()
        result = detect_instance_root(mods_path=str(mods))
        assert result == tmp_path

    def test_mods_path_nonexistent_raises(self, tmp_path: Path):
        with pytest.raises(DetectionError):
            detect_instance_root(mods_path=str(tmp_path / "nonexistent" / "mods"))

    def test_cwd_with_mo_ini(self, tmp_path: Path):
        (tmp_path / "ModOrganizer.ini").touch()
        (tmp_path / "mods").mkdir()
        result = detect_instance_root(cwd=tmp_path)
        assert result == tmp_path

    def test_walk_up_finds_instance(self, tmp_path: Path):
        (tmp_path / "ModOrganizer.ini").touch()
        (tmp_path / "mods").mkdir()
        nested = tmp_path / "tools" / "oar-manager"
        nested.mkdir(parents=True)
        result = detect_instance_root(cwd=nested)
        assert result == tmp_path

    def test_no_detection_raises(self, tmp_path: Path, monkeypatch):
        """Step 4 (appdata cache) must be patched so the test is machine-independent.

        Without the patch, a developer machine that has launched the app at
        least once will have a valid last-instance.json in %APPDATA%, causing
        step 4 to return a real path and preventing DetectionError from ever
        being raised.  The monkeypatch forces load_last_instance to return
        None, ensuring the full fallback chain exhausts at step 5.
        """
        monkeypatch.setattr(
            "oar_priority_manager.app.config.load_last_instance",
            lambda: None,
        )
        with pytest.raises(DetectionError):
            detect_instance_root(cwd=tmp_path)

class TestAppConfig:
    def test_default_values(self):
        cfg = AppConfig()
        assert cfg.relative_or_absolute == "relative"
        assert cfg.submod_sort == "priority"
        assert cfg.search_history == []

    def test_save_and_load_roundtrip(self, tmp_path: Path):
        cfg = AppConfig(
            relative_or_absolute="absolute",
            submod_sort="name",
            search_history=["IsFemale", "walkforward"],
        )
        config_path = tmp_path / "oar-priority-manager" / "config.json"
        save_config(cfg, config_path)
        assert config_path.exists()
        loaded = load_config(config_path)
        assert loaded.relative_or_absolute == "absolute"
        assert loaded.submod_sort == "name"
        assert loaded.search_history == ["IsFemale", "walkforward"]

    def test_load_missing_file_returns_defaults(self, tmp_path: Path):
        loaded = load_config(tmp_path / "nonexistent.json")
        assert loaded.relative_or_absolute == "relative"

    def test_load_corrupt_file_returns_defaults(self, tmp_path: Path):
        bad = tmp_path / "config.json"
        bad.write_text("not json!", encoding="utf-8")
        loaded = load_config(bad)
        assert loaded.relative_or_absolute == "relative"


class TestTagOverrides:
    def test_tag_overrides_default_empty(self):
        config = AppConfig()
        assert config.tag_overrides == {}

    def test_tag_overrides_round_trip(self, tmp_path: Path):
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

    def test_tag_overrides_missing_from_file(self, tmp_path: Path):
        """Old config files without tag_overrides should load with empty dict."""
        path = tmp_path / "config.json"
        path.write_text('{"submod_sort": "priority"}', encoding="utf-8")
        loaded = load_config(path)
        assert loaded.tag_overrides == {}
