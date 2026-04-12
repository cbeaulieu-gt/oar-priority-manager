"""Override manager — writes priority changes to MO2 Overwrite at mirrored paths.

See spec §6.2 (override_manager), §8.1 (OAR overrides), §8.2 (clear overrides).
NEVER writes to source mod paths. Only writes user.json to the Overwrite folder.
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path

from oar_priority_manager.core.models import METADATA_KEY, OAR_REL, OverrideSource, SubMod
from oar_priority_manager.core.parser import parse_config
from oar_priority_manager.core.serializer import serialize_raw_dict

logger = logging.getLogger(__name__)


def compute_overwrite_path(submod: SubMod, overwrite_dir: Path) -> Path:
    """Compute the mirrored path in MO2 Overwrite for a submod's user.json.

    The path mirrors the source mod's relative OAR structure:
    overwrite/<OAR_REL>/<replacer>/<submod_folder>/user.json
    """
    submod_folder = submod.config_path.parent.name
    return overwrite_dir / OAR_REL / submod.replacer / submod_folder / "user.json"


def write_override(submod: SubMod, new_priority: int, overwrite_dir: Path) -> None:
    """Write a priority override to MO2 Overwrite for the given submod.

    Builds a new raw_dict with only priority changed, writes via serializer
    (which enforces the mutable-field allowlist), and updates the SubMod
    in-memory state.
    """
    original_raw = submod.raw_dict
    previous_priority = submod.priority

    # Build modified dict — only change priority (deepcopy ensures allowlist
    # check in serializer compares truly independent objects, not aliased dicts)
    modified = copy.deepcopy(original_raw)
    modified["priority"] = new_priority

    output_path = compute_overwrite_path(submod, overwrite_dir)

    serialize_raw_dict(
        modified=modified,
        original=original_raw,
        output_path=output_path,
        previous_priority=previous_priority,
    )

    # Update in-memory state
    submod.priority = new_priority
    submod.override_source = OverrideSource.OVERWRITE
    submod.override_is_ours = True
    submod.raw_dict = modified

    logger.info(
        "Wrote override for %s: %d → %d at %s",
        submod.display_path, previous_priority, new_priority, output_path,
    )


def clear_override(submod: SubMod, overwrite_dir: Path) -> None:
    """Delete the Overwrite-layer user.json for a submod.

    See spec §8.2. Reverts in-memory SubMod state to whatever is in the
    source mod (source user.json if present, otherwise config.json).
    """
    output_path = compute_overwrite_path(submod, overwrite_dir)
    if output_path.exists():
        output_path.unlink()
        logger.info("Cleared override for %s: deleted %s", submod.display_path, output_path)
        _remove_empty_parents(output_path.parent, overwrite_dir)

    # Revert in-memory state by re-reading source files to determine correct
    # post-clear state (mirrors scanner precedence: source user.json > config.json)
    config_dict, _config_warnings = parse_config(submod.config_path)
    source_priority = config_dict.get("priority", 0)

    source_user = submod.config_path.parent / "user.json"
    if source_user.exists():
        su_dict, su_warnings = parse_config(source_user)
        if su_dict:
            winning_dict = su_dict
            winning_priority = su_dict.get("priority", source_priority)
            override_source = OverrideSource.USER_JSON
            override_is_ours = METADATA_KEY in su_dict
        else:
            winning_dict = config_dict
            winning_priority = source_priority
            override_source = OverrideSource.SOURCE
            override_is_ours = False
    else:
        winning_dict = config_dict
        winning_priority = source_priority
        override_source = OverrideSource.SOURCE
        override_is_ours = False

    submod.priority = winning_priority
    submod.override_source = override_source
    submod.override_is_ours = override_is_ours
    submod.raw_dict = winning_dict


def _remove_empty_parents(directory: Path, stop_at: Path) -> None:
    """Remove empty parent directories up to (but not including) stop_at."""
    # Resolve both paths at entry for case-insensitive comparison on Windows
    current = directory.resolve()
    boundary = stop_at.resolve()
    while current != boundary and current.is_dir():
        try:
            current.rmdir()  # Only removes if empty
            current = current.parent
        except OSError:
            break
