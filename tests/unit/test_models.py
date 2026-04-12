"""Tests for core data model types."""

from pathlib import Path

from oar_priority_manager.core.models import (
    IllegalMutationError,
    OverrideSource,
    PriorityStack,
    SubMod,
)


def test_submod_creation():
    """SubMod can be constructed with all required fields."""
    sm = SubMod(
        mo2_mod="Female Combat Pack v2.3",
        replacer="AMA",
        name="heavy",
        description="Heavy armor combat idles",
        priority=500,
        source_priority=300,
        disabled=False,
        config_path=Path("C:/mods/FCP/meshes/actors/character/animations/OpenAnimationReplacer/AMA/heavy/config.json"),
        override_source=OverrideSource.OVERWRITE,
        override_is_ours=True,
        raw_dict={"name": "heavy", "priority": 500},
        animations=["mt_idle.hkx", "mt_walkforward.hkx"],
        conditions={"type": "AND", "conditions": []},
        condition_types_present={"IsFemale", "IsInCombat"},
        condition_types_negated={"IsWearingHelmet"},
        warnings=[],
    )
    assert sm.mo2_mod == "Female Combat Pack v2.3"
    assert sm.priority == 500
    assert sm.source_priority == 300
    assert sm.override_source == OverrideSource.OVERWRITE
    assert sm.override_is_ours is True
    assert len(sm.animations) == 2
    assert "IsFemale" in sm.condition_types_present
    assert "IsWearingHelmet" in sm.condition_types_negated


def test_submod_has_warnings():
    """SubMod with non-empty warnings list is considered a warning item."""
    sm = SubMod(
        mo2_mod="Broken Mod",
        replacer="rep",
        name="bad",
        description="",
        priority=0,
        source_priority=0,
        disabled=False,
        config_path=Path("C:/mods/Broken/config.json"),
        override_source=OverrideSource.SOURCE,
        override_is_ours=False,
        raw_dict={},
        animations=[],
        conditions={},
        condition_types_present=set(),
        condition_types_negated=set(),
        warnings=["Missing required field: priority"],
    )
    assert sm.has_warnings is True


def test_submod_no_warnings():
    sm = SubMod(
        mo2_mod="Good Mod",
        replacer="rep",
        name="ok",
        description="",
        priority=100,
        source_priority=100,
        disabled=False,
        config_path=Path("C:/mods/Good/config.json"),
        override_source=OverrideSource.SOURCE,
        override_is_ours=False,
        raw_dict={"name": "ok", "priority": 100},
        animations=["mt_idle.hkx"],
        conditions={},
        condition_types_present=set(),
        condition_types_negated=set(),
        warnings=[],
    )
    assert sm.has_warnings is False


def test_override_source_values():
    """OverrideSource enum has the three expected values."""
    assert OverrideSource.SOURCE.value == "source"
    assert OverrideSource.USER_JSON.value == "user_json"
    assert OverrideSource.OVERWRITE.value == "overwrite"


def test_priority_stack_creation():
    """PriorityStack holds an animation filename and a list of competitors."""
    stack = PriorityStack(
        animation_filename="mt_idle.hkx",
        competitors=[],
    )
    assert stack.animation_filename == "mt_idle.hkx"
    assert stack.competitors == []


def test_illegal_mutation_error():
    """IllegalMutationError can be raised with field details."""
    err = IllegalMutationError("conditions", "original_value", "new_value")
    assert "conditions" in str(err)
    assert isinstance(err, Exception)
