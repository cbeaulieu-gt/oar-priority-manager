# OAR Priority Manager — Design Spec

**Date:** 2026-04-11
**Status:** Approved for implementation planning
**Authors:** Chris (product direction), Claude (brainstorming partner)

## 1. Summary

`oar-priority-manager` is a desktop tool for Skyrim modders using Mod Organizer 2 (MO2) and Open Animation Replacer (OAR). It lets the user inspect which OAR submods are competing for the same animation files, see who is currently winning each competition, and adjust submod priorities so their preferred submod wins — without ever modifying source mod files.

The tool is a Python + PySide6 desktop application deployed as an MO2 Executable. It reads the merged MO2 virtual filesystem (VFS), parses OAR `config.json` / `user.json` files, computes priority stacks per animation, and writes priority overrides to the MO2 Overwrite folder at mirrored paths.

## 2. Problem

### 2.1 User story

> *"I just added this OAR mod to my modlist and it's not playing. I'm sure the conditions are right. What priority do I need to set it to so it plays?"*

This is the central workflow the tool serves. Every UI and architectural decision is evaluated against whether it makes this workflow faster and clearer.

### 2.2 Why the user can't answer this today

OAR's in-game MCM shows each mod's submods in a list, but it does not surface:

- **Which animation files from one submod are actually competing with which files from another submod.** A submod that "provides" `mt_walkforward.hkx` is only in a real competition with other submods that also provide `mt_walkforward.hkx`. The MCM lists the submod's priority in isolation.
- **Which MO2 mod folder a given submod comes from.** OAR groups by its own display name, not by the underlying MO2 mod source. Two MO2 mods with the same display name would merge in OAR's view, and there's no way to tell them apart from in-game.
- **What priority delta is needed for a specific submod to win.** The user has to read both priorities and do the subtraction mentally.

### 2.3 Prior attempts and why they failed

- **Attempt 1 (`oar_config_manager`)** — 475-line parser with 83 condition types, seven phases built, including a Priority Engine and a drag-drop PriorityViewModel. Killed by scope creep into condition editing, which is a harder problem than priority management and took over the project.
- **Attempt 2 (`oar_plugin_sorter`)** — correctly simplified to priority-only with `raw_dict` round-trip preservation. Stalled because the author tried to statically determine whether two condition trees were mutually exclusive. That problem is equivalent to Boolean satisfiability (SAT), and attempting to solve it without a proper SAT backend led to a `conflict_engine.py` module that grew in complexity without converging on correct answers.

The critical lesson from both: **condition semantics is a trap.** This design explicitly excludes any form of semantic condition analysis. The user accepts responsibility for condition correctness themselves.

## 3. Goals and non-goals

### 3.1 Goals

- Show the user every OAR submod in their MO2 modlist, grouped by MO2 mod folder.
- For each animation a submod provides, show the full competition stack — every other submod that also provides that animation, ordered by OAR's evaluation order (priority descending).
- Let the user adjust priorities with three operations: Move to Top, Set Exact Priority, and Shift to Priority N.
- Persist all priority changes to the MO2 Overwrite folder at mirrored relative paths, never touching source mod files.
- Surface the MO2 mod folder provenance of every submod — the one piece of information OAR's in-game UI cannot show.
- Let the user filter the visible set of submods by structural presence of condition types (e.g. "show me every submod that has an `IsFemale` condition anywhere in its tree").
- Run as an MO2 Executable so it sees the correct merged VFS state.

### 3.2 Non-goals

- **Condition editing.** The tool displays conditions read-only. Condition authorship is done in OAR's in-game UI or by editing `config.json` directly.
- **Semantic condition analysis.** The tool never asks "can these two condition trees both be true at the same time?" It only asks "does this condition tree contain a node of type X?" — a structural tree walk, not a SAT problem.
- **Disable / enable toggling.** OAR already handles this in-game; the tool displays disabled state but does not change it.
- **In-game integration (SKSE plugin, MCM).** The tool is an external desktop application.
- **Cross-platform support.** Windows only — MO2 is Windows-only, and Skyrim modders are almost all on Windows.
- **Animation file editing or generation.** The tool never touches `.hkx` files.
- **Managing non-OAR animation replacement systems (DAR, etc.).** Out of scope; OAR-only.

## 4. Background: how OAR priority works

Verified from OAR source (`src/ReplacerMods.cpp::EvaluateConditionsAndGetReplacementAnimation()`):

1. For a given animation event, OAR collects all submods that provide a replacement for the matching `.hkx` filename (case-insensitive match on filename).
2. Disabled submods are excluded.
3. The remaining submods are pre-sorted by priority descending.
4. OAR iterates the sorted list and returns the first submod whose conditions evaluate to true at runtime.
5. If no submod's conditions match, vanilla plays.

**Key implications:**

- **Priority is a tiebreaker only when conditions match.** A higher-priority submod whose conditions fail does not block a lower-priority submod.
- **Filename is matched case-insensitively.** The tool normalizes `.hkx` filenames to lowercase when building its conflict map.
- **Priority is `int32`.** Values can range from `INT32_MIN` to `INT32_MAX`. Real-world OAR mods often use values in the 1e9 – 2e9 range.

## 5. Core data model

### 5.1 Terminology

- **MO2 mod** — a top-level folder under `<instance>/mods/`, discovered via VFS scan.
- **Replacer** — a subfolder under `meshes/actors/character/animations/OpenAnimationReplacer/` within a MO2 mod. Corresponds to OAR's `ReplacerMod`.
- **Submod** — a subfolder under a replacer, containing a `config.json` (and optionally `user.json`). Corresponds to OAR's `SubMod`.
- **Animation file** — an `.hkx` file inside a submod (or inside an `overrideAnimationsFolder` path if specified).
- **Priority stack** — the ordered list of all submods that provide a given animation filename, sorted by priority descending.
- **Override** — a priority change made by the tool. Stored in MO2 Overwrite at a mirrored path, never in the source mod folder.

### 5.2 Submod data

Every submod is stored as:

```python
SubMod:
    mo2_mod: str             # MO2 mod folder name
    replacer: str            # Replacer folder name
    name: str                # Display name from config.json
    description: str         # Description from config.json
    priority: int            # Current effective priority (from override precedence)
    source_priority: int     # Priority in source config.json (before any override)
    disabled: bool
    config_path: Path        # Absolute path to the source config.json
    override_source: Enum    # SOURCE | USER_JSON | OVERWRITE
    raw_dict: dict           # Complete round-trip-preserved config contents
    animations: list[str]    # Lowercased .hkx filenames (from anim_scanner)
    conditions: dict         # Full condition tree (read-only; for filter + display)
    condition_types: set[str]  # Flat set of all condition type names appearing in the tree
    warnings: list[str]      # Parse/validation warnings; non-empty blocks edits
```

### 5.3 Override precedence

When reading a submod's effective priority, the tool checks in this order:

1. **MO2 Overwrite** at `<Overwrite>/<mirrored path>/user.json` — tool-written overrides
2. **user.json** at `<source mod>/<replacer>/<submod>/user.json` — OAR in-game overrides
3. **config.json** at `<source mod>/<replacer>/<submod>/config.json` — original author value

The first file found in this order supplies the effective priority. The tool never writes to levels 2 or 3; it only writes to level 1.

### 5.4 Priority stack

For every unique lowercased animation filename across all submods, the tool builds a stack:

```python
PriorityStack:
    animation_filename: str        # lowercased .hkx name
    competitors: list[SubMod]      # ordered by effective priority descending
```

Stacks are computed by `priority_resolver.py` from the output of `anim_scanner.py`.

## 6. Architecture

### 6.1 Module layout

```
oar-priority-manager/
├── core/
│   ├── parser.py            (salvaged from attempt 2)
│   ├── scanner.py           (salvaged)
│   ├── anim_scanner.py      (salvaged)
│   ├── serializer.py        (salvaged)
│   ├── override_manager.py  (salvaged)
│   ├── priority_resolver.py (new)
│   ├── filter_engine.py     (new)
│   └── tree_model.py        (new)
├── ui/
│   ├── main_window.py
│   ├── tree_panel.py
│   ├── details_panel.py
│   ├── stacks_panel.py
│   ├── conditions_panel.py
│   └── filter_builder.py
├── app/
│   ├── config.py
│   └── main.py
├── tests/
│   ├── fixtures/mods/
│   ├── unit/
│   └── smoke/
├── pyproject.toml
├── .gitignore
└── README.md
```

Approximately **70% of core code is salvaged from attempt 2**, unchanged or with minimal edits. The `conflict_engine.py` module from attempt 2 is **not carried over** — it represents the SAT-solver trap that killed the previous effort. New modules (`priority_resolver`, `filter_engine`, `tree_model`) are all net-new, along with the entire `ui/` tree.

### 6.2 Module responsibilities

**`core/parser.py`** — Parses a single `config.json` / `user.json` into a raw_dict, with lenient JSON handling (trailing-comma repair). Produces warnings on malformed input without raising. Preserves all fields for round-trip.

**`core/scanner.py`** — Walks the MO2 mods directory, discovers every submod folder, applies override precedence, and builds the initial set of `SubMod` records. Handles the MO2 Overwrite folder as an override layer.

**`core/anim_scanner.py`** — Cross-mod scan of every submod's animation files, including `overrideAnimationsFolder` redirection. Produces a `conflict_map: dict[str, list[SubMod]]` keyed by lowercased filename.

**`core/serializer.py`** — Writes a `raw_dict` back to disk as JSON, preserving field order. Only the `priority` field is modified between read and write; every other field round-trips unchanged.

**`core/override_manager.py`** — Computes the mirrored path in MO2 Overwrite for a given submod, creates parent directories, writes via `serializer.py`, and exposes a `clear_override()` operation. Never writes to source mod paths.

**`core/priority_resolver.py`** *(new)* — Takes the conflict map from `anim_scanner` and produces an ordered `PriorityStack` per animation. Also exposes the three mutation operations:

- `move_to_top(target, scope)` — scope is submod / replacer / mod. Sets priority to `max(competitor_priorities) + 1`. When the scope is replacer or mod, the operation is applied per-stack for every animation the submods in scope contribute to. Edge case: if `max + 1` would overflow `INT32_MAX`, the operation fails with a user-visible error and no write is performed.
- `set_exact(submod, priority)` — submod-level only.
- `shift(scope, floor_priority)` — scope is replacer or mod. For the set of submods in scope, `new_priority = floor_priority + (old_priority - min(old_priorities))`.

**`core/filter_engine.py`** *(new)* — Structural condition-presence filter. Walks each submod's condition tree once to produce a `set[str]` of condition type names that appear anywhere (respecting `negated` flags as a separate "hasn't" bucket). Queries against this set require zero semantic evaluation.

**`core/tree_model.py`** *(new)* — Builds the left-tree hierarchy:

- **Level 1 (Mods):** alphabetical by OAR display name from config.json (matches OAR's UI sort order)
- **Level 2 (Replacers):** alphabetical by folder name (our addition; OAR's UI flattens this level, but the filesystem layer is useful for provenance)
- **Level 3 (Submods):** priority descending (matches OAR's UI sort order), with a user-toggleable alphabetical sort

**UI modules** — covered in §7.

**`app/config.py`** — Tool's own config (Relative/Absolute toggle state, window geometry, sort toggle state, filter history). Stored as JSON at `<MO2 instance root>/oar-priority-manager/config.json`. The tool detects instance root by walking up from the mods path or reading `ModOrganizer.ini`.

**`app/main.py`** — Entry point. Constructs the `QApplication` and `MainWindow`.

### 6.3 Data flow

```
1. Startup
   └─ Detect MO2 instance root from running environment
   └─ Load tool config from instance/oar-priority-manager/config.json
2. Scan phase
   └─ scanner.py walks <instance>/mods/*/
   └─ For each candidate submod, parser.py reads config.json
       + Overwrite/user.json override layer
   └─ anim_scanner.py aggregates .hkx files across all submods
   └─ priority_resolver.py builds conflict_map and PriorityStack list
3. Model construction
   └─ tree_model.py builds the left-tree hierarchy
   └─ filter_engine.py builds the condition_types set per submod
4. UI phase
   └─ main_window.py constructs the three-pane layout
   └─ Signals wire user actions to resolver/override_manager
5. Edit flow (per action)
   └─ User triggers Move to Top / Set Exact / Shift
   └─ priority_resolver computes new priority value(s)
   └─ override_manager writes to MO2 Overwrite at mirrored path
   └─ tree/stacks refresh from in-memory state (no re-scan)
6. Shutdown
   └─ app/config.py writes tool config back to disk
```

## 7. User interface

### 7.1 Layout

The main window uses a three-pane layout with a vertically split left column:

```
┌─────────────────────────────────────────────────────────────────────┐
│  [filter text input]  [Advanced…]                                    │
├─────────────────┬──────────────────────────────┬────────────────────┤
│                 │ Priority Stacks              │ Conditions         │
│  Tree           │ [filter animations]          │ [Formatted][Raw]   │
│  ────           │ [Relative][Absolute] [Coll]  │ ──────────         │
│  (mods)         │                              │                    │
│                 │ ▾ mt_idle.hkx                │ REQUIRED           │
│                 │   #1 +0   (you)              │   ✓ Is Female      │
│                 │   #2 −70  Vanilla Tweaks     │                    │
│                 │                              │ ONE OF             │
│                 │ ▾ mt_walk.hkx                │   • Heavy Armor    │
│                 │   #1 +0   Walking Overhaul   │   • Shield         │
│                 │   #2 −300 (you)              │                    │
│  ─────          │                              │ EXCLUDED           │
│  Details        │ [Move to Top] [Set Exact…]   │   ✗ Helmet         │
│  (for selection)│                              │                    │
└─────────────────┴──────────────────────────────┴────────────────────┘
```

### 7.2 Top bar

A single filter input with an **Advanced…** button. The text input accepts simple expressions like `IsFemale AND IsInCombat`. The Advanced button opens a modal filter builder (see §7.7). Filter state applies to the left tree: matching submods are shown normally; non-matching submods are dimmed but still visible. An empty filter shows everything normally.

### 7.3 Left column — Tree + Details

**Tree (top of left column):**

- Three levels: Mod → Replacer → Submod
- Sort order: Mod alphabetical (OAR-native), Replacer alphabetical, Submod priority descending (OAR-native)
- Sort toggle at the top of the panel: `Submods: [Priority] [Name]`, default Priority. Only applies to the submod level; mod and replacer levels have fixed sort.
- Each row is one line: a status icon (✓ enabled, ⚠ warning, ✗ disabled) and the display name.
- Selection fires signals that update the Details panel, the center pane, and the right pane.

**Details panel (bottom of left column):**

- Read-only metadata strip that reacts to tree selection.
- Resizable divider between tree and details.
- Contents vary by selection level:

**Mod selected:**
- MO2 mod folder name
- Full path on disk
- Counts: replacers, submods (total), animations (total)
- Override summary ("3 of 12 submods have priority overrides")
- Disabled count

**Replacer selected:**
- Replacer name (folder)
- Parent mod link
- Counts: submods, animations
- Priority range (e.g. "500 – 507") across contained submods
- Override summary

**Submod selected (richest case):**
- Display name and full path breadcrumb
- Enabled / Disabled badge
- Overridden badge (if priority differs from source config.json)
- Description from config.json
- MO2 mod source (the unique feature — which MO2 folder this submod came from)
- Filesystem path
- Current priority, with "was X" annotation if overridden
- Animation count
- Condition summary ("4 total · 2 types")
- Override source ("MO2 Overwrite", "user.json in source", or "config.json")

**All action buttons stay in the center pane.** The details panel is strictly read-only metadata.

**Priority display in the details panel is always absolute**, regardless of the Relative/Absolute toggle state in the center pane. The toggle only affects the competitor-row display in the priority stacks pane — the details panel shows the raw priority value because a delta has no meaning for a standalone submod outside a comparison context.

### 7.4 Center pane — Priority Stacks

One section per animation file provided by the currently selected submod (or by everything in scope, if a replacer or mod is selected).

- Sections are expandable, default expanded. `▾` / `▸` toggle state per section.
- Each section header shows: animation filename, competitor count, status (`you're #1` / `losing by N` / `losing by N to Mod X`).
- Each competitor row: rank badge + priority number column + owner.
  - Rank badge: `#1` in green for top, `#2`+ in grey, losing rows get a red background.
  - `(you)` marker on the selected submod's rows.
  - Number column: single column, width depends on mode. Relative mode: 80px delta column (`+0`, `−70`, `−300`). Absolute mode: 140px right-aligned tabular-nums absolute column (`2,099,200,278`). **Toggling hides the other column entirely** — it is not shown dimmed.
- Toolbar at the top of the pane: `[animation filter text input]`, `[Relative | Absolute]` segmented toggle, `[Collapse winning]` button.
- Action buttons per scope: `[Move to Top]` at submod / replacer / mod levels; `[Set Exact…]` at submod only; `[Shift to Priority N…]` at replacer / mod.

### 7.5 Right pane — Conditions Detail

Read-only display of the currently focused competitor's condition tree.

- Header: `[Formatted | Raw JSON]` toggle, default Formatted. Plus the owner label ("Vanilla Tweaks / idle").
- **Formatted view** — parses the condition tree into three semantic buckets:
  - **REQUIRED** — atomic non-negated conditions at the top level (implicit AND)
  - **ONE OF** — conditions inside a top-level OR group
  - **EXCLUDED** — atomic negated conditions at the top level, or conditions inside a top-level NOT group
  This is a rendering heuristic, not a full condition evaluator. It handles the common case of flat top-level condition lists plus one level of grouping. For condition trees with deeper nesting (e.g. an OR group containing another AND group, or a negated OR), the formatter shows a note ("This condition tree has complex nesting — see Raw JSON for full structure") and the user can toggle to Raw JSON to see the original source. No attempt is made to simplify, normalize, or evaluate the tree.
- **Raw JSON view** — pretty-printed source of the condition tree, read-only.

### 7.6 Filter text bar (simple)

Accepts a simple boolean expression like `IsFemale AND IsInCombat AND NOT IsWearingHelmet`. Parsed by a small hand-written expression parser. Matches any submod whose `condition_types` set contains the required tokens and lacks the excluded tokens. No parentheses support in the text bar — users who want nesting use Advanced… (or accept that the filter is a flat check).

### 7.7 Advanced filter builder

Modal dialog with three pill buckets:

- **REQUIRED** (green) — submod must have every condition type listed here
- **ANY OF** (yellow) — submod must have at least one of the condition types listed here
- **EXCLUDED** (red) — submod must have none of the condition types listed here

Each bucket has a `+` button that opens an autocompleting dropdown of all known OAR condition type names (sourced from the set of types observed in the current scan, plus a static list of common types as fallback).

No nested groups. Users who need `(A AND B) OR (C AND D)` fall back to the text bar (with the caveat that even the text bar is flat structural matching — it's an escape hatch, not a full semantic filter).

### 7.8 Warning indicators

- Warning items appear in the tree with a `⚠` icon.
- Clicking a warning item in the tree shows the parse error(s) in the details panel instead of normal metadata.
- All three action buttons are disabled for warning items — edits are blocked.
- A `Scan issues (N)` button at the top bar opens a log pane listing every warning with file path, error type, and line number if available.

## 8. Persistence

### 8.1 OAR overrides

All priority changes are written to the MO2 Overwrite folder at a path that mirrors the source mod's relative structure:

```
<source mod path>                                     → overwrite path
───────────────────────────────────────────────────────────────────────
<instance>/mods/<MO2 mod>/meshes/actors/character/    →
  animations/OpenAnimationReplacer/<rep>/<sub>/user.json

<instance>/overwrite/meshes/actors/character/
  animations/OpenAnimationReplacer/<rep>/<sub>/user.json
```

The tool always writes `user.json` (not `config.json`) to the Overwrite folder. Because MO2's VFS merges the Overwrite layer on top of the source mod at the same relative path, OAR sees the tool-written `user.json` as if it lived inside the source mod folder — and OAR's native precedence (`user.json` overrides `config.json`) applies naturally at runtime. The tool's precedence model (§5.3) mirrors this: when reading an effective priority, the tool itself checks Overwrite before checking the source `user.json`, so it sees its own writes immediately without waiting for a re-scan.

**Round-trip preservation.** The tool reads the full source `config.json` (or existing override), modifies only the `priority` field, and writes the complete structure back. All other fields — name, description, conditions, overrideAnimationsFolder, etc. — round-trip untouched. This is the `raw_dict` pattern from attempt 2 and is a hard correctness requirement: any field loss is a bug.

### 8.2 Clear Overrides

A `Clear Overrides` button at the top bar (per-mod scope via the tree) deletes the Overwrite-layer `user.json` files, reverting to whatever is in the source mod (either a `user.json` written by OAR's in-game UI, or the original `config.json`). The tool never writes to or deletes from source mod paths.

### 8.3 Tool config

Stored at `<MO2 instance root>/oar-priority-manager/config.json`. One config per MO2 instance. Created on first run with defaults. Contents include:

- `relative_or_absolute`: "relative" | "absolute" (priority display toggle state)
- `submod_sort`: "priority" | "name"
- `window_geometry`: serialized Qt geometry
- `splitter_positions`: for the tree/details divider and the three-pane splitter
- `filter_history`: recent filter expressions
- `last_selected_path`: tree path of the last selected node

The tool detects the MO2 instance root by walking up from the running mods directory, or by reading `ModOrganizer.ini` which lives at the instance root.

## 9. Error handling

**Strategy: load with warnings.** Parse errors and other file-level problems do not abort the scan. Problem submods appear in the tree with a `⚠` icon and are loaded into the model with non-empty `warnings: list[str]`. Edits are blocked on warning items. A `Scan issues (N)` button at the top bar opens a log pane with full details per problem: file path, error type, line number (when available).

**What counts as a warning:**

- Malformed JSON that lenient parsing cannot repair
- Missing required fields (`priority`, `name`)
- `priority` field not an integer
- Circular or invalid `overrideAnimationsFolder` redirection
- Unreadable file (permission denied, path too long)
- `config.json` absent from a submod-looking folder

**What is a hard error (modal + abort):**

- MO2 instance root cannot be detected
- `mods/` directory does not exist or is unreadable
- Tool config file exists but is corrupt and cannot be repaired (tool offers to reset)

## 10. Technology stack

- **Language:** Python 3.11+
- **GUI framework:** PySide6 (LGPL, Qt's official Python binding)
- **Packaging:** Nuitka — transpiles Python to C, compiles to a native Windows executable. Avoids the PyInstaller false-positive problem on AV scanners (including Nexus's upload scan).
- **Qt modules included:** `QtCore`, `QtGui`, `QtWidgets` only.
- **Qt modules explicitly excluded** via Nuitka flags: `QtWebEngine`, `QtWebEngineWidgets`, `QtMultimedia`, `QtQuick`, `QtQml`, `QtQuick3D`, `QtNetwork`, `QtSql`, `QtPrintSupport`, `QtCharts`, `QtDataVisualization`, `QtBluetooth`, `QtPositioning`, `QtLocation`, `QtSensors`, `QtSerialPort`, `QtXml`, `QtConcurrent`, `QtOpenGL`, `QtTest`, and all other optional modules.
- **Target distribution size:** ~50-60 MB (Qt bulk + Python runtime + bindings).
- **Deployment:** Standalone Windows binary distributed as a zip. User unzips into their MO2 tools directory, adds the `.exe` to MO2 Executables, and runs it from within MO2 so VFS is active.
- **Platform target:** Windows only.

## 11. Testing

### 11.1 Approach

- **Unit tests** using `pytest`. Target: 100% coverage of `core/` modules.
- **Fixture-based tests.** `tests/fixtures/mods/` contains 5-10 fake OAR mods with known-good, malformed, and edge-case `config.json` files. Scanner, parser, and anim_scanner tests run against this directory as if it were a real MO2 mods folder.
- **Golden-file round-trip tests for the serializer.** For each fixture config, load → modify priority → serialize → re-load → diff. Any field loss between the original and re-loaded dict fails the test.
- **UI smoke tests** via `pytest-qt`. Scope: construct the main window, load fixtures, click a small set of interactions (expand section, toggle Relative/Absolute, open Advanced filter, select tree item), verify no crashes or exceptions. Not full visual regression.
- **TDD is mandatory for the core engine.** Every function in `priority_resolver.py`, `filter_engine.py`, and `override_manager.py` is written test-first. TDD is best-effort for UI modules.
- **No end-to-end Skyrim launch tests.** Out of scope; too expensive for the payoff.

### 11.2 CI

- **GitHub Actions**, Windows runners only (the tool is Windows-only).
- **On push to any branch:** run full `pytest` suite (unit + smoke).
- **On push to `main` and on PR:** same as above plus lint (`ruff`) and type check (`mypy`, advisory not blocking).
- **Nuitka build only runs on release tags**, not on every push — Nuitka builds are slow (1-3 minutes) and don't add test signal.

### 11.3 Test-running discipline

Sub-agents asked to verify changes run the **full** `pytest` suite, not only the files they touched. Scoped verification misses stale contracts when a shared module's signature changes.

## 12. Build & release

- Local dev: `python -m venv venv`, `pip install -e .[dev]`, run `pytest`, run `python -m oar_priority_manager` for iterative development.
- Release build: `nuitka --standalone --windows-disable-console --enable-plugin=pyside6 --nofollow-import-to=<excluded modules> app/main.py`
- Release artifact: zipped output directory, uploaded to GitHub Releases and eventually to Nexus Mods.

## 13. Open questions to be addressed during implementation planning

These are not blocking for spec approval, but should be resolved in the implementation plan:

1. **Instance root detection fallback order.** Primary is walking up from the mods path. What's the fallback if that's ambiguous (e.g. user ran the tool from a weird working directory)?
2. **Animation filter scope when a replacer or mod is selected.** Should the center pane show every animation from every submod in scope, or only the "most interesting" ones (e.g. those where the user is losing)?
3. **Shift to Priority N — scope semantics.** When the user shifts a whole mod, is the floor applied to the minimum priority across all submods in the mod, or to each replacer independently? (The locked floor-anchored formula still needs this clarification.)
4. **Concurrent modification detection.** If the user edits `user.json` in OAR's in-game UI while the tool is running, the tool's in-memory model goes stale. Does the tool offer a Refresh button, or should it watch the filesystem?
5. **Performance target.** For a modlist with ~500 OAR mods totaling ~50,000 submods, is the scan fast enough to run on every tool launch, or does the tool need an on-disk cache?

## 14. Success criteria

- User can answer *"what priority do I need to set to win"* in under 30 seconds from tool launch.
- Zero source mod files are modified by the tool under any circumstance.
- Every field in a source `config.json` round-trips identically through the override writer — verified by golden-file tests on all fixtures.
- No `conflict_engine.py`. No semantic condition analysis. No SAT solver. No drift into the attempt-1 / attempt-2 traps.
- Nexus Mods upload scan does not flag the packaged binary (verified via a test upload before the first public release).
