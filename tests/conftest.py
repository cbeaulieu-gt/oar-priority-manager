"""Shared test fixtures for OAR Priority Manager.

Provides factory functions that create synthetic MO2 mod directories
with OAR config files on disk. Used by parser, scanner, anim_scanner,
serializer, and override_manager tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


# --- Standard OAR directory path segments ---
OAR_REL = Path("meshes/actors/character/animations/OpenAnimationReplacer")


def _write_json(path: Path, data: dict[str, Any]) -> Path:
    """Write a dict as JSON to the given path, creating parents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def make_config_json(
    name: str = "test_submod",
    description: str = "",
    priority: int = 100,
    disabled: bool = False,
    conditions: dict | list | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a config.json dict with standard OAR fields."""
    data: dict[str, Any] = {
        "name": name,
        "description": description,
        "priority": priority,
        "disabled": disabled,
        "conditions": conditions if conditions is not None else [],
    }
    if extra_fields:
        data.update(extra_fields)
    return data


def make_submod_dir(
    mods_dir: Path,
    mo2_mod: str,
    replacer: str,
    submod_name: str,
    config: dict[str, Any] | None = None,
    user_json: dict[str, Any] | None = None,
    animations: list[str] | None = None,
) -> Path:
    """Create a complete submod directory with config.json, optional user.json, and .hkx files.

    Returns the submod directory path.
    """
    submod_dir = mods_dir / mo2_mod / OAR_REL / replacer / submod_name
    submod_dir.mkdir(parents=True, exist_ok=True)

    # Write config.json (always present)
    if config is None:
        config = make_config_json(name=submod_name)
    _write_json(submod_dir / "config.json", config)

    # Write user.json (optional)
    if user_json is not None:
        _write_json(submod_dir / "user.json", user_json)

    # Write .hkx animation files (empty files, just need to exist)
    if animations:
        for anim in animations:
            anim_path = submod_dir / anim
            anim_path.touch()

    return submod_dir


@pytest.fixture
def tmp_mods_dir(tmp_path: Path) -> Path:
    """Provide a temporary 'mods/' directory."""
    mods = tmp_path / "mods"
    mods.mkdir()
    return mods


@pytest.fixture
def tmp_overwrite_dir(tmp_path: Path) -> Path:
    """Provide a temporary 'overwrite/' directory."""
    ow = tmp_path / "overwrite"
    ow.mkdir()
    return ow


@pytest.fixture
def tmp_instance(tmp_path: Path) -> Path:
    """Provide a complete MO2 instance root with mods/ and overwrite/ dirs."""
    (tmp_path / "mods").mkdir()
    (tmp_path / "overwrite").mkdir()
    (tmp_path / "ModOrganizer.ini").touch()
    return tmp_path
