"""Manual MO2 mods-folder picker dialog (spec §8.3.1, last-resort fallback).

Shown when all automatic MO2 instance detection steps are exhausted.  The
user browses to their MO2 mods folder; the chosen path is cached in
``%APPDATA%/oar-priority-manager/last-instance.json`` so subsequent launches
skip the dialog.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMessageBox,
)

from oar_priority_manager.app.config import save_last_instance

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

#: Minimum number of subdirectories a folder must contain to be considered a
#: plausible MO2 mods directory.
_MIN_SUBDIR_COUNT = 1


def _looks_like_mods_dir(path: Path) -> bool:
    """Return True if *path* looks like a plausible MO2 mods directory.

    The check is intentionally permissive — we only require that the folder
    has at least one subdirectory (i.e. it is not empty).  A stricter check
    (e.g. looking for OAR content) would reject valid but pristine installs.

    Args:
        path: Directory chosen by the user.

    Returns:
        ``True`` when the directory contains at least one sub-directory,
        ``False`` otherwise.
    """
    try:
        subdirs = [p for p in path.iterdir() if p.is_dir()]
        return len(subdirs) >= _MIN_SUBDIR_COUNT
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def pick_mods_directory(app: QApplication | None = None) -> Path:
    """Show a directory-picker dialog and return the chosen mods path.

    This function is the last-resort fallback in the MO2 instance detection
    chain.  It:

    1. Prompts the user with an informational message explaining why the
       dialog is appearing.
    2. Opens a :class:`~PySide6.QtWidgets.QFileDialog` so the user can
       browse to their MO2 ``mods/`` folder.
    3. Validates the selection (warns but does not block if validation fails).
    4. Saves the chosen path via :func:`~oar_priority_manager.app.config.\
save_last_instance` so the next launch can skip the dialog.
    5. Returns the chosen :class:`Path`.

    If the user cancels the dialog, the function prints a message to stderr
    and calls :func:`sys.exit` with exit code 1.

    Args:
        app: An existing :class:`~PySide6.QtWidgets.QApplication` instance.
            When ``None``, the function retrieves the running instance via
            :meth:`~PySide6.QtWidgets.QApplication.instance`.  A
            ``QApplication`` *must* already exist before calling this
            function.

    Returns:
        The directory chosen by the user as a resolved :class:`Path`.

    Raises:
        RuntimeError: If no ``QApplication`` is running when the function is
            called.
    """
    _app = app or QApplication.instance()
    if _app is None:
        raise RuntimeError(
            "pick_mods_directory() requires a running QApplication."
        )

    # Explain why we're asking before showing the file dialog.
    info = QMessageBox()
    info.setWindowTitle("MO2 Instance Not Found")
    info.setIcon(QMessageBox.Icon.Information)
    info.setText(
        "OAR Priority Manager could not automatically locate your MO2 "
        "instance.\n\n"
        "Please browse to your MO2 <b>mods/</b> folder in the next dialog. "
        "Your choice will be remembered for future launches."
    )
    info.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
    info.setDefaultButton(QMessageBox.StandardButton.Ok)
    result = info.exec()

    if result != QMessageBox.StandardButton.Ok:
        print(
            "Instance selection cancelled by user.",
            file=sys.stderr,
        )
        sys.exit(1)

    chosen = QFileDialog.getExistingDirectory(
        None,
        "Select MO2 Mods Folder",
        "",
        QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks,
    )

    if not chosen:
        print(
            "No directory selected. Exiting.",
            file=sys.stderr,
        )
        sys.exit(1)

    mods_path = Path(chosen)

    if not _looks_like_mods_dir(mods_path):
        warn = QMessageBox()
        warn.setWindowTitle("Directory May Not Be a Mods Folder")
        warn.setIcon(QMessageBox.Icon.Warning)
        warn.setText(
            f"The selected directory appears to be empty or does not contain "
            f"any mod sub-folders:\n\n{mods_path}\n\n"
            "You can still proceed, but scanning may return no results."
        )
        warn.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        warn.setDefaultButton(QMessageBox.StandardButton.Ok)
        if warn.exec() != QMessageBox.StandardButton.Ok:
            print(
                "User declined to proceed with empty mods folder. Exiting.",
                file=sys.stderr,
            )
            sys.exit(1)

    save_last_instance(mods_path)
    logger.info("User selected mods path: %s", mods_path)
    return mods_path
