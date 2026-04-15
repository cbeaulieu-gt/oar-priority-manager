# Conditions Panel — Formatted View Design

**Issues:** #43 (formatted conditions display), #44 (raw JSON toggle)
**Date:** 2026-04-12
**Status:** Approved

## Overview

Replace the current raw-JSON-only conditions panel (right pane) with a formatted
tree view that renders OAR condition structures as a human-readable AND/OR/NOT
hierarchy. A toggle switches between the formatted view (default) and raw JSON
for power users. PRESET references resolve on demand when the user clicks to
expand them.

## Current State

`conditions_panel.py` is a simple `QTextEdit` that calls
`json.dumps(submod.conditions, indent=2)`. No parsing, no formatting, no
preset awareness. The panel header shows
`"Conditions · {mo2_mod} / {submod_name}"`.

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Layout | Hybrid: formatted tree + JSON toggle | Readable for browsing, raw JSON for debugging configs |
| PRESET handling | Resolve on demand in UI | Keeps data model honest; preserves shared-preset relationships |
| Non-submod selection | Blank placeholder | YAGNI — conditions only exist on submods |
| Unknown condition types | Generic rendering | No known-types list to maintain; all conditions rendered uniformly |

## Architecture

### New module: `conditions_renderer.py`

A pure-logic module that converts a condition dict/list into a list of
`RenderedNode` dataclass instances. No Qt dependency — this is testable
without a GUI.

```
RenderedNode:
    text: str              # e.g. "IsSneaking"
    node_type: str         # "AND", "OR", "leaf", "preset"
    negated: bool
    params: dict[str, str] # extra JSON keys as key=value pairs
    children: list[RenderedNode]
    preset_name: str | None
```

**Public API:**

- `render_conditions(conditions: dict | list) -> list[RenderedNode]`
  Recursively walks the OAR condition tree and produces a flat/nested list of
  `RenderedNode` objects. Each node in the input maps to one `RenderedNode`:
  - `{"condition": "AND", "conditions": [...]}` → AND group with children
  - `{"condition": "OR", "conditions": [...]}` → OR group with children
  - `{"condition": "PRESET", "Preset": "name"}` → preset reference node
  - Any other `{"condition": "X", ...}` → leaf node; extra keys become `params`
  - `{"negated": true}` → sets `negated=True` on the node

- `resolve_preset(preset_name: str, presets: dict) -> list[RenderedNode] | None`
  Given a preset name and a replacer's `conditionPresets` dict, returns the
  rendered condition tree for that preset, or `None` if not found.

### Updated module: `conditions_panel.py`

The existing `ConditionsPanel` widget gains:

1. **Formatted/JSON toggle** — A `QButtonGroup` with two checkable `QPushButton`s
   in the header area, matching the segmented toggle pattern used in `tree_panel.py`
   (issue #45) and `stacks_panel.py` (issue #69). "Formatted" is checked by default.

2. **Formatted view** — A `QTreeWidget` (or `QScrollArea` with nested `QWidget`s)
   that renders the `RenderedNode` tree with:
   - AND groups: blue "ALL of:" label, children indented
   - OR groups: purple "ANY of:" label, children indented with left border line
   - Leaf conditions: green ✓ icon + name (or red ✗ + strikethrough + NOT badge
     if negated)
   - Parameters: muted key=value text below the condition name
   - PRESET references: amber ⚙ card with preset name, click to expand/collapse
   - Stats footer: condition count, type count, negated count, preset count

3. **JSON view** — The existing `QTextEdit` with `json.dumps(indent=2)`, preserved
   as-is.

4. **Placeholder state** — When no submod is selected (mod/replacer/root node),
   shows "Select a submod to view conditions."

### Data flow for PRESET resolution

1. Scanner already reads replacer-level `config.json` files. We need to store
   `conditionPresets` from these configs on a model accessible to the UI.
2. The `TreeNode` for a REPLACER already exists in `tree_model.py`. Add an
   optional `presets: dict` field to `TreeNode` (or to a new lightweight model)
   populated during `build_tree()` from the replacer's `config.json`.
3. When the user expands a PRESET card, the panel walks up to the parent
   REPLACER `TreeNode`, reads its `presets` dict, and calls
   `resolve_preset(name, presets)` to get the rendered subtree.
4. If the preset name is not found in the replacer's presets, show an inline
   warning: "Preset 'X' not found in replacer config."

### Scanner changes

The scanner (`scanner.py`) already reads replacer-level `config.json` for other
purposes. It needs to:

1. Extract `conditionPresets` from the replacer config dict.
2. Store them somewhere accessible — either on a new `Replacer` model, or as a
   dict keyed by replacer path that the UI can look up.

The minimal approach: add a `condition_presets: dict` field to the existing data
flow. The `build_tree()` function in `tree_model.py` already groups submods by
replacer — it can attach preset data to the REPLACER-level `TreeNode`.

## Rendering Rules

| Input | Rendered as |
|---|---|
| `{"condition": "AND", "conditions": [...]}` | Blue "ALL of:" label, children indented |
| `{"condition": "OR", "conditions": [...]}` | Purple "ANY of:" label, children indented, left border line |
| `{"condition": "X", "negated": false, ...}` | Green ✓ + condition name, extra keys as muted params |
| `{"condition": "X", "negated": true, ...}` | Red ✗ + strikethrough name + NOT badge, extra keys as muted params |
| `{"condition": "PRESET", "Preset": "name"}` | Amber ⚙ PRESET card with name, click to expand |
| Top-level list `[...]` | Treated as implicit AND group |
| Top-level dict `{"conditions": [...]}` | Treated as AND group (or whatever `type`/`condition` key says) |
| Empty conditions | "No conditions defined" placeholder |

### Parameter display

Every key in a condition dict other than `condition`, `negated`, `conditions`,
and `Preset` is treated as a parameter. Parameters are displayed as muted
`key = "value"` pairs on a line below the condition name, joined by ` · `.

### Stats footer

Below the rendered tree, a muted line shows:
`{n} conditions · {t} types · {neg} negated · {p} presets`

Preset count only shown when > 0.

## What this does NOT include

- Condition editing (read-only display only)
- Condition validation or type-specific rendering
- Aggregate condition views for mod/replacer selection
- Advanced condition filter builder (issues #49/#50 — separate design)

## Files to create or modify

| File | Action |
|---|---|
| `src/oar_priority_manager/ui/conditions_renderer.py` | **Create** — pure-logic renderer |
| `src/oar_priority_manager/ui/conditions_panel.py` | **Modify** — add toggle, formatted view, preset expansion |
| `src/oar_priority_manager/core/scanner.py` | **Modify** — extract conditionPresets from replacer configs |
| `src/oar_priority_manager/ui/tree_model.py` | **Modify** — attach presets to REPLACER TreeNodes |
| `tests/unit/test_conditions_renderer.py` | **Create** — unit tests for render_conditions and resolve_preset |
| `tests/unit/test_conditions_panel.py` | **Create** — widget tests for toggle, formatted view, preset expand |
