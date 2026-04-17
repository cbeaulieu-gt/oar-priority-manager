# Scan Issues Log Pane — Implementation Plan (Issue #51)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Tracking issue:** cbeaulieu-gt/oar-priority-manager#51
**Milestone:** Alpha 2 — Secondary Workflows
**Spec reference:** `docs/superpowers/specs/2026-04-11-oar-priority-manager-design.md` §7.8 and §9
**Tech stack:** Python 3.11+, PySide6 (Qt 6), pytest, pytest-qt, uv for package management
**Branch strategy:** create a fresh worktree off `main` at `.worktrees/051-scan-issues-pane/` with branch `feature/051-scan-issues-pane`. Pull `origin/main` first. `.worktrees/` is already in `.gitignore`. Use the `superpowers:using-git-worktrees` skill to set it up.

---

## 1. Goal

Surface every parse/validation warning collected during `scan_mods` in a dedicated log pane, and make the details panel show parse errors (only) when a warning submod is selected in the tree. Today warnings live only as bullets tacked onto the normal metadata and there is no way to enumerate them across the whole instance.

**Concrete behavioural requirements (restated from §7.8 + §9 + #51):**

1. A `Scan issues (N)` button appears in the top bar, placed between the existing `Advanced...` button and `Refresh` button on the `SearchBar`. `N` is the count of submods whose `has_warnings` is True (i.e. at least one warning string present).
2. `N` is updated whenever the window receives a new `submods` list — at startup and after every `_on_refresh`. If `N == 0` the button still renders but is disabled (grayed out) with the label `Scan issues (0)`.
3. Clicking the button opens a non-modal `ScanIssuesPane` dialog listing every warning across every submod. Each row shows: severity icon, submod display path (`Mod / Replacer / Submod`), file path, error type, and line number (when parseable from the warning string).
4. Double-clicking a row in the log pane (or pressing Enter on a selected row) selects the corresponding SUBMOD node in the tree via `TreePanel.select_submod`, scrolls it into view, and raises the main window. The pane itself stays open.
5. The pane has a `Copy All` button that copies the full list of warnings (one per line, `<path>\t<error type>\t<line>\t<message>`) to the clipboard, and a `Close` button that dismisses the dialog.
6. When the user selects a SUBMOD tree node whose `submod.has_warnings` is True, `DetailsPanel` renders a **parse-error-only view** (name, path, enumerated warnings with icon/line-number formatting) instead of the normal metadata layout. Non-warning nodes continue to render as today.
7. The log pane reads warning state off the currently loaded submods — warnings are **not** snapshotted. After the user triggers a refresh, the pane (if still open) automatically re-renders from the new submod list.

---

## 2. Architecture Overview

```
  user clicks "Scan issues (N)" in top bar
                   │
                   ▼
     SearchBar.scan_issues_requested ── signal (NEW)
                   │
                   ▼
  MainWindow._on_scan_issues_requested()  (NEW slot)
                   │
                   │ 1. Builds list[WarningEntry] from self._submods
                   │ 2. Instantiates ScanIssuesPane(entries, parent=self)
                   │ 3. Connects navigate_to_submod → _tree_panel.select_submod
                   │ 4. dialog.show()  (non-modal)
                   ▼
          ScanIssuesPane (QDialog, non-modal)
                   │
                   │ user double-clicks a row
                   │
                   └── navigate_to_submod(SubMod) ──▶ TreePanel.select_submod
                                                              │
                                                              ▼
                                                     tree updates selection
                                                     details_panel switches to
                                                     parse-error view (when
                                                     submod has warnings)
```

Secondary flow for the details panel:

```
TreePanel.currentItemChanged
        │
        ▼
MainWindow._on_tree_selection(node)
        │
        ▼
DetailsPanel.update_selection(node)
        │
        │ new branch: if node is SUBMOD and submod.has_warnings:
        │     render parse-error view
        │ else:
        │     render existing metadata view
        ▼
label text updated
```

**Boundary:** `ScanIssuesPane` is a pure view — it never touches the tree or the scanner. All navigation is channeled through a signal the MainWindow wires to `TreePanel.select_submod`. Warning-count computation lives on `MainWindow`, which tells `SearchBar` the number via a public setter.

---

## 3. Data Contracts

### 3.1 `WarningEntry` dataclass (new)

A new dataclass in a new module `core/warning_report.py` alongside `filter_engine.py`:

```python
@dataclass(frozen=True)
class WarningEntry:
    """One problem discovered during scan, formatted for display.

    Attributes:
        submod: The SubMod that produced the warning. Used by the log pane
            to navigate back to the tree when the user clicks a row.
        file_path: Absolute path to the offending file (e.g. the submod's
            config.json, user.json, or overwrite user.json). May equal
            ``submod.config_path`` when the warning string does not embed
            an explicit path.
        error_type: Short human-readable category:
            ``"JSON parse error"``, ``"Missing field"``, ``"Type error"``,
            ``"Read error"``, or ``"Other"``.
        line: 1-based line number extracted from a ``json.JSONDecodeError``
            message, or ``None`` if the source warning did not carry one.
        message: The original warning string, unmodified. Serves as the
            ground truth tooltip/copy payload — never strip info from it.
        severity: Reserved for future expansion. Always ``"warning"``
            in this plan — no error/info distinction in MVP.
    """

    submod: SubMod
    file_path: Path
    error_type: str
    line: int | None
    message: str
    severity: str = "warning"
```

### 3.2 `collect_warning_entries()` — pure function (new)

```python
def collect_warning_entries(submods: Iterable[SubMod]) -> list[WarningEntry]:
    """Flatten every submod.warnings list into a sorted list of WarningEntry.

    For each submod with non-empty warnings, parse each warning string into
    a structured WarningEntry. Parsing rules:

    - ``"JSON parse error in <path>: <json-error>"``
          → error_type="JSON parse error"; file_path=<path>; line parsed
            from the trailing ``line N column M`` if present.
    - ``"File not found: <path>"`` → error_type="Read error"; file_path=<path>.
    - ``"Cannot read <path>: <reason>"`` → error_type="Read error"; file_path=<path>.
    - ``"Empty file: <path>"`` → error_type="Read error"; file_path=<path>.
    - ``"Expected JSON object in <path>, got <type>"`` → error_type="Type error".
    - ``"Priority is not an integer in <path>: <value>"`` → error_type="Type error".
    - Anything else → error_type="Other"; file_path=submod.config_path.

    The returned list is sorted by (submod.display_path, file_path, line).
    """
```

### 3.3 `MainWindow` public API additions

| Member | Kind | Purpose |
|---|---|---|
| `self._scan_issues_pane: ScanIssuesPane \| None` | attribute | Holds the current pane instance so a second click re-focuses rather than spawning a duplicate. |
| `self._warning_count: int` | attribute | Cached count used to update the button label. Recomputed in `_on_refresh` and in `__init__`. |
| `_on_scan_issues_requested(self) -> None` | slot | Opens (or raises) the non-modal pane. |
| `_navigate_from_scan_issues(self, submod: SubMod) -> None` | slot | Bridges the pane's signal to `self._tree_panel.select_submod`. |
| `_refresh_warning_count(self) -> None` | private helper | Recomputes `_warning_count` from `_submods`, calls `self._search_bar.set_scan_issues_count`. |

### 3.4 `SearchBar` additions

```python
class SearchBar(QWidget):
    ...
    scan_issues_requested = Signal()     # NEW — emitted on button click
    ...

    def set_scan_issues_count(self, count: int) -> None:
        """Update the Scan issues button label and enabled state.

        Label format: ``Scan issues (N)`` where N is always shown, even
        when zero. Button is disabled when count == 0.
        """
```

The new button sits between `_advanced_btn` and `_refresh_btn` in `_setup_ui`. Object name: `"scan-issues-btn"` (for smoke tests).

### 3.5 `DetailsPanel` additions

Add a private method:

```python
def _render_submod_warnings(self, submod: SubMod) -> str:
    """Build rich HTML for a SUBMOD that has non-empty warnings.

    Replaces (not augments) the normal metadata view when called.
    Shows:
        - Bolded submod name
        - Grey file path (submod.config_path.parent)
        - A red WARNING banner
        - One bullet per warning string, with ⚠ icon
    Returns a string suitable for QLabel with RichText format.
    """
```

The branching happens in `update_selection`:

```python
elif node.node_type == NodeType.SUBMOD:
    if node.submod is None:
        self._label.setText("Select an item in the tree to see details.")
    elif node.submod.has_warnings:
        self._label.setText(self._render_submod_warnings(node.submod))
    else:
        self._label.setText(self._render_submod(node))
```

### 3.6 `ScanIssuesPane` signal

```python
class ScanIssuesPane(QDialog):
    ...
    navigate_to_submod = Signal(object)   # payload: SubMod
```

Fired when the user double-clicks a row or presses Enter on a selected row.

---

## 4. Component Breakdown

| Module / class | Status | One-line purpose |
|---|---|---|
| `core/warning_report.py` → `WarningEntry` | **New** | Frozen dataclass: structured view of one warning for the log pane. |
| `core/warning_report.py` → `collect_warning_entries()` | **New** | Pure function: parse each submod's warning strings into `WarningEntry` rows. |
| `ui/scan_issues_pane.py` → `ScanIssuesPane` | **New** (file + class) | Non-modal `QDialog` with a `QTableWidget` (5 columns), Copy All + Close buttons. Emits `navigate_to_submod`. |
| `ui/search_bar.py` → `scan_issues_requested` signal | **New** | Emitted when the new top-bar button is clicked. |
| `ui/search_bar.py` → `_scan_issues_btn` widget | **New** | `QPushButton` between Advanced and Refresh. |
| `ui/search_bar.py` → `set_scan_issues_count()` | **New method** | Public setter that rewrites the button label and enabled state. |
| `ui/main_window.py` → `_on_scan_issues_requested()` | **New slot** | Builds entries, opens pane (or raises existing one), wires `navigate_to_submod`. |
| `ui/main_window.py` → `_refresh_warning_count()` | **New helper** | Counts `sm.has_warnings` across submods and pushes to the search bar. |
| `ui/main_window.py` → `_navigate_from_scan_issues()` | **New slot** | Delegates to `_tree_panel.select_submod`. |
| `ui/main_window.py` → `_connect_signals()` | **Modify** | Connect `self._search_bar.scan_issues_requested` → `self._on_scan_issues_requested`. |
| `ui/main_window.py` → `__init__` + `_on_refresh` | **Modify** | Call `_refresh_warning_count()` after initial load and after every refresh. |
| `ui/details_panel.py` → `_render_submod_warnings()` | **New** | Renders the parse-error-only view. |
| `ui/details_panel.py` → `update_selection()` | **Modify** | Branch to warnings renderer when `submod.has_warnings`. |
| `ui/details_panel.py` → `_render_submod()` | **Modify** | Drop the trailing "Warnings" section (now shown only in the parse-error view — avoids double-rendering). |

---

## 5. Phased Implementation Steps

> **Each task below is scoped to one `code-writer` session: one concept, one PR-sized diff, ends green tests.**
> TDD is mandatory per `@C:\Users\chris\.claude\standards\software-standards.md` — every task writes the failing test first.
> After every task: run `uv run pytest tests/unit -q` locally; all previously-passing tests must still pass.

---

### Task 1: `WarningEntry` dataclass + `collect_warning_entries()` (pure logic)

**Files:**
- Create: `src/oar_priority_manager/core/warning_report.py`
- Create: `tests/unit/test_warning_report.py`

**Steps:**

- [ ] **Step 1: Write failing tests in `tests/unit/test_warning_report.py`.**

```python
"""Tests for WarningEntry dataclass and collect_warning_entries helper (issue #51)."""
from __future__ import annotations

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
        with pytest.raises(Exception):
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
```

- [ ] **Step 2: Run tests to verify they fail.**

Run: `uv run pytest tests/unit/test_warning_report.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'oar_priority_manager.core.warning_report'`

- [ ] **Step 3: Implement `warning_report.py`.**

```python
"""Warning-aggregation helpers for the Scan Issues log pane (issue #51).

Structures each submod's warning strings into ``WarningEntry`` rows with
parsed file paths, error categories, and line numbers — the data contract
consumed by ``ui.scan_issues_pane.ScanIssuesPane``.

The source of truth is still ``SubMod.warnings: list[str]`` — this module
only *derives* a display-time view from those strings; it never mutates
any SubMod.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from oar_priority_manager.core.models import SubMod

# ---------------------------------------------------------------------------
# Parsing regexes — one per known warning producer in parser.py / scanner.py.
# Kept in order of specificity. First match wins.
# ---------------------------------------------------------------------------

_JSON_PARSE_RE = re.compile(
    r"^JSON parse error in (?P<path>.+?):\s*(?P<detail>.*)$"
)
_LINE_COLUMN_RE = re.compile(r"line (?P<line>\d+) column \d+")

_FILE_NOT_FOUND_RE = re.compile(r"^File not found:\s*(?P<path>.+)$")
_CANNOT_READ_RE = re.compile(r"^Cannot read (?P<path>.+?):\s*.*$")
_EMPTY_FILE_RE = re.compile(r"^Empty file:\s*(?P<path>.+)$")
_EXPECTED_OBJECT_RE = re.compile(
    r"^Expected JSON object in (?P<path>.+?), got \w+$"
)
_PRIORITY_NOT_INT_RE = re.compile(
    r"^Priority is not an integer in (?P<path>.+?):\s*.*$"
)


@dataclass(frozen=True)
class WarningEntry:
    """Structured view of one warning for the log pane.

    Attributes:
        submod: The SubMod that produced the warning.
        file_path: Absolute path to the offending file.
        error_type: Short category — one of ``"JSON parse error"``,
            ``"Missing field"``, ``"Type error"``, ``"Read error"``,
            or ``"Other"``.
        line: 1-based line number when parseable from the message,
            otherwise ``None``.
        message: The original warning string, unmodified.
        severity: Reserved for future use. Always ``"warning"`` in MVP.
    """

    submod: SubMod
    file_path: Path
    error_type: str
    line: int | None
    message: str
    severity: str = "warning"


def _parse_one(submod: SubMod, message: str) -> WarningEntry:
    """Parse a single warning string into a WarningEntry.

    Args:
        submod: The owning submod — used both to fill in the ``submod``
            field and as the fallback file_path when the message does
            not embed one.
        message: The raw warning string produced by parser/scanner.

    Returns:
        A WarningEntry with file_path, error_type, and line best-effort
        extracted. Falls back to error_type="Other" and
        file_path=submod.config_path for unknown shapes.
    """
    if m := _JSON_PARSE_RE.match(message):
        path = Path(m.group("path"))
        line: int | None = None
        if ln := _LINE_COLUMN_RE.search(m.group("detail")):
            line = int(ln.group("line"))
        return WarningEntry(
            submod=submod,
            file_path=path,
            error_type="JSON parse error",
            line=line,
            message=message,
        )

    for regex, etype in (
        (_FILE_NOT_FOUND_RE, "Read error"),
        (_CANNOT_READ_RE, "Read error"),
        (_EMPTY_FILE_RE, "Read error"),
        (_EXPECTED_OBJECT_RE, "Type error"),
        (_PRIORITY_NOT_INT_RE, "Type error"),
    ):
        if m := regex.match(message):
            return WarningEntry(
                submod=submod,
                file_path=Path(m.group("path")),
                error_type=etype,
                line=None,
                message=message,
            )

    return WarningEntry(
        submod=submod,
        file_path=submod.config_path,
        error_type="Other",
        line=None,
        message=message,
    )


def collect_warning_entries(submods: Iterable[SubMod]) -> list[WarningEntry]:
    """Flatten every submod's warnings list into a sorted list of WarningEntry.

    See module docstring for parsing rules. Sort key is
    ``(submod.display_path, str(file_path), line or 0)`` so the log pane
    shows warnings grouped by submod, then by file, then by line number.

    Args:
        submods: Iterable of SubMod records, typically ``self._submods`` on
            MainWindow.

    Returns:
        A new list of WarningEntry. Empty when no submod has warnings.
    """
    entries: list[WarningEntry] = []
    for sm in submods:
        for msg in sm.warnings:
            entries.append(_parse_one(sm, msg))
    entries.sort(
        key=lambda e: (e.submod.display_path, str(e.file_path), e.line or 0)
    )
    return entries
```

- [ ] **Step 4: Run tests to verify they pass.**

Run: `uv run pytest tests/unit/test_warning_report.py -q`
Expected: PASS, 11 tests.

- [ ] **Step 5: Run the full unit suite to verify nothing broke.**

Run: `uv run pytest tests/unit -q`
Expected: PASS, existing tests unaffected.

- [ ] **Step 6: Commit.**

```bash
git add src/oar_priority_manager/core/warning_report.py tests/unit/test_warning_report.py
git commit -m "feat(warnings): add WarningEntry + collect_warning_entries (refs #51)"
```

**Done when:** `uv run pytest tests/unit/test_warning_report.py -q` passes; no existing test broken; `ruff check src tests` clean.

---

### Task 2: `Scan issues (N)` button on `SearchBar`

**Files:**
- Modify: `src/oar_priority_manager/ui/search_bar.py`
- Create: `tests/unit/test_search_bar_scan_issues.py`

**Steps:**

- [ ] **Step 1: Write failing tests in `tests/unit/test_search_bar_scan_issues.py`.**

```python
"""Tests for the Scan issues button on SearchBar (issue #51, Task 2)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from oar_priority_manager.ui.search_bar import SearchBar


class TestScanIssuesButton:
    def test_button_exists_with_object_name(self, qtbot) -> None:
        bar = SearchBar()
        qtbot.addWidget(bar)
        btn = bar.findChild(type(bar._refresh_btn), "scan-issues-btn")
        assert btn is not None, "scan-issues-btn not found on SearchBar"

    def test_default_label_is_zero_and_disabled(self, qtbot) -> None:
        bar = SearchBar()
        qtbot.addWidget(bar)
        assert bar._scan_issues_btn.text() == "Scan issues (0)"
        assert not bar._scan_issues_btn.isEnabled()

    def test_set_count_updates_label_and_enables(self, qtbot) -> None:
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.set_scan_issues_count(7)
        assert bar._scan_issues_btn.text() == "Scan issues (7)"
        assert bar._scan_issues_btn.isEnabled()

    def test_set_count_zero_disables_button(self, qtbot) -> None:
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.set_scan_issues_count(3)
        bar.set_scan_issues_count(0)
        assert bar._scan_issues_btn.text() == "Scan issues (0)"
        assert not bar._scan_issues_btn.isEnabled()

    def test_click_emits_signal(self, qtbot) -> None:
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.set_scan_issues_count(1)
        with qtbot.waitSignal(bar.scan_issues_requested, timeout=500):
            bar._scan_issues_btn.click()

    def test_button_order_is_advanced_scan_refresh(self, qtbot) -> None:
        """Scan issues button sits between Advanced... and Refresh."""
        bar = SearchBar()
        qtbot.addWidget(bar)
        layout = bar.layout()
        # Locate widget indices for the three buttons.
        indices: dict[str, int] = {}
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if w is bar._advanced_btn:
                indices["advanced"] = i
            elif w is bar._scan_issues_btn:
                indices["scan"] = i
            elif w is bar._refresh_btn:
                indices["refresh"] = i
        assert indices["advanced"] < indices["scan"] < indices["refresh"]
```

- [ ] **Step 2: Run tests to verify they fail.**

Run: `uv run pytest tests/unit/test_search_bar_scan_issues.py -q`
Expected: FAIL — `_scan_issues_btn` not present on `SearchBar`.

- [ ] **Step 3: Modify `src/oar_priority_manager/ui/search_bar.py`.**

1. Add a new signal next to the existing ones:

```python
class SearchBar(QWidget):
    ...
    search_changed = Signal(str)
    refresh_requested = Signal()
    advanced_requested = Signal()
    scan_issues_requested = Signal()   # NEW
    filter_mode_changed = Signal(bool)
    condition_mode_changed = Signal(object)
```

2. In `_setup_ui` (the method that currently adds `_advanced_btn` then `_refresh_btn`), insert the new button between them. Replace the existing block:

```python
        self._advanced_btn = QPushButton("Advanced...")
        self._advanced_btn.clicked.connect(self.advanced_requested.emit)
        layout.addWidget(self._advanced_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(self._refresh_btn)
```

…with:

```python
        self._advanced_btn = QPushButton("Advanced...")
        self._advanced_btn.clicked.connect(self.advanced_requested.emit)
        layout.addWidget(self._advanced_btn)

        self._scan_issues_btn = QPushButton("Scan issues (0)")
        self._scan_issues_btn.setObjectName("scan-issues-btn")
        self._scan_issues_btn.setToolTip(
            "Open the log pane listing parse and validation warnings"
            " found during scan."
        )
        self._scan_issues_btn.setEnabled(False)
        self._scan_issues_btn.clicked.connect(self.scan_issues_requested.emit)
        layout.addWidget(self._scan_issues_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(self._refresh_btn)
```

3. Append the public setter (place next to `focus_search`):

```python
    def set_scan_issues_count(self, count: int) -> None:
        """Update the Scan issues button label and enabled state.

        Args:
            count: Number of submods with warnings. The button is disabled
                when ``count == 0``.
        """
        self._scan_issues_btn.setText(f"Scan issues ({count})")
        self._scan_issues_btn.setEnabled(count > 0)
```

- [ ] **Step 4: Run tests to verify they pass.**

Run: `uv run pytest tests/unit/test_search_bar_scan_issues.py -q`
Expected: PASS, 6 tests.

- [ ] **Step 5: Run the full unit suite.**

Run: `uv run pytest tests/unit -q`
Expected: PASS. (`test_tree_panel_enhancements.py` imports `SearchBar`; verify it still loads.)

- [ ] **Step 6: Commit.**

```bash
git add src/oar_priority_manager/ui/search_bar.py tests/unit/test_search_bar_scan_issues.py
git commit -m "feat(search-bar): add Scan issues button + scan_issues_requested signal (refs #51)"
```

**Done when:** the six new tests pass; existing SearchBar tests untouched.

---

### Task 3: `ScanIssuesPane` widget — non-modal dialog with a table + navigate_to_submod signal

**Files:**
- Create: `src/oar_priority_manager/ui/scan_issues_pane.py`
- Create: `tests/unit/test_scan_issues_pane.py`

**Steps:**

- [ ] **Step 1: Write failing tests in `tests/unit/test_scan_issues_pane.py`.**

```python
"""Tests for ScanIssuesPane (issue #51, Task 3)."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QTableWidget

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.core.warning_report import WarningEntry
from oar_priority_manager.ui.scan_issues_pane import ScanIssuesPane


def _sm(name: str = "bad") -> SubMod:
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
        warnings=[],
    )


def _entry(
    sm: SubMod | None = None,
    file_path: Path | None = None,
    error_type: str = "JSON parse error",
    line: int | None = 12,
    message: str = "JSON parse error in C:/x/config.json: bad",
) -> WarningEntry:
    sm = sm or _sm()
    return WarningEntry(
        submod=sm,
        file_path=file_path or sm.config_path,
        error_type=error_type,
        line=line,
        message=message,
    )


class TestScanIssuesPane:
    def test_non_modal(self, qtbot) -> None:
        pane = ScanIssuesPane(entries=[])
        qtbot.addWidget(pane)
        # A non-modal dialog reports Qt.NonModal / Qt.WindowModal-or-less.
        assert pane.isModal() is False

    def test_empty_entries_shows_placeholder(self, qtbot) -> None:
        pane = ScanIssuesPane(entries=[])
        qtbot.addWidget(pane)
        # Placeholder label visible; table row count is zero.
        assert pane._table.rowCount() == 0
        assert pane._placeholder.isVisible()

    def test_table_has_five_columns(self, qtbot) -> None:
        pane = ScanIssuesPane(entries=[_entry()])
        qtbot.addWidget(pane)
        pane.show()  # placeholder visibility requires a visible window tree
        assert pane._table.columnCount() == 5
        headers = [
            pane._table.horizontalHeaderItem(i).text()
            for i in range(pane._table.columnCount())
        ]
        assert headers == [
            "Severity", "Submod", "File", "Error type", "Line",
        ]

    def test_populates_rows_from_entries(self, qtbot) -> None:
        sm = _sm("bad1")
        entries = [_entry(sm=sm, line=12)]
        pane = ScanIssuesPane(entries=entries)
        qtbot.addWidget(pane)
        assert pane._table.rowCount() == 1
        row = 0
        assert pane._table.item(row, 1).text() == sm.display_path
        assert pane._table.item(row, 3).text() == "JSON parse error"
        assert pane._table.item(row, 4).text() == "12"

    def test_line_column_shows_dash_when_none(self, qtbot) -> None:
        entries = [_entry(line=None)]
        pane = ScanIssuesPane(entries=entries)
        qtbot.addWidget(pane)
        assert pane._table.item(0, 4).text() == "—"

    def test_double_click_emits_navigate_to_submod(self, qtbot) -> None:
        sm = _sm("nav")
        entries = [_entry(sm=sm)]
        pane = ScanIssuesPane(entries=entries)
        qtbot.addWidget(pane)
        with qtbot.waitSignal(pane.navigate_to_submod, timeout=500) as blocker:
            pane._table.itemDoubleClicked.emit(pane._table.item(0, 1))
        assert blocker.args == [sm]

    def test_close_button_closes_dialog(self, qtbot) -> None:
        pane = ScanIssuesPane(entries=[_entry()])
        qtbot.addWidget(pane)
        pane.show()
        assert pane.isVisible()
        pane._close_btn.click()
        assert not pane.isVisible()

    def test_copy_all_writes_tsv_to_clipboard(self, qtbot) -> None:
        sm = _sm("copy")
        entries = [
            _entry(sm=sm, error_type="Read error", line=None,
                   message="File not found: C:/x/user.json",
                   file_path=Path("C:/x/user.json")),
        ]
        pane = ScanIssuesPane(entries=entries)
        qtbot.addWidget(pane)
        pane._copy_btn.click()
        clipboard = QApplication.clipboard().text()
        # Format: <display_path>\t<file_path>\t<error_type>\t<line>\t<message>
        assert sm.display_path in clipboard
        assert "C:/x/user.json".replace("/", "\\") in clipboard or "C:/x/user.json" in clipboard
        assert "Read error" in clipboard
        assert "File not found" in clipboard

    def test_set_entries_replaces_rows(self, qtbot) -> None:
        pane = ScanIssuesPane(entries=[_entry()])
        qtbot.addWidget(pane)
        assert pane._table.rowCount() == 1
        pane.set_entries([_entry(), _entry(), _entry()])
        assert pane._table.rowCount() == 3
        pane.set_entries([])
        assert pane._table.rowCount() == 0
```

- [ ] **Step 2: Run tests to verify they fail.**

Run: `uv run pytest tests/unit/test_scan_issues_pane.py -q`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement `src/oar_priority_manager/ui/scan_issues_pane.py`.**

```python
"""Non-modal log pane for scan warnings (issue #51, spec §7.8).

Presents every ``WarningEntry`` collected from the current submod list
in a five-column table. Double-clicking a row emits ``navigate_to_submod``
carrying the offending ``SubMod`` — the main window hooks this signal
up to ``TreePanel.select_submod`` so the tree highlights the entry.

The dialog is intentionally non-modal: the user can keep it open while
clicking around the tree and inspecting details. The main window caches
the instance so repeated clicks on the toolbar button re-focus rather
than spawn duplicates.

Public API
----------
ScanIssuesPane
"""
from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from oar_priority_manager.core.models import SubMod
from oar_priority_manager.core.warning_report import WarningEntry


_COLUMN_HEADERS: tuple[str, ...] = (
    "Severity",
    "Submod",
    "File",
    "Error type",
    "Line",
)
# QTableWidgetItem user-role slot that stores the SubMod for the row so
# we can round-trip from a clicked item back to the domain object.
_SUBMOD_ROLE = Qt.ItemDataRole.UserRole + 1


class ScanIssuesPane(QDialog):
    """Non-modal log pane listing every scan warning.

    Signals:
        navigate_to_submod: Emitted with a ``SubMod`` when the user
            double-clicks a row (or presses Enter on a selected row).

    Attributes:
        _entries: Current list of WarningEntry rendered in the table.
        _table: QTableWidget — five columns, one row per entry.
        _placeholder: QLabel shown when ``_entries`` is empty.
        _copy_btn: QPushButton — dumps the TSV-formatted rows to the
            system clipboard.
        _close_btn: QPushButton — closes the dialog.
    """

    navigate_to_submod = Signal(object)  # payload: SubMod

    def __init__(
        self,
        entries: Iterable[WarningEntry],
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the pane and populate rows from *entries*.

        Args:
            entries: Initial list of WarningEntry. May be empty — the
                pane shows a "No warnings" placeholder in that case.
            parent: Optional parent widget. Typically the MainWindow so
                the dialog inherits application icon and focus stacking.
        """
        super().__init__(parent)
        self.setWindowTitle("Scan Issues")
        self.setModal(False)
        self.resize(900, 500)

        self._entries: list[WarningEntry] = list(entries)
        self._build_ui()
        self._populate()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construct child widgets and layouts."""
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        self._placeholder = QLabel(
            "No warnings found in the current scan."
        )
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._placeholder)

        self._table = QTableWidget(0, len(_COLUMN_HEADERS))
        self._table.setHorizontalHeaderLabels(list(_COLUMN_HEADERS))
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._table.itemDoubleClicked.connect(self._on_row_activated)
        root.addWidget(self._table, stretch=1)

        # Button row
        btn_row = QHBoxLayout()
        self._copy_btn = QPushButton("Copy All")
        self._copy_btn.setToolTip(
            "Copy the entire warning list as tab-separated text."
        )
        self._copy_btn.clicked.connect(self._on_copy_all)
        btn_row.addWidget(self._copy_btn)
        btn_row.addStretch(1)
        self._close_btn = QPushButton("Close")
        self._close_btn.clicked.connect(self.close)
        btn_row.addWidget(self._close_btn)
        root.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Data population
    # ------------------------------------------------------------------

    def _populate(self) -> None:
        """Render ``self._entries`` into the table, swapping placeholder."""
        self._table.setRowCount(0)
        has_entries = bool(self._entries)
        self._placeholder.setVisible(not has_entries)
        self._table.setVisible(has_entries)

        for row, entry in enumerate(self._entries):
            self._table.insertRow(row)
            self._set_cell(row, 0, "⚠")
            self._set_cell(row, 1, entry.submod.display_path, entry.submod)
            self._set_cell(row, 2, str(entry.file_path))
            self._set_cell(row, 3, entry.error_type)
            self._set_cell(row, 4, str(entry.line) if entry.line else "—")
            # Tooltip on the full row points at the original message
            # so users can read long JSON error details without resizing.
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item is not None:
                    item.setToolTip(entry.message)

    def _set_cell(
        self,
        row: int,
        col: int,
        text: str,
        submod: SubMod | None = None,
    ) -> None:
        """Create a QTableWidgetItem with optional SubMod payload.

        Args:
            row: Zero-based row index (must already exist in the table).
            col: Zero-based column index.
            text: Display text.
            submod: When provided, stored under ``_SUBMOD_ROLE`` for the
                round-trip lookup in ``_on_row_activated``.
        """
        item = QTableWidgetItem(text)
        if submod is not None:
            item.setData(_SUBMOD_ROLE, submod)
        self._table.setItem(row, col, item)

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_row_activated(self, item: QTableWidgetItem) -> None:
        """Emit ``navigate_to_submod`` for the row's owning SubMod.

        The SubMod is stored on column-1's item under ``_SUBMOD_ROLE``.
        This handler resolves that regardless of which column the user
        actually double-clicked.
        """
        row = item.row()
        anchor = self._table.item(row, 1)
        if anchor is None:
            return
        submod = anchor.data(_SUBMOD_ROLE)
        if isinstance(submod, SubMod):
            self.navigate_to_submod.emit(submod)

    def _on_copy_all(self) -> None:
        """Copy the full table as TSV to the system clipboard."""
        lines = [
            "\t".join([
                entry.submod.display_path,
                str(entry.file_path),
                entry.error_type,
                str(entry.line) if entry.line else "",
                entry.message,
            ])
            for entry in self._entries
        ]
        QGuiApplication.clipboard().setText("\n".join(lines))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_entries(self, entries: Iterable[WarningEntry]) -> None:
        """Replace the current rows with *entries* and re-render.

        Args:
            entries: New iterable of WarningEntry.
        """
        self._entries = list(entries)
        self._populate()
```

- [ ] **Step 4: Run tests to verify they pass.**

Run: `uv run pytest tests/unit/test_scan_issues_pane.py -q`
Expected: PASS, 9 tests.

- [ ] **Step 5: Run the full unit suite.**

Run: `uv run pytest tests/unit -q`
Expected: PASS.

- [ ] **Step 6: Commit.**

```bash
git add src/oar_priority_manager/ui/scan_issues_pane.py tests/unit/test_scan_issues_pane.py
git commit -m "feat(ui): add ScanIssuesPane non-modal log dialog (refs #51)"
```

**Done when:** tests green, pane can be opened standalone with a list of entries.

---

### Task 4: Wire `scan_issues_requested` on `MainWindow` + `_refresh_warning_count`

**Files:**
- Modify: `src/oar_priority_manager/ui/main_window.py`
- Create: `tests/unit/test_main_window_scan_issues.py`

**Steps:**

- [ ] **Step 1: Write failing tests. Follow the `MagicMock`-as-`self` pattern used by `test_main_window_advanced.py`.**

```python
"""Tests for MainWindow's Scan issues wiring (issue #51, Task 4).

Uses the MagicMock-as-self pattern from test_main_window_advanced.py —
we do NOT instantiate a real MainWindow because that pulls in MO2
instance plumbing the unit tests do not have.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.ui.main_window import MainWindow


def _sm(name: str, warnings: list[str]) -> SubMod:
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


class TestRefreshWarningCount:
    def test_counts_submods_with_warnings(self) -> None:
        mock_self = MagicMock()
        mock_self._submods = [
            _sm("a", []),
            _sm("b", ["boom"]),
            _sm("c", ["x", "y"]),
        ]
        MainWindow._refresh_warning_count(mock_self)
        mock_self._search_bar.set_scan_issues_count.assert_called_once_with(2)
        assert mock_self._warning_count == 2

    def test_zero_when_no_warnings(self) -> None:
        mock_self = MagicMock()
        mock_self._submods = [_sm("a", [])]
        MainWindow._refresh_warning_count(mock_self)
        mock_self._search_bar.set_scan_issues_count.assert_called_once_with(0)


class TestOnScanIssuesRequested:
    def test_opens_new_pane_first_time(self) -> None:
        mock_self = MagicMock()
        mock_self._submods = [_sm("a", ["File not found: C:/x"])]
        mock_self._scan_issues_pane = None
        with patch(
            "oar_priority_manager.ui.main_window.ScanIssuesPane"
        ) as PaneCls:
            pane_inst = MagicMock()
            PaneCls.return_value = pane_inst
            MainWindow._on_scan_issues_requested(mock_self)
            # ScanIssuesPane was instantiated with the entry list and self as parent
            assert PaneCls.call_count == 1
            args, kwargs = PaneCls.call_args
            assert kwargs["parent"] is mock_self
            # navigate_to_submod connected to the bridge slot
            pane_inst.navigate_to_submod.connect.assert_called_once_with(
                mock_self._navigate_from_scan_issues
            )
            pane_inst.show.assert_called_once()
            pane_inst.raise_.assert_called_once()
            pane_inst.activateWindow.assert_called_once()
            assert mock_self._scan_issues_pane is pane_inst

    def test_reuses_existing_pane_and_refreshes_entries(self) -> None:
        mock_self = MagicMock()
        mock_self._submods = [_sm("a", ["File not found: C:/x"])]
        existing = MagicMock()
        mock_self._scan_issues_pane = existing
        with patch(
            "oar_priority_manager.ui.main_window.ScanIssuesPane"
        ) as PaneCls:
            MainWindow._on_scan_issues_requested(mock_self)
            # Should NOT construct a second pane
            PaneCls.assert_not_called()
            existing.set_entries.assert_called_once()
            existing.show.assert_called_once()
            existing.raise_.assert_called_once()
            existing.activateWindow.assert_called_once()


class TestNavigateFromScanIssues:
    def test_delegates_to_tree_panel_select_submod(self) -> None:
        mock_self = MagicMock()
        sm = _sm("nav", [])
        MainWindow._navigate_from_scan_issues(mock_self, sm)
        mock_self._tree_panel.select_submod.assert_called_once_with(sm)
```

- [ ] **Step 2: Run tests to verify they fail.**

Run: `uv run pytest tests/unit/test_main_window_scan_issues.py -q`
Expected: FAIL — `_refresh_warning_count`, `_on_scan_issues_requested`, `_navigate_from_scan_issues` not implemented; `ScanIssuesPane` not imported in main_window.

- [ ] **Step 3: Modify `src/oar_priority_manager/ui/main_window.py`.**

1. Add imports near the top:

```python
from oar_priority_manager.core.warning_report import collect_warning_entries
from oar_priority_manager.ui.scan_issues_pane import ScanIssuesPane
```

2. In `__init__`, initialise the new attributes alongside `_advanced_query`:

```python
        # Tracks the most recently applied advanced filter query.  None when
        # no advanced filter is active (text search is in effect instead).
        self._advanced_query: AdvancedFilterQuery | None = None
        # Scan Issues log pane (non-modal; lazily created on first open).
        self._scan_issues_pane: ScanIssuesPane | None = None
        self._warning_count: int = 0
```

3. At the tail end of `__init__`, after `_apply_config()`, add:

```python
        self._refresh_warning_count()
```

4. Add to `_connect_signals`:

```python
        self._search_bar.scan_issues_requested.connect(
            self._on_scan_issues_requested
        )
```

5. In `_on_refresh`, after the existing refresh body, append:

```python
        self._refresh_warning_count()
        if self._scan_issues_pane is not None and self._scan_issues_pane.isVisible():
            self._scan_issues_pane.set_entries(
                collect_warning_entries(self._submods)
            )
```

6. Append three new methods near `_on_advanced_requested`:

```python
    def _refresh_warning_count(self) -> None:
        """Recompute warning count and push it to the search bar.

        Counts SubMods whose ``has_warnings`` is ``True`` — NOT the total
        number of warning strings, because the spec phrases the button
        label as "how many submods are affected".
        """
        self._warning_count = sum(1 for sm in self._submods if sm.has_warnings)
        self._search_bar.set_scan_issues_count(self._warning_count)

    def _on_scan_issues_requested(self) -> None:
        """Open (or re-focus) the Scan Issues log pane (spec §7.8).

        First-click behaviour: build a list of WarningEntry from the
        current submods, instantiate ``ScanIssuesPane``, wire its
        ``navigate_to_submod`` signal to :meth:`_navigate_from_scan_issues`,
        then show the dialog non-modally.

        Subsequent clicks: refresh the existing pane's entries and raise
        it to the top rather than creating a duplicate dialog.
        """
        entries = collect_warning_entries(self._submods)
        if self._scan_issues_pane is None:
            pane = ScanIssuesPane(entries=entries, parent=self)
            pane.navigate_to_submod.connect(self._navigate_from_scan_issues)
            self._scan_issues_pane = pane
        else:
            self._scan_issues_pane.set_entries(entries)
        self._scan_issues_pane.show()
        self._scan_issues_pane.raise_()
        self._scan_issues_pane.activateWindow()

    def _navigate_from_scan_issues(self, submod: SubMod) -> None:
        """Forward a log-pane row activation to the tree panel.

        The tree panel's ``select_submod`` does the scroll-into-view and
        fires its own ``selection_changed`` signal, which ultimately
        drives :class:`DetailsPanel` to render the parse-error view for
        the warning node.

        Args:
            submod: The SubMod the user double-clicked on in the pane.
        """
        self._tree_panel.select_submod(submod)
```

- [ ] **Step 4: Run tests to verify they pass.**

Run: `uv run pytest tests/unit/test_main_window_scan_issues.py -q`
Expected: PASS, 5 tests.

- [ ] **Step 5: Run the full unit suite.**

Run: `uv run pytest tests/unit -q`
Expected: PASS.

- [ ] **Step 6: Commit.**

```bash
git add src/oar_priority_manager/ui/main_window.py tests/unit/test_main_window_scan_issues.py
git commit -m "feat(main-window): wire scan issues pane + warning count refresh (refs #51)"
```

**Done when:** `grep scan_issues_requested src/oar_priority_manager/ui/main_window.py` shows exactly one connection; `_warning_count` is refreshed on init and on refresh.

---

### Task 5: `DetailsPanel` parse-error view for warning submods

**Files:**
- Modify: `src/oar_priority_manager/ui/details_panel.py`
- Create: `tests/unit/test_details_panel_warnings.py`

**Steps:**

- [ ] **Step 1: Write failing tests in `tests/unit/test_details_panel_warnings.py`.**

```python
"""Tests for DetailsPanel parse-error view (issue #51, Task 5, spec §7.8)."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.ui.details_panel import DetailsPanel
from oar_priority_manager.ui.tree_model import NodeType, TreeNode


def _sm(warnings: list[str]) -> SubMod:
    return SubMod(
        mo2_mod="ModA",
        replacer="Rep",
        name="broken",
        description="A broken submod",
        priority=100,
        source_priority=100,
        disabled=False,
        config_path=Path("C:/mods/ModA/Rep/broken/config.json"),
        override_source=OverrideSource.SOURCE,
        override_is_ours=False,
        raw_dict={},
        warnings=warnings,
    )


def _submod_node(sm: SubMod) -> TreeNode:
    return TreeNode(
        display_name=sm.name,
        node_type=NodeType.SUBMOD,
        submod=sm,
    )


class TestDetailsPanelWarnings:
    def test_clean_submod_renders_normal_view(self, qtbot) -> None:
        panel = DetailsPanel()
        qtbot.addWidget(panel)
        sm = _sm(warnings=[])
        panel.update_selection(_submod_node(sm))
        html = panel._label.text()
        # Normal view includes "Priority:" and "Animations:" labels.
        assert "Priority:" in html
        assert "Animations:" in html

    def test_warning_submod_hides_normal_metadata(self, qtbot) -> None:
        panel = DetailsPanel()
        qtbot.addWidget(panel)
        sm = _sm(warnings=["File not found: C:/x/user.json"])
        panel.update_selection(_submod_node(sm))
        html = panel._label.text()
        # Normal metadata sections must NOT appear on a warning submod.
        assert "Animations:" not in html
        assert "Conditions:" not in html
        assert "Override source:" not in html

    def test_warning_submod_shows_each_warning_bullet(self, qtbot) -> None:
        panel = DetailsPanel()
        qtbot.addWidget(panel)
        warnings = [
            "File not found: C:/x/user.json",
            "JSON parse error in C:/x/config.json: line 5 column 1",
        ]
        sm = _sm(warnings=warnings)
        panel.update_selection(_submod_node(sm))
        html = panel._label.text()
        assert "File not found: C:/x/user.json" in html
        assert "JSON parse error in C:/x/config.json" in html

    def test_warning_submod_shows_submod_name_and_path(self, qtbot) -> None:
        panel = DetailsPanel()
        qtbot.addWidget(panel)
        sm = _sm(warnings=["Empty file: C:/x/config.json"])
        panel.update_selection(_submod_node(sm))
        html = panel._label.text()
        assert sm.name in html
        assert str(sm.config_path.parent) in html

    def test_warning_banner_is_styled_red(self, qtbot) -> None:
        panel = DetailsPanel()
        qtbot.addWidget(panel)
        sm = _sm(warnings=["File not found: C:/x"])
        panel.update_selection(_submod_node(sm))
        html = panel._label.text()
        # The banner uses the same red hex (#e66) as the existing warnings span.
        assert "#e66" in html
```

- [ ] **Step 2: Run tests to verify they fail.**

Run: `uv run pytest tests/unit/test_details_panel_warnings.py -q`
Expected: FAIL — on `test_warning_submod_hides_normal_metadata`, which currently fails because today's `_render_submod` appends warnings but also renders all normal metadata; on the parse-error-only tests the HTML still contains `Animations:` etc.

- [ ] **Step 3: Modify `src/oar_priority_manager/ui/details_panel.py`.**

1. In `update_selection`, change the SUBMOD branch:

```python
        elif node.node_type == NodeType.SUBMOD:
            if node.submod is None:
                self._label.setText("Select an item in the tree to see details.")
            elif node.submod.has_warnings:
                self._label.setText(self._render_submod_warnings(node.submod))
            else:
                self._label.setText(self._render_submod(node))
```

2. Add the new renderer (place it immediately after `_render_submod`):

```python
    def _render_submod_warnings(self, submod: SubMod) -> str:
        """Build rich HTML for a SUBMOD with non-empty warnings (spec §7.8).

        Replaces the normal metadata layout entirely — no priority line,
        no conditions summary, no tags. The idea is that a warning submod
        is broken; showing normal metadata implies the data is trustable.

        Args:
            submod: A SUBMOD whose ``has_warnings`` is ``True``.

        Returns:
            A RichText HTML string.
        """
        lines = [
            f"<b>{submod.name}</b>",
            f"<span style='color:gray'>{submod.config_path.parent}</span>",
            "<span style='color:#e66'><b>&#9888; WARNING — parse errors prevent normal display</b></span>",
            "",
        ]
        for warning in submod.warnings:
            lines.append(
                f"<span style='color:#e66'>&#8226; {warning}</span>"
            )
        return "<br>".join(lines)
```

3. Remove the trailing "Warnings section" from `_render_submod` — it becomes dead code once the branch above is in place. Delete these lines from `_render_submod`:

```python
        # Warnings section — parse errors and validation issues
        if submod.warnings:
            lines.append("<br><span style='color:#e66'><b>&#9888; Warnings</b></span>")
            for warning in submod.warnings:
                lines.append(f"<span style='color:#e66'>&#8226; {warning}</span>")
```

Rationale: a non-warning submod never has warnings (by definition of `has_warnings`), so those lines were already unreachable under the new branching. Removing them prevents future drift.

4. Add `from oar_priority_manager.core.models import SubMod` to the imports block (the file already imports `OverrideSource` from the same module — extend the existing import line to: `from oar_priority_manager.core.models import OverrideSource, SubMod`).

- [ ] **Step 4: Run tests to verify they pass.**

Run: `uv run pytest tests/unit/test_details_panel_warnings.py -q`
Expected: PASS, 5 tests.

- [ ] **Step 5: Run the full unit suite — existing DetailsPanel tests may need no change because non-warning submods (the default fixture case) still route through `_render_submod`.**

Run: `uv run pytest tests/unit -q`
Expected: PASS. If an existing test explicitly exercised the old "Warnings" bullets inside normal metadata, update it to use `_render_submod_warnings` (or remove — there should be no such test today based on the search below).

Sanity grep:

```bash
git -C I:/games/skyrim/mods/oar_plugin_sorter_2 grep -n "Warnings" tests/unit/test_details_panel*
```

- [ ] **Step 6: Commit.**

```bash
git add src/oar_priority_manager/ui/details_panel.py tests/unit/test_details_panel_warnings.py
git commit -m "feat(details-panel): render parse-error view for warning submods (refs #51)"
```

**Done when:** warning submods render only the parse-error view; clean submods render unchanged.

---

### Task 6: End-to-end smoke test

**Files:**
- Create: `tests/smoke/test_scan_issues_smoke.py`

**Steps:**

- [ ] **Step 1: Write the smoke test.**

```python
"""End-to-end smoke test for the Scan Issues log pane (issue #51, Task 6).

Scenario:
- Two submods on disk: one valid, one with an invalid JSON config.json.
- Launch a real MainWindow.
- Assert the Scan issues button label shows "Scan issues (1)" and is enabled.
- Open the pane via _on_scan_issues_requested().
- Assert the pane's table has exactly one row referencing the broken submod.
- Double-click the row, assert the tree currentItem becomes the broken submod.
- Assert the DetailsPanel switches to the parse-error view (contains the
  "WARNING — parse errors prevent normal display" banner, does NOT contain
  "Priority:" or "Animations:").
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from oar_priority_manager.app.config import AppConfig
from oar_priority_manager.core.anim_scanner import build_conflict_map, scan_animations
from oar_priority_manager.core.filter_engine import extract_condition_types
from oar_priority_manager.core.priority_resolver import build_stacks
from oar_priority_manager.core.scanner import scan_mods
from oar_priority_manager.ui.main_window import MainWindow
from oar_priority_manager.ui.tree_model import NodeType
from tests.conftest import make_config_json, make_submod_dir


@pytest.fixture
def warning_instance(tmp_path: Path) -> Path:
    """Create an MO2 instance with one valid and one broken submod.

    ``valid_sub`` has a normal config.json; ``broken_sub`` has config.json
    that fails to parse after trailing-comma repair (mismatched bracket).
    """
    instance = tmp_path
    mods = instance / "mods"
    mods.mkdir()
    (instance / "overwrite").mkdir()
    (instance / "ModOrganizer.ini").touch()

    make_submod_dir(
        mods,
        "TestMod",
        "REP",
        "valid_sub",
        config=make_config_json(name="valid_sub", priority=100),
        animations=["mt_walk.hkx"],
    )
    # Write a config.json that will not parse even after comma repair.
    broken_dir = (
        mods / "TestMod" / "meshes" / "actors" / "character"
        / "animations" / "OpenAnimationReplacer" / "REP" / "broken_sub"
    )
    broken_dir.mkdir(parents=True)
    (broken_dir / "config.json").write_text(
        "{\"name\": \"broken_sub\", \"priority\": 50,\n\"conditions\": [",
        encoding="utf-8",
    )
    # Drop a stub .hkx so the scanner considers it a submod.
    (broken_dir / "stub.hkx").write_text("", encoding="utf-8")
    return instance


@pytest.fixture
def main_window(qtbot, warning_instance: Path) -> MainWindow:
    mods_dir = warning_instance / "mods"
    overwrite_dir = warning_instance / "overwrite"
    submods = scan_mods(mods_dir, overwrite_dir)
    scan_animations(submods)
    for sm in submods:
        present, negated = extract_condition_types(sm.conditions)
        sm.condition_types_present = present
        sm.condition_types_negated = negated

    conflict_map = build_conflict_map(submods)
    stacks = build_stacks(conflict_map)

    window = MainWindow(
        submods=submods,
        conflict_map=conflict_map,
        stacks=stacks,
        app_config=AppConfig(),
        instance_root=warning_instance,
    )
    qtbot.addWidget(window)
    window.show()
    return window


def test_scan_issues_button_shows_count(main_window: MainWindow) -> None:
    """The Scan issues button label reflects 1 warning submod."""
    btn = main_window._search_bar._scan_issues_btn
    assert btn.isEnabled()
    assert btn.text() == "Scan issues (1)"


def test_scan_issues_pane_lists_broken_submod(
    qtbot, main_window: MainWindow
) -> None:
    """Opening the pane shows exactly one row for broken_sub."""
    main_window._on_scan_issues_requested()
    pane = main_window._scan_issues_pane
    assert pane is not None
    qtbot.waitUntil(lambda: pane.isVisible(), timeout=500)
    assert pane._table.rowCount() == 1
    row_submod = pane._table.item(0, 1).text()
    assert "broken_sub" in row_submod


def test_double_click_navigates_and_details_panel_switches_view(
    qtbot, main_window: MainWindow
) -> None:
    """Double-click on a log row selects the tree node and shows parse errors."""
    main_window._on_scan_issues_requested()
    pane = main_window._scan_issues_pane
    assert pane is not None
    qtbot.waitUntil(lambda: pane._table.rowCount() == 1, timeout=500)

    # Simulate double-click on column 1 (Submod column).
    item = pane._table.item(0, 1)
    pane._table.itemDoubleClicked.emit(item)

    # Tree selection should now be the broken_sub SUBMOD node.
    current = main_window._tree_panel._tree.currentItem()
    assert current is not None
    node = main_window._tree_panel._item_map.get(id(current))
    assert node is not None
    assert node.node_type == NodeType.SUBMOD
    assert node.submod is not None
    assert node.submod.name == "broken_sub"

    # Details panel rendered the parse-error view.
    html = main_window._details_panel._label.text()
    assert "WARNING" in html
    assert "parse errors" in html
    assert "Priority:" not in html
    assert "Animations:" not in html
```

- [ ] **Step 2: Run the smoke test.**

Run: `uv run pytest tests/smoke/test_scan_issues_smoke.py -q`
Expected: PASS, 3 tests.

- [ ] **Step 3: Run the full test suite.**

Run: `uv run pytest -q`
Expected: PASS across `tests/unit`, `tests/integration`, `tests/smoke`.

- [ ] **Step 4: Run the linter.**

Run: `uv run ruff check src tests`
Expected: clean.

- [ ] **Step 5: Commit.**

```bash
git add tests/smoke/test_scan_issues_smoke.py
git commit -m "test(smoke): scan issues pane + details panel parse-error view (refs #51)"
```

**Done when:** the smoke test is green; `ruff check` clean.

---

### Task 7: Documentation + spec compliance + PR

**Files:**
- Modify: `docs/spec-compliance-audit.md` — flip the three §7.8 / §9 rows from ❌ to ✅:
  - "Clicking warning item shows errors in details"
  - "Scan issues (N) button in top bar"
  - Under §9: "Scan issues (N) button"
  - Leave "Action buttons disabled for warning items" as ❌ — that is out of scope (see §9 below).
- Modify: `README.md` — add a one-paragraph note under "Usage" (if the section exists — `grep -n "^## Usage" README.md` first) describing the Scan issues button.
- Do **not** create new top-level design docs.

**Steps:**

- [ ] **Step 1: Edit `docs/spec-compliance-audit.md`.** Change lines 157, 159, 214 per the list above. Do not touch line 121/158/213 (action-button-disable rows).

- [ ] **Step 2: Check if README needs an update.**

```bash
git -C I:/games/skyrim/mods/oar_plugin_sorter_2 grep -n "^## Usage" README.md
```

If the section exists, append a paragraph such as:

> ### Reviewing scan warnings
> A `Scan issues (N)` button in the top bar lists every parse or validation
> problem found during the most recent scan. Double-click a row to jump to
> the offending submod in the tree; the details panel then shows a
> parse-error-only view instead of normal metadata.

If the section does not exist, skip the README update.

- [ ] **Step 3: Commit the docs change.**

```bash
git add docs/spec-compliance-audit.md README.md
git commit -m "docs: mark §7.8 Scan issues rows compliant (closes #51)"
```

- [ ] **Step 4: Push the branch and open a PR.**

Use the `superpowers:finishing-a-development-branch` skill. PR body must include `closes #51`.

**Done when:** audit doc updated, PR open and linked to issue.

---

## 6. Testing Strategy

### 6.1 Unit (pytest + pytest-qt)

- `tests/unit/test_warning_report.py` — pure logic for `WarningEntry` and `collect_warning_entries`; covers every parser/scanner warning prefix enumerated in §9.
- `tests/unit/test_search_bar_scan_issues.py` — button creation, label update, signal emission, layout order.
- `tests/unit/test_scan_issues_pane.py` — widget-level tests on `ScanIssuesPane` using the `QT_QPA_PLATFORM=offscreen` pattern.
- `tests/unit/test_main_window_scan_issues.py` — slots (`_refresh_warning_count`, `_on_scan_issues_requested`, `_navigate_from_scan_issues`) via `MagicMock`-as-`self`, mirroring `test_main_window_advanced.py` lines 1-40.
- `tests/unit/test_details_panel_warnings.py` — `DetailsPanel` branches to parse-error view when `submod.has_warnings`.

### 6.2 Integration / Smoke

- `tests/smoke/test_scan_issues_smoke.py` — one end-to-end test that writes a broken config to disk, scans, and drives the full open-pane → navigate → details-panel flow.

### 6.3 What NOT to test in this plan

- Warning *generation* (parser/scanner producing the original strings) — already covered by `test_parser.py` and `test_scanner.py`.
- The advanced filter builder — unrelated, already covered.
- Real-world OAR mods on disk — covered by existing fixture tests.
- Accessibility of the log pane (screen readers, high-contrast) — out of scope for MVP.

---

## 7. Integration Points

### 7.1 How the log pane coexists with the existing filter/search UX

The pane and the search bar operate on completely separate axes: the pane is a read-only diagnostic view, not a filter. Applying an advanced filter or a text search has no effect on what the pane shows — it always reads every warning in `self._submods`. Conversely, double-clicking a pane row does NOT clear any active filter; the tree simply highlights the submod via `select_submod`. If the active filter currently hides the warning submod, `select_submod` will still set `currentItem` but the item may be visually dim or hidden — this is acceptable for MVP and documented in §9 Out of Scope (filter-aware navigation).

### 7.2 Signal wiring audit

Current state (pre-change):

- `SearchBar` emits `advanced_requested`, `refresh_requested`, `search_changed`, `filter_mode_changed`, `condition_mode_changed`.
- Nothing emits `scan_issues_requested` today — the signal is new.

Task 2 introduces the emitter; Task 4 introduces the listener. After Task 4, `grep scan_issues_requested` must return:

- one emitter (`search_bar.py`)
- one connection (`main_window.py` `_connect_signals`)
- zero other references in production code

### 7.3 Warning count staleness

`_warning_count` is refreshed:

1. In `MainWindow.__init__` after `_apply_config()` — initial value on launch.
2. At the end of `_on_refresh` — every rescan.

There is intentionally NO live update when a submod is edited through the tool, because priority writes do not change warning state. If a future feature *does* mutate warnings (e.g. fixing a config in-tool), that feature must call `_refresh_warning_count` explicitly.

### 7.4 Pane lifecycle

- Lazily created on first click (not constructed in `__init__`).
- Held on `self._scan_issues_pane` so subsequent clicks re-focus rather than open a duplicate.
- Not destroyed on close — the user's window position / column widths stick for the session. (Persisting them to `AppConfig.window_geometry` is out of scope.)
- Destroyed automatically when the MainWindow is destroyed (parent-owned `QDialog`).

### 7.5 Non-modality and focus

`setModal(False)` + `show()` instead of `exec()`. The user can click around the tree with the pane open. `raise_()` + `activateWindow()` ensure a second click on the top-bar button brings the pane back to front rather than spawning a ghost behind.

---

## 8. Open Questions (proposed defaults — confirm before implementation)

Each question below carries a **proposed default**. The rest of the plan (data contracts, tasks, tests) is written *as if each default is accepted*. Confirm or override each one before Task 1 starts; if any default changes, amend the affected tasks first.

1. **Modal vs dockable vs non-modal pane.**
   The FilterBuilder is a modal `QDialog`. The log pane has a different access pattern — the user typically wants to scan the list, click a row, verify in the tree, come back. Three options:
   - **(a) Modal `QDialog`.** Matches FilterBuilder exactly; forces user to close the pane before touching the tree.
   - **(b) Dockable `QDockWidget`.** Persistent side panel. Requires turning the three-pane splitter into a dockable layout, which is a non-trivial refactor.
   - **(c) Non-modal `QDialog`.** Free-floating window; user can interact with the main window while the pane is open.

   **Proposed default: (c) Non-modal `QDialog`.** Cheapest to build (no layout refactor), best UX (user can double-click a row and immediately see the tree highlight without closing anything). Task 3 implements `setModal(False)` explicitly and the test asserts it.

2. **`Scan issues (N)` count update cadence — when does N refresh?**
   - **(a) Only on `__init__` and `_on_refresh`.** Simple; no live updates.
   - **(b) After every action that could change warnings** (priority edit, clear-override, tag edit).
   - **(c) Periodic poll.**

   **Proposed default: (a).** Rationale: no tool operation currently touches warning state — writes are priority-only, and warnings come from file-level parse problems. (b) and (c) would add plumbing for zero observable change today. Task 4 wires refresh at both call sites only.

3. **Warning count meaning — what does N represent?**
   - **(a) Number of SubMods with `has_warnings == True`** — "how many things are broken?".
   - **(b) Total number of warning strings across all SubMods** — "how many individual problems?".

   **Proposed default: (a).** A single broken config can emit 3+ warnings; counting submods more closely matches user intent ("X mods need attention"). Clicking the button always lists every warning regardless — the count is just a summary. Task 4 implements `sum(1 for sm in self._submods if sm.has_warnings)`.

4. **Severity levels.**
   Spec §9 says "load with warnings" vs "hard error (modal + abort)". The log pane only ever sees warnings (hard errors never reach this UI). Do we want info/warning/error tiers within the pane?

   **Proposed default: Single `"warning"` severity in MVP.** The `severity` field is reserved on `WarningEntry` for future expansion (e.g. distinguishing "recoverable parse repair applied" vs "field missing"), but defaults to `"warning"`. The severity column displays `⚠` uniformly. Task 1 test asserts the default.

5. **Click-through navigation.**
   When the user clicks a warning in the log pane, what happens?
   - **(a) Single-click selects the row only; double-click (or Enter) selects the corresponding tree node.**
   - **(b) Single-click both selects the row and selects the tree node.**

   **Proposed default: (a).** Single-click should not cause large UI side-effects (user may be scrolling, comparing, reading). Double-click is the conventional "activate" gesture for list rows. Task 3 wires `itemDoubleClicked`.

6. **Warning persistence across rescan.**
   - **(a) Rebuild from current `self._submods` on every open / refresh. No snapshot.**
   - **(b) Snapshot on first scan; persist; show "Stale" indicator after refresh.**

   **Proposed default: (a).** Warnings live on `SubMod.warnings` and are rebuilt by `scan_mods` every time. The pane is a view, not a history log. If the pane is open during a refresh, it auto-updates via `set_entries`. Task 4 `_on_refresh` adds the auto-refresh call.

7. **Details panel "parse error mode" — replacement or overlay?**
   - **(a) Replace: warning submods render ONLY the parse-error view — no priority, no conditions, no tags.**
   - **(b) Overlay: warning banner at top, then normal metadata below (today's behaviour, minus the banner placement).**

   **Proposed default: (a) Replace.** Spec §7.8 says "instead of normal metadata". A submod with parse errors has untrusted metadata — showing `Priority: 50,000` next to a banner saying "this file failed to parse" is misleading. Task 5 removes the existing trailing warnings block from `_render_submod` so there is exactly one code path per case.

8. **Log pane and filters.**
   If the user has an advanced filter active that hides some warning submods, does the log pane filter too?
   - **(a) Pane always shows every warning in `self._submods`, ignoring active filters.**
   - **(b) Pane only shows warnings for visible (matching) submods.**
   - **(c) Double-clicking a filtered-out row automatically clears the filter.**

   **Proposed default: (a).** Diagnostic surfaces should never hide diagnostic data. If a filter hides a warning submod, the log pane still lists it; double-clicking calls `select_submod` which does its best (the item may be dimmed/hidden by the filter). The user clears the filter if needed. See §7.1.

---

## 9. Out of Scope

Explicitly deferred — each becomes a separate issue if needed.

- **Disabling action buttons on warning items.** The broader spec §7.8 bullet "All three action buttons are disabled for warning items — edits are blocked" is a separate concern (details-panel / stacks-panel interaction, not log-pane work). The spec-compliance audit row for that bullet stays ❌ in this PR.
- **Auto-opening the pane on high warning counts.** Some tools pop up a toast or banner when scan issues exceed a threshold. Out of scope; the user controls when to open the pane.
- **Filter-aware navigation.** If a filter is hiding the target submod, double-clicking a pane row still calls `select_submod` but the tree may show the item dimmed or hidden. Clearing the filter is the user's responsibility. Enhancement: auto-clear-filter on navigate — separate issue.
- **Persisting pane geometry / column widths** to `AppConfig`. Current behaviour: session-only (lost on app restart). Enhancement — separate issue.
- **Filtering or sorting inside the pane.** No search box, no column sort toggles in MVP. Spec does not request them; can be added later.
- **Export warnings to file.** `Copy All` copies TSV to clipboard. Saving to a `.tsv` or `.json` file on disk is not in MVP.
- **Structured warnings at the SubMod level.** `SubMod.warnings` remains `list[str]`. Structuring the scanner/parser to produce `WarningEntry` directly (instead of string parsing in `collect_warning_entries`) would eliminate the regex layer but requires touching every warning producer and every existing test that asserts on the string format. Deferred to a dedicated refactor issue.
- **Per-warning "Open in editor" action.** A future right-click on a pane row could open the offending file in the user's configured text editor. Nice-to-have; not in MVP.
- **Warning severity differentiation.** Single `warning` severity today. If we add recoverable-vs-fatal distinctions later, the reserved `severity` field on `WarningEntry` absorbs it with no schema break.
- **Live recomputation of N on edits.** Warning count updates only on `__init__` and `_on_refresh`. If a future feature mutates warnings in-memory (unlikely — editing is write-through to disk followed by refresh), it must call `_refresh_warning_count` explicitly.

---

## 10. Definition of Done

- [ ] All tasks 1–7 checkboxes complete.
- [ ] `uv run pytest -q` green across `tests/unit`, `tests/integration`, `tests/smoke`.
- [ ] `uv run ruff check src tests` clean.
- [ ] `grep scan_issues_requested src/` shows exactly one emitter (`search_bar.py`) and one connection (`main_window.py`).
- [ ] `grep _render_submod_warnings src/` shows exactly one definition (`details_panel.py`) and one call site (`details_panel.py` `update_selection`).
- [ ] Manual smoke: launch the app against a real MO2 instance that contains at least one malformed `config.json` (e.g. temporarily break a fixture), observe:
  - button label reads `Scan issues (N)` with the right N
  - clicking opens the pane
  - double-clicking a row selects the warning submod in the tree AND the details panel switches to the parse-error view
  - clicking Refresh rebuilds everything; the open pane updates automatically
- [ ] `docs/spec-compliance-audit.md` updated: the three §7.8 / §9 rows covered by this issue flipped to ✅.
- [ ] PR opened with body referencing `closes #51`.
- [ ] Issue #51 closed automatically on merge to `main`.
