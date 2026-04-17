# Spec Compliance Audit — OAR Priority Manager

**Date:** 2026-04-12
**Spec:** `docs/superpowers/specs/2026-04-11-oar-priority-manager-design.md`
**Code:** `src/oar_priority_manager/` on branch `main` at commit `9a96e0e`

---

## §5 — Core Data Model

### §5.2 SubMod fields

| Spec field | Code (`models.py`) | Status |
|---|---|---|
| `mo2_mod: str` | ✅ Present | ✅ |
| `replacer: str` | ✅ Present | ✅ |
| `name: str` | ✅ Present | ✅ |
| `description: str` | ✅ Present | ✅ |
| `priority: int` | ✅ Present | ✅ |
| `source_priority: int` | ✅ Present | ✅ |
| `disabled: bool` | ✅ Present | ✅ |
| `config_path: Path` | ✅ Present | ✅ |
| `override_source: Enum` | ✅ Present (OverrideSource) | ✅ |
| `override_is_ours: bool` | ✅ Present | ✅ |
| `raw_dict: dict` | ✅ Present | ✅ |
| `animations: list[str]` | ✅ Present | ✅ |
| `conditions: dict` | ✅ Present | ✅ |
| `condition_types_present: set[str]` | ✅ Present | ✅ |
| `condition_types_negated: set[str]` | ✅ Present | ✅ |
| `warnings: list[str]` | ✅ Present | ✅ |

---

## §7 — User Interface

### §7.1 Layout (Three-pane)

- ✅ Three-pane horizontal splitter with left column vertically split
- ✅ Left column: tree (top) + details (bottom)
- ✅ Center pane: priority stacks
- ✅ Right pane: conditions
- ✅ Stretch factors configured (1:2:1)

### §7.2 Top Bar — Unified Search

| Requirement | Status | Detail |
|---|---|---|
| Search input with placeholder text | ✅ | "Search mods, submods, animations..." |
| Advanced… button | ✅ | Present, emits signal |
| Refresh button (🔄) | ✅ | Present, wired to `_on_refresh` |
| **Name search filters/highlights tree** | ❌ MISSING | `search_changed` signal exists but is **never connected** to anything in `main_window.py`. Typing in the search bar does nothing. |
| **Fuzzy match against mod names, submod names, replacer names, animation filenames** | ❌ MISSING | `SearchIndex` class exists in `tree_model.py` but is **never instantiated** anywhere in the UI. |
| **Non-matching nodes dimmed** | ❌ MISSING | No tree filtering/dimming logic exists. |
| **Animation filename matches highlight every submod** | ❌ MISSING | No animation-to-submod resolution in UI. |
| **Condition filter mode** (detects AND/OR/NOT keywords) | ❌ MISSING | No mode switching logic in search bar. |
| **Keyboard focus on launch** | ❌ MISSING | No `setFocus()` call on the search input at startup. |
| **Ctrl+F focuses search** | ✅ | Shortcut wired in `main_window.py`. |

### §7.3 Left Column — Tree + Details

**Tree panel:**

| Requirement | Status | Detail |
|---|---|---|
| Three levels: Mod → Replacer → Submod | ✅ | Correct hierarchy. |
| Sort: Mod alphabetical | ✅ | `sorted(grouped.keys())` in `tree_model.py`. |
| Sort: Replacer alphabetical | ✅ | `sorted(replacer_dict.keys())`. |
| Sort: Submod priority descending | ✅ | `sorted(..., key=lambda s: s.priority, reverse=True)`. |
| **Sort toggle: Priority / Name** | ✅ | Name/Priority toolbar in `tree_panel.py` (lines 65–121). Delivered by #45 (commit `cc08deb`). |
| **Auto-expand single replacers** | ✅ | `auto_expand=single_replacer` in `tree_model.py`, `setExpanded(True)` in `tree_panel.py`. |
| Status icons: ✓ enabled, ⚠ warning, ✗ disabled | ✅ | Present in `_populate()`. |
| Selection fires signals to details/stacks/conditions | ✅ | `selection_changed` signal connected. |

**Details panel:**

| Requirement | Status | Detail |
|---|---|---|
| **Mod selected: folder name, full path, counts, override summary, disabled count** | ❌ MISSING | Mod selection shows only "Mod — select a submod for details". No counts, no path, no override summary. |
| **Replacer selected: name, parent mod, counts, priority range, override summary** | ❌ MISSING | Replacer selection shows only "Replacer — select a submod for details". No data. |
| **Submod: display name** | ✅ | Bold name shown. |
| **Submod: full path breadcrumb** | ⚠️ PARTIAL | Shows `display_path` (mo2_mod / replacer / name) not filesystem path. |
| **Submod: enabled/disabled badge** | ❌ MISSING | `disabled` field not shown in details panel. |
| **Submod: overridden badge** | ⚠️ PARTIAL | Shows "was X" but no explicit "OVERRIDDEN" badge. |
| **Submod: description from config.json** | ❌ MISSING | Not displayed. |
| **Submod: MO2 mod source** | ✅ | Shows `MO2 source: <mod>`. |
| **Submod: filesystem path** | ❌ MISSING | Not displayed. |
| **Submod: current priority with "was X"** | ✅ | Priority shown, "was X" when overridden. |
| **Submod: animation count** | ✅ | Shows "N files". |
| **Submod: condition summary ("N total · M types")** | ❌ MISSING | Not displayed. |
| **Submod: override source label** | ❌ MISSING | Should show "MO2 Overwrite" / "user.json in source" / "config.json". Not displayed. |
| **Priority always absolute in details** | ✅ | Shows raw value. |
| **EXTERNAL OVERRIDE badge** (§8.1.1) | ❌ MISSING | No badge for overwrite user.json without tool metadata. |

### §7.4 Center Pane — Priority Stacks

| Requirement | Status | Detail |
|---|---|---|
| One section per animation | ✅ | Loops over `sm.animations`. |
| **Sections expandable with ▾/▸ toggle** | ❌ MISSING | Header shows static `▾` but clicking does nothing. No collapse/expand logic. No toggle state tracking. |
| **Default expanded** | N/A (not collapsible) | |
| Section header: animation filename | ✅ | Shows `<b>{anim}</b>`. |
| Section header: competitor count | ✅ | Shows `N competitors`. |
| Section header: status (you're #1 / losing by N) | ✅ | Green "you're #1", red "losing by N · set to X to win". |
| Section header: ⚠ TIED indicator | ✅ | Shows when priorities match. |
| **"set to X to win" value** | ✅ | Shows `max(competitor_priorities) + 1`. |
| **Competitor rows: rank badge with colors** | ❌ MISSING | Shows `#1`, `#2` etc. but **no color styling**. Spec: "#1 in green, #2+ in grey, losing rows get red background". All rows are unstyled QLabels. |
| **Rank #1 in green** | ❌ MISSING | |
| **#2+ in grey** | ❌ MISSING | |
| **Losing rows red background** | ❌ MISSING | |
| **`(you)` marker** | ✅ | Bold "(you)" on selected submod's rows. |
| **Relative mode: delta column (+0, −70)** | ✅ | Shows deltas when `_relative_mode=True`. |
| **Absolute mode: right-aligned tabular-nums** | ⚠️ PARTIAL | Shows comma-separated numbers but no right-alignment, no tabular-nums font, no fixed column width. |
| **Relative column width 80px, Absolute 140px** | ❌ MISSING | No fixed widths. Plain QLabel text. |
| **Toggling hides the other column entirely** | N/A | Only one mode shown at a time (correct), but no visible toggle to switch. |
| **Toolbar: animation filter text input** | ❌ MISSING | No animation filter input exists in the stacks panel. |
| **Toolbar: [Relative \| Absolute] segmented toggle** | ❌ MISSING | `set_relative_mode()` method exists but **no UI widget to trigger it**. The toggle is invisible to the user. |
| **Toolbar: [Collapse winning] button** | ❌ MISSING | No collapse-winning button. |
| **Action: Move to Top (submod/replacer/mod scopes)** | ⚠️ PARTIAL | Only submod scope. `_on_action` hardcodes `scope="submod"`. No replacer/mod scope UI. |
| **Action: Set Exact (submod only)** | ✅ | QInputDialog with INT32 range. |
| **Action: Shift to Priority N (replacer/mod)** | ❌ MISSING | No Shift button exists. `priority_resolver.shift()` is implemented in core but not wired to UI. |
| **Action buttons disabled for warning items** | ❌ MISSING | Buttons always enabled regardless of `has_warnings`. |
| **Post-action toast ("Priority updated — you're now #1")** | ❌ MISSING | No toast/notification. Stacks refresh silently. |
| **Competitor row clickable → updates conditions panel** | ❌ MISSING | `competitor_focused` signal exists but rows are plain QLabels, not clickable. No click handler. |

### §7.5 Right Pane — Conditions Detail

| Requirement | Status | Detail |
|---|---|---|
| **Header: [Formatted \| Raw JSON] toggle** | ❌ MISSING | No toggle. Only raw JSON shown. |
| **Header: owner label (mod/submod of focused competitor)** | ⚠️ PARTIAL | Shows `Conditions · {mo2_mod} / {name}` but only for the selected submod, not for a focused competitor (competitors aren't clickable). |
| **Formatted view: REQUIRED / ONE OF / EXCLUDED buckets** | ❌ MISSING | Not implemented. Only `json.dumps(submod.conditions, indent=2)`. |
| **Formatted view: complex nesting fallback note** | ❌ MISSING | |
| **Raw JSON view** | ✅ | Pretty-printed JSON in read-only QTextEdit. |
| **Conditions update when competitor row focused** | ❌ MISSING | Only updates on tree selection, not on competitor row click (rows aren't clickable). |

### §7.6 Condition Filter Mode

| Requirement | Status | Detail |
|---|---|---|
| Detect AND/OR/NOT keywords in search | ❌ MISSING | No detection logic in search_bar.py. |
| Condition filter query parsing + matching | ✅ | `filter_engine.py` has `parse_filter_query()` and `match_filter()` — fully implemented in core, not wired to UI. |
| Help tooltip when condition mode activates | ❌ MISSING | |

### §7.7 Advanced Filter Builder

| Requirement | Status | Detail |
|---|---|---|
| Modal dialog with three pill buckets | ✅ | `FilterBuilder` composes three `BucketWidget`s (Required / Any Of / Excluded) with Apply, Clear, Cancel buttons. |
| REQUIRED (green) / ANY OF (yellow) / EXCLUDED (red) | ✅ | `PillWidget` + `BucketWidget` implemented; dialog wired to `MainWindow._apply_advanced_filter` via `filter_applied` signal. |
| Autocompleting condition type dropdown | ✅ | `BucketWidget` uses `QLineEdit` + `QCompleter` (case-insensitive, contains-match) sourced from `collect_known_condition_types`. |

### §7.8 Warning Indicators

| Requirement | Status | Detail |
|---|---|---|
| ⚠ icon in tree | ✅ | Present in `tree_panel._populate()`. |
| **Clicking warning item shows errors in details** | ✅ | Warning submods render a parse-error-only view in the details panel showing name, path, WARNING banner, and per-warning bullets. Delivered by #51. |
| **Action buttons disabled for warning items** | ❌ MISSING | |
| **Scan issues (N) button in top bar** | ✅ | Button placed between Advanced and Refresh on SearchBar; label 'Scan issues (N)'; opens non-modal log pane listing every warning. Delivered by #51. |

---

## §8 — Persistence

### §8.1 OAR Overrides

- ✅ Writes to MO2 Overwrite at mirrored path
- ✅ Writes `user.json` (not `config.json`)
- ✅ Never writes to source mod paths

### §8.1.1 Override Provenance

- ✅ `_oarPriorityManager` metadata injected by serializer
- ✅ `override_is_ours` field on SubMod populated during scan
- ❌ **EXTERNAL OVERRIDE badge in UI** — not shown in details panel when overwrite user.json lacks tool metadata

### §8.2 Clear Overrides

| Requirement | Status | Detail |
|---|---|---|
| **Clear Overrides button (per-mod scope)** | ❌ MISSING | `clear_override()` exists in `override_manager.py` but no UI button anywhere triggers it. |

### §8.3 Tool Config

| Spec field | AppConfig field | Status |
|---|---|---|
| `relative_or_absolute` | ✅ Present | ⚠️ Not loaded/applied to stacks panel on startup |
| `submod_sort` | ✅ Present | ⚠️ Not loaded/applied to tree panel on startup |
| `window_geometry` | ✅ Present | ⚠️ Not restored on startup (no `restoreGeometry` call) |
| `splitter_positions` | ✅ Present | ⚠️ Not restored on startup |
| `search_history` | ✅ Present | ⚠️ Not used anywhere |
| `last_selected_path` | ✅ Present | ⚠️ Not restored on startup |

**Config is saved on shutdown** (`save_config` called after `app.exec()`), but **none of the config values are applied during UI construction** — the app always starts in default state. Config values are also never updated from UI state before saving, so the saved file is always the defaults.

### §8.3.1 Instance Root Detection

- ✅ `--mods-path` CLI argument (primary)
- ✅ CWD contains `ModOrganizer.ini` (fallback)
- ✅ Walk up from CWD (fallback)
- ✅ Hard error with descriptive message
- ✅ **Manual directory picker dialog on failure** — `instance_picker.py` presents a directory picker when detection fails. Delivered by #53 (commit `70ef236`).
- ❌ **`%APPDATA%/oar-priority-manager/last-instance.json` persistence** — not implemented.

---

## §9 — Error Handling

| Requirement | Status | Detail |
|---|---|---|
| Load with warnings (don't abort scan) | ✅ | Parser returns warnings, scanner collects them. |
| ⚠ icon on warning items | ✅ | In tree. |
| **Edits blocked on warning items** | ❌ MISSING | Action buttons don't check `has_warnings`. |
| **Scan issues (N) button** | ✅ | Non-modal ScanIssuesPane (QDialog) with 5-column table, Copy All button, and double-click-to-navigate. Delivered by #51. |
| **Modal dialog for hard errors** | ❌ MISSING | Prints to stderr and exits. |

---

## Summary — All Missing/Incomplete Items

### Tier 1 (Primary Workflow) Gaps — 11 items:

1. **Search bar not wired** — typing does nothing (`SearchIndex` never instantiated, `search_changed` signal not connected)
2. **Relative/Absolute toggle not visible** — no UI widget exists; `set_relative_mode()` is unreachable
3. **Rank badge colors** — #1 green, #2+ grey, losing red background — all unstyled plain text
4. **Expand/collapse animation sections** — `▾` is static decoration, no toggle/click logic
5. **Competitor rows not clickable** — can't focus a competitor to see its conditions
6. **Post-action toast** — no feedback after priority mutations
7. **Action buttons not disabled for warning items** — can attempt edits on broken submods
8. **Move to Top only submod scope** — replacer/mod scopes not wired to UI
9. **Details panel mostly empty** — mod/replacer show no data; submod missing disabled badge, description, filesystem path, condition summary, override source, EXTERNAL OVERRIDE badge
10. **Config not applied on startup** — relative/absolute, sort state, geometry, splitter positions all ignored; config never updated from UI state before save
11. **Clear Overrides button missing** — core `clear_override()` exists but nothing in UI calls it

### Tier 2 (Secondary Workflow) Gaps — 13 items:

12. **Formatted condition display** (REQUIRED / ONE OF / EXCLUDED three-bucket view)
13. **Formatted/Raw JSON toggle** in conditions panel header
14. ~~**Sort toggle** (Priority / Name) in tree panel~~ — ✅ delivered by #45
15. **Shift to Priority N** button — core `shift()` exists but no UI
16. **Animation filter input** in stacks toolbar
17. **Collapse-winning button** in stacks toolbar
18. ~~**Advanced filter builder** — stub only, no pill buckets~~ — ✅ delivered by #49
19. **Condition filter mode** detection in search bar
20. ~~**Scan issues (N) log pane** with file paths and error details~~ — ✅ delivered by #51
21. **EXTERNAL OVERRIDE badge** in details panel
22. ~~**Manual directory picker** dialog on detection failure~~ — ✅ delivered by #53
23. **Keyboard focus on search bar at launch**
24. ~~**Warning items show parse errors in details panel** instead of generic text~~ — ✅ delivered by #51
