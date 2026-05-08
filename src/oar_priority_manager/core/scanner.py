"""MO2 mod directory scanner — discovers OAR submods and applies override precedence.

See spec §5.3 (override precedence), §6.2 (scanner responsibilities).

CRITICAL: raw_dict must come from the WINNING file in the precedence chain,
not always from config.json. When user.json exists, it is a complete data
replacement for all fields except name/description (spec §4).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from oar_priority_manager.core.models import METADATA_KEY, OAR_REL, OverrideSource, SubMod
from oar_priority_manager.core.parser import parse_config

logger = logging.getLogger(__name__)


def _find_submod_dirs(mods_dir: Path) -> list[tuple[str, str, str, Path]]:
    """Find all submod directories under mods/.

    Returns list of (mo2_mod, replacer, submod_folder_name, submod_path).
    A submod directory is any folder under <mod>/<OAR_REL>/<replacer>/<submod>/
    that either contains config.json or contains .hkx files.
    """
    results = []
    if not mods_dir.is_dir():
        return results

    for mod_dir in sorted(mods_dir.iterdir()):
        if not mod_dir.is_dir():
            continue
        oar_root = mod_dir / OAR_REL
        if not oar_root.is_dir():
            continue

        mo2_mod = mod_dir.name

        for replacer_dir in sorted(oar_root.iterdir()):
            if not replacer_dir.is_dir():
                continue
            replacer = replacer_dir.name

            for submod_dir in sorted(replacer_dir.iterdir()):
                if not submod_dir.is_dir():
                    continue
                # A submod candidate: has config.json or has .hkx files
                has_config = (submod_dir / "config.json").exists()
                has_hkx = any(submod_dir.glob("*.hkx"))
                if has_config or has_hkx:
                    results.append((mo2_mod, replacer, submod_dir.name, submod_dir))

    return results


def _build_submod(
    mo2_mod: str,
    replacer: str,
    submod_folder: str,
    submod_path: Path,
    overwrite_dir: Path,
    replacer_presets: dict,
) -> SubMod:
    """Build a SubMod record for one discovered submod, applying override precedence.

    Precedence (spec §5.3):
    1. Overwrite user.json (at mirrored path)
    2. Source user.json (in source mod)
    3. Source config.json

    raw_dict comes from the WINNING file. name/description always from config.json.
    """
    warnings: list[str] = []

    # Always read config.json for name/description (OAR kInfoOnly)
    config_path = submod_path / "config.json"
    config_dict, config_warnings = parse_config(config_path)
    warnings.extend(config_warnings)

    # Extract name/description from config.json (always, per OAR §4)
    name = config_dict.get("name", submod_folder)
    description = config_dict.get("description", "")
    source_priority = config_dict.get("priority", 0)
    if not isinstance(source_priority, int):
        warnings.append(
            f"Priority is not an integer in {config_path}: {source_priority!r}"
        )
        source_priority = 0

    # Determine override precedence and select winning file for raw_dict.
    # The mirrored path in Overwrite uses the relative path from OAR root.
    rel_from_oar = Path(replacer) / submod_folder
    overwrite_user = overwrite_dir / OAR_REL / rel_from_oar / "user.json"
    source_user = submod_path / "user.json"

    override_source = OverrideSource.SOURCE
    override_is_ours = False
    raw_dict = config_dict
    effective_priority = source_priority

    # Check precedence: Overwrite > source user.json > config.json
    if overwrite_user.is_file():
        ow_dict, ow_warnings = parse_config(overwrite_user)
        warnings.extend(ow_warnings)
        if ow_dict:  # Empty dict {} means parse failed or no useful data — fall through
            override_source = OverrideSource.OVERWRITE
            raw_dict = ow_dict
            effective_priority = ow_dict.get("priority", source_priority)
            if not isinstance(effective_priority, int):
                warnings.append(
                    f"Priority is not an integer in {overwrite_user}: {effective_priority!r}"
                )
                effective_priority = source_priority
            override_is_ours = METADATA_KEY in ow_dict
    elif source_user.is_file():
        su_dict, su_warnings = parse_config(source_user)
        warnings.extend(su_warnings)
        if su_dict:  # Empty dict {} means parse failed or no useful data — fall through
            override_source = OverrideSource.USER_JSON
            # CRITICAL: raw_dict from user.json, not config.json (spec §4)
            raw_dict = su_dict
            effective_priority = su_dict.get("priority", source_priority)
            if not isinstance(effective_priority, int):
                warnings.append(
                    f"Priority is not an integer in {source_user}: {effective_priority!r}"
                )
                effective_priority = source_priority

    # Read disabled from the winning raw_dict (user.json is complete replacement)
    disabled = bool(raw_dict.get("disabled", False))

    # Read conditions from winning raw_dict for display/filtering
    conditions = raw_dict.get("conditions", {})
    if not isinstance(conditions, (dict, list)):
        conditions = {}

    return SubMod(
        mo2_mod=mo2_mod,
        replacer=replacer,
        name=name,
        description=description,
        priority=effective_priority,
        source_priority=source_priority,
        disabled=disabled,
        config_path=config_path,
        override_source=override_source,
        override_is_ours=override_is_ours,
        raw_dict=raw_dict,
        conditions=conditions,
        replacer_presets=replacer_presets,
        warnings=warnings,
    )


def scan_mods(
    mods_dir: Path,
    overwrite_dir: Path,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> list[SubMod]:
    """Scan the MO2 instance and build SubMod records for every OAR submod.

    Args:
        mods_dir: Path to the MO2 mods/ directory.
        overwrite_dir: Path to the MO2 overwrite/ directory.
        on_progress: Optional callback invoked after each submod is built.
            Called with ``(current, total, submod_name)`` where ``current``
            is the number of submods built so far, ``total`` is the total
            number to build, and ``submod_name`` is the display name of the
            submod directory currently being processed.

    Returns:
        List of SubMod records. Submods with parse errors have non-empty warnings.
    """
    submod_dirs = _find_submod_dirs(mods_dir)
    total = len(submod_dirs)
    submods: list[SubMod] = []

    for mo2_mod, replacer, submod_folder, submod_path in submod_dirs:
        # Read replacer-level config.json for conditionPresets
        replacer_dir = submod_path.parent
        replacer_config_path = replacer_dir / "config.json"
        replacer_presets: dict = {}
        if replacer_config_path.is_file():
            rep_dict, _ = parse_config(replacer_config_path)
            raw_presets = rep_dict.get("conditionPresets", {})
            if isinstance(raw_presets, list):
                # Real OAR format: list of {"name": ..., "conditions": [...]}
                replacer_presets = {
                    p["name"]: p.get("conditions", p.get("Conditions", []))
                    for p in raw_presets
                    if isinstance(p, dict) and "name" in p
                    and ("conditions" in p or "Conditions" in p)
                }
            elif isinstance(raw_presets, dict):
                # Legacy / test-fixture format: dict keyed by name
                replacer_presets = raw_presets

        sm = _build_submod(
            mo2_mod, replacer, submod_folder, submod_path,
            overwrite_dir, replacer_presets,
        )
        submods.append(sm)
        if on_progress is not None:
            on_progress(len(submods), total, sm.name)

    logger.info("Scanned %d submods from %s", len(submods), mods_dir)
    return submods
