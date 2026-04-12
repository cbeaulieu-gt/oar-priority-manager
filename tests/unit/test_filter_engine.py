"""Tests for core/filter_engine.py — structural condition-presence filter.

See spec §6.2 (filter_engine), §7.6 (condition filter semantics).
"""
from __future__ import annotations

from oar_priority_manager.core.filter_engine import (
    extract_condition_types,
    match_filter,
    parse_filter_query,
)


class TestExtractConditionTypes:
    def test_flat_condition_list(self):
        conditions = [
            {"condition": "IsFemale", "negated": False},
            {"condition": "IsInCombat", "negated": False},
        ]
        present, negated = extract_condition_types(conditions)
        assert present == {"IsFemale", "IsInCombat"}
        assert negated == set()

    def test_negated_condition(self):
        conditions = [
            {"condition": "IsFemale", "negated": False},
            {"condition": "IsWearingHelmet", "negated": True},
        ]
        present, negated = extract_condition_types(conditions)
        assert present == {"IsFemale", "IsWearingHelmet"}
        assert negated == {"IsWearingHelmet"}

    def test_nested_and_group(self):
        conditions = [
            {
                "condition": "AND",
                "conditions": [
                    {"condition": "IsFemale", "negated": False},
                    {"condition": "IsInCombat", "negated": False},
                ],
            },
        ]
        present, negated = extract_condition_types(conditions)
        assert "IsFemale" in present
        assert "IsInCombat" in present

    def test_nested_or_group(self):
        conditions = [
            {
                "condition": "OR",
                "conditions": [
                    {"condition": "HasKeyword", "negated": False},
                    {"condition": "HasPerk", "negated": False},
                ],
            },
        ]
        present, negated = extract_condition_types(conditions)
        assert present == {"HasKeyword", "HasPerk"}

    def test_type_in_both_present_and_negated(self):
        conditions = [
            {"condition": "IsFemale", "negated": False},
            {
                "condition": "AND",
                "conditions": [
                    {"condition": "IsFemale", "negated": True},
                ],
            },
        ]
        present, negated = extract_condition_types(conditions)
        assert "IsFemale" in present
        assert "IsFemale" in negated

    def test_empty_conditions(self):
        present, negated = extract_condition_types([])
        assert present == set()
        assert negated == set()

    def test_conditions_as_dict_with_conditions_key(self):
        conditions = {
            "type": "AND",
            "conditions": [
                {"condition": "IsFemale", "negated": False},
            ],
        }
        present, negated = extract_condition_types(conditions)
        assert "IsFemale" in present

    def test_deeply_nested(self):
        conditions = [
            {
                "condition": "AND",
                "conditions": [
                    {
                        "condition": "OR",
                        "conditions": [
                            {"condition": "DeepType", "negated": False},
                        ],
                    },
                ],
            },
        ]
        present, _ = extract_condition_types(conditions)
        assert "DeepType" in present


class TestParseFilterQuery:
    def test_simple_type_name(self):
        query = parse_filter_query("IsFemale")
        assert query.required == {"IsFemale"}
        assert query.excluded == set()

    def test_not_prefix(self):
        query = parse_filter_query("NOT IsInCombat")
        assert query.excluded == {"IsInCombat"}

    def test_multiple_terms(self):
        query = parse_filter_query("IsFemale IsInCombat")
        assert "IsFemale" in query.required
        assert "IsInCombat" in query.required

    def test_mixed_required_and_excluded(self):
        query = parse_filter_query("IsFemale NOT HasPerk")
        assert query.required == {"IsFemale"}
        assert query.excluded == {"HasPerk"}


class TestMatchFilter:
    def test_match_required(self):
        query = parse_filter_query("IsFemale")
        assert match_filter({"IsFemale", "IsInCombat"}, set(), query) is True

    def test_no_match_required(self):
        query = parse_filter_query("IsFemale")
        assert match_filter({"IsInCombat"}, set(), query) is False

    def test_excluded_rejects(self):
        query = parse_filter_query("NOT IsFemale")
        assert match_filter({"IsFemale"}, set(), query) is False

    def test_excluded_accepts_absent(self):
        query = parse_filter_query("NOT IsFemale")
        assert match_filter({"IsInCombat"}, set(), query) is True

    def test_empty_query_matches_all(self):
        query = parse_filter_query("")
        assert match_filter({"anything"}, set(), query) is True
