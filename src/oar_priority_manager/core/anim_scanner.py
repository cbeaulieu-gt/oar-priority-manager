"""Animation file scanner and conflict map builder.

See spec §6.2 (anim_scanner responsibilities).
Scans each submod's animation files, including overrideAnimationsFolder redirection.
overrideAnimationsFolder resolves relative to the PARENT of the submod directory
(the replacer folder), matching OAR's own resolution logic.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path, PureWindowsPath

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


def _extract_replaced_animations(
    raw_dict: dict,
) -> set[str]:
    """Extract vanilla animation names from replacementAnimDatas config.

    Each entry in the ``replacementAnimDatas`` array represents **one vanilla
    animation slot** being overridden.  The identity of that slot is encoded
    in the entry's ``path`` field — specifically in the last path segment,
    which follows the convention ``_variants_<vanillaname>``.

    For example, an entry whose path ends in ``_variants_sneakmtidle``
    overrides the vanilla ``sneakmtidle.hkx``.  The variant ``filename``
    fields inside each entry are the *replacement* .hkx assets used at
    runtime; they are **not** the vanilla animation identifiers and are
    intentionally ignored here.

    Derivation rules for each entry's ``path`` last segment:
    - If it starts with ``_variants_``, strip that prefix to get the name.
    - Otherwise use the segment as-is.
    - Lowercase and append ``.hkx`` if not already present.

    Args:
        raw_dict: The submod's raw config dictionary (``SubMod.raw_dict``).

    Returns:
        A deduplicated set of lowercased vanilla animation filenames, one per
        ``replacementAnimDatas`` entry whose ``path`` can be parsed.  Returns
        an empty set when the key is absent or the data is malformed.
    """
    filenames: set[str] = set()
    entries = raw_dict.get("replacementAnimDatas", [])
    if not isinstance(entries, list):
        return filenames

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if not path or not isinstance(path, str):
            continue
        # Use PureWindowsPath to correctly parse backslash-separated OAR paths.
        last_segment = PureWindowsPath(path).name
        if not last_segment:
            continue
        if last_segment.startswith("_variants_"):
            name = last_segment[len("_variants_"):]
        else:
            name = last_segment
        if not name:
            continue
        name = name.lower()
        if not name.endswith(".hkx"):
            name += ".hkx"
        filenames.add(name)

    return filenames


def _discover_variant_folders(submod_dir: Path) -> set[str]:
    """Discover implicit OAR variant folders in a submod directory.

    OAR auto-discovers subdirectories whose names start with ``_variants_``
    inside a submod folder, without those directories needing to be declared
    in config.json.  Each such directory implicitly overrides the vanilla
    animation whose name matches the suffix after ``_variants_``.

    Derivation rules for each matching subdirectory name:
    - Strip the ``_variants_`` prefix.
    - Lowercase the result.
    - Append ``.hkx``.

    Args:
        submod_dir: The submod directory to scan (``config_path.parent``).

    Returns:
        A deduplicated set of lowercased derived animation filenames.
        Returns an empty set on OSError (e.g. directory does not exist).
    """
    filenames: set[str] = set()
    try:
        for entry in submod_dir.iterdir():
            if entry.is_dir() and entry.name.startswith("_variants_"):
                name = entry.name[len("_variants_"):].lower()
                if name:
                    if not name.endswith(".hkx"):
                        name += ".hkx"
                    filenames.add(name)
    except OSError:
        pass
    return filenames


def scan_animations(submods: list[SubMod]) -> None:
    """Populate each SubMod's animations list with lowercased .hkx filenames.

    Discovers animations from three sources and merges them:

    1. Filesystem: ``.hkx`` files found in the submod's animation directory
       (or ``overrideAnimationsFolder`` if set).
    2. Config JSON: filenames declared in ``replacementAnimDatas`` entries
       within the submod's ``raw_dict``.
    3. Implicit variant folders: subdirectories starting with ``_variants_``
       in the submod directory, discovered by convention (no config.json entry
       required).

    Modifies submods in place.

    Args:
        submods: List of SubMod instances to populate.
    """
    for sm in submods:
        anim_dir = _get_animation_dir(sm)
        try:
            hkx_files: set[str] = {
                f.name.lower()
                for f in anim_dir.iterdir()
                if f.is_file() and f.suffix.lower() == ".hkx"
            }
        except OSError as e:
            sm.warnings.append(
                f"Cannot read animation directory {anim_dir}: {e}"
            )
            hkx_files = set()

        config_anims = _extract_replaced_animations(sm.raw_dict)
        variant_folder_anims = _discover_variant_folders(sm.config_path.parent)
        sm.animations = sorted(hkx_files | config_anims | variant_folder_anims)


def build_conflict_map(submods: list[SubMod]) -> dict[str, list[SubMod]]:
    """Build a map of animation filename -> list of competing submods, sorted by priority desc.

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
