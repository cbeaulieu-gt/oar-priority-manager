"""Override manager — writes priority changes to MO2 Overwrite at mirrored paths.

See spec §6.2 (override_manager), §8.1 (OAR overrides), §8.2 (clear overrides).
NEVER writes to source mod paths. Only writes user.json to the Overwrite folder.
"""

from __future__ import annotations

import logging
from pathlib import Path

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.core.serializer import serialize_raw_dict

logger = logging.getLogger(__name__)

# Relative path within the OAR structure
OAR_REL = Path("meshes/actors/character/animations/OpenAnimationReplacer")


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

    # Build modified dict — only change priority
    modified = dict(original_raw)
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

    See spec §8.2. Reverts to whatever is in the source mod.
    """
    output_path = compute_overwrite_path(submod, overwrite_dir)
    if output_path.exists():
        output_path.unlink()
        logger.info("Cleared override for %s: deleted %s", submod.display_path, output_path)
        _remove_empty_parents(output_path.parent, overwrite_dir)


def _remove_empty_parents(directory: Path, stop_at: Path) -> None:
    """Remove empty parent directories up to (but not including) stop_at."""
    current = directory
    while current != stop_at and current.is_dir():
        try:
            current.rmdir()  # Only removes if empty
            current = current.parent
        except OSError:
            break
