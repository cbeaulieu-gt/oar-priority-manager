# ADR-0002: Defer qt-material adoption in favor of a future UI overhaul

- **Status:** Accepted
- **Date:** 2026-05-08
- **Supersedes:** [ADR-0001](0001-qt-theme-evaluation.md) (qt-theme-evaluation, recommended qt-material adoption)
- **Related issues:** #90 (umbrella, closed `not_planned`), #92, #93, #98, #99 (all closed `not_planned`)

## Context

[ADR-0001](0001-qt-theme-evaluation.md) recommended adopting qt-material as the global Qt theme, replacing the project's hand-rolled QSS. The recommendation was implemented as a phased migration:

- **Phase 0** (#94, merged to `main` via PR for #89) — qt-material library installed; theme applied at startup as a dry-run.
- **Phase 1** (#92, merged to primary `feature/090-qt-material` via PR #97) — widget-level `setStyleSheet()` calls migrated to a consolidated `custom.qss` override; object-name-targeted selectors replaced hardcoded styles.
- **Phase 1.5** (#98, merged to primary via PR #97) — per-pane background tints, splitter-handle styling, AA-contrast subtext fixes, and a regression test suite (`test_pane_styled_background.py`) for QSS-render correctness.
- **Phase 2** (#93, unstarted) — CI import guard for qt-material.

After completing Phases 0/1/1.5 and reviewing the result against a populated Nolvus Awakening modlist (4,433 submods / 648 animation stacks at 3440×1369), the decision was made to defer qt-material in favor of a single larger UI overhaul rather than continuing the phased adoption. The overhaul will be planned after the current functional-work milestones (alpha 3) land.

## Decision

1. Close issues #90, #92, #93, #98, #99 as `not_planned` (won't-do, not completed).
2. Close the "qt-material adoption" milestone.
3. Archive the primary branch `feature/090-qt-material` (tip `b1c55d5`) as `archive/qt-material-spike` for reference, then delete the working `feature/090-qt-material` ref locally and on origin.
4. Phase 0 (#94) remains on `main` since it was already merged independently — qt-material is installed but inactive at runtime.

## Consequences

### Positive

- Avoids landing a half-finished theme migration on `main` (Phases 0/1/1.5 done; Phase 2 unstarted, polish issue #99 unstarted).
- Frees the team to design the future overhaul holistically rather than incrementally on top of qt-material's structural assumptions.
- Closed-issue history reflects what *shipped to users*, not what was technically implemented but never reached `main`.

### Negative

- Approximately ten commits of working code (PR #97's merged content) is shelved. Preserved at `archive/qt-material-spike` but not actively maintained.
- Phase 0 (qt-material installed but inactive at runtime) remains on `main` as a dependency. Removing it is a separate cleanup decision (see *Open follow-ups*).

## Technical findings worth carrying forward

These are the durable lessons from the spike. The future overhaul should consult them whenever it makes a Qt-styling decision.

### 1. `WA_StyledBackground` is required for QSS `background:` to paint on `QWidget` subclasses

Without `setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)` on the widget root, Qt silently drops `background:` rules from QSS — borders still render (different drawing path) but the fill colour never appears. This is the most common reason "my QSS background doesn't show up." Documented at the call sites in `archive/qt-material-spike` (`StacksPanel`, `ConditionsPanel`, `DetailsPanel` constructors).

### 2. `QScrollArea` viewport paints `palette(base)` by default and masks the styled root

When a pane root has a styled background, an embedded `QScrollArea` will mask it with `palette(base)` gray unless the scrollarea + viewport + content widget all have `background: transparent`. The fix is QSS-only:

```qss
QWidget#StacksPanel_root QScrollArea,
QWidget#StacksPanel_root QScrollArea > QWidget,
QWidget#StacksPanel_root QScrollArea > QWidget > QWidget {
    background: transparent;
    border: none;
}
```

Symptom: pane tints visible only in the narrow strips that aren't covered by the scrollarea (header, footer). Reproduced and fixed at `archive/qt-material-spike` commit `6e2fa2e`.

### 3. `palette()` vs hardcoded hex policy

Use `palette(role)` (e.g. `palette(base)`, `palette(text)`, `palette(window)`, `palette(mid)`) when the colour intent is theme-adaptive. Use hardcoded hex with an explanatory comment when the colour must remain semantic regardless of theme — e.g. competitor-row red `#4a2020`, error toast red, condition-mode blue `#5b9bd5`, and the three-tone pane tints `#3d4455` / `#2a2d33`. Mixing the two is fine; documenting *why* each colour is hex is what made the spike's QSS auditable.

### 4. Regression-test pattern for QSS rendering

`tests/unit/test_pane_styled_background.py` (in `archive/qt-material-spike`) demonstrates how to assert QSS background rules actually render: instantiate the widget headlessly under `QT_QPA_PLATFORM=offscreen`, call `widget.style().polish(widget)`, then read back the painted background colour via the widget's palette. The pattern catches the `WA_StyledBackground` and `QScrollArea` bugs above as regressions, which is otherwise impossible to test in CI.

### 5. Library choice findings (from the spike, not the migration)

- `qt-material` was the chosen library. The `dark_blue.xml` theme was the closest visual match to the project's pre-existing palette.
- Loading order: `apply_stylesheet(app, theme='dark_blue.xml')` *first*, then load the project's `custom.qss` override afterwards. The override merges with the qt-material rules; reversing the order silently drops the override.
- The `custom.qss` was 244 lines for full coverage — substantially smaller than the 17 inline `setStyleSheet()` strings it replaced, and centrally auditable.

## Reference

- **Working theme code:** `archive/qt-material-spike` (tip `b1c55d5`)
- **Spike PR:** #89
- **Phase implementations:** PR #94 (Phase 0, on main), PR #97 (Phase 1 + 1.5, on archive branch)
- **Original spike ADR:** [ADR-0001](0001-qt-theme-evaluation.md)

## Open follow-ups (not blocking this ADR)

- Decide whether to remove the `qt-material` dependency from `pyproject.toml` on `main` (Phase 0 left it installed but inactive). The future overhaul may keep it; if not, removing it is a small cleanup PR.
- When the future UI overhaul is planned, file a new umbrella issue and reference this ADR + `archive/qt-material-spike` as prior art.
