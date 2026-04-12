"""Animation file scanner and conflict map builder.

See spec §6.2 (anim_scanner responsibilities).
Scans each submod's animation files, including overrideAnimationsFolder redirection.
overrideAnimationsFolder resolves relative to the PARENT of the submod directory
(the replacer folder), matching OAR's own resolution logic.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

from oar_priority_manager.core.models import SubMod

logger = logging.getLogger(__name__)


def _get_animation_dir(submod: SubMod) -> Path:
    """Determine where to look for .hkx files.

    If overrideAnimationsFolder is set in raw_dict, resolve it relative to
    the parent of the submod directory (the replacer folder).
    Otherwise, look in the submod directory itself.
    """
    submod_dir = submod.config_path.parent
    override_folder = submod.raw_dict.get("overrideAnimationsFolder")

    if override_folder and isinstance(override_folder, str):
        # Resolve relative to the PARENT of submod dir (the replacer folder)
        replacer_dir = submod_dir.parent
        resolved = (replacer_dir / override_folder).resolve()
        if resolved.is_dir():
            return resolved
        else:
            submod.warnings.append(
                f"overrideAnimationsFolder '{override_folder}' resolves to "
                f"'{resolved}' which does not exist"
            )
    return submod_dir


def scan_animations(submods: list[SubMod]) -> None:
    """Populate each SubMod's animations list with lowercased .hkx filenames.

    Modifies submods in place.
    """
    for sm in submods:
        anim_dir = _get_animation_dir(sm)
        try:
            hkx_files = [
                f.name.lower()
                for f in anim_dir.iterdir()
                if f.is_file() and f.suffix.lower() == ".hkx"
            ]
        except OSError as e:
            sm.warnings.append(f"Cannot read animation directory {anim_dir}: {e}")
            hkx_files = []

        sm.animations = sorted(hkx_files)


def build_conflict_map(submods: list[SubMod]) -> dict[str, list[SubMod]]:
    """Build a map of animation filename -> list of competing submods, sorted by priority descending.

    See spec §5.4 (PriorityStack).
    """
    anim_to_submods: dict[str, list[SubMod]] = defaultdict(list)

    for sm in submods:
        for anim in sm.animations:
            anim_to_submods[anim].append(sm)

    # Sort each list by priority descending
    for anim in anim_to_submods:
        anim_to_submods[anim].sort(key=lambda s: s.priority, reverse=True)

    return dict(anim_to_submods)
