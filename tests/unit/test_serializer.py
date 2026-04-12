"""Tests for core/serializer.py — JSON writer with mutable-field allowlist.

See spec §3.3 (architectural enforcement), §6.2 (serializer), §8.1.2 (round-trip).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oar_priority_manager.core.models import IllegalMutationError
from oar_priority_manager.core.serializer import serialize_raw_dict


class TestAllowlistEnforcement:
    """Serializer rejects mutations to non-allowlisted fields."""

    def test_priority_change_allowed(self, tmp_path: Path):
        original = {"name": "heavy", "priority": 100, "conditions": []}
        modified = {"name": "heavy", "priority": 500, "conditions": []}
        out = tmp_path / "user.json"
        serialize_raw_dict(modified, original, out)
        result = json.loads(out.read_text(encoding="utf-8"))
        assert result["priority"] == 500

    def test_conditions_change_rejected(self, tmp_path: Path):
        original = {"name": "heavy", "priority": 100, "conditions": [{"type": "IsFemale"}]}
        modified = {"name": "heavy", "priority": 100, "conditions": [{"type": "IsInCombat"}]}
        out = tmp_path / "user.json"
        with pytest.raises(IllegalMutationError) as exc_info:
            serialize_raw_dict(modified, original, out)
        assert "conditions" in str(exc_info.value)

    def test_name_change_rejected(self, tmp_path: Path):
        original = {"name": "heavy", "priority": 100}
        modified = {"name": "CHANGED", "priority": 100}
        out = tmp_path / "user.json"
        with pytest.raises(IllegalMutationError):
            serialize_raw_dict(modified, original, out)

    def test_disabled_change_rejected(self, tmp_path: Path):
        original = {"name": "heavy", "priority": 100, "disabled": False}
        modified = {"name": "heavy", "priority": 100, "disabled": True}
        out = tmp_path / "user.json"
        with pytest.raises(IllegalMutationError):
            serialize_raw_dict(modified, original, out)

    def test_new_field_added_rejected(self, tmp_path: Path):
        """Adding a field not in original is rejected (except _oarPriorityManager)."""
        original = {"name": "heavy", "priority": 100}
        modified = {"name": "heavy", "priority": 100, "sneaky": True}
        out = tmp_path / "user.json"
        with pytest.raises(IllegalMutationError):
            serialize_raw_dict(modified, original, out)

    def test_field_removed_rejected(self, tmp_path: Path):
        """Removing a field from original is rejected."""
        original = {"name": "heavy", "priority": 100, "conditions": []}
        modified = {"name": "heavy", "priority": 100}
        out = tmp_path / "user.json"
        with pytest.raises(IllegalMutationError):
            serialize_raw_dict(modified, original, out)


class TestMetadataInjection:
    """Serializer injects _oarPriorityManager metadata."""

    def test_metadata_present_in_output(self, tmp_path: Path):
        original = {"name": "heavy", "priority": 100}
        modified = {"name": "heavy", "priority": 500}
        out = tmp_path / "user.json"
        serialize_raw_dict(modified, original, out, previous_priority=100)
        result = json.loads(out.read_text(encoding="utf-8"))
        meta = result["_oarPriorityManager"]
        assert meta["previousPriority"] == 100
        assert "toolVersion" in meta
        assert "writtenAt" in meta

    def test_metadata_not_counted_as_mutation(self, tmp_path: Path):
        """_oarPriorityManager metadata is exempt from the allowlist check."""
        original = {"name": "heavy", "priority": 100}
        modified = {"name": "heavy", "priority": 500}
        out = tmp_path / "user.json"
        # Should not raise even though _oarPriorityManager is a new key
        serialize_raw_dict(modified, original, out, previous_priority=100)

    def test_existing_metadata_updated(self, tmp_path: Path):
        """If original already has _oarPriorityManager, it gets updated."""
        original = {
            "name": "heavy",
            "priority": 300,
            "_oarPriorityManager": {
                "toolVersion": "0.1.0",
                "writtenAt": "2026-01-01T00:00:00Z",
                "previousPriority": 100,
            },
        }
        modified = {
            "name": "heavy",
            "priority": 500,
            "_oarPriorityManager": original["_oarPriorityManager"],
        }
        out = tmp_path / "user.json"
        serialize_raw_dict(modified, original, out, previous_priority=300)
        result = json.loads(out.read_text(encoding="utf-8"))
        assert result["_oarPriorityManager"]["previousPriority"] == 300


class TestRoundTrip:
    """Serializer preserves all non-mutable fields exactly."""

    def test_key_order_preserved(self, tmp_path: Path):
        original = {"zeta": 1, "alpha": 2, "name": "test", "priority": 100}
        modified = {"zeta": 1, "alpha": 2, "name": "test", "priority": 200}
        out = tmp_path / "user.json"
        serialize_raw_dict(modified, original, out)
        result = json.loads(out.read_text(encoding="utf-8"))
        # _oarPriorityManager is appended at end, but original keys keep order
        original_keys = list(original.keys())
        result_keys = [k for k in result if k != "_oarPriorityManager"]
        assert result_keys == original_keys

    def test_nested_structures_preserved(self, tmp_path: Path):
        conditions = [
            {
                "condition": "IsFemale",
                "negated": False,
                "requiredVersion": "1.0",
            },
            {
                "condition": "AND",
                "conditions": [
                    {"condition": "IsInCombat", "negated": False},
                ],
            },
        ]
        original = {"name": "test", "priority": 100, "conditions": conditions}
        modified = {"name": "test", "priority": 200, "conditions": conditions}
        out = tmp_path / "user.json"
        serialize_raw_dict(modified, original, out)
        result = json.loads(out.read_text(encoding="utf-8"))
        assert result["conditions"] == conditions

    def test_consistent_indentation(self, tmp_path: Path):
        """Output uses 2-space indentation (spec §8.1.2)."""
        original = {"name": "test", "priority": 100}
        modified = {"name": "test", "priority": 200}
        out = tmp_path / "user.json"
        serialize_raw_dict(modified, original, out)
        text = out.read_text(encoding="utf-8")
        assert '  "name"' in text  # 2-space indent

    def test_creates_parent_directories(self, tmp_path: Path):
        original = {"name": "test", "priority": 100}
        modified = {"name": "test", "priority": 200}
        out = tmp_path / "deep" / "nested" / "path" / "user.json"
        serialize_raw_dict(modified, original, out)
        assert out.exists()
