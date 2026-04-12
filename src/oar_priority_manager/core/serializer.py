"""JSON serializer with mutable-field allowlist for OAR user.json files.

See spec §3.3 (architectural enforcement), §6.2 (serializer responsibilities),
§8.1.1 (provenance metadata), §8.1.2 (round-trip precision).

CRITICAL ARCHITECTURAL GUARDRAIL: Only the 'priority' field may be modified.
Any other field change raises IllegalMutationError. This prevents scope creep
into condition editing or disable toggling — the trap that killed attempts 1 and 2.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from oar_priority_manager.core.models import METADATA_KEY, IllegalMutationError

# The ONLY fields the tool is allowed to modify. Everything else must round-trip
# unchanged. _oarPriorityManager is handled separately (always injected/updated).
MUTABLE_FIELDS: frozenset[str] = frozenset({"priority"})

# Current tool version — embedded in metadata for provenance tracking
_TOOL_VERSION = "0.1.0"


def _deep_equal(a: object, b: object) -> bool:
    """Deep equality check that handles nested dicts, lists, and primitives."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        if a.keys() != b.keys():  # type: ignore[union-attr]
            return False
        return all(_deep_equal(a[k], b[k]) for k in a)  # type: ignore[index]
    if isinstance(a, list):
        if len(a) != len(b):  # type: ignore[arg-type]
            return False
        return all(_deep_equal(x, y) for x, y in zip(a, b))  # type: ignore[arg-type]
    return a == b


def _validate_allowlist(modified: dict, original: dict) -> None:
    """Check that only allowlisted fields have changed.

    Raises IllegalMutationError if any non-allowlisted field differs.
    """
    # Check for removed keys
    for key in original:
        if key == METADATA_KEY:
            continue
        if key not in modified:
            raise IllegalMutationError(key, original[key], "<removed>")

    # Check for added keys
    for key in modified:
        if key == METADATA_KEY:
            continue
        if key not in original:
            raise IllegalMutationError(key, "<absent>", modified[key])

    # Check for modified values in non-allowlisted fields
    for key in original:
        if key == METADATA_KEY:
            continue
        if key in MUTABLE_FIELDS:
            continue
        if not _deep_equal(original[key], modified[key]):
            raise IllegalMutationError(key, original[key], modified[key])


def _build_metadata(previous_priority: int | None) -> dict:
    """Build the _oarPriorityManager metadata object."""
    meta: dict = {
        "toolVersion": _TOOL_VERSION,
        "writtenAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if previous_priority is not None:
        meta["previousPriority"] = previous_priority
    return meta


def serialize_raw_dict(
    modified: dict,
    original: dict,
    output_path: Path,
    previous_priority: int | None = None,
) -> None:
    """Write a modified raw_dict to disk as JSON.

    Args:
        modified: The raw_dict with updated priority.
        original: The raw_dict as originally read (for allowlist diffing).
        output_path: Where to write the file.
        previous_priority: The priority value before this change (for metadata).

    Raises:
        IllegalMutationError: If any non-allowlisted field has been modified.
    """
    # Validate before writing — the guardrail
    _validate_allowlist(modified, original)

    # Build output dict preserving key order from modified, inject metadata
    output = dict(modified)
    output[METADATA_KEY] = _build_metadata(previous_priority)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(output, indent=2, ensure_ascii=False) + "\n"

    # Atomic write: write to temp file then rename (safe on NTFS).
    # Prevents a crash mid-write from leaving a partial/corrupt user.json.
    fd, tmp_path_str = tempfile.mkstemp(
        dir=output_path.parent, suffix=".tmp", prefix=".oar_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json_text)
        Path(tmp_path_str).replace(output_path)
    except BaseException:
        Path(tmp_path_str).unlink(missing_ok=True)
        raise
