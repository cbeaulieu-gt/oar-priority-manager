"""Lenient JSON parser for OAR config.json / user.json files.

See spec §6.2. Handles:
- Standard JSON
- Trailing commas (common hand-edit artifact)
- Produces warnings on malformed input instead of raising

Returns (raw_dict, warnings). raw_dict is {} on failure.
Key ordering is preserved for round-trip (Python 3.7+ dicts are insertion-ordered).
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def _strip_trailing_commas(text: str) -> str:
    """Remove trailing commas before } and ] to make JSON valid.

    Handles nested cases. This is a regex-based repair — it won't fix all
    malformed JSON, but catches the most common hand-edit artifact.

    Args:
        text: JSON text potentially containing trailing commas.

    Returns:
        Text with trailing commas removed.
    """
    # Remove comma followed by optional whitespace/newlines then } or ]
    return re.sub(r",\s*([}\]])", r"\1", text)


def parse_config(path: Path) -> tuple[dict, list[str]]:
    """Parse a config.json or user.json file into a raw_dict.

    Lenient parsing: repairs trailing commas and produces warnings instead
    of raising exceptions.

    Args:
        path: Absolute path to the JSON file.

    Returns:
        Tuple of (raw_dict, warnings).
        raw_dict is {} if the file cannot be parsed.
        warnings is [] on success, contains error messages on failure.
    """
    warnings: list[str] = []

    # Read the file
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, [f"File not found: {path}"]
    except OSError as e:
        return {}, [f"Cannot read {path}: {e}"]

    if not text.strip():
        return {}, [f"Empty file: {path}"]

    # Try standard JSON first
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try with trailing-comma repair
        repaired = _strip_trailing_commas(text)
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError as e:
            return {}, [f"JSON parse error in {path}: {e}"]

    # Must be a dict (JSON object)
    if not isinstance(data, dict):
        return {}, [f"Expected JSON object in {path}, got {type(data).__name__}"]

    return data, warnings
