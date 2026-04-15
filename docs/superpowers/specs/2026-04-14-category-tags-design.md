# Category Tags for Mods/Submods — Design Spec

**Issue:** #73
**Date:** 2026-04-14
**Milestone:** Alpha 2

## Overview

Add auto-detected category tags (colored pills) to mods and submods in the tree panel, enabling quick visual identification of what each mod does. Tags are computed from animation filenames, condition types, and folder/mod name keywords, with manual override support. Tags also integrate into search and will serve as a filter dimension for the future advanced filter builder (#49/#50).

## Tag Taxonomy

10 categories derived from OAR's ~110 condition types and validated against 3,086 real config files across 64 installed mods:

| Tag | Sort Order | Colors (bg / fg / border) |
|---|---|---|
| NSFW | 0 | `#5c2d4a` / `#f0a0d0` / `#8b446e` |
| Combat | 1 | `#5c2d2d` / `#f0a0a0` / `#8b4444` |
| Equipment | 2 | `#3d3d3d` / `#b0b0b0` / `#5a5a5a` |
| Furniture | 3 | `#5c4a2d` / `#f0d0a0` / `#8b6e44` |
| Gender | 4 | `#5c5c2d` / `#f0f0a0` / `#8b8b44` |
| Idle | 5 | `#2d5c4a` / `#a0f0d0` / `#448b6e` |
| Magic | 6 | `#4a2d5c` / `#d0a0f0` / `#6e448b` |
| Movement | 7 | `#2d3a5c` / `#a0b8f0` / `#44578b` |
| NPC | 8 | `#2d4a5c` / `#a0d0f0` / `#446e8b` |
| Sneak | 9 | `#3d2d5c` / `#b8a0f0` / `#5b448b` |

Visual style: muted/subtle pills with dark backgrounds, tinted text, and 1px borders. Designed to blend into the dark theme without competing with mod names.

## Data Model

### TagCategory Enum

New enum in `core/tag_engine.py` with 10 values. Each member carries metadata:
- `label`: display name (e.g. "Combat")
- `color_bg`, `color_fg`, `color_border`: muted palette B hex colors
- `sort_order`: integer controlling pill display order (NSFW first, then alphabetical)

### SubMod Extension

`core/models.py` — add field:
- `tags: set[TagCategory]` (default: empty set) — populated by the tag engine during scan

### AppConfig Extension

`app/config.py` — add field:
- `tag_overrides: dict[str, list[str]]` — keyed by submod unique path (`"ModName/ReplacerName/SubModName"`), values are tag name strings. Overrides completely replace auto-detected tags for that submod. Persisted in the existing `config.json`.

Example in config.json:
```json
{
  "tag_overrides": {
    "Ashes of War - NPC's/ReplacerName/SubModName": ["combat", "npc"],
    "Dynamic Feminine Female Modesty Animations OAR/KP_nudeNPC/npc_both_fre": ["nsfw", "gender", "sneak"]
  }
}
```

### Mod-Level Rollup

Not stored. Computed on-the-fly by the tree model as the deduplicated union of all child submod tags. Avoids stale data when submods change.

## Tag Engine (`core/tag_engine.py`)

### Public API

`compute_tags(submod: SubMod) -> set[TagCategory]` — pure function, no side effects.

### Rule Pipeline

Rules run in priority order. Each layer can add tags (they accumulate, not replace).

#### Layer 1 — Folder/Mod Name Keywords (highest confidence)

Scan `submod.mo2_mod`, `submod.replacer`, `submod.name` for whole-word keyword matches:

| Tag | Keywords |
|---|---|
| NSFW | `nude`, `modesty`, `nsfw`, `adult`, `sexlab`, `ostim`, `pregnancy`, `inflation`, `flower girl`, `billyy`, `leito` |
| Gender | `female`, `male` (whole word match only) |
| NPC | `npc`, `children`, `child`, `cart driver` |
| Sneak | `sneak` |
| Combat | `combat`, `stagger`, `block`, `dodge`, `ashes of war`, `boss fight` |
| Movement | `traversal`, `clamber`, `swimming`, `jump` |

#### Layer 2 — Animation Filename Patterns (primary behavioral signal)

Classify each animation filename by prefix/pattern, then vote by category:

| Tag | Animation patterns |
|---|---|
| Combat | `*_attack*`, `*_block*`, `*_stagger*`, `*_recoil*`, `*_power*` |
| Movement | `*_run*`, `*_walk*`, `*_sprint*`, `*_swim*`, `*_jump*` |
| Sneak | `*sneak*` |
| Idle | `*_idle*`, `mt_idle*` |
| Furniture | `*_sit*`, `*_chair*`, `*_bed*`, `*_lean*` |
| Equipment | `*_equip*`, `*_sheathe*`, `*_draw*`, `*_unequip*` |
| Magic | `*_cast*`, `mlh_*`, `mrh_*` |

**Voting threshold:** A tag is applied only if >=30% of a submod's animations match that category. This prevents a single stray animation from mis-tagging a submod.

#### Layer 3 — Condition Types (secondary refinement)

Only fires for tags NOT already assigned by layers 1-2. Uses `submod.condition_types_present` with a precondition filter:

**Precondition filter heuristic:** If a submod has <=3 unique condition types, they're likely definitional (the purpose of the mod). If it has 8+, conditions are likely preconditions and only very distinctive ones count.

Distinctive conditions (always count regardless of total):
- `IsSneaking` → Sneak
- `IsFemale` (without negation) → Gender
- `IsChild` → NPC
- `IsOnMount` → Movement

Non-distinctive conditions (only count if <=3 total condition types):
- `IsEquippedType` → Equipment
- `IsWornInSlotHasKeyword` → Equipment
- `IsInCombat`, `IsCombatState` → Combat
- `IsAttacking`, `IsBlocking` → Combat
- `IsRunning`, `IsSprinting` → Movement
- `HasMagicEffect`, `HasSpell` → Magic
- `IsActorBase` (non-player), `IsRace`, `IsClass`, `IsVoiceType` → NPC
- `SitSleepState`, `CurrentFurniture*` → Furniture

#### Layer 4 — Fallback

If no tags assigned after all layers, the submod gets an empty set. No "Untagged" category — the absence of pills is signal enough.

**Ignored conditions:** Non-standard plugin conditions (`IED_*`, `SDS_*`) and structural types (`AND`, `OR`, `PRESET`) are excluded from tag computation.

## UI — Tree Panel Display

### Pill Rendering

Each tag rendered as a `QLabel`-style element with rich text, using palette B colors. Styled as inline pills with rounded corners (`border-radius: 10px`, `padding: 2px 8px`, `font-size: 11px`, `font-weight: 600`).

### Custom Item Delegate

A `QStyledItemDelegate` subclass paints pills inline after the display name. This avoids embedding QWidget instances in every tree row (which is slow with 3,000+ items) while keeping rendering fast.

### Mod-Level Rows (Collapsed)

Show deduplicated union of all child submod tags. Pills sorted by `TagCategory.sort_order`. Max 4 pills displayed — if more exist, show `+N` overflow indicator.

### Submod-Level Rows (Expanded)

Show that submod's own tags. No overflow limit (submods rarely have more than 2-3 tags).

### Override Indicator

If a submod/mod has user-overridden tags (from `AppConfig.tag_overrides`), display a small pencil icon next to the pills to indicate these are not auto-detected.

## UI — Manual Tag Editing

### Right-Click Context Menu

Add "Edit Tags..." action to the existing tree context menu (both mod and submod rows). Opens a dialog with:
- 10 checkboxes (one per `TagCategory`), each with the colored pill preview next to the label
- "Reset to Auto" button — clears the override, reverts to auto-detected tags
- OK / Cancel buttons

**Mod-level editing:** Edits a mod-level override in `AppConfig.tag_overrides` (keyed by mod path). Only affects rolled-up display; individual submod auto-tags unchanged.

**Submod-level editing:** Edits the submod's override directly.

### Details Panel

When a mod or submod is selected, the details panel shows a "Tags" section:
- Current tags as colored pills
- A `+` button that opens the same edit dialog
- Pencil icon for overridden tags (same as tree panel)

### Persistence

Overrides saved to `AppConfig.tag_overrides` immediately on OK. They survive rescans — auto-detected tags regenerate on scan, but overrides take priority.

## Filter Integration

### Immediate (this feature)

Extend `SearchIndex.search()` to match against tag names. Typing "combat" in the search bar matches submods tagged Combat, even if "combat" doesn't appear in their name or animations.

### Deferred (to #49/#50)

The advanced filter builder's three-bucket UI would include tags as a filter dimension alongside condition types and animation names. `TagCategory` enum is designed to plug in — each tag is typed and enumerable. Out of scope for this issue.

### Not included

No tree-level tag filtering toggle (e.g. "show only Combat mods") in the toolbar. Natural follow-up but adds scope beyond #73.

## Testing

### Unit Tests (`tests/unit/test_tag_engine.py`)

- One test per tag category verifying detection rules fire correctly
- Precondition filter: submod with `IsEquippedType` + 8 other conditions → NOT Equipment; submod with only `IsEquippedType` + `*_equip*` animations → Equipment
- Voting threshold: 10 combat animations + 1 idle animation → Combat only, not Idle
- Multi-tag: `IsFemale` + `IsSneaking` + sneak animations → Gender + Sneak
- Manual override: overrides replace auto-detected tags; "Reset to Auto" clears override
- Edge cases: empty conditions, empty animations, no matches → empty tag set
- Non-standard conditions (`IED_*`, `SDS_*`, `PRESET`) → ignored

### Integration Tests

- End-to-end: scan fixture submod → compute tags → verify correct tags
- AppConfig round-trip: save tag overrides → reload config → overrides preserved
- Search integration: tag names searchable via search bar

### No UI Tests

Tree delegate and edit dialog are thin wrappers over the tag engine. Engine tests cover the logic; UI testing is manual.

## Files Changed

| File | Change |
|---|---|
| `core/tag_engine.py` | **New** — TagCategory enum, compute_tags(), rule pipeline |
| `core/models.py` | Add `tags: set[TagCategory]` field to SubMod |
| `app/config.py` | Add `tag_overrides: dict[str, list[str]]` to AppConfig |
| `ui/tree_model.py` | Add tag pill rendering via custom delegate, mod-level rollup |
| `ui/tree_panel.py` | Wire delegate, add "Edit Tags..." context menu action |
| `ui/details_panel.py` | Add Tags section with pills and `+` button |
| `ui/tag_edit_dialog.py` | **New** — checkbox dialog for manual tag editing |
| `core/search_index.py` | Extend search to match tag names |
| `tests/unit/test_tag_engine.py` | **New** — tag engine unit tests |
| `tests/integration/test_tag_integration.py` | **New** — end-to-end and config round-trip tests |
