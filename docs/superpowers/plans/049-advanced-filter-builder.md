# Advanced Filter Builder — Implementation Plan (Issue #49)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Tracking issue:** cbeaulieu-gt/oar-priority-manager#49
**Milestone:** Alpha 2
**Spec reference:** `docs/superpowers/specs/2026-04-11-oar-priority-manager-design.md` §7.7
**Tech stack:** Python 3.11+, PySide6 (Qt 6), pytest, pytest-qt
**Branch strategy:** create a fresh branch off `main` named `feature/049-filter-builder` inside a worktree at `.worktrees/049-filter-builder/` per repo policy. Pull `origin/main` first.

---

## 1. Goal

Replace the "coming soon" stub in `ui/filter_builder.py` with a functional modal dialog that lets a user build a structural condition-presence filter across three buckets and apply it to the tree panel, producing the same filtering behaviour the text-mode condition filter produces today — but without requiring the user to remember condition names or boolean syntax.

**Concrete behavioural requirements (restated from §7.7 + #49):**

1. Clicking the existing **Advanced...** button in the top bar opens a modal `FilterBuilder` dialog (the signal already fires — it is simply not connected to anything yet).
2. The dialog displays three labelled, colour-coded pill buckets:
   - **REQUIRED** (green) — all listed condition types must appear in a submod's `condition_types_present`.
   - **ANY OF** (yellow) — at least one listed condition type must appear.
   - **EXCLUDED** (red) — none of the listed condition types may appear.
3. Each bucket has a `+` button. Clicking `+` opens an autocompleting input (a `QCompleter`-backed `QLineEdit`, or a popup combo) sourced from the union of:
   a. Every condition type observed in the currently loaded submods (`SubMod.condition_types_present` aggregated).
   b. A static fallback list of common OAR condition names (re-use the keys of `_DISTINCTIVE_CONDITIONS` + `_NON_DISTINCTIVE_CONDITIONS` from `core/tag_engine.py` — ~20 names, already curated).
4. Each pill shows the condition name and an `x` control to remove it from the bucket.
5. The dialog has **Apply**, **Clear**, and **Cancel** buttons. On Apply: the tree filters to submods that pass all three bucket rules; dialog closes. On Clear: all three buckets are emptied AND the dialog emits an empty-query `filter_applied` (clearing any active filter), then closes. On Cancel: dialog closes without changing the current filter.
6. If the user opens the dialog while a condition-mode text filter is active, the dialog pre-populates from the parsed query where possible (REQUIRED <- `query.required`, EXCLUDED <- `query.excluded`, ANY OF starts empty — text mode has no ANY OF semantics today).

---

## 2. Architecture Overview

```
            user clicks "Advanced..." in top bar
                           │
                           ▼
   SearchBar.advanced_requested ── signal (already emitted; currently unwired)
                           │
          ┌────────────────┴─────────────────┐
          ▼                                  │
   MainWindow._on_advanced_requested()  (NEW slot)
          │
          │ 1. Aggregate known condition types from self._submods
          │ 2. Instantiate FilterBuilder(known_types, preload_query)
          │ 3. Connect filter_applied signal
          │ 4. dialog.exec()
          ▼
   FilterBuilder (modal QDialog) ──── filter_applied(AdvancedFilterQuery) ───▶
          │                                                                    │
          │ user adds/removes pills, clicks Apply                               │
          │                                                                    │
          └──────────── closes with Accepted / Rejected                        │
                                                                                │
                                                                                ▼
                                            MainWindow._apply_advanced_filter()
                                                        │
                                                        │ Walks tree; runs
                                                        │ match_advanced_filter()
                                                        │ per submod.
                                                        ▼
                                            TreePanel.filter_tree(matching, hide_mode)
```

**Boundary:** `FilterBuilder` is a pure view — it emits a data object describing what the user wants filtered and never touches the tree or the filter engine directly. All state on the window (search bar text, tree filter) remains `MainWindow`'s responsibility.

---

## 3. Data Contracts

### 3.1 Condition-type source (input to `FilterBuilder`)

A **sorted, deduplicated `list[str]`** of condition type names — passed as the existing `known_types` constructor arg.

Producer: a new helper in `core/filter_engine.py`:

```python
def collect_known_condition_types(submods: Iterable[SubMod]) -> list[str]:
    """Union of every SubMod.condition_types_present + static fallbacks, sorted."""
```

The static fallback set lives in the helper (or is imported from `tag_engine._DISTINCTIVE_CONDITIONS` / `_NON_DISTINCTIVE_CONDITIONS` keys — decide in Task 2). Returning a `list` (not `set`) guarantees stable UI ordering.

### 3.2 Filter state (output from `FilterBuilder`)

A new dataclass, added to `core/filter_engine.py` alongside `FilterQuery`:

```python
@dataclass
class AdvancedFilterQuery:
    required: set[str] = field(default_factory=set)   # all must be present
    any_of:   set[str] = field(default_factory=set)   # at least one must be present
    excluded: set[str] = field(default_factory=set)   # none may be present

    def is_empty(self) -> bool: ...
```

### 3.3 Matching semantics (new pure function)

```python
def match_advanced_filter(
    present: set[str],
    negated: set[str],          # reserved, unused for MVP
    query: AdvancedFilterQuery,
) -> bool:
    """
    Rules (spec §7.7):
      - empty query matches all
      - query.required.issubset(present) must hold (empty REQUIRED = auto-pass)
      - if query.any_of non-empty: (query.any_of & present) must be non-empty
      - (query.excluded & present) must be empty
    """
```

### 3.4 Signals

On `FilterBuilder` (new public surface):

```python
filter_applied = Signal(object)   # payload: AdvancedFilterQuery
filter_cleared = Signal()         # payload: (none) — user wants filter off
```

`filter_applied` fires exactly once, immediately before `accept()`, when the user clicks **Apply**.
`filter_cleared` fires if the user clicks a **Clear** button (optional — see §8 Open Questions).

### 3.5 MainWindow integration

New attribute `self._advanced_query: AdvancedFilterQuery | None = None` tracks the currently-applied advanced filter. When set, it takes precedence over the text search bar (or coexists — see §7 Integration Points).

---

## 4. Component Breakdown

| Module / class | Status | One-line purpose |
|---|---|---|
| `core/filter_engine.py` → `AdvancedFilterQuery` | **New** | Dataclass holding the three bucket sets. |
| `core/filter_engine.py` → `match_advanced_filter()` | **New** | Pure function: does a submod's condition-type sets satisfy the query? |
| `core/filter_engine.py` → `collect_known_condition_types()` | **New** | Build the autocomplete source list from submods + static fallback. |
| `ui/filter_builder.py` → `FilterBuilder` | **Rewrite** | Modal dialog hosting three `BucketWidget`s, Apply/Cancel buttons, pre-population. |
| `ui/filter_builder.py` → `BucketWidget` | **New** (private) | One labelled, colour-coded area with a `+` button, an autocompleting input, and a `FlowLayout`-ish row of `PillWidget`s. Exposes `items()` and `set_items()`. |
| `ui/filter_builder.py` → `PillWidget` | **New** (private) | `QFrame` showing condition name + `x` button; emits `removed` signal. |
| `ui/filter_builder.py` → `FlowLayout` or `QHBoxLayout` w/ wrap | **New** (private) | Container that wraps pills to next line when width exceeded. A minimal `QHBoxLayout` is acceptable for MVP (no wrapping) — see §8 Open Questions. |
| `ui/main_window.py` → `_on_advanced_requested()` | **New slot** | Build known-types list, open the dialog, wire the `filter_applied` signal. |
| `ui/main_window.py` → `_apply_advanced_filter()` | **New** | Walk the tree, run `match_advanced_filter()` per submod, forward to `TreePanel.filter_tree()`. Mirrors `_apply_condition_filter()`. |
| `ui/main_window.py` → `_connect_signals()` | **Modify** | Connect `self._search_bar.advanced_requested` → `self._on_advanced_requested`. |

---

## 5. Phased Implementation Steps

> **Each task below is scoped to one `code-writer` session: one concept, one PR-sized diff, ends green tests.**
> TDD is mandatory per `@C:\Users\chris\.claude\standards\software-standards.md` — every task writes the failing test first.
> After every task: run `pytest tests/unit -q` locally; all previously-passing tests must still pass.

### Task 1: `AdvancedFilterQuery` dataclass + `match_advanced_filter()` (pure logic)

**Files:**
- Modify: `src/oar_priority_manager/core/filter_engine.py`
- Create: `tests/unit/test_advanced_filter.py`

**Steps:**
- [ ] Write failing tests in `tests/unit/test_advanced_filter.py`:
  - `TestAdvancedFilterQuery`: default-constructed is empty; `is_empty()` returns True.
  - `TestMatchAdvancedFilter`:
    - Empty query matches every `present` set (including `set()`).
    - REQUIRED only: `{"A"}` required, `present={"A","B"}` → True; `present={"B"}` → False.
    - ANY_OF only: `{"A","B"}` any_of, `present={"B"}` → True; `present={"C"}` → False; empty `present` → False.
    - EXCLUDED only: `{"A"}` excluded, `present={"A"}` → False; `present={"B"}` → True.
    - Combined: REQUIRED={"A"}, ANY_OF={"X","Y"}, EXCLUDED={"Z"}, `present={"A","Y"}` → True; with extra `"Z"` → False; without any of X/Y → False.
    - Same name in REQUIRED and EXCLUDED with `present={"A"}` → False (EXCLUDED wins because required passes but excluded fails — document this behaviour in the test name).
- [ ] Implement `AdvancedFilterQuery` (dataclass) and `match_advanced_filter()` in `filter_engine.py`.
- [ ] Export new names from module (add to module docstring's "Public API" list).

**Done when:** `pytest tests/unit/test_advanced_filter.py -q` passes; no existing test broken.

---

### Task 2: `collect_known_condition_types()` helper

**Files:**
- Modify: `src/oar_priority_manager/core/filter_engine.py`
- Modify: `tests/unit/test_advanced_filter.py`

**Steps:**
- [ ] Write failing tests:
  - Empty submod list → returns only the static fallback list, sorted.
  - Submods with overlapping `condition_types_present` → deduplicated, sorted union.
  - Result is a `list` (not `set`) and is sorted ascending (verifies UI stability).
  - Fallback list contains at least `"IsFemale"`, `"IsInCombat"`, `"HasMagicEffect"` (sentinel coverage check — do not assert the exact set, future-proofing).
- [ ] Implement. **Decision:** import the static fallback from `tag_engine._DISTINCTIVE_CONDITIONS` + `_NON_DISTINCTIVE_CONDITIONS` keys to avoid duplication. Do NOT depend on `tag_engine` at import time from `filter_engine.py` — do the import lazily inside the function to avoid a circular-import risk (flagged in §8).

**Done when:** new tests green; existing tests untouched; `ruff check` clean.

---

### Task 3: `PillWidget` (reusable single-pill UI element)

**Files:**
- Modify: `src/oar_priority_manager/ui/filter_builder.py`
- Create: `tests/unit/test_filter_builder.py`

**Steps:**
- [ ] Write failing pytest-qt tests in `tests/unit/test_filter_builder.py` using the `qtbot` fixture pattern from `test_condition_filter_search.py` (`os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")` at top of file).
  - `TestPillWidget`:
    - Constructing with `("IsFemale", bucket_color="#2e7d32")` shows "IsFemale" label.
    - Constructing exposes an `x`-style close button (`QToolButton` or `QPushButton` with object name `"pill-remove"`).
    - Clicking the close button emits `removed` signal with the condition name as payload.
    - `name` property returns the original string.
    - Stylesheet contains the supplied background colour hex.
- [ ] Implement `PillWidget(QFrame)`:
  - Signal: `removed = Signal(str)`.
  - Layout: horizontal — `QLabel(name)` + `QPushButton("x")` (flat, small).
  - Stylesheet applied at construction using the passed bucket colour (rounded corners, white text, small padding — mirror the existing `tag_delegate.py` pill aesthetic).
  - Expose `name` as a read-only `@property`.

**Done when:** new tests green.

---

### Task 4: `BucketWidget` (one labelled bucket with autocomplete + pills)

**Files:**
- Modify: `src/oar_priority_manager/ui/filter_builder.py`
- Modify: `tests/unit/test_filter_builder.py`

**Steps:**
- [ ] Write failing pytest-qt tests:
  - `TestBucketWidget`:
    - `BucketWidget("REQUIRED", "#2e7d32", known_types=["A","B","C"])` shows a "REQUIRED" header and a `+` button.
    - `.items()` returns `[]` on fresh instance.
    - `add_item("A")` appends a pill; `.items()` now returns `["A"]`.
    - `add_item("A")` a second time is a no-op (no duplicate pills — de-dupe in the bucket).
    - Simulating the `+` button → autocomplete popup shows (use `qtbot.mouseClick`, verify a `QCompleter`/`QLineEdit`/`QComboBox` becomes visible). Test against object name, not widget type, to allow flexibility.
    - Typing "A" + Enter in the popup's input adds a pill for "A".
    - Adding a condition not in `known_types` is still allowed (user may have a custom/plugin condition). Emit a signal or log-level event? → For MVP: allow it silently.
    - `set_items(["A","B"])` replaces current pills; calling `.items()` returns `["A","B"]` (order preserved).
    - A pill emitting `removed("A")` causes the bucket to remove it; `.items()` no longer contains "A".
    - `items_changed` signal fires on every add/remove.
- [ ] Implement `BucketWidget(QWidget)`:
  - Constructor: `(label: str, color: str, known_types: list[str], parent=None)`.
  - Layout:
    - Top row: `QLabel(label)` styled with the bucket colour + `QPushButton("+")` right-aligned.
    - Pills row: `QHBoxLayout` inside a `QWidget` (MVP — no wrapping; see §8 Open Questions). Add `addStretch()` at the end so pills pack left.
  - Clicking `+` opens a small popup or inline input with `QCompleter(known_types, caseSensitivity=Qt.CaseInsensitive, filterMode=Qt.MatchContains)`.
  - Public API: `items() -> list[str]`, `set_items(list[str])`, `add_item(str)`, signal `items_changed = Signal()`.
  - Use Context7 / `mcp__plugin_context7_context7__query-docs` for the current PySide6 `QCompleter` API (`setCompletionMode(QCompleter.PopupCompletion)`, `setFilterMode(Qt.MatchContains)`), plus whether `QLineEdit.editingFinished` or `QCompleter.activated[str]` is the right signal to pick an item.

**Done when:** new tests green; `BucketWidget` can round-trip a set of names through `set_items` / `items`.

---

### Task 5: `FilterBuilder` dialog composition (replaces the stub)

**Files:**
- Modify: `src/oar_priority_manager/ui/filter_builder.py`
- Modify: `tests/unit/test_filter_builder.py`

**Steps:**
- [ ] Write failing pytest-qt tests:
  - `TestFilterBuilder`:
    - Constructor accepts `known_types: list[str]` and optional `initial: AdvancedFilterQuery | None = None`.
    - Dialog hosts three `BucketWidget`s with labels "REQUIRED", "ANY OF", "EXCLUDED" in that order (verify by finding child `BucketWidget`s and reading their label text).
    - Each bucket uses its spec-defined colour (green `#2e7d32`, yellow `#f9a825`, red `#c62828`). Test by asserting the colour string is present in the bucket's stylesheet — do not snapshot exact CSS.
    - Apply button exists and is connected.
    - Clear button exists and is connected.
    - Cancel button exists.
    - `initial=AdvancedFilterQuery(required={"A"}, any_of={"B"}, excluded={"C"})` → dialog pre-populates buckets accordingly.
    - Clicking Apply emits `filter_applied` once with an `AdvancedFilterQuery` whose three sets reflect current bucket contents, THEN calls `accept()` (dialog closes with `QDialog.Accepted`).
    - Clicking Clear: empties all three buckets (`bucket.items()` → `[]` for each), emits `filter_applied` once with a default-constructed (empty) `AdvancedFilterQuery`, THEN calls `accept()` (dialog closes with `QDialog.Accepted`). Verify emitted query's `is_empty()` is True.
    - Clicking Cancel does NOT emit `filter_applied` and closes with `QDialog.Rejected`.
    - Applying with all three buckets empty emits an `AdvancedFilterQuery` whose `is_empty()` is True (MainWindow treats that as "clear filter" — see Task 7).
- [ ] Implement `FilterBuilder(QDialog)`:
  - Replace the "coming soon" stub with three stacked `BucketWidget`s, followed by a `QDialogButtonBox` with Apply, Clear (add as a custom `ResetRole` button — `button_box.addButton("Clear", QDialogButtonBox.ResetRole)`), and Cancel.
  - Signal: `filter_applied = Signal(object)`.
  - Method: `_collect_query() -> AdvancedFilterQuery` — read `items()` from each bucket.
  - Apply handler: emit `filter_applied(self._collect_query())`, then `self.accept()`.
  - Clear handler: call `bucket.set_items([])` on each of the three buckets, emit `filter_applied(AdvancedFilterQuery())` (default-constructed, empty), then `self.accept()`. Rationale: emitting a single empty query cleanly instructs `MainWindow._apply_advanced_filter` to clear the filter via its existing `query.is_empty()` short-circuit — no extra API surface needed.
  - Cancel handler: `self.reject()`.
  - Window title: "Advanced Condition Filter" (already set).
  - Sensible default size: `self.resize(600, 400)` — do not hard-code a fixed size; allow resize.

**Done when:** FilterBuilder tests green; existing stub tests (if any) updated or deleted; no visual regression in existing dialogs.

---

### Task 6: Wire `advanced_requested` in MainWindow + `_on_advanced_requested` slot

**Files:**
- Modify: `src/oar_priority_manager/ui/main_window.py`
- Modify: `tests/unit/test_condition_filter_search.py` OR create `tests/unit/test_main_window_advanced.py`

**Steps:**
- [ ] Write failing tests (follow the `MagicMock`-as-`self` pattern already used for `_apply_condition_filter` — do not instantiate a real `MainWindow` since that requires MO2 infra):
  - `TestOnAdvancedRequested`:
    - Calling `_on_advanced_requested` with the mock self opens a `FilterBuilder` (mock the class to assert it's called with the right `known_types`).
    - `known_types` passed to the dialog is the sorted union of `_submods[*].condition_types_present` plus static fallback.
    - If `self._search_bar.current_mode == SearchMode.CONDITION`, the dialog is constructed with a pre-populated `initial` matching the parsed query.
    - If the dialog emits `filter_applied(query)`, `self._apply_advanced_filter(query)` is called.
- [ ] Implement `_on_advanced_requested(self)`:
  - Build `known_types = collect_known_condition_types(self._submods)`.
  - Build `initial: AdvancedFilterQuery | None`:
    - If search bar is in condition mode: parse current text, convert `FilterQuery` → `AdvancedFilterQuery(required=fq.required, excluded=fq.excluded)` (any_of stays empty).
    - Else `None`.
  - Instantiate `FilterBuilder(known_types, initial=initial, parent=self)`.
  - Connect `dialog.filter_applied` to `self._apply_advanced_filter`.
  - Call `dialog.exec()`.
- [ ] Modify `_connect_signals()` to connect `self._search_bar.advanced_requested` to `self._on_advanced_requested`. (Currently the signal is emitted but unwired — see §5.1 below.)

**Done when:** new tests green; `grep advanced_requested` shows exactly one connection in MainWindow.

---

### Task 7: `_apply_advanced_filter()` on MainWindow

**Files:**
- Modify: `src/oar_priority_manager/ui/main_window.py`
- Modify: `tests/unit/test_condition_filter_search.py` (extend the existing `TestApplyConditionFilter` pattern, or add a new `TestApplyAdvancedFilter` class)

**Steps:**
- [ ] Write failing tests (use the same `_run_filter` harness pattern already in `test_condition_filter_search.py` — see lines 347-407):
  - Empty query → `filter_tree(None)` called (clears filter).
  - REQUIRED={"IsFemale"} matches only submods with IsFemale.
  - ANY_OF={"IsFemale","HasPerk"} matches submods with either.
  - EXCLUDED={"HasPerk"} excludes submods with HasPerk.
  - All three combined yields the expected intersection.
  - Tree nodes without a SubMod are skipped (mirror `test_none_submod_node_skipped`).
  - `hide_mode` is forwarded from `self._hide_mode` to `TreePanel.filter_tree()`.
- [ ] Implement `_apply_advanced_filter(self, query: AdvancedFilterQuery) -> None`:
  - If `query.is_empty()`: `self._tree_panel.filter_tree(None); return`.
  - Walk `self._tree_panel.tree_root` → children → children → children, filter SUBMOD nodes by `match_advanced_filter(sm.condition_types_present, sm.condition_types_negated, query)`, accumulate `id(node)` into `matching`.
  - `self._tree_panel.filter_tree(matching, hide_mode=self._hide_mode)`.
  - Store `self._advanced_query = query` so state can be interrogated later (enables future "clear" / "edit existing filter" flows).

**Done when:** tests green; manual smoke: launch app, click Advanced, add IsFemale to REQUIRED, Apply, tree dims non-matching submods.

---

### Task 8: End-to-end smoke test

**Files:**
- Create: `tests/smoke/test_filter_builder_smoke.py` (or extend `tests/smoke/test_ui_smoke.py`)

**Steps:**
- [ ] Write one smoke test that:
  - Creates a minimal on-disk MO2 instance via the existing `tmp_instance` + `make_submod_dir` fixtures (two submods: one with `IsFemale` condition, one without).
  - Launches a real `MainWindow` with the synthetic instance.
  - Programmatically triggers `_on_advanced_requested`, obtains the open `FilterBuilder`, calls `BucketWidget.add_item("IsFemale")` on REQUIRED, clicks Apply.
  - Asserts the tree panel now has exactly one SUBMOD node in the matching set (via the `filter_tree` spy pattern, or via reading item visibility if the tree is in hide mode).
- [ ] Use `qtbot.waitUntil` with a short timeout for dialog-close races.

**Done when:** smoke test green under `pytest tests/smoke/ -q`.

---

### Task 9: Documentation + changelog

**Files:**
- Modify: `README.md` (if filter mode is surfaced to users there — grep first).
- Modify: `docs/spec-compliance-audit.md` — flip the three §7.7 rows from ❌ to ✅.
- Close #49 via commit trailer (`closes #49`).

**Done when:** audit doc reflects new state; commit pushed; PR opened with body referencing #49.

---

## 6. Testing Strategy

### 6.1 Unit (pytest + pytest-qt)
- `tests/unit/test_advanced_filter.py` — pure logic for `AdvancedFilterQuery`, `match_advanced_filter`, `collect_known_condition_types`.
- `tests/unit/test_filter_builder.py` — widget-level tests (Pill, Bucket, FilterBuilder). Use the `QT_QPA_PLATFORM=offscreen` pattern from `tests/unit/test_condition_filter_search.py` lines 14-16.
- `tests/unit/test_condition_filter_search.py` (or new `test_main_window_advanced.py`) — `MainWindow._on_advanced_requested` and `MainWindow._apply_advanced_filter` via the `MagicMock`-as-`self` pattern (reuse the `_run_filter` harness at lines 347-407).

### 6.2 Integration / Smoke
- One end-to-end test in `tests/smoke/` exercising open-dialog → add-pill → apply → tree-filtered.

### 6.3 What NOT to test in this plan
- Real-world OAR `config.json` integration — covered by existing `test_scanner` / `test_filter_engine`.
- The text-mode search bar — covered by `test_condition_filter_search.py`.
- `FilterQuery` / `match_filter` — untouched.

---

## 7. Integration Points

### 7.1 How FilterBuilder coexists with text-mode condition search

**Proposed behaviour (see §8 Open Questions for confirmation):** text search and advanced filter are **mutually exclusive** — whichever fires last wins.

- Opening Advanced... while text is in condition mode → dialog pre-populates from the parsed text query.
- Applying a filter from Advanced... → clear the search bar text (to avoid stale text staying visible while a different filter is active), set `self._advanced_query`, call `_apply_advanced_filter`.
- Typing in the search bar after applying an advanced filter → the new text takes over, `self._advanced_query = None`.

This matches the spec's framing of Advanced... as "a secondary interaction for cross-mod auditing" (§7.2, line 305), not as a parallel filter layer.

### 7.2 Signal wiring audit

Current state (from grep):
- `SearchBar.advanced_requested` is emitted by the Advanced... button click handler.
- Nothing connects to it — opening the `FilterBuilder` dialog is dead-ended today.

Task 6 is the fix. The wiring must go in `MainWindow._connect_signals()`.

### 7.3 Persistence

Applied advanced filters are **not persisted across restarts** in this plan. This matches current behaviour for text-mode filters and spec §8.3 (which lists `search_history` as a persisted field but says nothing about advanced filter state).

---

## 8. Decisions (locked in 2026-04-16)

All eight questions below were resolved before implementation began. Code-writer sessions should treat these as fixed constraints, not open questions.

1. **REQUIRED ∩ EXCLUDED conflict** → **RESOLVED: EXCLUDED wins.** If a condition is in both buckets, the submod fails. No UI warning in MVP. Task 1 tests encode this.
2. **ANY OF + empty REQUIRED semantics** → **RESOLVED: Independent AND.** The three buckets combine with AND: must have all REQUIRED, must have at least one of ANY OF (only when non-empty), must have none of EXCLUDED. ANY OF is NOT a fallback when REQUIRED is empty.
3. **Static fallback list source** → **RESOLVED: Reuse `tag_engine` keys + discovered union.** Task 2 imports `_DISTINCTIVE_CONDITIONS` + `_NON_DISTINCTIVE_CONDITIONS` keys (~20 names) as the fallback, then unions with observed `condition_types_present`. Lazy import to avoid circular dependency.
4. **Pill wrapping** → **RESOLVED: Flat `QHBoxLayout` for MVP.** No `FlowLayout`. If real-world usage hits truncation, open a follow-up polish issue. Task 4 implementation uses `addStretch()` for left-packing.
5. **"Clear filter" button** → **RESOLVED: ADD the Clear button.** The dialog has three buttons: Apply, Clear, Cancel. Clear empties all buckets, emits an empty `filter_applied`, and closes with `Accepted`. Task 5 tests and implementation updated accordingly.
6. **Autocomplete UI pattern** → **RESOLVED: Inline `QLineEdit` + `QCompleter` popup** (option a). No separate picker dialog. Task 4 tests assert against object name for flexibility.
7. **Text-mode / Advanced mutual exclusivity** → **RESOLVED: Latest wins.** Opening Advanced pre-populates from the current text query where possible (REQUIRED / EXCLUDED; ANY OF starts empty). Applying Advanced clears the search text. Typing in the search bar after an Advanced filter takes over and clears `self._advanced_query`. See §7.1.
8. **ANY OF pre-population from text queries** → **RESOLVED: Accept empty for MVP.** The text parser has no OR output, so ANY OF starts empty when opening the builder over a condition-mode query. Document in §9 (Out of Scope) that extending the text parser to produce OR and re-checking this mapping is a follow-up.

---

## 9. Out of Scope

Explicitly deferred — each becomes a separate issue if needed.

- **Filter presets** (save / name / recall filter configurations). Not in §7.7. Candidate post-Alpha 2 feature.
- **Tag-based filtering.** The category-tags design doc (`docs/superpowers/specs/2026-04-14-category-tags-design.md` §Deferred) explicitly defers tag-bucket filtering to issues #49/#50 as a follow-up. This plan does not add tags as a fourth bucket.
- **Nested grouping** (`(A AND B) OR (C AND D)`). Spec §7.7 explicitly excludes this ("No nested groups").
- **Condition-value filtering** (e.g. `IsFemale AND HasPerk=Ancient Knowledge`). Spec is structural-presence only (§6.2, §7.6).
- **Persisting advanced filter state across restarts.** See §7.3.
- **Visualizing the currently-applied filter** in the top bar (e.g. a chip reading "Advanced: 2 required, 1 excluded"). Discoverability improvement — separate issue.
- **Filter negation of groups** (e.g. "NONE of these must be present AS NEGATED"). The negated-set is left reserved in `match_advanced_filter` per the existing `match_filter` contract.
- **Circular-import hardening of `core/filter_engine` → `core/tag_engine`.** If the lazy import in Task 2 becomes awkward, extract the shared condition-type list into a new `core/oar_constants.py` module. Not needed for correctness, just a cleanup.

---

## 10. Definition of Done

- [ ] All tasks 1–9 checkboxes complete.
- [ ] `pytest -q` green across `tests/unit`, `tests/integration`, `tests/smoke`.
- [ ] `ruff check src tests` clean.
- [ ] Manual smoke: launch the app against a real MO2 instance, click Advanced..., add at least one pill to each bucket, click Apply, observe tree filter behaves correctly.
- [ ] `docs/spec-compliance-audit.md` updated.
- [ ] PR opened referencing `closes #49`.
- [ ] Issue #49 closed automatically on merge to `main`.
