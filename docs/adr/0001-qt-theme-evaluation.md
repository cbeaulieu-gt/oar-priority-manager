# ADR 0001 — Qt Theme Library Evaluation

**Status**: Proposed
**Issue**: [#76](https://github.com/cbeaulieu-gt/oar-priority-manager/issues/76)
**Date**: 2026-04-17

---

## Context

The application currently styles itself with hand-rolled QSS strings scattered
across multiple widget files (notably `tree_panel.py`, `stacks_panel.py`,
`filter_bucket.py`, `filter_pill.py`, and `search_bar.py`). This is functional
but creates maintenance friction: colour values are duplicated, there is no
single source of truth for the dark palette, and adding new widgets requires
manually threading the right hex codes.

Two areas of the UI require special attention for any theme migration:

1. **`TagDelegate` (custom `QStyledItemDelegate`)** — paints coloured tag pills
   directly after each tree item's display text using `QPainter` calls in its
   `paint()` override. Pill colours are derived from `TagCategory` metadata
   (hard-coded `color_bg`, `color_border`, `color_fg` fields), not from any
   Qt style role. The delegate is installed on `QTreeWidget` via
   `setItemDelegate()`.

2. **Per-item foreground colouring** — `TreePanel.filter_tree()` calls
   `QTreeWidgetItem.setForeground()` to dim non-matching items to
   `QColor(160, 160, 160)` in search/filter mode. This relies on per-item
   palette data not being clobbered by a theme-wide `color:` QSS rule with
   higher specificity.

The spike evaluated three candidate libraries to answer:

- **Blocker**: Does the theme mechanism compose with custom `paint()` delegates,
  or can it hijack `drawControl()` / `drawPrimitive()` and break custom painting?
- **Important**: Does the theme's QSS hard-code `color:` rules on `QTreeView`
  that would win over per-item `setForeground()` calls?

---

## Evaluation

### Mechanism analysis (source inspection)

All three libraries were installed (`qt-material==2.17`,
`pyqtdarktheme==2.1.0`, `qdarkstyle==3.2.3`) and their source read directly.

| Candidate | Theme mechanism | Installs QProxyStyle? | Overrides `drawControl`/`drawPrimitive`? |
|---|---|---|---|
| `qt-material` | `app.setStyleSheet(qss_string)` only; also calls `app.setStyle("Fusion")` before setting QSS | No — uses the built-in Fusion style | No — Fusion does not intercept `paint()` |
| `PyQtDarkTheme` | `app.setStyleSheet(qss)` + `app.setPalette(palette)` + **`app.setStyle(QDarkThemeStyle())`** | **Yes** — `QDarkThemeStyle(QProxyStyle)` | No — proxy only overrides `standardIcon()`; `drawControl` and `drawPrimitive` are not overridden |
| `QDarkStyleSheet` | `app.setStyleSheet(qss_string)` only; applies a single `QPalette.Link` colour fix | No | No |

**Blocker verdict**: All three pass. `QDarkThemeStyle` is a `QProxyStyle`, but
its only override is `standardIcon()`, which replaces standard toolbar/dialog
icons with SVG equivalents. It does not touch `drawControl()`, `drawPrimitive()`,
or any code path that calls a `QStyledItemDelegate`'s `paint()` method.
`TagDelegate.paint()` calls `super().paint()` (the `QStyledItemDelegate`
default, not a style method), so it is unaffected by any proxy style that only
overrides `standardIcon`.

### Per-item colour rule analysis (QSS inspection)

All three themes include a `QTreeView { color: <hex>; }` rule:

- `qt-material`: `QTreeView, … { color: {{primaryTextColor}}; … }` (template variable)
- `PyQtDarkTheme`: theme palette applied via `app.setPalette()`, plus `QTreeView`
  rules in generated QSS
- `QDarkStyleSheet`: `QTreeView, QListView, … { color: #DFE1E2; … }`

**Important verdict**: All three set a base `color:` on `QTreeView`. However,
`QTreeWidgetItem.setForeground()` stores colour in the item's *data model*, not
via a stylesheet rule. Qt's item-view painting reads item data (role
`Qt::ForegroundRole`) after the stylesheet has painted the background — the
per-item foreground from `setForeground()` takes precedence over the widget-level
`color:` stylesheet rule when the item has a non-null foreground brush set. This
is standard Qt behaviour (item data overrides stylesheet for per-item attributes).

**Empirical confirmation**: The smoke tests (`tests/smoke/test_theme_compat.py`,
9 tests × 3 themes) all pass, confirming no runtime breakage.

### Nice-to-have axes

| Candidate | License | Last release (approx.) | Bundle size (installed) | Customisation ergonomics |
|---|---|---|---|---|
| `qt-material` | BSD-2 | Active (2024) | ~1.6 MB (QSS template + SVG icons + Roboto fonts) | Good — XML theme files, Jinja2 templates, `extra` dict for colour overrides; runtime theme switching |
| `PyQtDarkTheme` | MIT | Last tagged 2.1.0 (2022); **unmaintained** | ~small | Moderate — `custom_colors` dict; OS accent sync; but no active maintenance |
| `QDarkStyleSheet` | MIT | Active (3.2.3, 2023) | ~moderate (includes compiled `.qrc` assets) | Moderate — subclass `Palette`; limited to dark/light variants |

---

## Options

### (a) Keep hand-rolled QSS

Continue with the current per-widget inline `setStyleSheet()` strings.

**Trade-offs**:
- Pro: zero new dependencies, no risk of upstream breakage.
- Pro: full control over every pixel.
- Con: colour duplication across ~8 files, no theming story, maintenance
  overhead grows with every new widget.

### (b) Adopt `qt-material`

Replace application-level palette QSS with `apply_stylesheet(app, theme='...')`
and migrate per-widget inline strings to a single custom CSS override file.

**Trade-offs**:
- Pro: single source of truth for colours; runtime theme switching is free.
- Pro: QSS-only mechanism — zero risk to custom delegates.
- Pro: actively maintained, good PySide6 support.
- Con: Adds Roboto font (~several hundred kB) and SVG icon assets to the
  install; these are not needed for a desktop-native app.
- Con: Material Design aesthetics may clash with the current utilitarian dark
  look; some density/spacing defaults need tuning.
- Con: `apply_stylesheet()` also calls `app.setStyle("Fusion")`, replacing the
  platform native style. This is fine on Windows but worth noting.
- **Requires a follow-up issue** to do the actual migration (out of scope here).

### (c) Defer permanently

Acknowledge the maintenance cost but decide that the app's styling complexity
will not grow enough to justify a dependency.

**Trade-offs**:
- Pro: no dependency risk.
- Con: the problem is real and will compound as the UI grows.
- Con: does not produce a better developer experience.

---

## Decision

**Recommend option (b): adopt `qt-material` in a follow-up issue, if the
team decides to act on this spike.**

Rationale:

1. **The Blocker question is resolved for all three candidates** — none breaks
   `TagDelegate` or per-item foreground colouring at the mechanism level, and
   all nine smoke tests pass.

2. **`qt-material` is the strongest candidate on the nice-to-have axes**: it is
   actively maintained (unlike `PyQtDarkTheme`, which has been unmaintained
   since 2022), uses a pure-QSS mechanism (lower risk than even the benign
   `QDarkThemeStyle` proxy), and provides the most ergonomic customisation path
   (per-theme XML + Jinja2 environment variables for overrides).

3. **`QDarkStyleSheet` is a viable fallback** if Material Design aesthetics are
   unwanted. It is also pure-QSS and actively maintained. The primary downside
   is that customisation requires subclassing `Palette`, which is less ergonomic
   than `qt-material`'s XML/dict approach.

4. **`PyQtDarkTheme` is not recommended** solely due to its maintenance status
   (last tagged 2022, no recent commits). The proxy style concern is not a
   blocker (see above), but a dependency on unmaintained software is.

**If no candidate passes team review**: option (a) keep hand-rolled QSS is
acceptable. The maintenance cost is manageable at the current UI surface area.

---

## Consequences

If the team adopts `qt-material` (in a follow-up issue):

- `qt-material` is added to `pyproject.toml` `[project.dependencies]`.
- `app/main.py` gains a single `apply_stylesheet(app, theme='dark_teal.xml')`
  call before `MainWindow.__init__`.
- Per-widget inline `setStyleSheet()` strings for background/border/font colours
  are migrated to a single `custom.css` override file (except for the
  `TagDelegate` pill colours, which use hard-coded `TagCategory` metadata and
  should remain as-is).
- The `tree_panel.py` segmented-toggle stylesheet and any similar one-off widget
  styles are moved to the override file.
- No changes to `TagDelegate.paint()`, `TreePanel.filter_tree()`, or any custom
  painting logic — these compose with the theme without modification.
- Bundle size increases by approximately 1.6 MB (fonts + SVG icons).
- CI gains an `import qt_material` smoke step to catch upstream regressions.
