# OAR Priority Manager

A desktop tool for Skyrim modders using Mod Organizer 2 (MO2) and Open Animation Replacer (OAR). Inspect which OAR submods compete for the same animation files, see who's winning, and adjust priorities — without modifying source mod files.

## Quick Start

### As an MO2 Executable (recommended)

1. Download the latest release zip from GitHub Releases.
2. Extract to your MO2 tools directory (e.g. `<instance>/tools/oar-priority-manager/`).
3. In MO2, go to **Tools → Executables → Add**.
4. Set the binary path to the extracted `.exe`.
5. Set arguments: `--mods-path "%BASE_DIR%/mods"`
6. Run from MO2 so the tool sees the merged VFS.

### Development Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -v
python -m oar_priority_manager --mods-path "C:\path\to\your\MO2\instance\mods"
```

## How It Works

The tool scans your MO2 mods directory for OAR submod folders (`config.json` files under `OpenAnimationReplacer/`). For each animation file (`.hkx`), it builds a **priority stack** — the ordered list of all submods that provide that animation, sorted by OAR's evaluation order (priority descending, first-match-wins).

You can:
- **Search** for any mod, submod, or animation filename
- **See** exactly who's winning each animation and by how much
- **Fix it** with Move to Top (one click) or Set Exact Priority
- All changes are written to MO2 Overwrite — source mods are never touched

## Technology

- Python 3.11+ / PySide6
- Packaged with Nuitka for native Windows binaries
- Tests: pytest + pytest-qt

## License

TBD
