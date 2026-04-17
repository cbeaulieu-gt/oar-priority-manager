"""Tests for WarningEntry dataclass and collect_warning_entries helper (issue #51)."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.core.warning_report import (
    WarningEntry,
    collect_warning_entries,
)


def _sm(name: str, warnings: list[str]) -> SubMod:
    """Return a minimal SubMod with the given warnings."""
    return SubMod(
        mo2_mod="ModA",
        replacer="Rep",
        name=name,
        description="",
        priority=100,
        source_priority=100,
        disabled=False,
        config_path=Path(f"C:/mods/ModA/Rep/{name}/config.json"),
        override_source=OverrideSource.SOURCE,
        override_is_ours=False,
        raw_dict={},
        warnings=warnings,
    )


class TestWarningEntry:
    def test_is_frozen(self) -> None:
        sm = _sm("a", [])
        entry = WarningEntry(
            submod=sm,
            file_path=sm.config_path,
            error_type="Other",
            line=None,
            message="whatever",
        )
        with pytest.raises(FrozenInstanceError):
            entry.error_type = "changed"  # type: ignore[misc]

    def test_default_severity_is_warning(self) -> None:
        sm = _sm("a", [])
        entry = WarningEntry(
            submod=sm,
            file_path=sm.config_path,
            error_type="Other",
            line=None,
            message="whatever",
        )
        assert entry.severity == "warning"


class TestCollectWarningEntries:
    def test_empty_submods_returns_empty_list(self) -> None:
        assert collect_warning_entries([]) == []

    def test_submod_without_warnings_is_skipped(self) -> None:
        assert collect_warning_entries([_sm("clean", [])]) == []

    def test_json_parse_error_extracts_path_type_and_line(self) -> None:
        path = Path("C:/mods/ModA/Rep/broken/config.json")
        msg = (
            f"JSON parse error in {path}: Expecting ',' delimiter: "
            f"line 12 column 5 (char 210)"
        )
        sm = _sm("broken", [msg])
        [entry] = collect_warning_entries([sm])
        assert entry.error_type == "JSON parse error"
        assert entry.file_path == path
        assert entry.line == 12
        assert entry.message == msg

    def test_file_not_found_maps_to_read_error(self) -> None:
        path = Path("C:/mods/ModA/Rep/missing/user.json")
        sm = _sm("missing", [f"File not found: {path}"])
        [entry] = collect_warning_entries([sm])
        assert entry.error_type == "Read error"
        assert entry.file_path == path
        assert entry.line is None

    def test_cannot_read_maps_to_read_error(self) -> None:
        path = Path("C:/mods/ModA/Rep/denied/config.json")
        sm = _sm("denied", [f"Cannot read {path}: Permission denied"])
        [entry] = collect_warning_entries([sm])
        assert entry.error_type == "Read error"
        assert entry.file_path == path

    def test_empty_file_maps_to_read_error(self) -> None:
        path = Path("C:/mods/ModA/Rep/empty/config.json")
        sm = _sm("empty", [f"Empty file: {path}"])
        [entry] = collect_warning_entries([sm])
        assert entry.error_type == "Read error"
        assert entry.file_path == path

    def test_expected_object_maps_to_type_error(self) -> None:
        path = Path("C:/mods/ModA/Rep/list/config.json")
        sm = _sm("list", [f"Expected JSON object in {path}, got list"])
        [entry] = collect_warning_entries([sm])
        assert entry.error_type == "Type error"
        assert entry.file_path == path

    def test_priority_not_int_maps_to_type_error(self) -> None:
        path = Path("C:/mods/ModA/Rep/bad_prio/config.json")
        sm = _sm("bad_prio", [f"Priority is not an integer in {path}: 'hi'"])
        [entry] = collect_warning_entries([sm])
        assert entry.error_type == "Type error"
        assert entry.file_path == path

    def test_unknown_message_maps_to_other_with_config_path(self) -> None:
        sm = _sm("weird", ["something the parser did not emit today"])
        [entry] = collect_warning_entries([sm])
        assert entry.error_type == "Other"
        assert entry.file_path == sm.config_path
        assert entry.line is None

    def test_one_submod_with_two_warnings_produces_two_entries(self) -> None:
        path1 = Path("C:/mods/ModA/Rep/multi/config.json")
        path2 = Path("C:/mods/ModA/Rep/multi/user.json")
        sm = _sm(
            "multi",
            [
                f"JSON parse error in {path1}: Expecting value: line 1 column 1 (char 0)",
                f"File not found: {path2}",
            ],
        )
        entries = collect_warning_entries([sm])
        assert len(entries) == 2
        # Sorted by file_path so config.json comes before user.json alphabetically
        assert [e.file_path for e in entries] == sorted([path1, path2])

    def test_results_sorted_by_display_path_then_file_then_line(self) -> None:
        sm_a = _sm("aaa", ["File not found: C:/x/user.json"])
        sm_b = _sm("bbb", ["File not found: C:/y/user.json"])
        entries = collect_warning_entries([sm_b, sm_a])
        assert [e.submod.name for e in entries] == ["aaa", "bbb"]
