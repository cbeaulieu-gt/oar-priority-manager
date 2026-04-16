"""Tests for AdvancedFilterQuery dataclass and match_advanced_filter() function.

Covers the pure-logic foundation for the advanced filter builder (Issue #49).
See plan §5 Task 1 and spec §7.7 for semantics.
"""
from __future__ import annotations

from oar_priority_manager.core.filter_engine import (
    AdvancedFilterQuery,
    match_advanced_filter,
)


class TestAdvancedFilterQuery:
    def test_default_constructed_is_empty(self):
        """A default-constructed AdvancedFilterQuery has all three sets empty."""
        query = AdvancedFilterQuery()
        assert query.required == set()
        assert query.any_of == set()
        assert query.excluded == set()

    def test_is_empty_returns_true_when_all_sets_empty(self):
        """is_empty() returns True when required, any_of, and excluded are all empty."""
        query = AdvancedFilterQuery()
        assert query.is_empty() is True

    def test_is_empty_returns_false_when_required_nonempty(self):
        """is_empty() returns False when required has at least one entry."""
        query = AdvancedFilterQuery(required={"IsFemale"})
        assert query.is_empty() is False

    def test_is_empty_returns_false_when_any_of_nonempty(self):
        """is_empty() returns False when any_of has at least one entry."""
        query = AdvancedFilterQuery(any_of={"IsFemale"})
        assert query.is_empty() is False

    def test_is_empty_returns_false_when_excluded_nonempty(self):
        """is_empty() returns False when excluded has at least one entry."""
        query = AdvancedFilterQuery(excluded={"IsFemale"})
        assert query.is_empty() is False


class TestMatchAdvancedFilter:
    # ------------------------------------------------------------------
    # Empty query
    # ------------------------------------------------------------------

    def test_empty_query_matches_nonempty_present(self):
        """An empty query (all three sets empty) matches any non-empty present set."""
        query = AdvancedFilterQuery()
        assert match_advanced_filter({"IsFemale", "IsInCombat"}, set(), query) is True

    def test_empty_query_matches_empty_present(self):
        """An empty query also matches a submod with no conditions at all."""
        query = AdvancedFilterQuery()
        assert match_advanced_filter(set(), set(), query) is True

    # ------------------------------------------------------------------
    # REQUIRED only
    # ------------------------------------------------------------------

    def test_required_only_matches_when_present(self):
        """REQUIRED={"A"}, present contains A → True."""
        query = AdvancedFilterQuery(required={"A"})
        assert match_advanced_filter({"A", "B"}, set(), query) is True

    def test_required_only_fails_when_absent(self):
        """REQUIRED={"A"}, present does NOT contain A → False."""
        query = AdvancedFilterQuery(required={"A"})
        assert match_advanced_filter({"B"}, set(), query) is False

    def test_required_all_must_be_present(self):
        """REQUIRED={"A","B"}, present contains only A → False (AND semantics)."""
        query = AdvancedFilterQuery(required={"A", "B"})
        assert match_advanced_filter({"A"}, set(), query) is False

    # ------------------------------------------------------------------
    # ANY OF only
    # ------------------------------------------------------------------

    def test_any_of_matches_when_one_present(self):
        """ANY_OF={"A","B"}, present contains B → True."""
        query = AdvancedFilterQuery(any_of={"A", "B"})
        assert match_advanced_filter({"B"}, set(), query) is True

    def test_any_of_fails_when_none_present(self):
        """ANY_OF={"A","B"}, present contains only C → False."""
        query = AdvancedFilterQuery(any_of={"A", "B"})
        assert match_advanced_filter({"C"}, set(), query) is False

    def test_any_of_fails_when_present_empty(self):
        """ANY_OF={"A","B"}, present is empty → False."""
        query = AdvancedFilterQuery(any_of={"A", "B"})
        assert match_advanced_filter(set(), set(), query) is False

    # ------------------------------------------------------------------
    # EXCLUDED only
    # ------------------------------------------------------------------

    def test_excluded_fails_when_term_is_present(self):
        """EXCLUDED={"A"}, present contains A → False."""
        query = AdvancedFilterQuery(excluded={"A"})
        assert match_advanced_filter({"A"}, set(), query) is False

    def test_excluded_passes_when_term_absent(self):
        """EXCLUDED={"A"}, present contains only B → True."""
        query = AdvancedFilterQuery(excluded={"A"})
        assert match_advanced_filter({"B"}, set(), query) is True

    # ------------------------------------------------------------------
    # Combined buckets (AND semantics across all three)
    # ------------------------------------------------------------------

    def test_combined_all_three_pass(self):
        """REQUIRED={"A"}, ANY_OF={"X","Y"}, EXCLUDED={"Z"}, present={"A","Y"} → True."""
        query = AdvancedFilterQuery(
            required={"A"},
            any_of={"X", "Y"},
            excluded={"Z"},
        )
        assert match_advanced_filter({"A", "Y"}, set(), query) is True

    def test_combined_excluded_present_causes_failure(self):
        """Same query but present also contains Z → False (excluded check fails)."""
        query = AdvancedFilterQuery(
            required={"A"},
            any_of={"X", "Y"},
            excluded={"Z"},
        )
        assert match_advanced_filter({"A", "Y", "Z"}, set(), query) is False

    def test_combined_any_of_not_satisfied_causes_failure(self):
        """REQUIRED={"A"}, ANY_OF={"X","Y"}, EXCLUDED={"Z"}, present={"A"} → False
        (ANY OF not satisfied because neither X nor Y is present)."""
        query = AdvancedFilterQuery(
            required={"A"},
            any_of={"X", "Y"},
            excluded={"Z"},
        )
        assert match_advanced_filter({"A"}, set(), query) is False

    # ------------------------------------------------------------------
    # EXCLUDED wins on conflict (§8 decision #1)
    # ------------------------------------------------------------------

    def test_excluded_wins_when_same_term_in_required_and_excluded(self):
        """If a term is in both REQUIRED and EXCLUDED and is present, EXCLUDED wins → False.

        REQUIRED={"A"}, EXCLUDED={"A"}, present={"A"}: REQUIRED is satisfied (A is
        present) but EXCLUDED is also triggered (A is present), so the submod is
        rejected. EXCLUDED always wins on conflict per plan §8 decision #1.
        """
        query = AdvancedFilterQuery(
            required={"A"},
            excluded={"A"},
        )
        assert match_advanced_filter({"A"}, set(), query) is False

    # ------------------------------------------------------------------
    # negated parameter is reserved — passing it should not break anything
    # ------------------------------------------------------------------

    def test_negated_parameter_is_accepted_and_ignored(self):
        """The negated parameter is reserved for future use; passing it must not crash."""
        query = AdvancedFilterQuery(required={"A"})
        # Non-empty negated set — should have zero effect on MVP matching.
        assert match_advanced_filter({"A"}, {"A"}, query) is True
