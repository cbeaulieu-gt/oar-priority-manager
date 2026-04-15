"""Application config and MO2 instance root detection.

See spec §8.3 (tool config), §8.3.1 (detection chain).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Last-instance persistence (spec §8.3.1 — manual picker fallback)
# ---------------------------------------------------------------------------

#: Subdirectory under %APPDATA% where the last-instance file is stored.
_APPDATA_SUBDIR = "oar-priority-manager"

#: File that stores the manually-chosen mods path across launches.
_LAST_INSTANCE_FILENAME = "last-instance.json"


def _appdata_dir() -> Path:
    """Return the %APPDATA%/oar-priority-manager directory.

    Returns:
        Path to the application data directory.
    """
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / _APPDATA_SUBDIR


def load_last_instance() -> Path | None:
    """Load the manually-chosen mods path from the last-instance cache.

    Reads ``%APPDATA%/oar-priority-manager/last-instance.json``.  Returns
    ``None`` on any failure (missing file, bad JSON, path no longer valid).

    Returns:
        The cached mods directory as a resolved :class:`Path`, or ``None`` if
        the cache is absent, unreadable, or points to a directory that no
        longer exists.
    """
    cache_path = _appdata_dir() / _LAST_INSTANCE_FILENAME
    if not cache_path.is_file():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        mods_path = Path(data["mods_path"])
        if mods_path.is_dir():
            return mods_path
        logger.warning(
            "Cached mods path no longer exists: %s", mods_path
        )
        return None
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        logger.warning("Could not read last-instance cache: %s", exc)
        return None


def save_last_instance(mods_path: Path) -> None:
    """Persist the manually-chosen mods path for use on subsequent launches.

    Writes ``%APPDATA%/oar-priority-manager/last-instance.json`` with the
    given path and the current UTC timestamp.

    Args:
        mods_path: Absolute path to the MO2 ``mods/`` directory chosen by
            the user via the directory picker dialog.
    """
    cache_dir = _appdata_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / _LAST_INSTANCE_FILENAME
    payload = {
        "mods_path": str(mods_path),
        "timestamp": datetime.now(tz=UTC).isoformat(),
    }
    cache_path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.debug("Saved last-instance cache: %s", cache_path)


class DetectionError(Exception):
    """Raised when MO2 instance root cannot be detected."""


@dataclass
class AppConfig:
    """Tool configuration persisted to disk. One config per MO2 instance."""

    relative_or_absolute: str = "relative"
    submod_sort: str = "priority"
    window_geometry: str = ""
    splitter_positions: list[int] = field(default_factory=list)
    search_history: list[str] = field(default_factory=list)
    last_selected_path: str = ""
    tag_overrides: dict = field(default_factory=dict)


def detect_instance_root(
    mods_path: str | None = None,
    cwd: Path | None = None,
) -> Path:
    """Detect the MO2 instance root using the fallback chain (spec §8.3.1).

    Detection order:
      1. ``mods_path`` CLI arg — parent directory is the instance root.
      2. ``cwd`` contains both ``ModOrganizer.ini`` and ``mods/``.
      3. Walk up from ``cwd`` looking for ``ModOrganizer.ini`` + ``mods/``.
      4. Cached last-instance path from ``%APPDATA%/oar-priority-manager/``
         ``last-instance.json`` — parent directory is the instance root.
      5. Raise :class:`DetectionError` — no instance found (caller should
         show the directory-picker dialog as a last resort).

    Args:
        mods_path: Explicit path to the MO2 ``mods/`` directory, typically
            supplied via the ``--mods-path`` CLI argument.
        cwd: Directory to start the walk-up search from.  Defaults to
            ``None`` (walk-up step is skipped when not provided).

    Returns:
        The resolved MO2 instance root directory.

    Raises:
        DetectionError: When the instance root cannot be determined.
    """
    if mods_path:
        mods = Path(mods_path)
        if mods.is_dir():
            return mods.parent
        raise DetectionError(
            f"--mods-path '{mods_path}' does not exist or is not a directory."
        )

    if cwd is not None:
        if (cwd / "ModOrganizer.ini").is_file() and (cwd / "mods").is_dir():
            return cwd

        current = cwd
        while current != current.parent:
            if (
                (current / "ModOrganizer.ini").is_file()
                and (current / "mods").is_dir()
            ):
                return current
            current = current.parent

    # Step 4 — check the last-instance cache written by the directory picker.
    cached = load_last_instance()
    if cached is not None:
        logger.info("Using cached mods path from last-instance: %s", cached)
        return cached.parent

    raise DetectionError(
        "Could not detect MO2 instance. Please configure the executable with "
        "--mods-path or run the tool from within your MO2 instance directory."
    )


def load_config(path: Path) -> AppConfig:
    """Load tool config from disk, returning defaults on any failure.

    Graceful degradation: if the file is missing, unreadable, or contains
    malformed JSON the function logs a warning and returns a default
    :class:`AppConfig` rather than propagating an exception.

    Args:
        path: Absolute path to the JSON config file.

    Returns:
        The loaded (or default) :class:`AppConfig` instance.
    """
    if not path.is_file():
        return AppConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            logger.warning("Config at %s is not a JSON object, using defaults", path)
            return AppConfig()
        return AppConfig(
            relative_or_absolute=data.get("relative_or_absolute", "relative"),
            submod_sort=data.get("submod_sort", "priority"),
            window_geometry=data.get("window_geometry", ""),
            splitter_positions=data.get("splitter_positions", []),
            search_history=data.get("search_history", []),
            last_selected_path=data.get("last_selected_path", ""),
            tag_overrides=data.get("tag_overrides", {}),
        )
    except (json.JSONDecodeError, OSError):
        logger.warning("Corrupt config at %s, using defaults", path)
        return AppConfig()


def save_config(config: AppConfig, path: Path) -> None:
    """Persist tool config to disk as formatted JSON.

    Creates parent directories as needed.

    Args:
        config: The :class:`AppConfig` instance to serialise.
        path: Destination file path (will be created or overwritten).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(config), indent=2) + "\n",
        encoding="utf-8",
    )
