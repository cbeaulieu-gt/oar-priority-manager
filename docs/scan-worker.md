# Scan Worker — Architecture Note

## Why

The full scan pipeline (`scan_mods` → `scan_animations` → `build_conflict_map` →
`build_stacks`) blocks the GUI thread for several seconds on large MO2 instances
(e.g. Nolvus-class with ~4 500 submods).  Two consequences:

1. **GUI freeze at startup** — the main window does not appear until the scan
   completes, which looks like the application has hung.
2. **Splash prerequisite** — a future live scan-progress window (#96) needs an
   async scan to drive its progress bar.  A synchronous call site makes that
   impossible without major restructuring.

`ScanWorker` moves the pipeline off the GUI thread so the event loop stays alive.

---

## Worker Contract

`ScanWorker` is a `QObject` that lives on a `QThread`.  It exposes four signals:

| Signal | Payload | When emitted |
|---|---|---|
| `progress_updated(stage, current, total, label)` | `str, int, int, str` | At each of the 5 stage boundaries and after each submod during `scan_mods` |
| `finished(result)` | `tuple` — `(submods, conflict_map, stacks)` | Scan completed successfully |
| `failed(exception)` | `Exception` | Any uncaught exception in the pipeline |
| `cancelled()` | _(none)_ | Scan stopped via `QThread.requestInterruption()` |

`finished` and `failed` are mutually exclusive.  Neither fires if `cancelled` fires.

Stage names are the `_STAGES` module-level tuple in `scan_worker.py`:

```python
_STAGES = ("detect", "scan_mods", "scan_animations", "build_conflict_map", "build_stacks")
```

Consumer code (splash screen, status bar) should use these string constants.

---

## Threading Model

```
GUI thread                     Worker thread
──────────────────────         ──────────────────────────────
QThread(parent=window)
worker = ScanWorker(root)
worker.moveToThread(thread)    # worker now lives on thread
thread.started → worker.run    # slot executes on thread
thread.start()
                               worker.run()
                                 _run_pipeline()
                                   scan_mods(…, on_progress)
                                     on_progress(cur, total)  ← checks isInterruptionRequested()
                                   scan_animations(…)
                                   build_conflict_map(…)
                                   build_stacks(…)
                               worker.finished.emit(result)   ← Qt queued connection back to GUI
GUI on_finished(result)
  update self._submods …
  thread.quit() / wait()
```

**Cancellation** is implemented without locks:

1. Caller calls `QThread.requestInterruption()` (thread-safe Qt primitive).
2. The `on_progress` callback (runs on the worker thread) checks
   `QThread.currentThread().isInterruptionRequested()` after each submod.
3. If set, it raises `_Cancelled` (a private `Exception` subclass).
4. `_run_pipeline` also checks at the top of each stage so cancellation
   propagates even when a stage produces zero submods.
5. `worker.run()` catches `_Cancelled` and emits `cancelled()`.

There is no shared mutable state between the threads beyond Qt's signal queue.

### Startup (blocking pattern)

`main()` must not show the window before the first scan has data.
`_run_scan_blocking()` pumps a `QEventLoop` while the worker thread runs:

```python
loop = QEventLoop()
worker.finished.connect(lambda r: (result_holder.append(r), loop.quit()))
worker.failed.connect(lambda e: (error_holder.append(e), loop.quit()))
thread.start()
loop.exec()          # keeps GUI event loop alive; exits when finished/failed fires
thread.quit(); thread.wait()
```

This is simpler and more correct than `QThread.wait()` (which would deadlock
if any cross-thread signal tried to call back to the GUI thread while we were
blocked inside `wait()`).

### Refresh (async pattern)

`MainWindow._on_refresh()` starts the worker and returns immediately.  The GUI
stays interactive; `on_finished` re-populates the panels when the scan completes.
A guard (`self._scan_thread is not None and thread.isRunning()`) prevents
concurrent scans.

---

---

## Progress Dialog (`ScanProgressDialog`)

`ScanProgressDialog` (`ui/scan_progress_dialog.py`) is the visual counterpart
to `ScanWorker`.  It reads the worker's signals and renders a splash-style
modal dialog with an overall progress bar, a per-stage label, a per-item
submod name, and a Cancel button.

### Stage weighting

The overall progress bar maps the five pipeline stages to contiguous ranges:

| Stage               | Start % | Weight % |
|---------------------|---------|---------|
| `detect`            | 0       | 5       |
| `scan_mods`         | 5       | 55      |
| `scan_animations`   | 60      | 30      |
| `build_conflict_map`| 90      | 5       |
| `build_stacks`      | 95      | 5       |

Overall = start + (weight × current / total).  When `total = 0` (indeterminate
stage boundary), only the start offset is shown.

### Modality

The dialog uses different modality depending on the context:

| Context | Mode string | Modality | Parent |
|---------|-------------|----------|--------|
| Initial startup | `"startup"` | `ApplicationModal` (frameless) | `None` |
| User-triggered refresh | `"refresh"` | `WindowModal` (title-bar chrome) | `MainWindow` |

`WindowModal` is used for refresh because it blocks the main window (the only
window that matters during a re-scan) while leaving other applications usable.
`ApplicationModal` is used for startup because there is no parent window yet.

### Cancel behaviour

Clicking **Cancel**:
1. Disables the button and updates the stage label to "Cancelling…".
2. Emits `cancellation_requested`.
3. The caller wires this to `thread.requestInterruption()`.

The dialog does not close on cancel-click — it waits for the worker to emit
`cancelled`, which calls `on_cancelled()` → `reject()`.  This keeps the user
informed that cancellation is in progress.

**Startup cancel**: `_run_scan_blocking` detects `cancelled` and calls
`sys.exit(0)` — the user explicitly chose not to scan, so a clean exit is
the right response.

**Refresh cancel**: `_on_refresh` detects the empty `result_holder` after
`dialog.exec()` returns and returns without updating the panels.  The
existing data remains displayed.

### Signal connections summary

```
worker.progress_updated  →  dialog.on_progress
worker.finished          →  dialog.on_finished  (auto-dismiss after 1 s)
worker.failed            →  dialog.on_failed    (immediate close)
worker.cancelled         →  dialog.on_cancelled (immediate close)
dialog.cancellation_requested  →  thread.requestInterruption
```

---

## Why Not Subclass QThread

The Qt documentation and several Qt style guides recommend the **QObject +
moveToThread** pattern over subclassing `QThread` for non-trivial workers:

- **Composability** — `ScanWorker`'s signals are ordinary `QObject` signals;
  any slot or `qtbot.waitSignal()` call can connect to them without knowing
  anything about the thread.
- **pytest-qt testability** — `qtbot.waitSignal(worker.finished)` works
  directly on the worker object regardless of which thread it is moved to.
  If `ScanWorker` subclassed `QThread`, `finished` would be the *thread's*
  `finished` (fired when the thread exits), not the scan's, making it
  impossible to distinguish "scan done" from "thread stopped".
- **Separation of concerns** — the worker's `run()` slot contains domain
  logic, not thread lifecycle code.  The caller controls thread start/stop/wait.
