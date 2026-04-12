"""Core data model types for OAR Priority Manager.

See spec §5.2 (SubMod), §5.4 (PriorityStack), §3.3 (IllegalMutationError).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class OverrideSource(Enum):
    """Where the effective priority was read from (spec §5.3)."""

    SOURCE = "source"          # config.json in source mod
    USER_JSON = "user_json"    # user.json in source mod (OAR in-game override)
    OVERWRITE = "overwrite"    # user.json in MO2 Overwrite folder


@dataclass
class SubMod:
    """A single OAR submod discovered during scan.

    Fields match spec §5.2. raw_dict comes from the WINNING file in the
    override precedence chain (§5.3) — NOT always from config.json.
    When user.json exists, it is a complete data replacement for all fields
    except name and description (§4).
    """

    mo2_mod: str
    replacer: str
    name: str
    description: str
    priority: int
    source_priority: int
    disabled: bool
    config_path: Path
    override_source: OverrideSource
    override_is_ours: bool
    raw_dict: dict
    animations: list[str] = field(default_factory=list)
    conditions: dict = field(default_factory=dict)
    condition_types_present: set[str] = field(default_factory=set)
    condition_types_negated: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_warnings(self) -> bool:
        """True if this submod has parse/validation warnings. Edits are blocked."""
        return len(self.warnings) > 0

    @property
    def is_overridden(self) -> bool:
        """True if priority differs from the source config.json value."""
        return self.priority != self.source_priority

    @property
    def display_path(self) -> str:
        """Human-readable breadcrumb: 'MO2 Mod / Replacer / Submod'."""
        return f"{self.mo2_mod} / {self.replacer} / {self.name}"


@dataclass
class PriorityStack:
    """All submods competing for one animation filename, sorted by priority descending.

    See spec §5.4. Built by priority_resolver.py.
    """

    animation_filename: str
    competitors: list[SubMod] = field(default_factory=list)


class IllegalMutationError(Exception):
    """Raised by serializer when a non-allowlisted field has been modified.

    See spec §3.3 and §6.2. This is the architectural guardrail that prevents
    scope creep into condition editing or disable toggling.
    """

    def __init__(self, field_name: str, original_value: object, new_value: object) -> None:
        self.field_name = field_name
        self.original_value = original_value
        self.new_value = new_value
        super().__init__(
            f"Illegal mutation of field '{field_name}': "
            f"original={original_value!r}, new={new_value!r}. "
            f"Only 'priority' may be modified."
        )
