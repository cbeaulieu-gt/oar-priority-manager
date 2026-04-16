"""Condition-tree walker and search-bar filter engine for OAR Priority Manager.

See spec §6.2 (filter_engine), §7.6 (condition filter semantics),
§7.7 (advanced filter builder semantics).

This module operates purely on already-parsed condition data stored on SubMod
objects (condition_types_present, condition_types_negated).  It does NOT read
JSON files; that is the scanner's responsibility.

Public API
----------
extract_condition_types(conditions)
    Walk an OAR condition tree and return (present, negated) type-name sets.

FilterQuery
    Dataclass produced by parse_filter_query — holds required/excluded sets.

parse_filter_query(text)
    Parse a search-bar string such as "IsFemale NOT HasPerk" into a FilterQuery.

match_filter(present, negated, query)
    Test whether a SubMod's condition sets satisfy a FilterQuery.

AdvancedFilterQuery
    Dataclass holding three bucket sets for the advanced filter builder:
    required, any_of, excluded.

match_advanced_filter(present, negated, query)
    Test whether a SubMod's condition sets satisfy an AdvancedFilterQuery.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# OAR group-node types — these are structural and must NOT appear in the
# output sets produced by extract_condition_types.
_GROUP_TYPES: frozenset[str] = frozenset({"AND", "OR"})


def extract_condition_types(
    conditions: dict | list,
) -> tuple[set[str], set[str]]:
    """Walk an OAR condition tree and collect every leaf condition type name.

    Args:
        conditions: Either a list of condition dicts (the top-level format used
            by OAR config.json) or a dict that has a ``"conditions"`` key
            (a group node encountered during recursion or passed directly).

    Returns:
        A two-tuple ``(present, negated)`` where:

        * ``present`` — every non-group condition type name found anywhere in
          the tree.
        * ``negated`` — the subset of ``present`` where at least one occurrence
          had ``negated: True``.  A type can appear in both sets when it occurs
          both negated and non-negated in the same tree.
    """
    present: set[str] = set()
    negated: set[str] = set()
    _walk(conditions, present, negated)
    return present, negated


def _walk(node: dict | list, present: set[str], negated: set[str]) -> None:
    """Recursive helper that mutates *present* and *negated* in place.

    Args:
        node: The current tree node — either a list of siblings or a single
            condition/group dict.
        present: Accumulator for all condition type names seen so far.
        negated: Accumulator for condition type names seen with negated=True.
    """
    if isinstance(node, list):
        for child in node:
            _walk(child, present, negated)
        return

    if not isinstance(node, dict):
        # Defensive: skip unexpected node types without crashing.
        return

    condition_type: str | None = node.get("condition")

    # If this dict has a "conditions" key it is a group node — recurse into
    # children.  We do this regardless of whether "condition" is AND/OR or
    # absent, to handle any variation in the serialised format.
    if "conditions" in node:
        _walk(node["conditions"], present, negated)
        # Group labels (AND, OR) are structural — do not add to present.
        return

    # Leaf condition node.
    if condition_type is not None and condition_type not in _GROUP_TYPES:
        present.add(condition_type)
        if node.get("negated", False):
            negated.add(condition_type)


# ---------------------------------------------------------------------------
# Filter query parsing and matching
# ---------------------------------------------------------------------------


@dataclass
class FilterQuery:
    """Parsed representation of a search-bar filter string.

    Attributes:
        required: Condition type names that MUST be present in a SubMod for it
            to pass the filter.  Corresponds to bare tokens in the query string.
        excluded: Condition type names that must NOT be present in a SubMod for
            it to pass the filter.  Corresponds to ``NOT <name>`` tokens.
    """

    required: set[str] = field(default_factory=set)
    excluded: set[str] = field(default_factory=set)


def parse_filter_query(text: str) -> FilterQuery:
    """Parse a free-text condition filter string into a :class:`FilterQuery`.

    Grammar (case-sensitive, whitespace-separated tokens)::

        query  ::= token*
        token  ::= "NOT" name | name
        name   ::= any non-whitespace string

    Examples::

        "IsFemale"                 → required={"IsFemale"}, excluded=set()
        "NOT HasPerk"              → required=set(), excluded={"HasPerk"}
        "IsFemale NOT HasPerk"     → required={"IsFemale"}, excluded={"HasPerk"}
        ""                         → required=set(), excluded=set()

    Args:
        text: Raw text from the UI search bar.

    Returns:
        A :class:`FilterQuery` with the parsed required and excluded sets.
    """
    query = FilterQuery()
    tokens = text.split()
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token == "NOT":
            # Consume the next token as the excluded term (if present).
            if i + 1 < len(tokens):
                query.excluded.add(tokens[i + 1])
                i += 2
            else:
                # Trailing "NOT" with no following name — skip silently.
                i += 1
        else:
            query.required.add(token)
            i += 1
    return query


def match_filter(
    present: set[str],
    negated: set[str],  # noqa: ARG001 — reserved for future semantics
    query: FilterQuery,
) -> bool:
    """Test whether a SubMod's condition sets satisfy *query*.

    The ``negated`` parameter is accepted for API completeness and future
    extension (e.g. filtering *only* on negated occurrences) but is not used
    by the current MVP semantics.

    Matching rules (spec §7.6):

    * An empty query (no required, no excluded tokens) matches every SubMod.
    * All required type names must appear in ``present``.
    * None of the excluded type names may appear in ``present``.

    Args:
        present: Set of condition type names found anywhere in the SubMod's
            condition tree (i.e. ``SubMod.condition_types_present``).
        negated: Set of condition type names that appeared with ``negated:
            True`` (i.e. ``SubMod.condition_types_negated``).  Currently unused.
        query: The parsed filter produced by :func:`parse_filter_query`.

    Returns:
        ``True`` if the SubMod passes the filter, ``False`` otherwise.
    """
    # All required types must be present.
    if not query.required.issubset(present):
        return False
    # No excluded type may be present.
    return not (query.excluded & present)


# ---------------------------------------------------------------------------
# Advanced filter query (three-bucket semantics — spec §7.7)
# ---------------------------------------------------------------------------


@dataclass
class AdvancedFilterQuery:
    """Filter state produced by the advanced filter builder dialog.

    Holds three independent bucket sets that are combined with AND semantics
    when evaluating a SubMod.  See :func:`match_advanced_filter` for rules.

    Attributes:
        required: Condition type names that MUST ALL be present in a SubMod's
            ``condition_types_present`` set.  Empty means no restriction.
        any_of: Condition type names where AT LEAST ONE must be present.
            Empty means no restriction (the bucket is a no-op).
        excluded: Condition type names where NONE may be present.  Empty means
            no restriction.  EXCLUDED wins on conflict: if a name appears in
            both ``required`` and ``excluded``, the submod is rejected.
    """

    required: set[str] = field(default_factory=set)
    any_of: set[str] = field(default_factory=set)
    excluded: set[str] = field(default_factory=set)

    def is_empty(self) -> bool:
        """Return True iff all three bucket sets are empty.

        An empty query matches every submod (no filter is applied).

        Returns:
            ``True`` when ``required``, ``any_of``, and ``excluded`` are all
            empty; ``False`` otherwise.
        """
        return not self.required and not self.any_of and not self.excluded


def match_advanced_filter(
    present: set[str],
    negated: set[str],  # noqa: ARG001 — reserved for future semantics
    query: AdvancedFilterQuery,
) -> bool:
    """Test whether a SubMod's condition sets satisfy an :class:`AdvancedFilterQuery`.

    The ``negated`` parameter is accepted for API symmetry with
    :func:`match_filter` and for future extension, but is not used by the
    current MVP semantics.

    Matching rules (spec §7.7, plan §8 locked-in decisions):

    * An empty query (all three sets empty) matches every SubMod.
    * ``query.excluded & present`` must be empty — EXCLUDED wins on conflict.
      If a condition name appears in both ``required`` and ``excluded`` and is
      present, the submod is rejected (excluded check runs after required).
    * ``query.required.issubset(present)`` must hold.  Empty ``required``
      auto-passes.
    * If ``query.any_of`` is non-empty, ``query.any_of & present`` must be
      non-empty (at least one of the ANY OF names must be present).  An empty
      ``any_of`` is a no-op and does not restrict matching.

    Args:
        present: Set of condition type names found anywhere in the SubMod's
            condition tree (i.e. ``SubMod.condition_types_present``).
        negated: Set of condition type names that appeared with ``negated:
            True`` (i.e. ``SubMod.condition_types_negated``).  Currently unused.
        query: The advanced filter query produced by the filter builder dialog.

    Returns:
        ``True`` if the SubMod passes all three bucket checks, ``False``
        otherwise.
    """
    # EXCLUDED wins — check first so a conflict (name in both required and
    # excluded) correctly rejects the submod.
    if query.excluded & present:
        return False
    # All REQUIRED names must be present.
    if not query.required.issubset(present):
        return False
    # ANY OF: only restricts when the bucket is non-empty.
    return not (query.any_of and not query.any_of & present)
