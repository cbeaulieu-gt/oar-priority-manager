"""Tests for core/parser.py — lenient JSON parsing of OAR config files.

See spec §6.2 (parser responsibilities).
"""

from __future__ import annotations

import json
from pathlib import Path

from oar_priority_manager.core.parser import parse_config


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestValidJson:
    """Parser handles well-formed JSON config files."""

    def test_minimal_config(self, tmp_path: Path):
        f = _write(tmp_path / "config.json", json.dumps({
            "name": "test",
            "priority": 100,
        }))
        raw, warnings = parse_config(f)
        assert raw["name"] == "test"
        assert raw["priority"] == 100
        assert warnings == []

    def test_full_config_preserves_all_fields(self, tmp_path: Path):
        data = {
            "name": "heavy",
            "description": "Heavy armor idles",
            "priority": 500,
            "disabled": False,
            "interruptible": True,
            "replaceOnLoop": False,
            "overrideAnimationsFolder": "../shared/",
            "conditions": [
                {"condition": "IsFemale", "negated": False},
                {"condition": "IsInCombat", "negated": False},
            ],
            "unknownFutureField": "preserved",
        }
        f = _write(tmp_path / "config.json", json.dumps(data, indent=2))
        raw, warnings = parse_config(f)
        assert raw == data
        assert warnings == []

    def test_user_json_parsed_same_as_config(self, tmp_path: Path):
        data = {"priority": 200, "name": "modified", "conditions": []}
        f = _write(tmp_path / "user.json", json.dumps(data))
        raw, warnings = parse_config(f)
        assert raw["priority"] == 200
        assert warnings == []

    def test_integer_priority_types(self, tmp_path: Path):
        """Large OAR priorities (10-12 digits) are parsed as int, not float."""
        f = _write(tmp_path / "config.json", json.dumps({
            "name": "big", "priority": 2099200278,
        }))
        raw, _ = parse_config(f)
        assert isinstance(raw["priority"], int)
        assert raw["priority"] == 2099200278


class TestTrailingCommaRepair:
    """Parser repairs trailing commas — a common hand-edit artifact."""

    def test_trailing_comma_in_object(self, tmp_path: Path):
        text = '{"name": "test", "priority": 100,}'
        f = _write(tmp_path / "config.json", text)
        raw, warnings = parse_config(f)
        assert raw["name"] == "test"
        assert raw["priority"] == 100
        assert warnings == []

    def test_trailing_comma_in_array(self, tmp_path: Path):
        text = '{"name": "test", "priority": 100, "conditions": ["a", "b",]}'
        f = _write(tmp_path / "config.json", text)
        raw, warnings = parse_config(f)
        assert raw["conditions"] == ["a", "b"]

    def test_nested_trailing_commas(self, tmp_path: Path):
        text = '{"name": "test", "priority": 100, "conditions": [{"a": 1,},]}'
        f = _write(tmp_path / "config.json", text)
        raw, warnings = parse_config(f)
        assert raw["conditions"][0]["a"] == 1


class TestMalformedInput:
    """Parser returns empty dict + warnings for unrecoverable input."""

    def test_completely_invalid_json(self, tmp_path: Path):
        f = _write(tmp_path / "config.json", "not json at all {{{")
        raw, warnings = parse_config(f)
        assert raw == {}
        assert len(warnings) > 0
        assert any("parse" in w.lower() or "json" in w.lower() for w in warnings)

    def test_empty_file(self, tmp_path: Path):
        f = _write(tmp_path / "config.json", "")
        raw, warnings = parse_config(f)
        assert raw == {}
        assert len(warnings) > 0

    def test_file_not_found(self, tmp_path: Path):
        raw, warnings = parse_config(tmp_path / "nonexistent.json")
        assert raw == {}
        assert len(warnings) > 0
        assert any("not found" in w.lower() or "no such" in w.lower() for w in warnings)

    def test_not_a_dict(self, tmp_path: Path):
        """JSON that parses but isn't an object is a warning."""
        f = _write(tmp_path / "config.json", "[1, 2, 3]")
        raw, warnings = parse_config(f)
        assert raw == {}
        assert len(warnings) > 0


class TestKeyOrdering:
    """Parser preserves the original key ordering for round-trip."""

    def test_key_order_preserved(self, tmp_path: Path):
        text = '{"zeta": 1, "alpha": 2, "middle": 3}'
        f = _write(tmp_path / "config.json", text)
        raw, _ = parse_config(f)
        assert list(raw.keys()) == ["zeta", "alpha", "middle"]
