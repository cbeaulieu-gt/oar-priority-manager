"""Priority resolver — builds PriorityStacks and exposes mutation operations.

See spec §5.4 (PriorityStack), §6.2 (priority_resolver responsibilities).
"""

from __future__ import annotations

import logging

from oar_priority_manager.core.models import PriorityStack, SubMod

logger = logging.getLogger(__name__)

INT32_MAX = 2_147_483_647
INT32_MIN = -2_147_483_648


class PriorityOverflowError(Exception):
    """Raised when a computed priority would exceed INT32 range."""

    def __init__(self, computed: int) -> None:
        self.computed = computed
        super().__init__(
            f"Computed priority {computed} exceeds INT32 range "
            f"[{INT32_MIN}, {INT32_MAX}]. Operation cancelled."
        )


def _check_overflow(value: int) -> None:
    if value > INT32_MAX or value < INT32_MIN:
        raise PriorityOverflowError(value)


def build_stacks(conflict_map: dict[str, list[SubMod]]) -> list[PriorityStack]:
    """Build PriorityStack objects from the conflict map, sorted alphabetically by filename."""
    stacks = []
    for filename in sorted(conflict_map.keys()):
        stacks.append(PriorityStack(
            animation_filename=filename,
            competitors=conflict_map[filename],
        ))
    return stacks


def _get_scope_submods(
    target: SubMod | None,
    conflict_map: dict[str, list[SubMod]],
    scope: str,
) -> list[SubMod]:
    """Get all unique submods in the scope (submod/replacer/mod).

    Args:
        target: The submod selected by the user, or ``None`` when the UI
            dispatches an action before a selection exists.  A ``None``
            target returns an empty list so callers see a no-op result
            rather than an ``AttributeError``.
        conflict_map: Animation filename -> list of competing submods.
        scope: One of ``"submod"``, ``"replacer"``, or ``"mod"``.

    Returns:
        Unique submods within the requested scope, in encounter order.
        Returns ``[]`` when ``target`` is ``None``.

    Note:
        The ``None`` guard exists because the UI may dispatch actions
        (e.g., via keyboard shortcuts) before any row is selected in the
        tree.  Callers that pass a guaranteed non-None value are unaffected.
    """
    if target is None:
        return []

    seen: set[int] = set()
    result: list[SubMod] = []

    for anim in target.animations:
        if anim not in conflict_map:
            continue
        for sm in conflict_map[anim]:
            sm_id = id(sm)
            if sm_id in seen:
                continue
            in_scope = (
                (scope == "submod" and sm is target)
                or (
                    scope == "replacer"
                    and sm.mo2_mod == target.mo2_mod
                    and sm.replacer == target.replacer
                )
                or (scope == "mod" and sm.mo2_mod == target.mo2_mod)
            )
            if in_scope:
                seen.add(sm_id)
                result.append(sm)

    return result


def _get_external_max(
    scope_submods: list[SubMod],
    conflict_map: dict[str, list[SubMod]],
) -> int | None:
    """Find the highest priority among external competitors (not in scope)."""
    scope_ids = {id(sm) for sm in scope_submods}
    max_ext: int | None = None

    for sm in scope_submods:
        for anim in sm.animations:
            if anim not in conflict_map:
                continue
            for competitor in conflict_map[anim]:
                if id(competitor) not in scope_ids and (
                    max_ext is None or competitor.priority > max_ext
                ):
                    max_ext = competitor.priority

    return max_ext


def move_to_top(
    target: SubMod | None,
    conflict_map: dict[str, list[SubMod]],
    scope: str = "submod",
) -> dict[SubMod, int]:
    """Compute new priorities to make target (and scope) #1 in all stacks.

    Args:
        target: The submod the user selected, or ``None`` when no row is
            selected.  A ``None`` target produces an empty result dict
            (the ``_get_scope_submods`` None guard fires first).
        conflict_map: Animation filename -> list of competing submods.
        scope: "submod", "replacer", or "mod".

    Returns:
        Dict of SubMod -> new_priority. Empty if already winning everywhere
        or if ``target`` is ``None``.

    Raises:
        PriorityOverflowError: If computed priority exceeds INT32_MAX.
    """
    scope_submods = _get_scope_submods(target, conflict_map, scope)
    if not scope_submods:
        return {}

    external_max = _get_external_max(scope_submods, conflict_map)
    if external_max is None:
        # No external competitors — already winning
        return {}

    # Check if already winning (all scope submods have priority > external_max)
    if all(sm.priority > external_max for sm in scope_submods):
        return {}

    if scope == "submod":
        new_priority = external_max + 1
        _check_overflow(new_priority)
        return {target: new_priority}

    # Replacer/mod scope: floor-anchored shift
    old_priorities = [sm.priority for sm in scope_submods]
    min_old = min(old_priorities)
    base = external_max + 1

    result: dict[SubMod, int] = {}
    for sm in scope_submods:
        new_p = base + (sm.priority - min_old)
        _check_overflow(new_p)
        result[sm] = new_p

    return result


def set_exact(target: SubMod, priority: int) -> dict[SubMod, int]:
    """Set an exact priority for a single submod.

    Raises:
        PriorityOverflowError: If priority exceeds INT32 range.
    """
    _check_overflow(priority)
    return {target: priority}


def shift(
    submods: list[SubMod],
    floor_priority: int,
) -> dict[SubMod, int]:
    """Shift a group of submods so the lowest lands at floor_priority,
    preserving relative gaps.

    Args:
        submods: The submods to shift.
        floor_priority: The target priority for the lowest submod.

    Returns:
        Dict of SubMod -> new_priority.

    Raises:
        PriorityOverflowError: If any computed priority exceeds INT32 range.

    Note:
        The caller is responsible for ensuring all submods belong to the same
        logical group. Passing submods from different mods preserves relative
        gaps but may produce semantically meaningless results.
    """
    if not submods:
        return {}

    old_priorities = [sm.priority for sm in submods]
    min_old = min(old_priorities)

    result: dict[SubMod, int] = {}
    for sm in submods:
        new_p = floor_priority + (sm.priority - min_old)
        _check_overflow(new_p)
        result[sm] = new_p

    return result
