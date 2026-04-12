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

### 3.3 Architectural enforcement of non-goals

Stated non-goals did not prevent scope creep in attempts 1 and 2. This attempt includes structural guardrails:

- **Serializer allowlist.** `core/serializer.py` maintains an explicit allowlist of mutable fields: `["priority"]`. Before writing a `raw_dict`, the serializer compares it against the original read and raises an exception if any field outside the allowlist has been modified. This makes condition editing, disable toggling, or any other non-priority mutation a code-breaking action — not just a social norm.
- **Condition tree is opaque for mutation purposes.** The `conditions` field on `SubMod` is read-only at the type level. No module in the codebase should accept a `SubMod` and return a modified condition tree. The filter engine reads the tree; the conditions panel displays it; nothing writes to it.
- **No `conflict_engine.py`.** This filename is explicitly banned. If a module with this name (or equivalent semantic-analysis responsibilities) appears in the codebase, it is a scope violation to be reverted, not a feature to be reviewed.

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
    override_is_ours: bool   # True if Overwrite user.json has _oarPriorityManager metadata
    raw_dict: dict           # Complete round-trip-preserved config contents
    animations: list[str]    # Lowercased .hkx filenames (from anim_scanner)
    conditions: dict         # Full condition tree (read-only; for filter + display)
    condition_types_present: set[str]   # All condition type names appearing anywhere in the tree
    condition_types_negated: set[str]   # Condition type names appearing inside NOT groups or with negated=true
    warnings: list[str]      # Parse/validation warnings; non-empty blocks edits
```

**Note on `condition_types_present` vs `condition_types_negated`:** A condition type can appear in both sets simultaneously (e.g. `IsFemale` required at the top level AND `IsFemale` negated inside a sub-group). The filter engine uses these two sets independently — see §6.2 and §7.6 for precise semantics.

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

**`core/serializer.py`** — Writes a `raw_dict` back to disk as JSON, preserving field order. Enforces a **mutable-field allowlist**: before writing, the serializer diffs the output `raw_dict` against the original read and raises `IllegalMutationError` if any field outside `["priority"]` has been modified. This is the architectural guardrail described in §3.3 — it makes non-priority mutations a hard failure, not a silent corruption. The serializer also injects a `_oarPriorityManager` metadata object (tool version + write timestamp) into every `user.json` it writes, used for override provenance detection (§8.1).

**`core/override_manager.py`** — Computes the mirrored path in MO2 Overwrite for a given submod, creates parent directories, writes via `serializer.py`, and exposes a `clear_override()` operation. Never writes to source mod paths.

**`core/priority_resolver.py`** *(new)* — Takes the conflict map from `anim_scanner` and produces an ordered `PriorityStack` per animation. Also exposes the three mutation operations:

- `move_to_top(target, scope)` — scope is submod / replacer / mod.
  - **Submod scope:** sets `priority = max(competitor_priorities_across_all_stacks) + 1`. Simple: one submod, one new value.
  - **Replacer / mod scope:** preserves relative ordering among the in-scope submods. Algorithm: find `global_max` = the highest competitor priority across all stacks that any in-scope submod participates in. Then apply a floor-anchored shift: `new_priority = (global_max + 1) + (old_priority - min(old_priorities_in_scope))`. This ensures every in-scope submod is above all external competitors, while their internal priority gaps are preserved. The user's internal ordering stays intact.
  - **Overflow guard:** if any computed priority would exceed `INT32_MAX`, the operation fails with a user-visible error and no write is performed.
- `set_exact(submod, priority)` — submod-level only. Sets the priority to the exact value the user enters.
- `shift(scope, floor_priority)` — scope is replacer or mod. For the set of submods in scope, `new_priority = floor_priority + (old_priority - min(old_priorities_in_scope))`. The floor is computed from the minimum priority across all submods in the scope (per-mod minimum, not per-replacer). This preserves relative gaps between submods while anchoring the lowest to the user's specified floor.

**`core/filter_engine.py`** *(new)* — Structural condition-presence filter. Walks each submod's condition tree once to produce two sets per submod: `condition_types_present` (every condition type name that appears anywhere in the tree) and `condition_types_negated` (types appearing inside NOT groups or with `negated: true`). A type can appear in both sets simultaneously.

Filter query semantics are intentionally simple and documented to the user:

- `has IsFemale` → matches if `IsFemale` ∈ `condition_types_present`. This means *"the submod mentions IsFemale somewhere in its condition tree"* — it does **not** mean *"the submod applies to females."* A submod that excludes females (`IsFemale` inside a NOT group) also matches this filter.
- `hasn't IsFemale` → matches if `IsFemale` ∉ `condition_types_present`. This means *"the submod never mentions IsFemale."*
- The filter is structural presence-matching, not semantic evaluation. The UI text bar and Advanced builder both display a help tooltip: *"Filters match submods that mention a condition type, regardless of whether the condition is required, optional, or excluded."*

This is a deliberate trade-off. Semantic filtering ("show me submods that apply to females") would require the condition evaluator that killed attempt 2. Structural filtering is tractable, and the results are useful for the primary workflow: finding which submods are involved with a given condition type, so the user can inspect and adjust priorities manually.

**`core/tree_model.py`** *(new)* — Builds the left-tree hierarchy:

- **Level 1 (Mods):** alphabetical by OAR display name from config.json (matches OAR's UI sort order)
- **Level 2 (Replacers):** alphabetical by folder name (our addition; OAR's UI flattens this level, but the filesystem layer is useful for provenance)
- **Level 3 (Submods):** priority descending (matches OAR's UI sort order), with a user-toggleable alphabetical sort

**UI modules** — covered in §7.

**`app/config.py`** — Tool's own config (Relative/Absolute toggle state, window geometry, sort toggle state, filter history). Stored as JSON at `<MO2 instance root>/oar-priority-manager/config.json`. Instance root detection uses the chain described in §8.3.1 (`--mods-path` CLI arg → CWD check → walk-up → manual picker).

**`app/main.py`** — Entry point. Constructs the `QApplication` and `MainWindow`.

### 6.3 Data flow

```
1. Startup
   └─ Parse CLI arguments (--mods-path is the primary instance detection mechanism)
   └─ Detect MO2 instance root (see §8.3 for detection chain)
   └─ Load tool config from instance/oar-priority-manager/config.json
2. Scan phase (also triggered by Refresh button — see below)
   └─ scanner.py walks <instance>/mods/*/
   └─ For each candidate submod, parser.py reads config.json
       + Overwrite/user.json override layer
   └─ For Overwrite user.json files, check for _oarPriorityManager metadata
       to determine if the override was written by this tool (§8.1)
   └─ anim_scanner.py aggregates .hkx files across all submods
   └─ priority_resolver.py builds conflict_map and PriorityStack list
3. Model construction
   └─ tree_model.py builds the left-tree hierarchy
   └─ filter_engine.py builds condition_types_present and
       condition_types_negated sets per submod
4. UI phase
   └─ main_window.py constructs the three-pane layout
   └─ Signals wire user actions to resolver/override_manager
5. Edit flow (per action)
   └─ User triggers Move to Top / Set Exact / Shift
   └─ priority_resolver computes new priority value(s)
   └─ override_manager writes to MO2 Overwrite at mirrored path
   └─ tree/stacks refresh from in-memory state (no re-scan)
6. Refresh (user-triggered via toolbar button)
   └─ Discards in-memory model, re-runs steps 2-4
   └─ Needed after: using OAR's in-game UI, enabling/disabling mods
       in MO2, manually editing config files, or any external change
7. Shutdown
   └─ app/config.py writes tool config back to disk
```

**Consistency guarantee:** The tool takes a VFS snapshot at launch (or on Refresh). All priority computations and displays are based on this snapshot. Changes made outside the tool — in OAR's in-game UI, in MO2's mod list, or by manual file editing — are not reflected until the user clicks Refresh or relaunches. No filesystem watching is implemented. This is consistent with the modding-tool UX convention (xEdit, zEdit, and BodySlide all work this way).

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

A single filter input with an **Advanced…** button, plus a **Refresh** button (🔄) on the far right. The text input accepts simple expressions like `IsFemale AND IsInCombat`. The Advanced button opens a modal filter builder (see §7.7). Filter state applies to the left tree: matching submods are shown normally; non-matching submods are dimmed but still visible. An empty filter shows everything normally.

The Refresh button discards the in-memory model and re-scans the entire VFS (see §6.3 step 6). Use after making changes in OAR's in-game UI, enabling/disabling mods in MO2, or manually editing config files.

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

**Formatter validation requirement:** During the first implementation milestone, the formatter must be tested against real-world `config.json` files from at least 10 popular OAR mods on Nexus. If the fallback rate (trees too complex for three-bucket rendering) exceeds 30%, the formatted view should be replaced with a simple indented-tree display that doesn't attempt to classify. The three-bucket model is a hypothesis about real-world condition trees — it must be validated before committing to the UX.

### 7.6 Filter text bar (simple)

Accepts a simple boolean expression like `IsFemale AND IsInCombat AND NOT IsWearingHelmet`. Parsed by a small hand-written expression parser. Semantics:

- `IsFemale` → matches submods where `IsFemale` ∈ `condition_types_present`
- `NOT IsWearingHelmet` → matches submods where `IsWearingHelmet` ∉ `condition_types_present`
- `AND` combines terms: all must match

No parentheses support in the text bar — users who want grouping use Advanced… (or accept that the filter is a flat check).

**User-visible help text** (displayed as a tooltip on the filter bar): *"Filters match submods that mention a condition type anywhere in their condition tree, regardless of whether the condition is required, optional, or negated. For example, 'IsFemale' will match both submods that require females and submods that exclude females."*

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

### 8.1.1 Override provenance detection

Every `user.json` the tool writes includes a `_oarPriorityManager` metadata object:

```json
{
  "priority": 500,
  "name": "heavy",
  "_oarPriorityManager": {
    "toolVersion": "1.0.0",
    "writtenAt": "2026-04-11T14:30:00Z",
    "previousPriority": 300
  }
}
```

On scan, the tool uses this metadata to distinguish its own overrides from third-party `user.json` files in Overwrite:

- **Overwrite `user.json` with `_oarPriorityManager` metadata** → tool-written override. Shown as "OVERRIDDEN" in the details panel with the "was X" annotation derived from `previousPriority`.
- **Overwrite `user.json` without metadata** → third-party override (written by OAR's in-game UI, another tool, or manual edit). Shown with a `⚠ EXTERNAL OVERRIDE` badge in the details panel. The tool can still read the priority from this file but warns the user that it didn't write it.
- **Source-mod `user.json` with tool metadata** → the user copied an Overwrite file back into the source mod. Treated as a normal source-level override; metadata is ignored outside Overwrite.

This prevents the silent-override problem identified in review: if the user changes a priority in OAR's in-game UI after the tool wrote an override, the Overwrite version still wins at runtime — but the tool now surfaces this divergence via the EXTERNAL OVERRIDE badge, prompting the user to either clear the tool's override or re-apply it.

### 8.1.2 Round-trip preservation

The tool reads the full source `config.json` (or existing override), modifies only the `priority` field (and adds/updates the `_oarPriorityManager` metadata), and writes the complete structure back. All other fields — name, description, conditions, overrideAnimationsFolder, etc. — round-trip untouched. The serializer's mutable-field allowlist (§3.3, §6.2) enforces this at the code level.

**Round-trip precision:** round-trip means **semantically equivalent JSON**, not byte-identical output. Acceptable mutations on write:

- Whitespace and indentation may change (the tool always writes with consistent 2-space indentation)
- Trailing commas are removed (the lenient parser strips them on read; they are not restored on write)
- Key ordering within objects is preserved (Python 3.7+ dicts are insertion-ordered; `json.dumps` with `sort_keys=False`)
- Numeric precision is preserved (integers stay integers; floats keep their precision)
- No keys are added, removed, or renamed — except `_oarPriorityManager` which is the tool's own metadata
- No values are modified — except `priority` which is the tool's designated mutable field

**Unacceptable mutations (test failures):**

- Any key present in the original that is absent in the output
- Any value that differs from the original (except `priority` and `_oarPriorityManager`)
- Structural changes (array reordering, object nesting changes)

This is the `raw_dict` pattern from attempt 2 and is a hard correctness requirement.

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

### 8.3.1 MO2 instance root detection

The tool must know the MO2 instance root to find `mods/`, `overwrite/`, and to store its own config. Detection uses a strict fallback chain:

1. **`--mods-path <path>` CLI argument** *(primary, recommended)*. MO2 Executables support passing arguments to tools. The user configures the executable entry with `--mods-path "%BASE_DIR%/mods"` (MO2 expands `%BASE_DIR%` to the instance root). This is deterministic, portable-mode-safe, and documented in the tool's README as the recommended setup. The instance root is inferred as the parent of the mods path.

2. **CWD contains `ModOrganizer.ini`** *(fallback for portable MO2)*. If `--mods-path` is not provided, check if the current working directory (set by MO2 when launching executables) contains `ModOrganizer.ini`. If so, CWD is the instance root.

3. **Walk up from CWD looking for `mods/` + `ModOrganizer.ini`** *(fallback for nested tool directories)*. Check each parent directory of CWD for the presence of both `mods/` and `ModOrganizer.ini`. Stop at the drive root.

4. **Hard error.** If none of the above succeed, show a modal dialog: *"Could not detect MO2 instance. Please configure the executable with --mods-path or run the tool from within your MO2 instance directory."* The dialog includes a directory picker as a last-resort manual override. The chosen path is saved to a global (non-instance) config at `%APPDATA%/oar-priority-manager/last-instance.json` so the user doesn't have to pick again.

This chain handles both MO2 portable mode (instance root = MO2 folder) and MO2 installed mode (instance root = `%LOCALAPPDATA%/ModOrganizer/<name>/`). The `--mods-path` argument sidesteps all ambiguity and is the only method documented in the setup instructions.

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
- **Fixture-based tests.** `tests/fixtures/mods/` contains two categories of fixtures:
  - **Synthetic fixtures** (5-10 fake OAR mods): known-good, malformed, and edge-case `config.json` files covering every warning path in the parser. Created by the developer.
  - **Real-world fixtures** (10+ files): `config.json` files harvested from popular OAR mods on Nexus (with mod author attribution in the fixture directory's README). These cover undocumented fields, non-standard formatting, large condition trees, and fields added by newer OAR versions that the developer has never seen. Scanner, parser, and anim_scanner tests run against both categories.
- **Golden-file round-trip tests for the serializer.** For each fixture config (synthetic and real-world), load → modify priority → serialize → re-load → diff. The diff checks the precision rules defined in §8.1.2: no key loss, no value changes except `priority` and `_oarPriorityManager`, no structural changes. Any violation fails the test.
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

Items 1, 3, and 4 from the original list have been resolved in the spec (see §8.3.1, §6.2, and §6.3 respectively). Remaining items:

1. **Animation filter scope when a replacer or mod is selected.** Should the center pane show every animation from every submod in scope, or only the "most interesting" ones (e.g. those where the user is losing)?
2. **Performance target.** For a modlist with ~500 OAR mods totaling ~50,000 submods, is the scan fast enough to run on every tool launch, or does the tool need an on-disk cache? Profile against a real large modlist during the first implementation milestone. If scan exceeds 10 seconds, add a progress bar + background thread with progressive UI population. The architecture supports this (scan is sequential; UI construction can start on partial data).
3. **VFS file shadowing.** If two MO2 mods provide the same `.hkx` file at the exact same relative OAR submod path, MO2 mod order determines which is visible to OAR. The tool does not resolve VFS shadows — it treats all discovered animation files as real competitors. This is a **known limitation** for the rare edge case where two mods use identical replacer and submod folder names. In practice, OAR submod paths are unique per mod author, so false competitors from VFS shadowing are extremely uncommon. If a user reports this edge case, the fix is to add MO2 load-order awareness to the anim_scanner, but this is not MVP scope.
4. **Condition formatter fallback rate.** The three-bucket formatted view (§7.5) must be validated against real-world condition trees during the first milestone. If the fallback rate exceeds 30%, replace with a simpler indented-tree display.

## 14. Success criteria

- User can answer *"what priority do I need to set to win"* in under 30 seconds from tool launch.
- Zero source mod files are modified by the tool under any circumstance.
- Every field in a source `config.json` round-trips per the precision rules in §8.1.2 — verified by golden-file tests on all fixtures (synthetic and real-world).
- Serializer allowlist (§3.3) rejects any attempt to mutate a non-priority field — verified by a dedicated test that modifies `conditions` in a `raw_dict` and asserts `IllegalMutationError`.
- Override provenance: tool-written `user.json` files are distinguishable from third-party writes via `_oarPriorityManager` metadata — verified by round-trip tests.
- No `conflict_engine.py`. No semantic condition analysis. No SAT solver. No drift into the attempt-1 / attempt-2 traps.
- Nexus Mods upload scan does not flag the packaged binary (verified via a test upload before the first public release).
