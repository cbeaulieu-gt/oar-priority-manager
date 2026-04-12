"""Application config and MO2 instance root detection.

See spec §8.3 (tool config), §8.3.1 (detection chain).
"""
from __future__ import annotations
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


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


def detect_instance_root(
    mods_path: str | None = None,
    cwd: Path | None = None,
) -> Path:
    """Detect the MO2 instance root using the fallback chain (spec §8.3.1).

    Detection order:
      1. ``mods_path`` CLI arg — parent directory is the instance root.
      2. ``cwd`` contains both ``ModOrganizer.ini`` and ``mods/``.
      3. Walk up from ``cwd`` looking for ``ModOrganizer.ini`` + ``mods/``.
      4. Raise :class:`DetectionError` — no instance found.

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
