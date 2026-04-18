"""Application entry point.

See spec §6.3 (data flow). Parses CLI args, detects MO2 instance,
runs scan pipeline, constructs UI.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from qt_material import apply_stylesheet

# Path to the per-widget QSS override file, relative to this module.
# Loaded after apply_stylesheet() so our rules layer on top of the theme.
_CUSTOM_QSS_PATH = (
    Path(__file__).parent.parent / "ui" / "theme" / "custom.qss"
)

from oar_priority_manager.app.config import (
    DetectionError,
    detect_instance_root,
    load_config,
    save_config,
)
from oar_priority_manager.core.anim_scanner import build_conflict_map, scan_animations
from oar_priority_manager.core.filter_engine import extract_condition_types
from oar_priority_manager.core.priority_resolver import build_stacks
from oar_priority_manager.core.scanner import scan_mods
from oar_priority_manager.core.tag_engine import apply_overrides, compute_tags

logger = logging.getLogger(__name__)

CONFIG_SUBDIR = "oar-priority-manager"
CONFIG_FILENAME = "config.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="oar-priority-manager",
        description="OAR priority management tool for Skyrim modders using MO2",
    )
    parser.add_argument(
        "--mods-path",
        help='Path to MO2 mods/ directory. Recommended: --mods-path "%%BASE_DIR%%/mods"',
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args(argv)


def run_scan(instance_root: Path) -> tuple:
    """Execute the full scan pipeline (spec §6.3 steps 2-3).

    Returns (submods, conflict_map, stacks).
    """
    mods_dir = instance_root / "mods"
    overwrite_dir = instance_root / "overwrite"

    submods = scan_mods(mods_dir, overwrite_dir)
    scan_animations(submods)
    conflict_map = build_conflict_map(submods)
    stacks = build_stacks(conflict_map)

    for sm in submods:
        present, negated = extract_condition_types(sm.conditions)
        sm.condition_types_present = present
        sm.condition_types_negated = negated
        sm.tags = compute_tags(sm)

    return submods, conflict_map, stacks


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(name)s %(levelname)s: %(message)s",
    )

    # Force the native Windows platform plugin.  pytest-qt sets
    # QT_QPA_PLATFORM=offscreen for headless tests — if that leaks into
    # a real launch (same terminal, IDE env, etc.) the app renders to an
    # invisible buffer and no window ever appears.
    os.environ.pop("QT_QPA_PLATFORM", None)
    app = QApplication(sys.argv[:1] + ["-platform", "windows"])
    app.setApplicationName("OAR Priority Manager")
    apply_stylesheet(app, theme="dark_blue.xml")

    # Append per-widget overrides defined in custom.qss.  Using
    # app.styleSheet() + override preserves the qt-material base rules.
    _override = _CUSTOM_QSS_PATH.read_text(encoding="utf-8")
    app.setStyleSheet(app.styleSheet() + _override)

    try:
        instance_root = detect_instance_root(
            mods_path=args.mods_path,
            cwd=Path.cwd(),
        )
    except DetectionError:
        # All auto-detection steps failed — fall back to the manual picker.
        logger.info("Auto-detection failed; showing directory picker dialog.")
        from oar_priority_manager.ui.instance_picker import pick_mods_directory

        mods_path = pick_mods_directory(app)
        instance_root = mods_path.parent

    logger.info("MO2 instance root: %s", instance_root)

    config_path = instance_root / CONFIG_SUBDIR / CONFIG_FILENAME
    app_config = load_config(config_path)

    submods, conflict_map, stacks = run_scan(instance_root)
    apply_overrides(submods, app_config.tag_overrides)
    logger.info("Loaded %d submods, %d animation stacks", len(submods), len(stacks))

    # Diagnostic: which Qt platform plugin is loaded?
    logger.info("Qt platform: %s", app.platformName())

    from oar_priority_manager.ui.main_window import MainWindow

    window = MainWindow(
        submods=submods,
        conflict_map=conflict_map,
        stacks=stacks,
        app_config=app_config,
        instance_root=instance_root,
    )
    window.show()
    window.activateWindow()
    app.processEvents()

    logger.info(
        "Window state: visible=%s geometry=%s handle=%s",
        window.isVisible(),
        window.geometry(),
        window.windowHandle(),
    )

    exit_code = app.exec()
    window.capture_config()
    save_config(app_config, config_path)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
