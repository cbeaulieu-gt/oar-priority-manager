"""Integration test: write_override → clear_override → re-scan round-trip.

Verifies that:
1. write_override correctly updates both disk and in-memory SubMod state.
2. clear_override removes the Overwrite file and reverts in-memory state.
3. A fresh scan_mods() after clear produces a SubMod that matches the
   in-memory state clear_override left behind.
"""

from __future__ import annotations

import json
from pathlib import Path

from oar_priority_manager.core.models import OverrideSource
from oar_priority_manager.core.override_manager import clear_override, write_override
from oar_priority_manager.core.scanner import scan_mods
from tests.conftest import make_config_json, make_submod_dir


class TestWriteClearRescan:
    """Full round-trip: write override, clear it, re-scan — state must be consistent."""

    def _setup_instance(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create two competing mods sharing an animation file.

        Returns (mods_dir, overwrite_dir).
        """
        mods_dir = tmp_path / "mods"
        mods_dir.mkdir()
        overwrite_dir = tmp_path / "overwrite"
        overwrite_dir.mkdir()

        # ModA: replacer "Rep", submod "sub1", priority 100, with a shared animation
        make_submod_dir(
            mods_dir,
            mo2_mod="ModA",
            replacer="Rep",
            submod_name="sub1",
            config=make_config_json(name="sub1", priority=100),
            animations=["attack.hkx"],
        )

        # ModB: replacer "Rep", submod "sub2", priority 200, same animation filename
        make_submod_dir(
            mods_dir,
            mo2_mod="ModB",
            replacer="Rep",
            submod_name="sub2",
            config=make_config_json(name="sub2", priority=200),
            animations=["attack.hkx"],
        )

        return mods_dir, overwrite_dir

    def test_write_updates_disk_and_memory(self, tmp_path: Path):
        """write_override must create the Overwrite user.json and update in-memory fields."""
        mods_dir, overwrite_dir = self._setup_instance(tmp_path)

        submods = scan_mods(mods_dir, overwrite_dir)
        assert len(submods) == 2

        # Pick sub1 (priority 100) and write a new priority
        sub1 = next(sm for sm in submods if sm.name == "sub1")
        write_override(sub1, 999, overwrite_dir)

        # In-memory state
        assert sub1.priority == 999
        assert sub1.override_source == OverrideSource.OVERWRITE
        assert sub1.override_is_ours is True

        # Disk state
        from oar_priority_manager.core.override_manager import compute_overwrite_path
        ow_path = compute_overwrite_path(sub1, overwrite_dir)
        assert ow_path.exists()
        data = json.loads(ow_path.read_text(encoding="utf-8"))
        assert data["priority"] == 999
        assert "_oarPriorityManager" in data
        assert data["_oarPriorityManager"]["previousPriority"] == 100

    def test_clear_removes_disk_file_and_reverts_memory(self, tmp_path: Path):
        """clear_override must delete the Overwrite file and revert in-memory to source state."""
        mods_dir, overwrite_dir = self._setup_instance(tmp_path)

        submods = scan_mods(mods_dir, overwrite_dir)
        sub1 = next(sm for sm in submods if sm.name == "sub1")

        # Write then clear
        write_override(sub1, 999, overwrite_dir)
        clear_override(sub1, overwrite_dir)

        # Disk file must be gone
        from oar_priority_manager.core.override_manager import compute_overwrite_path
        ow_path = compute_overwrite_path(sub1, overwrite_dir)
        assert not ow_path.exists()

        # In-memory state must revert to source config.json values
        assert sub1.priority == 100
        assert sub1.override_source == OverrideSource.SOURCE
        assert sub1.override_is_ours is False
        assert sub1.raw_dict.get("priority") == 100

    def test_rescan_after_clear_matches_cleared_state(self, tmp_path: Path):
        """A fresh scan_mods after clear must match the post-clear in-memory state."""
        mods_dir, overwrite_dir = self._setup_instance(tmp_path)

        submods = scan_mods(mods_dir, overwrite_dir)
        sub1 = next(sm for sm in submods if sm.name == "sub1")

        # Write then clear
        write_override(sub1, 999, overwrite_dir)
        clear_override(sub1, overwrite_dir)

        # Re-scan
        rescanned = scan_mods(mods_dir, overwrite_dir)
        rescanned_sub1 = next(sm for sm in rescanned if sm.name == "sub1")

        # Rescanned SubMod must agree with post-clear in-memory state on every
        # state field the tool manages
        assert rescanned_sub1.priority == sub1.priority
        assert rescanned_sub1.override_source == sub1.override_source
        assert rescanned_sub1.override_is_ours == sub1.override_is_ours
        # raw_dict keys should be identical (both from config.json)
        assert set(rescanned_sub1.raw_dict.keys()) == set(sub1.raw_dict.keys())

    def test_write_clear_write_again(self, tmp_path: Path):
        """After a clear, a second write_override must succeed and write correct state."""
        mods_dir, overwrite_dir = self._setup_instance(tmp_path)

        submods = scan_mods(mods_dir, overwrite_dir)
        sub1 = next(sm for sm in submods if sm.name == "sub1")

        # First write, then clear, then second write
        write_override(sub1, 999, overwrite_dir)
        clear_override(sub1, overwrite_dir)
        write_override(sub1, 777, overwrite_dir)

        assert sub1.priority == 777
        assert sub1.override_source == OverrideSource.OVERWRITE
        assert sub1.override_is_ours is True

        from oar_priority_manager.core.override_manager import compute_overwrite_path
        ow_path = compute_overwrite_path(sub1, overwrite_dir)
        data = json.loads(ow_path.read_text(encoding="utf-8"))
        assert data["priority"] == 777
        # previousPriority should reflect the priority at time of second write (100, not 999)
        assert data["_oarPriorityManager"]["previousPriority"] == 100
