"""Tests for core/override_manager.py — Overwrite path computation and write operations.

See spec §6.2 (override_manager), §8.1 (OAR overrides).
"""

from __future__ import annotations

import json
from pathlib import Path

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.core.override_manager import (
    _remove_empty_parents,
    clear_override,
    compute_overwrite_path,
    write_override,
)


def _make_submod(
    tmp_path: Path,
    name: str = "sub1",
    mo2_mod: str = "ModA",
    replacer: str = "Rep",
    priority: int = 100,
    raw_dict: dict | None = None,
) -> SubMod:
    config_path = (
        tmp_path / "mods" / mo2_mod
        / "meshes" / "actors" / "character" / "animations"
        / "OpenAnimationReplacer" / replacer / name / "config.json"
    )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    rd = raw_dict or {"name": name, "priority": priority, "conditions": []}
    config_path.write_text(json.dumps(rd), encoding="utf-8")
    return SubMod(
        mo2_mod=mo2_mod,
        replacer=replacer,
        name=name,
        description="",
        priority=priority,
        source_priority=priority,
        disabled=False,
        config_path=config_path,
        override_source=OverrideSource.SOURCE,
        override_is_ours=False,
        raw_dict=rd,
        animations=[],
        conditions={},
        warnings=[],
    )


class TestComputeOverwritePath:
    def test_mirrors_relative_path(self, tmp_path: Path):
        sm = _make_submod(tmp_path, name="sub1", mo2_mod="ModA", replacer="Rep")
        overwrite_dir = tmp_path / "overwrite"
        result = compute_overwrite_path(sm, overwrite_dir)
        expected = (
            overwrite_dir
            / "meshes" / "actors" / "character" / "animations"
            / "OpenAnimationReplacer" / "Rep" / "sub1" / "user.json"
        )
        assert result == expected


class TestWriteOverride:
    def test_writes_user_json_to_overwrite(self, tmp_path: Path):
        sm = _make_submod(tmp_path, priority=100)
        overwrite_dir = tmp_path / "overwrite"
        overwrite_dir.mkdir()
        write_override(sm, 500, overwrite_dir)

        ow_path = compute_overwrite_path(sm, overwrite_dir)
        assert ow_path.exists()
        data = json.loads(ow_path.read_text(encoding="utf-8"))
        assert data["priority"] == 500
        assert data["_oarPriorityManager"]["previousPriority"] == 100
        # Non-priority fields preserved
        assert data["name"] == "sub1"
        assert data["conditions"] == []

    def test_updates_submod_in_memory(self, tmp_path: Path):
        sm = _make_submod(tmp_path, priority=100)
        overwrite_dir = tmp_path / "overwrite"
        overwrite_dir.mkdir()
        write_override(sm, 500, overwrite_dir)
        assert sm.priority == 500
        assert sm.override_source == OverrideSource.OVERWRITE
        assert sm.override_is_ours is True

    def test_never_writes_to_source_mod(self, tmp_path: Path):
        sm = _make_submod(tmp_path, priority=100)
        overwrite_dir = tmp_path / "overwrite"
        overwrite_dir.mkdir()
        source_user = sm.config_path.parent / "user.json"
        write_override(sm, 500, overwrite_dir)
        assert not source_user.exists()


class TestClearOverride:
    def test_deletes_overwrite_user_json(self, tmp_path: Path):
        sm = _make_submod(tmp_path, priority=100)
        overwrite_dir = tmp_path / "overwrite"
        overwrite_dir.mkdir()
        write_override(sm, 500, overwrite_dir)
        ow_path = compute_overwrite_path(sm, overwrite_dir)
        assert ow_path.exists()

        clear_override(sm, overwrite_dir)
        assert not ow_path.exists()

    def test_clear_nonexistent_is_noop(self, tmp_path: Path):
        sm = _make_submod(tmp_path, priority=100)
        overwrite_dir = tmp_path / "overwrite"
        overwrite_dir.mkdir()
        # Should not raise
        clear_override(sm, overwrite_dir)


class TestRemoveEmptyParents:
    def test_removes_empty_parents_up_to_boundary(self, tmp_path: Path):
        """Nested empty dirs are removed; boundary dir itself is kept."""
        boundary = tmp_path / "stop"
        boundary.mkdir()
        leaf = boundary / "a" / "b" / "c"
        leaf.mkdir(parents=True)

        _remove_empty_parents(leaf, boundary)

        # All intermediate dirs should be gone
        assert not (boundary / "a").exists()
        # Boundary itself must survive
        assert boundary.exists()

    def test_stops_at_nonempty_parent(self, tmp_path: Path):
        """Stops climbing when a parent directory still has content."""
        boundary = tmp_path / "stop"
        boundary.mkdir()
        mid = boundary / "mid"
        mid.mkdir()
        # Sibling file makes mid non-empty
        (mid / "sibling.txt").write_text("keep me")
        leaf = mid / "empty_child"
        leaf.mkdir()

        _remove_empty_parents(leaf, boundary)

        # The empty leaf is removed
        assert not leaf.exists()
        # mid still exists because it has sibling.txt
        assert mid.exists()

    def test_stops_at_boundary(self, tmp_path: Path):
        """Boundary directory is never removed even when empty."""
        boundary = tmp_path / "stop"
        boundary.mkdir()
        leaf = boundary / "child"
        leaf.mkdir()

        _remove_empty_parents(leaf, boundary)

        # child was empty and removed
        assert not leaf.exists()
        # boundary survives
        assert boundary.exists()
