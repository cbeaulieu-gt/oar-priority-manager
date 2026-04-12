"""Tests for core/priority_resolver.py — stack building and mutation operations.

See spec §6.2 (priority_resolver), §5.4 (PriorityStack).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.core.priority_resolver import (
    INT32_MAX,
    INT32_MIN,
    PriorityOverflowError,
    build_stacks,
    move_to_top,
    set_exact,
    shift,
)


def _sm(
    name: str,
    priority: int,
    mo2_mod: str = "Mod",
    replacer: str = "Rep",
    animations: list[str] | None = None,
) -> SubMod:
    return SubMod(
        mo2_mod=mo2_mod,
        replacer=replacer,
        name=name,
        description="",
        priority=priority,
        source_priority=priority,
        disabled=False,
        config_path=Path(f"C:/fake/{mo2_mod}/{replacer}/{name}/config.json"),
        override_source=OverrideSource.SOURCE,
        override_is_ours=False,
        raw_dict={"name": name, "priority": priority},
        animations=animations or [],
        conditions={},
        warnings=[],
    )


class TestBuildStacks:
    def test_builds_from_conflict_map(self):
        conflict_map = {
            "mt_idle.hkx": [
                _sm("high", 500, animations=["mt_idle.hkx"]),
                _sm("low", 100, animations=["mt_idle.hkx"]),
            ],
        }
        stacks = build_stacks(conflict_map)
        assert len(stacks) == 1
        assert stacks[0].animation_filename == "mt_idle.hkx"
        assert len(stacks[0].competitors) == 2
        assert stacks[0].competitors[0].priority == 500

    def test_stacks_sorted_alphabetically(self):
        conflict_map = {
            "mt_walkforward.hkx": [_sm("a", 100, animations=["mt_walkforward.hkx"])],
            "mt_idle.hkx": [_sm("b", 200, animations=["mt_idle.hkx"])],
        }
        stacks = build_stacks(conflict_map)
        names = [s.animation_filename for s in stacks]
        assert names == ["mt_idle.hkx", "mt_walkforward.hkx"]


class TestMoveToTopSubmod:
    def test_single_submod_gets_max_plus_one(self):
        target = _sm("you", 100, animations=["mt_idle.hkx"])
        competitor = _sm("other", 500, animations=["mt_idle.hkx"])
        conflict_map = {"mt_idle.hkx": [competitor, target]}

        new_priorities = move_to_top(target, conflict_map, scope="submod")
        assert new_priorities == {target: 501}

    def test_already_winning_stays_same(self):
        target = _sm("you", 500, animations=["mt_idle.hkx"])
        competitor = _sm("other", 100, animations=["mt_idle.hkx"])
        conflict_map = {"mt_idle.hkx": [target, competitor]}

        new_priorities = move_to_top(target, conflict_map, scope="submod")
        # Already #1 everywhere — no change needed
        assert new_priorities == {}

    def test_multiple_stacks_uses_global_max(self):
        target = _sm("you", 100, animations=["a.hkx", "b.hkx"])
        comp_a = _sm("ca", 300, animations=["a.hkx"])
        comp_b = _sm("cb", 700, animations=["b.hkx"])
        conflict_map = {
            "a.hkx": [comp_a, target],
            "b.hkx": [comp_b, target],
        }
        new_priorities = move_to_top(target, conflict_map, scope="submod")
        assert new_priorities[target] == 701


class TestMoveToTopReplacerScope:
    def test_preserves_relative_ordering(self):
        """Floor-anchored shift: (global_max+1) + (old - min(old_in_scope))"""
        sub_a = _sm("a", 100, mo2_mod="MyMod", replacer="Rep", animations=["idle.hkx"])
        sub_b = _sm("b", 200, mo2_mod="MyMod", replacer="Rep", animations=["idle.hkx"])
        competitor = _sm("ext", 500, mo2_mod="Other", animations=["idle.hkx"])
        conflict_map = {"idle.hkx": [competitor, sub_b, sub_a]}

        new_priorities = move_to_top(sub_a, conflict_map, scope="replacer")
        # global_max of external competitors = 500
        # min(old_in_scope) = 100, so:
        # sub_a: 501 + (100-100) = 501
        # sub_b: 501 + (200-100) = 601
        assert new_priorities[sub_a] == 501
        assert new_priorities[sub_b] == 601


class TestMoveToTopModScope:
    def test_mod_scope_includes_all_replacers(self):
        sub_a = _sm("a", 100, mo2_mod="MyMod", replacer="Rep1", animations=["idle.hkx"])
        sub_b = _sm("b", 300, mo2_mod="MyMod", replacer="Rep2", animations=["idle.hkx"])
        competitor = _sm("ext", 500, mo2_mod="Other", animations=["idle.hkx"])
        conflict_map = {"idle.hkx": [competitor, sub_b, sub_a]}

        new_priorities = move_to_top(sub_a, conflict_map, scope="mod")
        # Both submods from MyMod get shifted
        assert sub_a in new_priorities
        assert sub_b in new_priorities
        assert new_priorities[sub_a] == 501  # 501 + (100-100)
        assert new_priorities[sub_b] == 701  # 501 + (300-100)


class TestOverflowGuard:
    def test_rejects_overflow(self):
        target = _sm("you", 100, animations=["idle.hkx"])
        competitor = _sm("other", INT32_MAX, animations=["idle.hkx"])
        conflict_map = {"idle.hkx": [competitor, target]}
        with pytest.raises(PriorityOverflowError):
            move_to_top(target, conflict_map, scope="submod")

    def test_rejects_negative_overflow_set_exact(self):
        target = _sm("you", 100, animations=["idle.hkx"])
        with pytest.raises(PriorityOverflowError):
            set_exact(target, INT32_MIN - 1)

    def test_rejects_negative_overflow_shift(self):
        sub_a = _sm("a", 0, animations=["idle.hkx"])
        sub_b = _sm("b", 100, animations=["idle.hkx"])
        with pytest.raises(PriorityOverflowError):
            shift([sub_a, sub_b], floor_priority=INT32_MIN - 1)


class TestSetExact:
    def test_sets_specific_priority(self):
        target = _sm("you", 100, animations=["idle.hkx"])
        result = set_exact(target, 999)
        assert result == {target: 999}

    def test_rejects_overflow(self):
        target = _sm("you", 100, animations=["idle.hkx"])
        with pytest.raises(PriorityOverflowError):
            set_exact(target, INT32_MAX + 1)


class TestShift:
    def test_floor_anchored_shift(self):
        sub_a = _sm("a", 100, mo2_mod="MyMod", replacer="Rep", animations=["idle.hkx"])
        sub_b = _sm("b", 200, mo2_mod="MyMod", replacer="Rep", animations=["idle.hkx"])
        new_priorities = shift([sub_a, sub_b], floor_priority=500)
        # min = 100, so a -> 500+(100-100)=500, b -> 500+(200-100)=600
        assert new_priorities[sub_a] == 500
        assert new_priorities[sub_b] == 600

    def test_shift_preserves_gaps(self):
        sub_a = _sm("a", 100, animations=["idle.hkx"])
        sub_b = _sm("b", 150, animations=["idle.hkx"])
        sub_c = _sm("c", 300, animations=["idle.hkx"])
        new_priorities = shift([sub_a, sub_b, sub_c], floor_priority=1000)
        # Gaps: 100->150 is 50, 150->300 is 150. Preserved.
        assert new_priorities[sub_a] == 1000
        assert new_priorities[sub_b] == 1050
        assert new_priorities[sub_c] == 1200

    def test_rejects_overflow(self):
        sub_a = _sm("a", 0, animations=["idle.hkx"])
        sub_b = _sm("b", INT32_MAX, animations=["idle.hkx"])
        with pytest.raises(PriorityOverflowError):
            shift([sub_a, sub_b], floor_priority=1)
