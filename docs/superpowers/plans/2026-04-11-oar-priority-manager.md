# OAR Priority Manager — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a PySide6 desktop tool that shows Skyrim modders which OAR submods compete for the same animation files, who is winning, and lets them adjust priorities — all without modifying source mod files.

**Architecture:** Python 3.11+ with PySide6 (Qt Widgets). Core engine is a pure-Python pipeline: parser → scanner → anim_scanner → priority_resolver, with a serializer that enforces a mutable-field allowlist (`["priority"]` only). All writes go to MO2 Overwrite at mirrored paths. UI is a three-pane layout (tree+details | priority stacks | conditions). The tool runs as an MO2 Executable so it sees the merged VFS.

**Tech Stack:** Python 3.11+, PySide6, pytest, pytest-qt, ruff, mypy, Nuitka (release builds only), GitHub Actions (Windows runners)

**Spec:** `docs/superpowers/specs/2026-04-11-oar-priority-manager-design.md`

**Repo note:** The current repo is named `oar_plugin_sorter_2`. It should be renamed to `oar-priority-manager` before the first public release, but implementation proceeds in this repo as-is.

---

## File Map

Every file the plan creates, grouped by responsibility. Each file has one clear purpose.

### Core engine (`src/oar_priority_manager/core/`)

| File | Responsibility |
|---|---|
| `models.py` | `SubMod` dataclass, `OverrideSource` enum, `PriorityStack` dataclass, `IllegalMutationError` |
| `parser.py` | Parse a single `config.json` / `user.json` into a `raw_dict`. Lenient JSON (trailing-comma repair). Returns `(raw_dict, warnings)`. |
| `scanner.py` | Walk MO2 `mods/` + `overwrite/`, discover every submod folder, apply override precedence (§5.3), build `list[SubMod]`. |
| `anim_scanner.py` | Scan each submod's animations (incl. `overrideAnimationsFolder`), produce `conflict_map: dict[str, list[SubMod]]`. |
| `serializer.py` | Write `raw_dict` to disk. Enforces mutable-field allowlist. Injects `_oarPriorityManager` metadata. |
| `override_manager.py` | Compute mirrored Overwrite path, write via serializer, `clear_override()`. |
| `priority_resolver.py` | Build `PriorityStack` per animation. `move_to_top()`, `set_exact()`, `shift()`. |
| `filter_engine.py` | Walk condition trees → `condition_types_present` + `condition_types_negated` sets. Match queries. |

### App infrastructure (`src/oar_priority_manager/app/`)

| File | Responsibility |
|---|---|
| `config.py` | Tool config read/write (toggle state, geometry, history). MO2 instance root detection chain (§8.3.1). |
| `main.py` | Entry point. CLI arg parsing, `QApplication` bootstrap, `MainWindow` construction. |

### UI (`src/oar_priority_manager/ui/`)

| File | Responsibility |
|---|---|
| `main_window.py` | Three-pane layout with splitters. Top bar (search + Advanced + Refresh). Wires signals. |
| `tree_panel.py` | `QTreeView` with Mod → Replacer → Submod hierarchy. Status icons. Sort toggle. |
| `tree_model.py` | `QAbstractItemModel` subclass. Hierarchy construction, search index, fuzzy-match filtering. |
| `details_panel.py` | Read-only metadata strip. Content varies by selection level (mod/replacer/submod). |
| `stacks_panel.py` | Priority stacks display. Rank badges, delta/absolute column, `(you)` marker, TIED indicator. Action buttons. Toast. |
| `conditions_panel.py` | Formatted (REQUIRED/ONE OF/EXCLUDED) + Raw JSON toggle. Read-only. |
| `search_bar.py` | Unified search: name fuzzy-match (default) + condition filter mode (AND/OR/NOT detection). |
| `filter_builder.py` | Advanced filter modal. Three pill buckets (REQUIRED/ANY OF/EXCLUDED). |

### Tests (`tests/`)

| File | Responsibility |
|---|---|
| `conftest.py` | Shared fixtures: `tmp_mods_dir`, `make_submod()` factory, `make_config_json()` helper. |
| `fixtures/mods/` | Synthetic fixture directories (created by Task 2). |
| `unit/test_parser.py` | Parser: valid JSON, trailing commas, malformed, missing fields, user.json. |
| `unit/test_scanner.py` | Scanner: discovery, override precedence, raw_dict sourcing from winning file. |
| `unit/test_anim_scanner.py` | Anim scanner: .hkx discovery, overrideAnimationsFolder, conflict map. |
| `unit/test_serializer.py` | Serializer: round-trip, allowlist enforcement, metadata injection. |
| `unit/test_override_manager.py` | Override manager: mirrored path, write, clear. |
| `unit/test_priority_resolver.py` | Priority resolver: stack building, move_to_top (all scopes), set_exact, shift, overflow. |
| `unit/test_filter_engine.py` | Filter engine: tree walk, presence/negation sets, query matching. |
| `unit/test_config.py` | App config: read/write, instance detection chain. |
| `unit/test_tree_model.py` | Tree model: hierarchy, sort order, search index. |
| `smoke/test_ui_smoke.py` | UI smoke: window construction, basic interactions, no crashes. |

### Project root

| File | Responsibility |
|---|---|
| `pyproject.toml` | Project metadata, dependencies, dev deps, entry point, ruff/mypy config. |
| `src/oar_priority_manager/__init__.py` | Package init. Version string. |
| `src/oar_priority_manager/core/__init__.py` | Core package init. |
| `src/oar_priority_manager/app/__init__.py` | App package init. |
| `src/oar_priority_manager/ui/__init__.py` | UI package init. |
| `.github/workflows/ci.yml` | CI: pytest + ruff + mypy on Windows runners. |
| `README.md` | Setup instructions, MO2 executable config, `--mods-path` usage. |

---

## Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/oar_priority_manager/__init__.py`
- Create: `src/oar_priority_manager/core/__init__.py`
- Create: `src/oar_priority_manager/app/__init__.py`
- Create: `src/oar_priority_manager/ui/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/smoke/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68.0", "setuptools-scm"]
build-backend = "setuptools.build_meta"

[project]
name = "oar-priority-manager"
version = "0.1.0"
description = "OAR priority management tool for Skyrim modders using MO2"
requires-python = ">=3.11"
dependencies = [
    "PySide6-Essentials>=6.6,<6.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-qt>=4.4",
    "ruff>=0.4",
    "mypy>=1.10",
]

[project.gui-scripts]
oar-priority-manager = "oar_priority_manager.app.main:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.11"
strict = false
warn_return_any = true
warn_unused_configs = true

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create package init files**

`src/oar_priority_manager/__init__.py`:
```python
"""OAR Priority Manager — priority management tool for Skyrim modders using MO2."""

__version__ = "0.1.0"
```

`src/oar_priority_manager/core/__init__.py`:
```python
"""Core engine: parser, scanner, serializer, priority resolver."""
```

`src/oar_priority_manager/app/__init__.py`:
```python
"""Application infrastructure: config, entry point."""
```

`src/oar_priority_manager/ui/__init__.py`:
```python
"""PySide6 user interface modules."""
```

`tests/__init__.py`, `tests/unit/__init__.py`, `tests/smoke/__init__.py`: empty files.

- [ ] **Step 3: Create venv and install**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

- [ ] **Step 4: Verify pytest discovers test directory**

```powershell
pytest --collect-only
```

Expected: `no tests ran` (0 items collected, no errors).

- [ ] **Step 5: Commit**

```
feat: scaffold project structure with pyproject.toml and package layout
```

---

## Task 2: Data Model + Test Fixtures

**Files:**
- Create: `src/oar_priority_manager/core/models.py`
- Create: `tests/unit/test_models.py`
- Create: `tests/conftest.py`
- Create: `tests/fixtures/mods/` (synthetic fixture directories)

- [ ] **Step 1: Write the data model tests**

`tests/unit/test_models.py`:
```python
"""Tests for core data model types."""

from pathlib import Path

from oar_priority_manager.core.models import (
    IllegalMutationError,
    OverrideSource,
    PriorityStack,
    SubMod,
)


def test_submod_creation():
    """SubMod can be constructed with all required fields."""
    sm = SubMod(
        mo2_mod="Female Combat Pack v2.3",
        replacer="AMA",
        name="heavy",
        description="Heavy armor combat idles",
        priority=500,
        source_priority=300,
        disabled=False,
        config_path=Path("C:/mods/FCP/meshes/actors/character/animations/OpenAnimationReplacer/AMA/heavy/config.json"),
        override_source=OverrideSource.OVERWRITE,
        override_is_ours=True,
        raw_dict={"name": "heavy", "priority": 500},
        animations=["mt_idle.hkx", "mt_walkforward.hkx"],
        conditions={"type": "AND", "conditions": []},
        condition_types_present={"IsFemale", "IsInCombat"},
        condition_types_negated={"IsWearingHelmet"},
        warnings=[],
    )
    assert sm.mo2_mod == "Female Combat Pack v2.3"
    assert sm.priority == 500
    assert sm.source_priority == 300
    assert sm.override_source == OverrideSource.OVERWRITE
    assert sm.override_is_ours is True
    assert len(sm.animations) == 2
    assert "IsFemale" in sm.condition_types_present
    assert "IsWearingHelmet" in sm.condition_types_negated


def test_submod_has_warnings():
    """SubMod with non-empty warnings list is considered a warning item."""
    sm = SubMod(
        mo2_mod="Broken Mod",
        replacer="rep",
        name="bad",
        description="",
        priority=0,
        source_priority=0,
        disabled=False,
        config_path=Path("C:/mods/Broken/config.json"),
        override_source=OverrideSource.SOURCE,
        override_is_ours=False,
        raw_dict={},
        animations=[],
        conditions={},
        condition_types_present=set(),
        condition_types_negated=set(),
        warnings=["Missing required field: priority"],
    )
    assert sm.has_warnings is True


def test_submod_no_warnings():
    sm = SubMod(
        mo2_mod="Good Mod",
        replacer="rep",
        name="ok",
        description="",
        priority=100,
        source_priority=100,
        disabled=False,
        config_path=Path("C:/mods/Good/config.json"),
        override_source=OverrideSource.SOURCE,
        override_is_ours=False,
        raw_dict={"name": "ok", "priority": 100},
        animations=["mt_idle.hkx"],
        conditions={},
        condition_types_present=set(),
        condition_types_negated=set(),
        warnings=[],
    )
    assert sm.has_warnings is False


def test_override_source_values():
    """OverrideSource enum has the three expected values."""
    assert OverrideSource.SOURCE.value == "source"
    assert OverrideSource.USER_JSON.value == "user_json"
    assert OverrideSource.OVERWRITE.value == "overwrite"


def test_priority_stack_creation():
    """PriorityStack holds an animation filename and a list of competitors."""
    stack = PriorityStack(
        animation_filename="mt_idle.hkx",
        competitors=[],
    )
    assert stack.animation_filename == "mt_idle.hkx"
    assert stack.competitors == []


def test_illegal_mutation_error():
    """IllegalMutationError can be raised with field details."""
    err = IllegalMutationError("conditions", "original_value", "new_value")
    assert "conditions" in str(err)
    assert isinstance(err, Exception)
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/unit/test_models.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'oar_priority_manager.core.models'`

- [ ] **Step 3: Implement data model**

`src/oar_priority_manager/core/models.py`:
```python
"""Core data model types for OAR Priority Manager.

See spec §5.2 (SubMod), §5.4 (PriorityStack), §3.3 (IllegalMutationError).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class OverrideSource(Enum):
    """Where the effective priority was read from (spec §5.3)."""

    SOURCE = "source"          # config.json in source mod
    USER_JSON = "user_json"    # user.json in source mod (OAR in-game override)
    OVERWRITE = "overwrite"    # user.json in MO2 Overwrite folder


@dataclass
class SubMod:
    """A single OAR submod discovered during scan.

    Fields match spec §5.2. raw_dict comes from the WINNING file in the
    override precedence chain (§5.3) — NOT always from config.json.
    When user.json exists, it is a complete data replacement for all fields
    except name and description (§4).
    """

    mo2_mod: str
    replacer: str
    name: str
    description: str
    priority: int
    source_priority: int
    disabled: bool
    config_path: Path
    override_source: OverrideSource
    override_is_ours: bool
    raw_dict: dict
    animations: list[str] = field(default_factory=list)
    conditions: dict = field(default_factory=dict)
    condition_types_present: set[str] = field(default_factory=set)
    condition_types_negated: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_warnings(self) -> bool:
        """True if this submod has parse/validation warnings. Edits are blocked."""
        return len(self.warnings) > 0

    @property
    def is_overridden(self) -> bool:
        """True if priority differs from the source config.json value."""
        return self.priority != self.source_priority

    @property
    def display_path(self) -> str:
        """Human-readable breadcrumb: 'MO2 Mod / Replacer / Submod'."""
        return f"{self.mo2_mod} / {self.replacer} / {self.name}"


@dataclass
class PriorityStack:
    """All submods competing for one animation filename, sorted by priority descending.

    See spec §5.4. Built by priority_resolver.py.
    """

    animation_filename: str
    competitors: list[SubMod] = field(default_factory=list)


class IllegalMutationError(Exception):
    """Raised by serializer when a non-allowlisted field has been modified.

    See spec §3.3 and §6.2. This is the architectural guardrail that prevents
    scope creep into condition editing or disable toggling.
    """

    def __init__(self, field_name: str, original_value: object, new_value: object) -> None:
        self.field_name = field_name
        self.original_value = original_value
        self.new_value = new_value
        super().__init__(
            f"Illegal mutation of field '{field_name}': "
            f"original={original_value!r}, new={new_value!r}. "
            f"Only 'priority' may be modified."
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/unit/test_models.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Create shared test fixtures**

`tests/conftest.py`:
```python
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
```

- [ ] **Step 6: Create synthetic fixture directories**

Create `tests/fixtures/mods/README.md`:
```markdown
# Test Fixtures

## Synthetic fixtures (created by tests)

Tests use `conftest.py` factory functions (`make_submod_dir`, `make_config_json`)
to create fixture directories in `tmp_path`. No static fixtures are committed here
for the initial implementation.

## Real-world fixtures (to be added during first milestone)

During the first implementation milestone, harvest config.json files from 10+
popular OAR mods on Nexus Mods. Place them here with mod author attribution.
These validate the parser against undocumented fields and non-standard formatting.

See spec §11.1 for details.
```

- [ ] **Step 7: Run full test suite**

```powershell
pytest -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```
feat: add core data model (SubMod, PriorityStack, OverrideSource) and test fixtures
```

---

## Task 3: Parser

**Files:**
- Create: `src/oar_priority_manager/core/parser.py`
- Create: `tests/unit/test_parser.py`

The parser reads a single `config.json` or `user.json` into a `raw_dict` with lenient JSON handling (trailing-comma repair). It returns `(raw_dict, warnings)` and never raises on bad input — it returns an empty dict with warnings instead.

- [ ] **Step 1: Write parser tests**

`tests/unit/test_parser.py`:
```python
"""Tests for core/parser.py — lenient JSON parsing of OAR config files.

See spec §6.2 (parser responsibilities).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/unit/test_parser.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'oar_priority_manager.core.parser'`

- [ ] **Step 3: Implement parser**

`src/oar_priority_manager/core/parser.py`:
```python
"""Lenient JSON parser for OAR config.json / user.json files.

See spec §6.2. Handles:
- Standard JSON
- Trailing commas (common hand-edit artifact)
- Produces warnings on malformed input instead of raising

Returns (raw_dict, warnings). raw_dict is {} on failure.
Key ordering is preserved for round-trip (Python 3.7+ dicts are insertion-ordered).
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def _strip_trailing_commas(text: str) -> str:
    """Remove trailing commas before } and ] to make JSON valid.

    Handles nested cases. This is a regex-based repair — it won't fix all
    malformed JSON, but catches the most common hand-edit artifact.
    """
    # Remove comma followed by optional whitespace/newlines then } or ]
    return re.sub(r",\s*([}\]])", r"\1", text)


def parse_config(path: Path) -> tuple[dict, list[str]]:
    """Parse a config.json or user.json file into a raw_dict.

    Args:
        path: Absolute path to the JSON file.

    Returns:
        Tuple of (raw_dict, warnings).
        raw_dict is {} if the file cannot be parsed.
        warnings is [] on success.
    """
    warnings: list[str] = []

    # Read the file
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, [f"File not found: {path}"]
    except OSError as e:
        return {}, [f"Cannot read {path}: {e}"]

    if not text.strip():
        return {}, [f"Empty file: {path}"]

    # Try standard JSON first
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try with trailing-comma repair
        repaired = _strip_trailing_commas(text)
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError as e:
            return {}, [f"JSON parse error in {path}: {e}"]

    # Must be a dict (JSON object)
    if not isinstance(data, dict):
        return {}, [f"Expected JSON object in {path}, got {type(data).__name__}"]

    return data, warnings
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/unit/test_parser.py -v
```

Expected: all 12 tests PASS.

- [ ] **Step 5: Run full test suite**

```powershell
pytest -v
```

Expected: all tests pass (models + parser).

- [ ] **Step 6: Commit**

```
feat: add lenient JSON parser with trailing-comma repair
```

---

## Task 4: Serializer

**Files:**
- Create: `src/oar_priority_manager/core/serializer.py`
- Create: `tests/unit/test_serializer.py`

The serializer is implemented **before** scanner/override_manager because it contains the critical architectural guardrail (mutable-field allowlist). Every write flows through it.

- [ ] **Step 1: Write serializer tests**

`tests/unit/test_serializer.py`:
```python
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
        modified = {"name": "heavy", "priority": 500, "_oarPriorityManager": original["_oarPriorityManager"]}
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
        result_keys = [k for k in result.keys() if k != "_oarPriorityManager"]
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
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/unit/test_serializer.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement serializer**

`src/oar_priority_manager/core/serializer.py`:
```python
"""JSON serializer with mutable-field allowlist for OAR user.json files.

See spec §3.3 (architectural enforcement), §6.2 (serializer responsibilities),
§8.1.1 (provenance metadata), §8.1.2 (round-trip precision).

CRITICAL ARCHITECTURAL GUARDRAIL: Only the 'priority' field may be modified.
Any other field change raises IllegalMutationError. This prevents scope creep
into condition editing or disable toggling — the trap that killed attempts 1 and 2.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from oar_priority_manager.core.models import IllegalMutationError

# The ONLY fields the tool is allowed to modify. Everything else must round-trip
# unchanged. _oarPriorityManager is handled separately (always injected/updated).
MUTABLE_FIELDS: frozenset[str] = frozenset({"priority"})

# Metadata key injected into every tool-written user.json (spec §8.1.1)
METADATA_KEY = "_oarPriorityManager"

# Current tool version — embedded in metadata for provenance tracking
_TOOL_VERSION = "0.1.0"


def _deep_equal(a: object, b: object) -> bool:
    """Deep equality check that handles nested dicts, lists, and primitives."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        if a.keys() != b.keys():  # type: ignore[union-attr]
            return False
        return all(_deep_equal(a[k], b[k]) for k in a)  # type: ignore[index]
    if isinstance(a, list):
        if len(a) != len(b):  # type: ignore[arg-type]
            return False
        return all(_deep_equal(x, y) for x, y in zip(a, b))  # type: ignore[arg-type]
    return a == b


def _validate_allowlist(modified: dict, original: dict) -> None:
    """Check that only allowlisted fields have changed.

    Raises IllegalMutationError if any non-allowlisted field differs.
    """
    # Check for removed keys
    for key in original:
        if key == METADATA_KEY:
            continue
        if key not in modified:
            raise IllegalMutationError(key, original[key], "<removed>")

    # Check for added keys
    for key in modified:
        if key == METADATA_KEY:
            continue
        if key not in original:
            raise IllegalMutationError(key, "<absent>", modified[key])

    # Check for modified values in non-allowlisted fields
    for key in original:
        if key == METADATA_KEY:
            continue
        if key in MUTABLE_FIELDS:
            continue
        if not _deep_equal(original[key], modified[key]):
            raise IllegalMutationError(key, original[key], modified[key])


def _build_metadata(previous_priority: int | None) -> dict:
    """Build the _oarPriorityManager metadata object."""
    meta: dict = {
        "toolVersion": _TOOL_VERSION,
        "writtenAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if previous_priority is not None:
        meta["previousPriority"] = previous_priority
    return meta


def serialize_raw_dict(
    modified: dict,
    original: dict,
    output_path: Path,
    previous_priority: int | None = None,
) -> None:
    """Write a modified raw_dict to disk as JSON.

    Args:
        modified: The raw_dict with updated priority.
        original: The raw_dict as originally read (for allowlist diffing).
        output_path: Where to write the file.
        previous_priority: The priority value before this change (for metadata).

    Raises:
        IllegalMutationError: If any non-allowlisted field has been modified.
    """
    # Validate before writing — the guardrail
    _validate_allowlist(modified, original)

    # Build output dict preserving key order from modified, inject metadata
    output = dict(modified)
    output[METADATA_KEY] = _build_metadata(previous_priority)

    # Create parent directories
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write with consistent formatting (spec §8.1.2)
    output_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/unit/test_serializer.py -v
```

Expected: all 13 tests PASS.

- [ ] **Step 5: Run full test suite**

```powershell
pytest -v
```

- [ ] **Step 6: Commit**

```
feat: add serializer with mutable-field allowlist guardrail
```

---

## Task 5: Scanner

**Files:**
- Create: `src/oar_priority_manager/core/scanner.py`
- Create: `tests/unit/test_scanner.py`

The scanner walks `mods/` + `overwrite/`, discovers submod folders, applies override precedence (§5.3), and builds `SubMod` records. This is the most complex core module — it implements the critical `raw_dict` sourcing from the winning file.

- [ ] **Step 1: Write scanner tests**

`tests/unit/test_scanner.py`:
```python
"""Tests for core/scanner.py — MO2 mod directory discovery and override precedence.

See spec §5.3 (override precedence), §6.2 (scanner), §4 (user.json data replacement).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/unit/test_scanner.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement scanner**

`src/oar_priority_manager/core/scanner.py`:
```python
"""MO2 mod directory scanner — discovers OAR submods and applies override precedence.

See spec §5.3 (override precedence), §6.2 (scanner responsibilities).

CRITICAL: raw_dict must come from the WINNING file in the precedence chain,
not always from config.json. When user.json exists, it is a complete data
replacement for all fields except name/description (spec §4).
"""

from __future__ import annotations

import logging
from pathlib import Path

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.core.parser import parse_config

logger = logging.getLogger(__name__)

# The relative path within a mod that marks the OAR animation replacer root
OAR_REL = Path("meshes/actors/character/animations/OpenAnimationReplacer")

# Metadata key injected by this tool into Overwrite user.json files
METADATA_KEY = "_oarPriorityManager"


def _find_submod_dirs(mods_dir: Path) -> list[tuple[str, str, str, Path]]:
    """Find all submod directories under mods/.

    Returns list of (mo2_mod, replacer, submod_folder_name, submod_path).
    A submod directory is any folder under <mod>/<OAR_REL>/<replacer>/<submod>/
    that either contains config.json or contains .hkx files.
    """
    results = []
    if not mods_dir.is_dir():
        return results

    for mod_dir in sorted(mods_dir.iterdir()):
        if not mod_dir.is_dir():
            continue
        oar_root = mod_dir / OAR_REL
        if not oar_root.is_dir():
            continue

        mo2_mod = mod_dir.name

        for replacer_dir in sorted(oar_root.iterdir()):
            if not replacer_dir.is_dir():
                continue
            replacer = replacer_dir.name

            for submod_dir in sorted(replacer_dir.iterdir()):
                if not submod_dir.is_dir():
                    continue
                # A submod candidate: has config.json or has .hkx files
                has_config = (submod_dir / "config.json").exists()
                has_hkx = any(submod_dir.glob("*.hkx"))
                if has_config or has_hkx:
                    results.append((mo2_mod, replacer, submod_dir.name, submod_dir))

    return results


def _build_submod(
    mo2_mod: str,
    replacer: str,
    submod_folder: str,
    submod_path: Path,
    overwrite_dir: Path,
) -> SubMod:
    """Build a SubMod record for one discovered submod, applying override precedence.

    Precedence (spec §5.3):
    1. Overwrite user.json (at mirrored path)
    2. Source user.json (in source mod)
    3. Source config.json

    raw_dict comes from the WINNING file. name/description always from config.json.
    """
    warnings: list[str] = []

    # Always read config.json for name/description (OAR kInfoOnly)
    config_path = submod_path / "config.json"
    config_dict, config_warnings = parse_config(config_path)
    warnings.extend(config_warnings)

    # Extract name/description from config.json (always, per OAR §4)
    name = config_dict.get("name", submod_folder)
    description = config_dict.get("description", "")
    source_priority = config_dict.get("priority", 0)
    if not isinstance(source_priority, int):
        warnings.append(f"Priority is not an integer in {config_path}: {source_priority!r}")
        source_priority = 0

    # Determine override precedence and select winning file for raw_dict
    # The mirrored path in Overwrite uses the relative path from OAR root
    rel_from_oar = Path(replacer) / submod_folder
    overwrite_user = overwrite_dir / OAR_REL / rel_from_oar / "user.json"
    source_user = submod_path / "user.json"

    override_source = OverrideSource.SOURCE
    override_is_ours = False
    raw_dict = config_dict
    effective_priority = source_priority

    # Check precedence: Overwrite > source user.json > config.json
    if overwrite_user.is_file():
        ow_dict, ow_warnings = parse_config(overwrite_user)
        warnings.extend(ow_warnings)
        if ow_dict:
            override_source = OverrideSource.OVERWRITE
            raw_dict = ow_dict
            effective_priority = ow_dict.get("priority", source_priority)
            if not isinstance(effective_priority, int):
                warnings.append(f"Priority is not an integer in {overwrite_user}: {effective_priority!r}")
                effective_priority = source_priority
            override_is_ours = METADATA_KEY in ow_dict
    elif source_user.is_file():
        su_dict, su_warnings = parse_config(source_user)
        warnings.extend(su_warnings)
        if su_dict:
            override_source = OverrideSource.USER_JSON
            raw_dict = su_dict  # CRITICAL: raw_dict from user.json, not config.json
            effective_priority = su_dict.get("priority", source_priority)
            if not isinstance(effective_priority, int):
                warnings.append(f"Priority is not an integer in {source_user}: {effective_priority!r}")
                effective_priority = source_priority

    # Read disabled from the winning raw_dict (user.json is complete replacement)
    disabled = bool(raw_dict.get("disabled", False))

    # Read conditions from winning raw_dict for display/filtering
    conditions = raw_dict.get("conditions", {})
    if not isinstance(conditions, (dict, list)):
        conditions = {}

    return SubMod(
        mo2_mod=mo2_mod,
        replacer=replacer,
        name=name,
        description=description,
        priority=effective_priority,
        source_priority=source_priority,
        disabled=disabled,
        config_path=config_path,
        override_source=override_source,
        override_is_ours=override_is_ours,
        raw_dict=raw_dict,
        conditions=conditions,
        warnings=warnings,
    )


def scan_mods(mods_dir: Path, overwrite_dir: Path) -> list[SubMod]:
    """Scan the MO2 instance and build SubMod records for every OAR submod.

    Args:
        mods_dir: Path to the MO2 mods/ directory.
        overwrite_dir: Path to the MO2 overwrite/ directory.

    Returns:
        List of SubMod records. Submods with parse errors have non-empty warnings.
    """
    submod_dirs = _find_submod_dirs(mods_dir)
    submods: list[SubMod] = []

    for mo2_mod, replacer, submod_folder, submod_path in submod_dirs:
        sm = _build_submod(mo2_mod, replacer, submod_folder, submod_path, overwrite_dir)
        submods.append(sm)

    logger.info("Scanned %d submods from %s", len(submods), mods_dir)
    return submods
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/unit/test_scanner.py -v
```

Expected: all 11 tests PASS.

- [ ] **Step 5: Run full test suite**

```powershell
pytest -v
```

- [ ] **Step 6: Commit**

```
feat: add scanner with override precedence and raw_dict from winning file
```

---

## Task 6: Animation Scanner

**Files:**
- Create: `src/oar_priority_manager/core/anim_scanner.py`
- Create: `tests/unit/test_anim_scanner.py`

Scans each submod's animation files (including `overrideAnimationsFolder` redirection) and builds the conflict map.

- [ ] **Step 1: Write anim scanner tests**

`tests/unit/test_anim_scanner.py`:
```python
"""Tests for core/anim_scanner.py — animation file discovery and conflict map.

See spec §6.2 (anim_scanner responsibilities).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from oar_priority_manager.core.anim_scanner import build_conflict_map, scan_animations
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
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/unit/test_anim_scanner.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement anim scanner**

`src/oar_priority_manager/core/anim_scanner.py`:
```python
"""Animation file scanner and conflict map builder.

See spec §6.2 (anim_scanner responsibilities).
Scans each submod's animation files, including overrideAnimationsFolder redirection.
overrideAnimationsFolder resolves relative to the PARENT of the submod directory
(the replacer folder), matching OAR's own resolution logic.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

from oar_priority_manager.core.models import SubMod

logger = logging.getLogger(__name__)


def _get_animation_dir(submod: SubMod) -> Path:
    """Determine where to look for .hkx files.

    If overrideAnimationsFolder is set in raw_dict, resolve it relative to
    the parent of the submod directory (the replacer folder).
    Otherwise, look in the submod directory itself.
    """
    submod_dir = submod.config_path.parent
    override_folder = submod.raw_dict.get("overrideAnimationsFolder")

    if override_folder and isinstance(override_folder, str):
        # Resolve relative to the PARENT of submod dir (the replacer folder)
        replacer_dir = submod_dir.parent
        resolved = (replacer_dir / override_folder).resolve()
        if resolved.is_dir():
            return resolved
        else:
            submod.warnings.append(
                f"overrideAnimationsFolder '{override_folder}' resolves to "
                f"'{resolved}' which does not exist"
            )
    return submod_dir


def scan_animations(submods: list[SubMod]) -> None:
    """Populate each SubMod's animations list with lowercased .hkx filenames.

    Modifies submods in place.
    """
    for sm in submods:
        anim_dir = _get_animation_dir(sm)
        try:
            hkx_files = [
                f.name.lower()
                for f in anim_dir.iterdir()
                if f.is_file() and f.suffix.lower() == ".hkx"
            ]
        except OSError as e:
            sm.warnings.append(f"Cannot read animation directory {anim_dir}: {e}")
            hkx_files = []

        sm.animations = sorted(hkx_files)


def build_conflict_map(submods: list[SubMod]) -> dict[str, list[SubMod]]:
    """Build a map of animation filename → list of competing submods, sorted by priority descending.

    See spec §5.4 (PriorityStack).
    """
    anim_to_submods: dict[str, list[SubMod]] = defaultdict(list)

    for sm in submods:
        for anim in sm.animations:
            anim_to_submods[anim].append(sm)

    # Sort each list by priority descending
    for anim in anim_to_submods:
        anim_to_submods[anim].sort(key=lambda s: s.priority, reverse=True)

    return dict(anim_to_submods)
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/unit/test_anim_scanner.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Run full test suite**

```powershell
pytest -v
```

- [ ] **Step 6: Commit**

```
feat: add animation scanner with overrideAnimationsFolder and conflict map
```

---

## Task 7: Override Manager

**Files:**
- Create: `src/oar_priority_manager/core/override_manager.py`
- Create: `tests/unit/test_override_manager.py`

Computes mirrored Overwrite paths, writes via serializer, and provides `clear_override()`.

- [ ] **Step 1: Write override manager tests**

`tests/unit/test_override_manager.py`:
```python
"""Tests for core/override_manager.py — Overwrite path computation and write operations.

See spec §6.2 (override_manager), §8.1 (OAR overrides).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.core.override_manager import (
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
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/unit/test_override_manager.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement override manager**

`src/oar_priority_manager/core/override_manager.py`:
```python
"""Override manager — writes priority changes to MO2 Overwrite at mirrored paths.

See spec §6.2 (override_manager), §8.1 (OAR overrides), §8.2 (clear overrides).
NEVER writes to source mod paths. Only writes user.json to the Overwrite folder.
"""

from __future__ import annotations

import logging
from pathlib import Path

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.core.serializer import serialize_raw_dict

logger = logging.getLogger(__name__)

# Relative path within the OAR structure
OAR_REL = Path("meshes/actors/character/animations/OpenAnimationReplacer")


def compute_overwrite_path(submod: SubMod, overwrite_dir: Path) -> Path:
    """Compute the mirrored path in MO2 Overwrite for a submod's user.json.

    The path mirrors the source mod's relative OAR structure:
    overwrite/<OAR_REL>/<replacer>/<submod_folder>/user.json
    """
    # The submod folder name is the last component of config_path's parent
    submod_folder = submod.config_path.parent.name
    return overwrite_dir / OAR_REL / submod.replacer / submod_folder / "user.json"


def write_override(submod: SubMod, new_priority: int, overwrite_dir: Path) -> None:
    """Write a priority override to MO2 Overwrite for the given submod.

    Builds a new raw_dict with only priority changed, writes via serializer
    (which enforces the mutable-field allowlist), and updates the SubMod
    in-memory state.
    """
    original_raw = submod.raw_dict
    previous_priority = submod.priority

    # Build modified dict — only change priority
    modified = dict(original_raw)
    modified["priority"] = new_priority

    output_path = compute_overwrite_path(submod, overwrite_dir)

    serialize_raw_dict(
        modified=modified,
        original=original_raw,
        output_path=output_path,
        previous_priority=previous_priority,
    )

    # Update in-memory state
    submod.priority = new_priority
    submod.override_source = OverrideSource.OVERWRITE
    submod.override_is_ours = True
    # Update raw_dict to reflect the new state (for subsequent operations)
    submod.raw_dict = modified

    logger.info(
        "Wrote override for %s: %d → %d at %s",
        submod.display_path, previous_priority, new_priority, output_path,
    )


def clear_override(submod: SubMod, overwrite_dir: Path) -> None:
    """Delete the Overwrite-layer user.json for a submod.

    See spec §8.2. Reverts to whatever is in the source mod.
    """
    output_path = compute_overwrite_path(submod, overwrite_dir)
    if output_path.exists():
        output_path.unlink()
        logger.info("Cleared override for %s: deleted %s", submod.display_path, output_path)
        # Clean up empty parent directories (cosmetic)
        _remove_empty_parents(output_path.parent, overwrite_dir)


def _remove_empty_parents(directory: Path, stop_at: Path) -> None:
    """Remove empty parent directories up to (but not including) stop_at."""
    current = directory
    while current != stop_at and current.is_dir():
        try:
            current.rmdir()  # Only removes if empty
            current = current.parent
        except OSError:
            break
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/unit/test_override_manager.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Run full test suite**

```powershell
pytest -v
```

- [ ] **Step 6: Commit**

```
feat: add override manager for MO2 Overwrite writes and clear operations
```

---

## Task 8: Priority Resolver

**Files:**
- Create: `src/oar_priority_manager/core/priority_resolver.py`
- Create: `tests/unit/test_priority_resolver.py`

Builds `PriorityStack` objects from the conflict map and exposes the three mutation operations: `move_to_top`, `set_exact`, `shift`.

- [ ] **Step 1: Write priority resolver tests**

`tests/unit/test_priority_resolver.py`:
```python
"""Tests for core/priority_resolver.py — stack building and mutation operations.

See spec §6.2 (priority_resolver), §5.4 (PriorityStack).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.core.priority_resolver import (
    INT32_MAX,
    OverflowError as PriorityOverflowError,
    build_stacks,
    move_to_top,
    set_exact,
    shift,
)


def _sm(
    name: str,
    priority: int,
    mo2_mod: str = "Mod",
    replacer: str = "Rep",
    animations: list[str] | None = None,
) -> SubMod:
    return SubMod(
        mo2_mod=mo2_mod,
        replacer=replacer,
        name=name,
        description="",
        priority=priority,
        source_priority=priority,
        disabled=False,
        config_path=Path(f"C:/fake/{mo2_mod}/{replacer}/{name}/config.json"),
        override_source=OverrideSource.SOURCE,
        override_is_ours=False,
        raw_dict={"name": name, "priority": priority},
        animations=animations or [],
        conditions={},
        warnings=[],
    )


class TestBuildStacks:
    def test_builds_from_conflict_map(self):
        conflict_map = {
            "mt_idle.hkx": [
                _sm("high", 500, animations=["mt_idle.hkx"]),
                _sm("low", 100, animations=["mt_idle.hkx"]),
            ],
        }
        stacks = build_stacks(conflict_map)
        assert len(stacks) == 1
        assert stacks[0].animation_filename == "mt_idle.hkx"
        assert len(stacks[0].competitors) == 2
        assert stacks[0].competitors[0].priority == 500

    def test_stacks_sorted_alphabetically(self):
        conflict_map = {
            "mt_walkforward.hkx": [_sm("a", 100, animations=["mt_walkforward.hkx"])],
            "mt_idle.hkx": [_sm("b", 200, animations=["mt_idle.hkx"])],
        }
        stacks = build_stacks(conflict_map)
        names = [s.animation_filename for s in stacks]
        assert names == ["mt_idle.hkx", "mt_walkforward.hkx"]


class TestMoveToTopSubmod:
    def test_single_submod_gets_max_plus_one(self):
        target = _sm("you", 100, animations=["mt_idle.hkx"])
        competitor = _sm("other", 500, animations=["mt_idle.hkx"])
        conflict_map = {"mt_idle.hkx": [competitor, target]}

        new_priorities = move_to_top(target, conflict_map, scope="submod")
        assert new_priorities == {target: 501}

    def test_already_winning_stays_same(self):
        target = _sm("you", 500, animations=["mt_idle.hkx"])
        competitor = _sm("other", 100, animations=["mt_idle.hkx"])
        conflict_map = {"mt_idle.hkx": [target, competitor]}

        new_priorities = move_to_top(target, conflict_map, scope="submod")
        # Already #1 everywhere — no change needed
        assert new_priorities == {}

    def test_multiple_stacks_uses_global_max(self):
        target = _sm("you", 100, animations=["a.hkx", "b.hkx"])
        comp_a = _sm("ca", 300, animations=["a.hkx"])
        comp_b = _sm("cb", 700, animations=["b.hkx"])
        conflict_map = {
            "a.hkx": [comp_a, target],
            "b.hkx": [comp_b, target],
        }
        new_priorities = move_to_top(target, conflict_map, scope="submod")
        assert new_priorities[target] == 701


class TestMoveToTopReplacerScope:
    def test_preserves_relative_ordering(self):
        """Floor-anchored shift: (global_max+1) + (old - min(old_in_scope))"""
        sub_a = _sm("a", 100, mo2_mod="MyMod", replacer="Rep", animations=["idle.hkx"])
        sub_b = _sm("b", 200, mo2_mod="MyMod", replacer="Rep", animations=["idle.hkx"])
        competitor = _sm("ext", 500, mo2_mod="Other", animations=["idle.hkx"])
        conflict_map = {"idle.hkx": [competitor, sub_b, sub_a]}

        new_priorities = move_to_top(sub_a, conflict_map, scope="replacer")
        # global_max of external competitors = 500
        # min(old_in_scope) = 100, so:
        # sub_a: 501 + (100-100) = 501
        # sub_b: 501 + (200-100) = 601
        assert new_priorities[sub_a] == 501
        assert new_priorities[sub_b] == 601


class TestMoveToTopModScope:
    def test_mod_scope_includes_all_replacers(self):
        sub_a = _sm("a", 100, mo2_mod="MyMod", replacer="Rep1", animations=["idle.hkx"])
        sub_b = _sm("b", 300, mo2_mod="MyMod", replacer="Rep2", animations=["idle.hkx"])
        competitor = _sm("ext", 500, mo2_mod="Other", animations=["idle.hkx"])
        conflict_map = {"idle.hkx": [competitor, sub_b, sub_a]}

        new_priorities = move_to_top(sub_a, conflict_map, scope="mod")
        # Both submods from MyMod get shifted
        assert sub_a in new_priorities
        assert sub_b in new_priorities
        assert new_priorities[sub_a] == 501  # 501 + (100-100)
        assert new_priorities[sub_b] == 701  # 501 + (300-100)


class TestOverflowGuard:
    def test_rejects_overflow(self):
        target = _sm("you", 100, animations=["idle.hkx"])
        competitor = _sm("other", INT32_MAX, animations=["idle.hkx"])
        conflict_map = {"idle.hkx": [competitor, target]}
        with pytest.raises(PriorityOverflowError):
            move_to_top(target, conflict_map, scope="submod")


class TestSetExact:
    def test_sets_specific_priority(self):
        target = _sm("you", 100, animations=["idle.hkx"])
        result = set_exact(target, 999)
        assert result == {target: 999}

    def test_rejects_overflow(self):
        target = _sm("you", 100, animations=["idle.hkx"])
        with pytest.raises(PriorityOverflowError):
            set_exact(target, INT32_MAX + 1)


class TestShift:
    def test_floor_anchored_shift(self):
        sub_a = _sm("a", 100, mo2_mod="MyMod", replacer="Rep", animations=["idle.hkx"])
        sub_b = _sm("b", 200, mo2_mod="MyMod", replacer="Rep", animations=["idle.hkx"])
        new_priorities = shift([sub_a, sub_b], floor_priority=500)
        # min = 100, so a -> 500+(100-100)=500, b -> 500+(200-100)=600
        assert new_priorities[sub_a] == 500
        assert new_priorities[sub_b] == 600

    def test_shift_preserves_gaps(self):
        sub_a = _sm("a", 100, animations=["idle.hkx"])
        sub_b = _sm("b", 150, animations=["idle.hkx"])
        sub_c = _sm("c", 300, animations=["idle.hkx"])
        new_priorities = shift([sub_a, sub_b, sub_c], floor_priority=1000)
        # Gaps: 100->150 is 50, 150->300 is 150. Preserved.
        assert new_priorities[sub_a] == 1000
        assert new_priorities[sub_b] == 1050
        assert new_priorities[sub_c] == 1200

    def test_rejects_overflow(self):
        sub_a = _sm("a", 0, animations=["idle.hkx"])
        sub_b = _sm("b", INT32_MAX, animations=["idle.hkx"])
        with pytest.raises(PriorityOverflowError):
            shift([sub_a, sub_b], floor_priority=1)
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/unit/test_priority_resolver.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement priority resolver**

`src/oar_priority_manager/core/priority_resolver.py`:
```python
"""Priority resolver — builds PriorityStacks and exposes mutation operations.

See spec §5.4 (PriorityStack), §6.2 (priority_resolver responsibilities).
"""

from __future__ import annotations

import logging
from pathlib import Path

from oar_priority_manager.core.models import PriorityStack, SubMod

logger = logging.getLogger(__name__)

INT32_MAX = 2_147_483_647
INT32_MIN = -2_147_483_648


class OverflowError(Exception):
    """Raised when a computed priority would exceed INT32 range."""

    def __init__(self, computed: int) -> None:
        self.computed = computed
        super().__init__(
            f"Computed priority {computed} exceeds INT32 range "
            f"[{INT32_MIN}, {INT32_MAX}]. Operation cancelled."
        )


def _check_overflow(value: int) -> None:
    if value > INT32_MAX or value < INT32_MIN:
        raise OverflowError(value)


def build_stacks(conflict_map: dict[str, list[SubMod]]) -> list[PriorityStack]:
    """Build PriorityStack objects from the conflict map, sorted alphabetically by filename."""
    stacks = []
    for filename in sorted(conflict_map.keys()):
        stacks.append(PriorityStack(
            animation_filename=filename,
            competitors=conflict_map[filename],
        ))
    return stacks


def _get_scope_submods(
    target: SubMod,
    conflict_map: dict[str, list[SubMod]],
    scope: str,
) -> list[SubMod]:
    """Get all unique submods in the scope (submod/replacer/mod)."""
    seen: set[int] = set()
    result: list[SubMod] = []

    for anim in target.animations:
        if anim not in conflict_map:
            continue
        for sm in conflict_map[anim]:
            sm_id = id(sm)
            if sm_id in seen:
                continue
            if scope == "submod" and sm is target:
                seen.add(sm_id)
                result.append(sm)
            elif scope == "replacer" and sm.mo2_mod == target.mo2_mod and sm.replacer == target.replacer:
                seen.add(sm_id)
                result.append(sm)
            elif scope == "mod" and sm.mo2_mod == target.mo2_mod:
                seen.add(sm_id)
                result.append(sm)

    return result


def _get_external_max(
    scope_submods: list[SubMod],
    conflict_map: dict[str, list[SubMod]],
) -> int | None:
    """Find the highest priority among external competitors (not in scope)."""
    scope_ids = {id(sm) for sm in scope_submods}
    max_ext: int | None = None

    for sm in scope_submods:
        for anim in sm.animations:
            if anim not in conflict_map:
                continue
            for competitor in conflict_map[anim]:
                if id(competitor) not in scope_ids:
                    if max_ext is None or competitor.priority > max_ext:
                        max_ext = competitor.priority

    return max_ext


def move_to_top(
    target: SubMod,
    conflict_map: dict[str, list[SubMod]],
    scope: str = "submod",
) -> dict[SubMod, int]:
    """Compute new priorities to make target (and scope) #1 in all stacks.

    Args:
        target: The submod the user selected.
        conflict_map: Animation filename → list of competing submods.
        scope: "submod", "replacer", or "mod".

    Returns:
        Dict of SubMod → new_priority. Empty if already winning everywhere.

    Raises:
        OverflowError: If computed priority exceeds INT32_MAX.
    """
    scope_submods = _get_scope_submods(target, conflict_map, scope)
    if not scope_submods:
        return {}

    external_max = _get_external_max(scope_submods, conflict_map)
    if external_max is None:
        # No external competitors — already winning
        return {}

    # Check if already winning (all scope submods have priority > external_max)
    if all(sm.priority > external_max for sm in scope_submods):
        return {}

    if scope == "submod":
        new_priority = external_max + 1
        _check_overflow(new_priority)
        return {target: new_priority}

    # Replacer/mod scope: floor-anchored shift
    old_priorities = [sm.priority for sm in scope_submods]
    min_old = min(old_priorities)
    base = external_max + 1

    result: dict[SubMod, int] = {}
    for sm in scope_submods:
        new_p = base + (sm.priority - min_old)
        _check_overflow(new_p)
        result[sm] = new_p

    return result


def set_exact(target: SubMod, priority: int) -> dict[SubMod, int]:
    """Set an exact priority for a single submod.

    Raises:
        OverflowError: If priority exceeds INT32 range.
    """
    _check_overflow(priority)
    return {target: priority}


def shift(
    submods: list[SubMod],
    floor_priority: int,
) -> dict[SubMod, int]:
    """Shift a group of submods so the lowest lands at floor_priority,
    preserving relative gaps.

    Args:
        submods: The submods to shift.
        floor_priority: The target priority for the lowest submod.

    Returns:
        Dict of SubMod → new_priority.

    Raises:
        OverflowError: If any computed priority exceeds INT32 range.
    """
    if not submods:
        return {}

    old_priorities = [sm.priority for sm in submods]
    min_old = min(old_priorities)

    result: dict[SubMod, int] = {}
    for sm in submods:
        new_p = floor_priority + (sm.priority - min_old)
        _check_overflow(new_p)
        result[sm] = new_p

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/unit/test_priority_resolver.py -v
```

Expected: all 13 tests PASS.

- [ ] **Step 5: Run full test suite**

```powershell
pytest -v
```

- [ ] **Step 6: Commit**

```
feat: add priority resolver with move_to_top, set_exact, and shift operations
```

---

## Task 9: Filter Engine

**Files:**
- Create: `src/oar_priority_manager/core/filter_engine.py`
- Create: `tests/unit/test_filter_engine.py`

Walks condition trees to build `condition_types_present` and `condition_types_negated` sets, and matches filter queries.

- [ ] **Step 1: Write filter engine tests**

`tests/unit/test_filter_engine.py`:
```python
"""Tests for core/filter_engine.py — structural condition-presence filter.

See spec §6.2 (filter_engine), §7.6 (condition filter semantics).
"""

from __future__ import annotations

import pytest

from oar_priority_manager.core.filter_engine import (
    extract_condition_types,
    match_filter,
    parse_filter_query,
)


class TestExtractConditionTypes:
    def test_flat_condition_list(self):
        conditions = [
            {"condition": "IsFemale", "negated": False},
            {"condition": "IsInCombat", "negated": False},
        ]
        present, negated = extract_condition_types(conditions)
        assert present == {"IsFemale", "IsInCombat"}
        assert negated == set()

    def test_negated_condition(self):
        conditions = [
            {"condition": "IsFemale", "negated": False},
            {"condition": "IsWearingHelmet", "negated": True},
        ]
        present, negated = extract_condition_types(conditions)
        assert present == {"IsFemale", "IsWearingHelmet"}
        assert negated == {"IsWearingHelmet"}

    def test_nested_and_group(self):
        conditions = [
            {
                "condition": "AND",
                "conditions": [
                    {"condition": "IsFemale", "negated": False},
                    {"condition": "IsInCombat", "negated": False},
                ],
            },
        ]
        present, negated = extract_condition_types(conditions)
        assert "IsFemale" in present
        assert "IsInCombat" in present

    def test_nested_or_group(self):
        conditions = [
            {
                "condition": "OR",
                "conditions": [
                    {"condition": "HasKeyword", "negated": False},
                    {"condition": "HasPerk", "negated": False},
                ],
            },
        ]
        present, negated = extract_condition_types(conditions)
        assert present == {"HasKeyword", "HasPerk"}

    def test_type_in_both_present_and_negated(self):
        """A type can appear in both sets (spec note on §5.2)."""
        conditions = [
            {"condition": "IsFemale", "negated": False},
            {
                "condition": "AND",
                "conditions": [
                    {"condition": "IsFemale", "negated": True},
                ],
            },
        ]
        present, negated = extract_condition_types(conditions)
        assert "IsFemale" in present
        assert "IsFemale" in negated

    def test_empty_conditions(self):
        present, negated = extract_condition_types([])
        assert present == set()
        assert negated == set()

    def test_conditions_as_dict_with_conditions_key(self):
        """Some OAR configs wrap conditions in an outer dict."""
        conditions = {
            "type": "AND",
            "conditions": [
                {"condition": "IsFemale", "negated": False},
            ],
        }
        present, negated = extract_condition_types(conditions)
        assert "IsFemale" in present

    def test_deeply_nested(self):
        conditions = [
            {
                "condition": "AND",
                "conditions": [
                    {
                        "condition": "OR",
                        "conditions": [
                            {"condition": "DeepType", "negated": False},
                        ],
                    },
                ],
            },
        ]
        present, _ = extract_condition_types(conditions)
        assert "DeepType" in present


class TestParseFilterQuery:
    def test_single_term(self):
        query = parse_filter_query("IsFemale")
        assert query == [("has", "IsFemale")]

    def test_and_terms(self):
        query = parse_filter_query("IsFemale AND IsInCombat")
        assert query == [("has", "IsFemale"), ("has", "IsInCombat")]

    def test_not_term(self):
        query = parse_filter_query("NOT IsWearingHelmet")
        assert query == [("hasn't", "IsWearingHelmet")]

    def test_combined(self):
        query = parse_filter_query("IsFemale AND IsInCombat AND NOT IsWearingHelmet")
        assert query == [
            ("has", "IsFemale"),
            ("has", "IsInCombat"),
            ("hasn't", "IsWearingHelmet"),
        ]

    def test_condition_prefix_stripped(self):
        query = parse_filter_query("condition: IsFemale")
        assert query == [("has", "IsFemale")]


class TestMatchFilter:
    def test_has_match(self):
        query = [("has", "IsFemale")]
        assert match_filter(query, {"IsFemale", "IsInCombat"}) is True

    def test_has_no_match(self):
        query = [("has", "IsFemale")]
        assert match_filter(query, {"IsInCombat"}) is False

    def test_hasnt_match(self):
        query = [("hasn't", "IsWearingHelmet")]
        assert match_filter(query, {"IsFemale"}) is True

    def test_hasnt_no_match(self):
        query = [("hasn't", "IsWearingHelmet")]
        assert match_filter(query, {"IsWearingHelmet"}) is False

    def test_combined_query(self):
        query = [("has", "IsFemale"), ("hasn't", "IsWearingHelmet")]
        assert match_filter(query, {"IsFemale", "IsInCombat"}) is True
        assert match_filter(query, {"IsFemale", "IsWearingHelmet"}) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/unit/test_filter_engine.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement filter engine**

`src/oar_priority_manager/core/filter_engine.py`:
```python
"""Structural condition-presence filter engine.

See spec §6.2 (filter_engine), §7.6 (semantics).

This is a structural tree walk, NOT a semantic condition evaluator.
It only answers "does this condition tree mention type X?" —
never "would this condition tree evaluate to true for actor Y?"
That distinction is what keeps this project from becoming attempt 2.
"""

from __future__ import annotations

import re

# Logical group types that are not leaf conditions
_GROUP_TYPES = frozenset({"AND", "OR", "NOT"})


def extract_condition_types(
    conditions: dict | list,
) -> tuple[set[str], set[str]]:
    """Walk a condition tree and extract condition type names.

    Args:
        conditions: The condition tree from a config.json/user.json.
            Can be a list of condition dicts or a single dict with "conditions" key.

    Returns:
        Tuple of (present, negated):
        - present: all condition type names that appear anywhere
        - negated: types appearing with negated=True or inside NOT groups
    """
    present: set[str] = set()
    negated: set[str] = set()

    def _walk(node: dict | list, in_not: bool = False) -> None:
        if isinstance(node, list):
            for item in node:
                if isinstance(item, dict):
                    _walk(item, in_not)
            return

        if not isinstance(node, dict):
            return

        condition_type = node.get("condition", node.get("type", ""))

        # Recurse into nested conditions
        nested = node.get("conditions")
        if nested and isinstance(nested, (list, dict)):
            is_not = condition_type == "NOT"
            _walk(nested, in_not or is_not)

        # Record leaf condition types (skip logical group names)
        if condition_type and condition_type not in _GROUP_TYPES:
            present.add(condition_type)
            if in_not or node.get("negated", False):
                negated.add(condition_type)

    _walk(conditions)
    return present, negated


def parse_filter_query(text: str) -> list[tuple[str, str]]:
    """Parse a condition filter query string into a list of (operator, type_name) tuples.

    Supported syntax (spec §7.6):
    - "IsFemale" → [("has", "IsFemale")]
    - "IsFemale AND IsInCombat" → [("has", "IsFemale"), ("has", "IsInCombat")]
    - "NOT IsWearingHelmet" → [("hasn't", "IsWearingHelmet")]
    - "condition: IsFemale" → [("has", "IsFemale")]
    """
    # Strip "condition:" prefix
    text = re.sub(r"^condition:\s*", "", text.strip())

    terms: list[tuple[str, str]] = []
    tokens = text.split()

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.upper() == "AND":
            i += 1
            continue
        if token.upper() == "NOT" and i + 1 < len(tokens):
            terms.append(("hasn't", tokens[i + 1]))
            i += 2
            continue
        if token.upper() not in ("OR",):  # OR is accepted but treated as AND for flat queries
            terms.append(("has", token))
        i += 1

    return terms


def match_filter(
    query: list[tuple[str, str]],
    condition_types_present: set[str],
) -> bool:
    """Check if a submod matches a parsed filter query.

    All terms must match (AND semantics).
    - ("has", X): X must be in condition_types_present
    - ("hasn't", X): X must NOT be in condition_types_present
    """
    for op, type_name in query:
        if op == "has" and type_name not in condition_types_present:
            return False
        if op == "hasn't" and type_name in condition_types_present:
            return False
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/unit/test_filter_engine.py -v
```

Expected: all 18 tests PASS.

- [ ] **Step 5: Run full test suite**

```powershell
pytest -v
```

- [ ] **Step 6: Commit**

```
feat: add structural condition-presence filter engine
```

---

## Task 10: App Config + Instance Detection

**Files:**
- Create: `src/oar_priority_manager/app/config.py`
- Create: `tests/unit/test_config.py`

Tool config read/write and MO2 instance root detection chain (§8.3.1).

- [ ] **Step 1: Write config tests**

`tests/unit/test_config.py`:
```python
"""Tests for app/config.py — tool config and MO2 instance detection.

See spec §8.3 (tool config), §8.3.1 (instance detection chain).
"""

from __future__ import annotations

import json
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
        """--mods-path argument is the primary detection method."""
        mods = tmp_path / "mods"
        mods.mkdir()
        result = detect_instance_root(mods_path=str(mods))
        assert result == tmp_path

    def test_mods_path_nonexistent_raises(self, tmp_path: Path):
        with pytest.raises(DetectionError):
            detect_instance_root(mods_path=str(tmp_path / "nonexistent" / "mods"))

    def test_cwd_with_mo_ini(self, tmp_path: Path):
        """CWD containing ModOrganizer.ini is the fallback."""
        (tmp_path / "ModOrganizer.ini").touch()
        (tmp_path / "mods").mkdir()
        result = detect_instance_root(cwd=tmp_path)
        assert result == tmp_path

    def test_walk_up_finds_instance(self, tmp_path: Path):
        """Walk-up from CWD finds instance root in a parent directory."""
        (tmp_path / "ModOrganizer.ini").touch()
        (tmp_path / "mods").mkdir()
        nested = tmp_path / "tools" / "oar-manager"
        nested.mkdir(parents=True)
        result = detect_instance_root(cwd=nested)
        assert result == tmp_path

    def test_no_detection_raises(self, tmp_path: Path):
        """No detection method succeeds → DetectionError."""
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
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/unit/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement config**

`src/oar_priority_manager/app/config.py`:
```python
"""Application config and MO2 instance root detection.

See spec §8.3 (tool config), §8.3.1 (detection chain).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


class DetectionError(Exception):
    """Raised when MO2 instance root cannot be detected."""


@dataclass
class AppConfig:
    """Tool configuration persisted to disk. One config per MO2 instance."""

    relative_or_absolute: str = "relative"
    submod_sort: str = "priority"
    window_geometry: str = ""
    splitter_positions: list[int] = field(default_factory=list)
    search_history: list[str] = field(default_factory=list)
    last_selected_path: str = ""


def detect_instance_root(
    mods_path: str | None = None,
    cwd: Path | None = None,
) -> Path:
    """Detect the MO2 instance root using the fallback chain (spec §8.3.1).

    1. --mods-path CLI arg → parent is instance root
    2. CWD contains ModOrganizer.ini
    3. Walk up from CWD looking for mods/ + ModOrganizer.ini
    4. Hard error (DetectionError)
    """
    # 1. --mods-path argument (primary, recommended)
    if mods_path:
        mods = Path(mods_path)
        if mods.is_dir():
            return mods.parent
        raise DetectionError(
            f"--mods-path '{mods_path}' does not exist or is not a directory."
        )

    # 2. CWD contains ModOrganizer.ini
    if cwd and (cwd / "ModOrganizer.ini").is_file() and (cwd / "mods").is_dir():
        return cwd

    # 3. Walk up from CWD
    if cwd:
        current = cwd
        while current != current.parent:
            if (current / "ModOrganizer.ini").is_file() and (current / "mods").is_dir():
                return current
            current = current.parent

    raise DetectionError(
        "Could not detect MO2 instance. Please configure the executable with "
        "--mods-path or run the tool from within your MO2 instance directory."
    )


def load_config(path: Path) -> AppConfig:
    """Load tool config from disk. Returns defaults if file is missing or corrupt."""
    if not path.is_file():
        return AppConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return AppConfig()
        return AppConfig(
            relative_or_absolute=data.get("relative_or_absolute", "relative"),
            submod_sort=data.get("submod_sort", "priority"),
            window_geometry=data.get("window_geometry", ""),
            splitter_positions=data.get("splitter_positions", []),
            search_history=data.get("search_history", []),
            last_selected_path=data.get("last_selected_path", ""),
        )
    except (json.JSONDecodeError, OSError):
        logger.warning("Corrupt config at %s, using defaults", path)
        return AppConfig()


def save_config(config: AppConfig, path: Path) -> None:
    """Save tool config to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(config), indent=2) + "\n",
        encoding="utf-8",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/unit/test_config.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Run full test suite**

```powershell
pytest -v
```

- [ ] **Step 6: Commit**

```
feat: add app config with MO2 instance detection chain
```

---

## Task 11: App Entry Point

**Files:**
- Create: `src/oar_priority_manager/app/main.py`

This is a thin entry point. It parses CLI args, detects the instance, runs the scan pipeline, and launches the UI. Tested via smoke tests (Task 20).

- [ ] **Step 1: Implement entry point**

`src/oar_priority_manager/app/main.py`:
```python
"""Application entry point.

See spec §6.3 (data flow). Parses CLI args, detects MO2 instance,
runs scan pipeline, constructs UI.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from oar_priority_manager.app.config import (
    AppConfig,
    DetectionError,
    detect_instance_root,
    load_config,
    save_config,
)
from oar_priority_manager.core.anim_scanner import build_conflict_map, scan_animations
from oar_priority_manager.core.filter_engine import extract_condition_types
from oar_priority_manager.core.priority_resolver import build_stacks
from oar_priority_manager.core.scanner import scan_mods

logger = logging.getLogger(__name__)

CONFIG_SUBDIR = "oar-priority-manager"
CONFIG_FILENAME = "config.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="oar-priority-manager",
        description="OAR priority management tool for Skyrim modders using MO2",
    )
    parser.add_argument(
        "--mods-path",
        help="Path to MO2 mods/ directory. Recommended: --mods-path \"%%BASE_DIR%%/mods\"",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


def run_scan(instance_root: Path) -> tuple:
    """Execute the full scan pipeline (spec §6.3 steps 2-3).

    Returns (submods, conflict_map, stacks).
    """
    mods_dir = instance_root / "mods"
    overwrite_dir = instance_root / "overwrite"

    # Step 2: Scan
    submods = scan_mods(mods_dir, overwrite_dir)
    scan_animations(submods)
    conflict_map = build_conflict_map(submods)
    stacks = build_stacks(conflict_map)

    # Step 3: Populate condition type sets
    for sm in submods:
        present, negated = extract_condition_types(sm.conditions)
        sm.condition_types_present = present
        sm.condition_types_negated = negated

    return submods, conflict_map, stacks


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(name)s %(levelname)s: %(message)s",
    )

    # Detect MO2 instance
    try:
        instance_root = detect_instance_root(
            mods_path=args.mods_path,
            cwd=Path.cwd(),
        )
    except DetectionError as e:
        # Fall through to UI error dialog if QApplication is running,
        # otherwise print and exit
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    logger.info("MO2 instance root: %s", instance_root)

    # Load tool config
    config_path = instance_root / CONFIG_SUBDIR / CONFIG_FILENAME
    app_config = load_config(config_path)

    # Run scan
    submods, conflict_map, stacks = run_scan(instance_root)
    logger.info("Loaded %d submods, %d animation stacks", len(submods), len(stacks))

    # Launch UI (placeholder until UI tasks are complete)
    app = QApplication(sys.argv)
    app.setApplicationName("OAR Priority Manager")

    # Import here to avoid circular imports and allow headless testing
    from oar_priority_manager.ui.main_window import MainWindow

    window = MainWindow(
        submods=submods,
        conflict_map=conflict_map,
        stacks=stacks,
        app_config=app_config,
        instance_root=instance_root,
    )
    window.show()

    exit_code = app.exec()

    # Save config on shutdown
    save_config(app_config, config_path)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify import works (no runtime test yet — UI not built)**

```powershell
python -c "from oar_priority_manager.app.main import parse_args; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```
feat: add application entry point with CLI args and scan pipeline
```

---

## Task 12: UI — Tree Model

**Files:**
- Create: `src/oar_priority_manager/ui/tree_model.py`
- Create: `tests/unit/test_tree_model.py`

Qt `QAbstractItemModel` subclass that builds the Mod → Replacer → Submod hierarchy and provides a search index for the unified search bar.

- [ ] **Step 1: Write tree model tests**

`tests/unit/test_tree_model.py`:
```python
"""Tests for ui/tree_model.py — hierarchy construction and search index.

See spec §6.2 (tree_model), §7.3 (tree sort order).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.ui.tree_model import SearchIndex, TreeNode, build_tree


def _sm(
    name: str,
    mo2_mod: str = "ModA",
    replacer: str = "Rep",
    priority: int = 100,
    disabled: bool = False,
    animations: list[str] | None = None,
) -> SubMod:
    return SubMod(
        mo2_mod=mo2_mod,
        replacer=replacer,
        name=name,
        description="",
        priority=priority,
        source_priority=priority,
        disabled=disabled,
        config_path=Path(f"C:/mods/{mo2_mod}/{replacer}/{name}/config.json"),
        override_source=OverrideSource.SOURCE,
        override_is_ours=False,
        raw_dict={"name": name, "priority": priority},
        animations=animations or [],
        conditions={},
        warnings=[],
    )


class TestBuildTree:
    def test_single_submod(self):
        submods = [_sm("sub1", mo2_mod="ModA", replacer="Rep1")]
        root = build_tree(submods)
        assert len(root.children) == 1  # One mod
        mod = root.children[0]
        assert mod.display_name == "ModA"
        assert len(mod.children) == 1  # One replacer
        rep = mod.children[0]
        assert rep.display_name == "Rep1"
        assert len(rep.children) == 1  # One submod
        assert rep.children[0].display_name == "sub1"

    def test_mods_sorted_alphabetically(self):
        submods = [
            _sm("s1", mo2_mod="Zebra"),
            _sm("s2", mo2_mod="Alpha"),
            _sm("s3", mo2_mod="Middle"),
        ]
        root = build_tree(submods)
        names = [c.display_name for c in root.children]
        assert names == ["Alpha", "Middle", "Zebra"]

    def test_submods_sorted_by_priority_descending(self):
        submods = [
            _sm("low", mo2_mod="Mod", replacer="Rep", priority=100),
            _sm("high", mo2_mod="Mod", replacer="Rep", priority=500),
            _sm("mid", mo2_mod="Mod", replacer="Rep", priority=300),
        ]
        root = build_tree(submods)
        rep = root.children[0].children[0]
        priorities = [c.submod.priority for c in rep.children]
        assert priorities == [500, 300, 100]

    def test_multiple_replacers_under_mod(self):
        submods = [
            _sm("s1", mo2_mod="Mod", replacer="RepB"),
            _sm("s2", mo2_mod="Mod", replacer="RepA"),
        ]
        root = build_tree(submods)
        rep_names = [c.display_name for c in root.children[0].children]
        assert rep_names == ["RepA", "RepB"]  # Alphabetical

    def test_auto_expand_single_replacer(self):
        """Mods with one replacer have that replacer marked auto-expand."""
        submods = [_sm("s1", mo2_mod="Mod", replacer="OnlyRep")]
        root = build_tree(submods)
        mod = root.children[0]
        assert len(mod.children) == 1
        assert mod.children[0].auto_expand is True

    def test_no_auto_expand_multiple_replacers(self):
        submods = [
            _sm("s1", mo2_mod="Mod", replacer="Rep1"),
            _sm("s2", mo2_mod="Mod", replacer="Rep2"),
        ]
        root = build_tree(submods)
        mod = root.children[0]
        assert not any(c.auto_expand for c in mod.children)


class TestSearchIndex:
    def test_indexes_mod_names(self):
        submods = [_sm("s1", mo2_mod="Female Combat Pack")]
        root = build_tree(submods)
        index = SearchIndex(root, {})
        results = index.search("Female")
        assert any("Female Combat Pack" in r.display_text for r in results)

    def test_indexes_submod_names(self):
        submods = [_sm("heavy", mo2_mod="Mod")]
        root = build_tree(submods)
        index = SearchIndex(root, {})
        results = index.search("heavy")
        assert any("heavy" in r.display_text for r in results)

    def test_indexes_animation_filenames(self):
        submods = [_sm("s1", animations=["mt_walkforward.hkx"])]
        conflict_map = {"mt_walkforward.hkx": submods}
        root = build_tree(submods)
        index = SearchIndex(root, conflict_map)
        results = index.search("walkforward")
        assert len(results) > 0

    def test_empty_query_returns_empty(self):
        submods = [_sm("s1")]
        root = build_tree(submods)
        index = SearchIndex(root, {})
        assert index.search("") == []

    def test_case_insensitive(self):
        submods = [_sm("Heavy", mo2_mod="Mod")]
        root = build_tree(submods)
        index = SearchIndex(root, {})
        results = index.search("heavy")
        assert len(results) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
pytest tests/unit/test_tree_model.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement tree model**

`src/oar_priority_manager/ui/tree_model.py`:
```python
"""Tree hierarchy model and search index for the left panel.

See spec §6.2 (tree_model), §7.3 (sort order, auto-expand).
Builds a Mod → Replacer → Submod tree from a flat list of SubMods.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import NamedTuple

from oar_priority_manager.core.models import SubMod


class NodeType(Enum):
    ROOT = "root"
    MOD = "mod"
    REPLACER = "replacer"
    SUBMOD = "submod"


@dataclass
class TreeNode:
    """A node in the Mod → Replacer → Submod tree."""

    display_name: str
    node_type: NodeType
    children: list[TreeNode] = field(default_factory=list)
    submod: SubMod | None = None
    parent: TreeNode | None = field(default=None, repr=False)
    auto_expand: bool = False

    @property
    def mo2_mod(self) -> str | None:
        if self.node_type == NodeType.MOD:
            return self.display_name
        if self.parent:
            return self.parent.mo2_mod
        return None

    @property
    def replacer_name(self) -> str | None:
        if self.node_type == NodeType.REPLACER:
            return self.display_name
        return None


def build_tree(submods: list[SubMod]) -> TreeNode:
    """Build the tree hierarchy from a flat list of submods.

    Sort order (spec §7.3):
    - Mods: alphabetical by display name (case-sensitive, OAR-native)
    - Replacers: alphabetical by folder name
    - Submods: priority descending (OAR-native)
    """
    root = TreeNode(display_name="", node_type=NodeType.ROOT)

    # Group submods by (mo2_mod, replacer)
    mods: dict[str, dict[str, list[SubMod]]] = {}
    for sm in submods:
        if sm.mo2_mod not in mods:
            mods[sm.mo2_mod] = {}
        if sm.replacer not in mods[sm.mo2_mod]:
            mods[sm.mo2_mod][sm.replacer] = []
        mods[sm.mo2_mod][sm.replacer].append(sm)

    # Build tree nodes, sorted per spec
    for mod_name in sorted(mods.keys()):
        mod_node = TreeNode(
            display_name=mod_name,
            node_type=NodeType.MOD,
            parent=root,
        )
        replacers = mods[mod_name]

        for rep_name in sorted(replacers.keys()):
            rep_node = TreeNode(
                display_name=rep_name,
                node_type=NodeType.REPLACER,
                parent=mod_node,
            )

            # Submods sorted by priority descending
            rep_submods = sorted(replacers[rep_name], key=lambda s: s.priority, reverse=True)
            for sm in rep_submods:
                submod_node = TreeNode(
                    display_name=sm.name,
                    node_type=NodeType.SUBMOD,
                    submod=sm,
                    parent=rep_node,
                )
                rep_node.children.append(submod_node)

            mod_node.children.append(rep_node)

        # Auto-expand single replacers (spec §7.3)
        if len(mod_node.children) == 1:
            mod_node.children[0].auto_expand = True

        root.children.append(mod_node)

    return root


class SearchResult(NamedTuple):
    display_text: str
    node_type: NodeType
    node: TreeNode


class SearchIndex:
    """Flat search index for the unified search bar (spec §7.2).

    Indexes mod names, replacer names, submod names, and animation filenames.
    Fuzzy-match: case-insensitive substring match.
    """

    def __init__(self, root: TreeNode, conflict_map: dict[str, list[SubMod]]) -> None:
        self._entries: list[SearchResult] = []
        self._anim_entries: dict[str, list[TreeNode]] = {}  # anim -> submod nodes
        self._build(root, conflict_map)

    def _build(self, root: TreeNode, conflict_map: dict[str, list[SubMod]]) -> None:
        # Map submod identity → tree node for animation lookups
        submod_to_node: dict[int, TreeNode] = {}

        for mod_node in root.children:
            self._entries.append(SearchResult(mod_node.display_name, NodeType.MOD, mod_node))
            for rep_node in mod_node.children:
                self._entries.append(SearchResult(rep_node.display_name, NodeType.REPLACER, rep_node))
                for sub_node in rep_node.children:
                    self._entries.append(SearchResult(sub_node.display_name, NodeType.SUBMOD, sub_node))
                    if sub_node.submod:
                        submod_to_node[id(sub_node.submod)] = sub_node

        # Index animations
        for anim_name, competitors in conflict_map.items():
            nodes = [submod_to_node[id(sm)] for sm in competitors if id(sm) in submod_to_node]
            if nodes:
                self._anim_entries[anim_name] = nodes

    def search(self, query: str) -> list[SearchResult]:
        """Fuzzy-match against all indexed entries. Case-insensitive substring match."""
        if not query.strip():
            return []
        q = query.lower()
        results: list[SearchResult] = []

        # Match against mod/replacer/submod names
        for entry in self._entries:
            if q in entry.display_text.lower():
                results.append(entry)

        # Match against animation filenames
        for anim_name, nodes in self._anim_entries.items():
            if q in anim_name.lower():
                for node in nodes:
                    result = SearchResult(
                        f"{anim_name} ({node.display_name})",
                        NodeType.SUBMOD,
                        node,
                    )
                    if result not in results:
                        results.append(result)

        return results
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
pytest tests/unit/test_tree_model.py -v
```

Expected: all 11 tests PASS.

- [ ] **Step 5: Run full test suite**

```powershell
pytest -v
```

- [ ] **Step 6: Commit**

```
feat: add tree model with hierarchy construction and search index
```

---

## Task 13: UI Shell — Main Window

**Files:**
- Create: `src/oar_priority_manager/ui/main_window.py`
- Create: `src/oar_priority_manager/ui/tree_panel.py`
- Create: `src/oar_priority_manager/ui/details_panel.py`
- Create: `src/oar_priority_manager/ui/stacks_panel.py`
- Create: `src/oar_priority_manager/ui/conditions_panel.py`
- Create: `src/oar_priority_manager/ui/search_bar.py`
- Create: `src/oar_priority_manager/ui/filter_builder.py`

This is a large UI task. The goal is to get the three-pane layout wired up with **stub panels** that display basic content. Each panel will be fleshed out in subsequent tasks. The main window establishes the layout, splitters, and signal wiring.

- [ ] **Step 1: Create all UI module stubs**

Each stub panel is a `QWidget` subclass with a constructor that accepts the data it needs and displays placeholder content. These will be progressively implemented in Tasks 14-19.

`src/oar_priority_manager/ui/tree_panel.py`:
```python
"""Left-column tree panel showing Mod → Replacer → Submod hierarchy.

See spec §7.3. Full implementation in Task 14.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from oar_priority_manager.core.models import SubMod
from oar_priority_manager.ui.tree_model import NodeType, TreeNode, build_tree


class TreePanel(QWidget):
    """Tree panel: Mod → Replacer → Submod hierarchy with status icons."""

    # Emitted when a tree node is selected: (node_type, submod_or_None)
    selection_changed = Signal(object, object)

    def __init__(self, submods: list[SubMod], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._submods = submods
        self._root = build_tree(submods)
        self._setup_ui()
        self._populate()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.currentItemChanged.connect(self._on_selection)
        layout.addWidget(self._tree)

    def _populate(self) -> None:
        self._tree.clear()
        self._item_map: dict[int, TreeNode] = {}

        for mod_node in self._root.children:
            mod_item = QTreeWidgetItem([mod_node.display_name])
            self._item_map[id(mod_item)] = mod_node

            for rep_node in mod_node.children:
                rep_item = QTreeWidgetItem([rep_node.display_name])
                self._item_map[id(rep_item)] = rep_node

                for sub_node in rep_node.children:
                    sm = sub_node.submod
                    icon = "⚠" if (sm and sm.has_warnings) else ("✗" if (sm and sm.disabled) else "✓")
                    sub_item = QTreeWidgetItem([f"{icon} {sub_node.display_name}"])
                    self._item_map[id(sub_item)] = sub_node
                    rep_item.addChild(sub_item)

                mod_item.addChild(rep_item)
                if rep_node.auto_expand:
                    rep_item.setExpanded(True)

            self._tree.addTopLevelItem(mod_item)

    def _on_selection(self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None) -> None:
        if current is None:
            self.selection_changed.emit(None, None)
            return
        node = self._item_map.get(id(current))
        if node:
            self.selection_changed.emit(node.node_type, node.submod)

    def refresh(self, submods: list[SubMod]) -> None:
        """Refresh tree from new submod data."""
        self._submods = submods
        self._root = build_tree(submods)
        self._populate()
```

`src/oar_priority_manager/ui/details_panel.py`:
```python
"""Details panel — read-only metadata for the currently selected tree node.

See spec §7.3. Shows different content for mod/replacer/submod selection levels.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from oar_priority_manager.core.models import SubMod
from oar_priority_manager.ui.tree_model import NodeType


class DetailsPanel(QWidget):
    """Bottom section of left column — read-only metadata."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self._label = QLabel("Select an item in the tree to see details.")
        self._label.setWordWrap(True)
        layout.addWidget(self._label)

    def update_selection(self, node_type: NodeType | None, submod: SubMod | None) -> None:
        """Update display based on tree selection."""
        if node_type is None or (node_type == NodeType.SUBMOD and submod is None):
            self._label.setText("Select an item in the tree to see details.")
            return

        if node_type == NodeType.SUBMOD and submod is not None:
            lines = [
                f"<b>{submod.name}</b>",
                f"<span style='color:gray'>{submod.display_path}</span>",
                f"Priority: <b>{submod.priority:,}</b>",
            ]
            if submod.is_overridden:
                lines.append(f"<span style='color:#aa4'>was {submod.source_priority:,}</span>")
            lines.append(f"MO2 source: <code>{submod.mo2_mod}</code>")
            lines.append(f"Animations: {len(submod.animations)} files")
            self._label.setText("<br>".join(lines))
        elif node_type == NodeType.MOD:
            self._label.setText(f"<b>Mod</b> — select a submod for details")
        elif node_type == NodeType.REPLACER:
            self._label.setText(f"<b>Replacer</b> — select a submod for details")
```

`src/oar_priority_manager/ui/stacks_panel.py`:
```python
"""Priority stacks panel — shows animation competition for the selected submod.

See spec §7.4. Center pane of the main layout.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from oar_priority_manager.core.models import PriorityStack, SubMod


class StacksPanel(QWidget):
    """Center pane: priority stacks for the selected submod's animations."""

    # Emitted when user clicks a competitor row: (submod,)
    competitor_focused = Signal(object)
    # Emitted when user triggers a priority action: (action_name, submod, value)
    action_triggered = Signal(str, object, object)

    def __init__(
        self,
        conflict_map: dict[str, list[SubMod]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._conflict_map = conflict_map
        self._current_submod: SubMod | None = None
        self._relative_mode = True
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._header = QLabel("Select a submod to see priority stacks.")
        layout.addWidget(self._header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll)

        # Action buttons (spec §7.4)
        layout.addWidget(self._build_action_bar())

    def update_selection(self, submod: SubMod | None) -> None:
        """Update stacks display for the selected submod."""
        self._current_submod = submod
        self._refresh_display()

    def _refresh_display(self) -> None:
        # Clear existing content
        while self._content_layout.count():
            child = self._content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        sm = self._current_submod
        if sm is None:
            self._header.setText("Select a submod to see priority stacks.")
            return

        self._header.setText(f"<b>Priority Stacks</b> · <code>{sm.name}</code>")

        for anim in sm.animations:
            competitors = self._conflict_map.get(anim, [])
            section = self._build_stack_section(anim, competitors, sm)
            self._content_layout.addWidget(section)

        self._content_layout.addStretch()

    def _build_stack_section(
        self, anim: str, competitors: list[SubMod], selected: SubMod,
    ) -> QWidget:
        """Build one expandable stack section for an animation."""
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(4, 4, 4, 4)

        # Header
        rank = next((i for i, c in enumerate(competitors) if c is selected), -1)
        if rank == 0:
            status = "<span style='color:#4a9'>you're #1</span>"
        elif rank > 0 and competitors:
            delta = competitors[0].priority - selected.priority
            target = competitors[0].priority + 1
            status = f"<span style='color:#e66'>losing by {delta} · set to {target:,} to win</span>"
        else:
            status = ""

        # Check for ties
        priorities = [c.priority for c in competitors]
        has_ties = len(priorities) != len(set(priorities))
        if has_ties and rank >= 0:
            tied_with = [c for c in competitors if c.priority == selected.priority and c is not selected]
            if tied_with:
                status += " <span style='color:#aa4'>⚠ TIED</span>"

        header = QLabel(f"▾ <b>{anim}</b> · {len(competitors)} competitors · {status}")
        header.setTextFormat(1)  # RichText
        layout.addWidget(header)

        # Competitor rows
        for i, comp in enumerate(competitors):
            is_you = comp is selected
            rank_num = i + 1
            if self._relative_mode:
                delta = comp.priority - competitors[0].priority if competitors else 0
                val_text = f"+{delta}" if delta >= 0 else str(delta)
            else:
                val_text = f"{comp.priority:,}"

            you_marker = " <b>(you)</b>" if is_you else ""
            row_text = f"  #{rank_num} {val_text}  {comp.mo2_mod} / {comp.name}{you_marker}"
            row = QLabel(row_text)
            layout.addWidget(row)

        return section

    def _build_action_bar(self) -> QWidget:
        """Build Move to Top / Set Exact action buttons."""
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 4, 4, 4)

        self._move_to_top_btn = QPushButton("Move to Top")
        self._move_to_top_btn.clicked.connect(
            lambda: self.action_triggered.emit("move_to_top", self._current_submod, None)
        )
        layout.addWidget(self._move_to_top_btn)

        self._set_exact_btn = QPushButton("Set Exact…")
        self._set_exact_btn.clicked.connect(self._on_set_exact)
        layout.addWidget(self._set_exact_btn)

        layout.addStretch()
        return bar

    def _on_set_exact(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        if self._current_submod is None:
            return
        value, ok = QInputDialog.getInt(
            self, "Set Exact Priority",
            f"New priority for {self._current_submod.name}:",
            value=self._current_submod.priority,
            min=-2_147_483_648, max=2_147_483_647,
        )
        if ok:
            self.action_triggered.emit("set_exact", self._current_submod, value)

    def set_relative_mode(self, relative: bool) -> None:
        self._relative_mode = relative
        self._refresh_display()

    def refresh(self, conflict_map: dict[str, list[SubMod]]) -> None:
        self._conflict_map = conflict_map
        self._refresh_display()
```

`src/oar_priority_manager/ui/conditions_panel.py`:
```python
"""Conditions panel — read-only display of a competitor's condition tree.

See spec §7.5. Right pane of the main layout.
"""

from __future__ import annotations

import json

from PySide6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget

from oar_priority_manager.core.models import SubMod


class ConditionsPanel(QWidget):
    """Right pane: conditions for the focused competitor."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._header = QLabel("Conditions")
        layout.addWidget(self._header)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        layout.addWidget(self._text)

    def update_focus(self, submod: SubMod | None) -> None:
        """Update conditions display for the focused competitor."""
        if submod is None:
            self._header.setText("Conditions")
            self._text.clear()
            return

        self._header.setText(f"<b>Conditions</b> · {submod.mo2_mod} / {submod.name}")
        # Raw JSON display (Tier 2: formatted REQUIRED/ONE OF/EXCLUDED view)
        self._text.setPlainText(json.dumps(submod.conditions, indent=2))
```

`src/oar_priority_manager/ui/search_bar.py`:
```python
"""Unified search bar — name search + condition filter mode.

See spec §7.2. Tier 2: condition filter mode (AND/OR/NOT), autocomplete.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget


class SearchBar(QWidget):
    """Top-bar search input with Advanced button and Refresh button."""

    search_changed = Signal(str)
    refresh_requested = Signal()
    advanced_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Search mods, submods, animations...")
        self._input.textChanged.connect(self.search_changed.emit)
        layout.addWidget(self._input, stretch=1)

        self._advanced_btn = QPushButton("Advanced...")
        self._advanced_btn.clicked.connect(self.advanced_requested.emit)
        layout.addWidget(self._advanced_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(self._refresh_btn)

    def focus_search(self) -> None:
        self._input.setFocus()
        self._input.selectAll()
```

`src/oar_priority_manager/ui/filter_builder.py`:
```python
"""Advanced filter builder modal — three pill buckets.

See spec §7.7. Stub for now — Tier 2: three pill buckets with autocomplete.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout


class FilterBuilder(QDialog):
    """Modal dialog with REQUIRED / ANY OF / EXCLUDED pill buckets."""

    def __init__(self, known_types: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Advanced Condition Filter")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Advanced filter builder — coming soon"))
        self._known_types = known_types
```

- [ ] **Step 2: Create main window**

`src/oar_priority_manager/ui/main_window.py`:
```python
"""Main application window — three-pane layout with splitters.

See spec §7.1 (layout), §6.3 (data flow).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QSplitter, QVBoxLayout, QWidget

from oar_priority_manager.app.config import AppConfig
from oar_priority_manager.core.anim_scanner import build_conflict_map, scan_animations
from oar_priority_manager.core.filter_engine import extract_condition_types
from oar_priority_manager.core.models import PriorityStack, SubMod
from oar_priority_manager.core.priority_resolver import build_stacks
from oar_priority_manager.core.scanner import scan_mods
from oar_priority_manager.ui.conditions_panel import ConditionsPanel
from oar_priority_manager.ui.details_panel import DetailsPanel
from oar_priority_manager.ui.search_bar import SearchBar
from oar_priority_manager.ui.stacks_panel import StacksPanel
from oar_priority_manager.ui.tree_panel import TreePanel


class MainWindow(QMainWindow):
    """Three-pane main window: (Tree+Details) | Stacks | Conditions."""

    def __init__(
        self,
        submods: list[SubMod],
        conflict_map: dict[str, list[SubMod]],
        stacks: list[PriorityStack],
        app_config: AppConfig,
        instance_root: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("OAR Priority Manager")
        self.resize(1400, 800)

        self._submods = submods
        self._conflict_map = conflict_map
        self._stacks = stacks
        self._config = app_config
        self._instance_root = instance_root

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # Top bar: search + advanced + refresh
        self._search_bar = SearchBar()
        main_layout.addWidget(self._search_bar)

        # Three-pane splitter
        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left column: tree + details (vertical split)
        self._left_splitter = QSplitter(Qt.Orientation.Vertical)
        self._tree_panel = TreePanel(self._submods)
        self._details_panel = DetailsPanel()
        self._left_splitter.addWidget(self._tree_panel)
        self._left_splitter.addWidget(self._details_panel)
        self._left_splitter.setStretchFactor(0, 3)
        self._left_splitter.setStretchFactor(1, 1)

        # Center: priority stacks
        self._stacks_panel = StacksPanel(self._conflict_map)

        # Right: conditions
        self._conditions_panel = ConditionsPanel()

        self._main_splitter.addWidget(self._left_splitter)
        self._main_splitter.addWidget(self._stacks_panel)
        self._main_splitter.addWidget(self._conditions_panel)
        self._main_splitter.setStretchFactor(0, 1)
        self._main_splitter.setStretchFactor(1, 2)
        self._main_splitter.setStretchFactor(2, 1)

        main_layout.addWidget(self._main_splitter)

        # Ctrl+F shortcut to focus search
        shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut.activated.connect(self._search_bar.focus_search)

    def _connect_signals(self) -> None:
        self._tree_panel.selection_changed.connect(self._on_tree_selection)
        self._search_bar.refresh_requested.connect(self._on_refresh)
        self._stacks_panel.action_triggered.connect(self._on_action)

    def _on_tree_selection(self, node_type, submod) -> None:
        self._details_panel.update_selection(node_type, submod)
        self._stacks_panel.update_selection(submod)
        if submod:
            self._conditions_panel.update_focus(submod)

    def _on_action(self, action: str, submod: SubMod, value: object) -> None:
        """Handle priority mutation actions from the stacks panel (spec §6.3 step 5)."""
        from oar_priority_manager.core.override_manager import write_override
        from oar_priority_manager.core.priority_resolver import (
            OverflowError as PriorityOverflowError,
            move_to_top,
            set_exact,
        )

        try:
            if action == "move_to_top":
                new_priorities = move_to_top(submod, self._conflict_map, scope="submod")
            elif action == "set_exact" and isinstance(value, int):
                new_priorities = set_exact(submod, value)
            else:
                return

            overwrite_dir = self._instance_root / "overwrite"
            for sm, new_p in new_priorities.items():
                write_override(sm, new_p, overwrite_dir)

            # Refresh stacks display (in-memory, no re-scan)
            self._conflict_map = build_conflict_map(self._submods)
            self._stacks = build_stacks(self._conflict_map)
            self._stacks_panel.refresh(self._conflict_map)
            self._stacks_panel.update_selection(submod)
            self._tree_panel.refresh(self._submods)

        except PriorityOverflowError as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Priority Overflow", str(e))

    def _on_refresh(self) -> None:
        """Re-scan the VFS and rebuild all models (spec §6.3 step 6)."""
        mods_dir = self._instance_root / "mods"
        overwrite_dir = self._instance_root / "overwrite"

        self._submods = scan_mods(mods_dir, overwrite_dir)
        scan_animations(self._submods)
        self._conflict_map = build_conflict_map(self._submods)
        self._stacks = build_stacks(self._conflict_map)

        for sm in self._submods:
            present, negated = extract_condition_types(sm.conditions)
            sm.condition_types_present = present
            sm.condition_types_negated = negated

        self._tree_panel.refresh(self._submods)
        self._stacks_panel.refresh(self._conflict_map)
```

- [ ] **Step 3: Run full test suite to verify nothing is broken**

```powershell
pytest -v
```

Expected: all existing tests pass (UI imports are not yet tested).

- [ ] **Step 4: Commit**

```
feat: add UI shell — main window, tree panel, details, stacks, conditions panels
```

---

## Task 14: UI Smoke Tests

**Files:**
- Create: `tests/smoke/test_ui_smoke.py`

Basic smoke tests that construct the main window with fixture data and verify no crashes. Uses `pytest-qt`.

- [ ] **Step 1: Write smoke tests**

`tests/smoke/test_ui_smoke.py`:
```python
"""UI smoke tests — verify panels construct and basic interactions don't crash.

See spec §11.1 (smoke tests).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from oar_priority_manager.app.config import AppConfig
from oar_priority_manager.core.anim_scanner import build_conflict_map, scan_animations
from oar_priority_manager.core.models import PriorityStack
from oar_priority_manager.core.priority_resolver import build_stacks
from oar_priority_manager.core.scanner import scan_mods
from oar_priority_manager.ui.main_window import MainWindow
from tests.conftest import make_config_json, make_submod_dir


@pytest.fixture
def populated_instance(tmp_path: Path) -> Path:
    """Create a tmp MO2 instance with a few OAR mods."""
    instance = tmp_path
    mods = instance / "mods"
    mods.mkdir()
    (instance / "overwrite").mkdir()
    (instance / "ModOrganizer.ini").touch()

    make_submod_dir(
        mods, "Female Combat Pack", "AMA", "heavy",
        config=make_config_json(name="heavy", priority=500),
        animations=["mt_idle.hkx", "mt_walkforward.hkx"],
    )
    make_submod_dir(
        mods, "Female Combat Pack", "AMA", "light",
        config=make_config_json(name="light", priority=400),
        animations=["mt_idle.hkx"],
    )
    make_submod_dir(
        mods, "Vanilla Tweaks", "VT", "idle",
        config=make_config_json(name="idle", priority=200),
        animations=["mt_idle.hkx", "mt_walkforward.hkx"],
    )
    return instance


@pytest.fixture
def main_window(qtbot, populated_instance: Path) -> MainWindow:
    mods_dir = populated_instance / "mods"
    overwrite_dir = populated_instance / "overwrite"

    submods = scan_mods(mods_dir, overwrite_dir)
    scan_animations(submods)
    conflict_map = build_conflict_map(submods)
    stacks = build_stacks(conflict_map)

    window = MainWindow(
        submods=submods,
        conflict_map=conflict_map,
        stacks=stacks,
        app_config=AppConfig(),
        instance_root=populated_instance,
    )
    qtbot.addWidget(window)
    window.show()
    return window


def test_main_window_constructs(main_window: MainWindow):
    """Main window constructs without crashing."""
    assert main_window.isVisible()


def test_window_has_three_panes(main_window: MainWindow):
    """Window has the expected panel structure."""
    assert main_window._tree_panel is not None
    assert main_window._stacks_panel is not None
    assert main_window._conditions_panel is not None
    assert main_window._details_panel is not None


def test_tree_has_items(main_window: MainWindow):
    """Tree is populated with mod data."""
    tree = main_window._tree_panel._tree
    assert tree.topLevelItemCount() > 0
```

- [ ] **Step 2: Run smoke tests**

```powershell
pytest tests/smoke/ -v
```

Expected: all 3 tests PASS (may need a display server — on CI, xvfb or `QT_QPA_PLATFORM=offscreen`).

If running headless:
```powershell
$env:QT_QPA_PLATFORM = "offscreen"
pytest tests/smoke/ -v
```

- [ ] **Step 3: Run full test suite**

```powershell
pytest -v
```

- [ ] **Step 4: Commit**

```
feat: add UI smoke tests for main window construction
```

---

## Task 15: CI Workflow

**Files:**
- Create: `.github/workflows/ci.yml`

GitHub Actions workflow on Windows runners (spec §11.2).

- [ ] **Step 1: Create CI workflow**

`.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
    branches: ["**"]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Lint with ruff
        run: ruff check src/ tests/

      - name: Type check with mypy (advisory)
        run: mypy src/ --ignore-missing-imports
        continue-on-error: true

      - name: Run tests
        env:
          QT_QPA_PLATFORM: offscreen
        run: pytest -v --tb=short
```

- [ ] **Step 2: Commit**

```
ci: add GitHub Actions workflow with pytest, ruff, and mypy on Windows
```

---

## Task 16: README

**Files:**
- Create: `README.md`

Setup and usage instructions (spec §12).

- [ ] **Step 1: Write README**

`README.md`:
```markdown
# OAR Priority Manager

A desktop tool for Skyrim modders using Mod Organizer 2 (MO2) and Open Animation Replacer (OAR). Inspect which OAR submods compete for the same animation files, see who's winning, and adjust priorities — without modifying source mod files.

## Quick Start

### As an MO2 Executable (recommended)

1. Download the latest release zip from GitHub Releases.
2. Extract to your MO2 tools directory (e.g. `<instance>/tools/oar-priority-manager/`).
3. In MO2, go to **Tools → Executables → Add**.
4. Set the binary path to the extracted `.exe`.
5. Set arguments: `--mods-path "%BASE_DIR%/mods"`
6. Run from MO2 so the tool sees the merged VFS.

### Development Setup

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -v
python -m oar_priority_manager --mods-path "C:\path\to\your\MO2\instance\mods"
```

## How It Works

The tool scans your MO2 mods directory for OAR submod folders (`config.json` files under `OpenAnimationReplacer/`). For each animation file (`.hkx`), it builds a **priority stack** — the ordered list of all submods that provide that animation, sorted by OAR's evaluation order (priority descending, first-match-wins).

You can:
- **Search** for any mod, submod, or animation filename
- **See** exactly who's winning each animation and by how much
- **Fix it** with Move to Top (one click) or Set Exact Priority
- All changes are written to MO2 Overwrite — source mods are never touched

## Technology

- Python 3.11+ / PySide6
- Packaged with Nuitka for native Windows binaries
- Tests: pytest + pytest-qt

## License

TBD
```

- [ ] **Step 2: Commit**

```
docs: add README with setup instructions and usage guide
```

---

## Summary of Remaining Work (Tier 2)

The following Tier 2 features are deferred to separate follow-up tasks after the Tier 1 MVP is working end-to-end. Each would be its own task with TDD:

1. **Formatted condition display** (REQUIRED/ONE OF/EXCLUDED bucketing in conditions panel) — spec §7.5
2. **Condition filter mode in search bar** (AND/OR/NOT keyword detection, autocomplete) — spec §7.6
3. **Advanced filter builder modal** (three pill buckets) — spec §7.7
4. **Shift to Priority N** operation — spec §6.2
5. **Clear Overrides** button — spec §8.2
6. **Collapse-winning button** in stacks panel — spec §7.4
7. **Animation filter** in center pane — spec §7.4
8. **Submod sort toggle** (Priority/Name) — spec §7.3
9. **Details panel: extended fields** (description, path, condition summary, override source) — spec §7.3
10. **Scan issues log pane** — spec §7.8
11. **Post-action toast notification** — spec §7.4
12. **Nuitka build configuration** — spec §10, §12
13. **Real-world fixture harvesting** from Nexus mods — spec §11.1
