"""UI tree model for OAR Priority Manager.

Builds a Mod -> Replacer -> SubMod hierarchy from a flat list[SubMod], and
provides a SearchIndex for the unified search bar.

See spec §6.2 (tree_model), §7.3 (tree sort order):
  - Mods: alphabetical
  - Replacers: alphabetical
  - Submods: priority descending
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import NamedTuple

from oar_priority_manager.core.models import SubMod


class NodeType(Enum):
    """Identifies the role of a node in the three-level tree.

    ROOT is the invisible container at the top; MOD, REPLACER, and SUBMOD
    correspond to each level of the OAR directory hierarchy.
    """

    ROOT = auto()
    MOD = auto()
    REPLACER = auto()
    SUBMOD = auto()


@dataclass
class TreeNode:
    """One node in the Mod -> Replacer -> SubMod display tree.

    Attributes:
        display_name: The human-readable label shown in the UI.
        node_type: Which level of the hierarchy this node occupies.
        children: Ordered child nodes (see §7.3 for sort rules).
        submod: The underlying SubMod, populated only for SUBMOD nodes.
        parent: The parent TreeNode (None for ROOT).
        auto_expand: True when this REPLACER node is the sole replacer
            under its parent MOD — the UI should expand it automatically.
        condition_presets: conditionPresets dict from the replacer-level
            config.json. Populated only on REPLACER nodes; empty for others.
    """

    display_name: str
    node_type: NodeType
    children: list[TreeNode] = field(default_factory=list)
    submod: SubMod | None = None
    parent: TreeNode | None = field(default=None, repr=False)
    auto_expand: bool = False
    condition_presets: dict = field(default_factory=dict)


def build_tree(submods: list[SubMod]) -> TreeNode:
    """Construct the three-level display tree from a flat SubMod list.

    Sort order per spec §7.3:
      - MOD nodes: alphabetical by display_name (case-sensitive)
      - REPLACER nodes: alphabetical by display_name (case-sensitive)
      - SUBMOD nodes: priority descending (highest priority first)

    A REPLACER node gains ``auto_expand = True`` when its parent MOD has
    exactly one replacer, so the UI can expand it without user interaction.

    Args:
        submods: Flat list of SubMod instances from the scanner.

    Returns:
        The ROOT TreeNode whose children are the sorted MOD nodes.
    """
    root = TreeNode(display_name="", node_type=NodeType.ROOT)

    # Group: mod -> replacer -> [submods]
    # Use nested defaultdicts keyed by (mo2_mod, replacer)
    grouped: dict[str, dict[str, list[SubMod]]] = defaultdict(lambda: defaultdict(list))
    for sm in submods:
        grouped[sm.mo2_mod][sm.replacer].append(sm)

    # Build MOD nodes sorted alphabetically
    for mod_name in sorted(grouped.keys()):
        mod_node = TreeNode(
            display_name=mod_name,
            node_type=NodeType.MOD,
            parent=root,
        )

        replacer_dict = grouped[mod_name]
        single_replacer = len(replacer_dict) == 1

        # Build REPLACER nodes sorted alphabetically
        for rep_name in sorted(replacer_dict.keys()):
            # Get presets from first submod in this replacer (all share the same)
            first_submod = replacer_dict[rep_name][0]
            rep_presets = getattr(first_submod, "replacer_presets", {})
            rep_node = TreeNode(
                display_name=rep_name,
                node_type=NodeType.REPLACER,
                parent=mod_node,
                auto_expand=single_replacer,
                condition_presets=rep_presets,
            )

            # Build SUBMOD nodes sorted by priority descending
            for sm in sorted(replacer_dict[rep_name], key=lambda s: s.priority, reverse=True):
                sub_node = TreeNode(
                    display_name=sm.name,
                    node_type=NodeType.SUBMOD,
                    submod=sm,
                    parent=rep_node,
                )
                rep_node.children.append(sub_node)

            mod_node.children.append(rep_node)

        root.children.append(mod_node)

    return root


class SearchResult(NamedTuple):
    """A single hit returned from SearchIndex.search().

    Attributes:
        display_text: Human-readable label for this result (shown in the UI).
        node_type: Which level of the tree this result came from.
        node: The matching TreeNode so the UI can navigate to it.
    """

    display_text: str
    node_type: NodeType
    node: TreeNode


class SearchIndex:
    """Case-insensitive substring search across the entire tree.

    Indexes mod names, replacer names, submod names, and animation
    filenames. Animation hits resolve to the SUBMOD nodes that own
    the matching animation via ``conflict_map``.

    Args:
        root: The ROOT TreeNode produced by :func:`build_tree`.
        conflict_map: Mapping from animation filename to list[SubMod],
            as produced by the priority resolver. Used to resolve
            animation-filename hits back to tree nodes.
    """

    def __init__(self, root: TreeNode, conflict_map: dict[str, list[SubMod]]) -> None:
        self._root = root
        self._conflict_map = conflict_map
        # Maps id(SubMod) -> SUBMOD TreeNode for O(1) animation lookup
        self._submod_node_map: dict[int, TreeNode] = {}
        # Pre-built list of (lowercased_text, SearchResult) for non-animation entries
        self._entries: list[tuple[str, SearchResult]] = []
        self._build()

    def _build(self) -> None:
        """Walk the tree once to populate the search index."""
        self._entries.clear()
        self._submod_node_map.clear()

        def _walk(node: TreeNode) -> None:
            if node.node_type == NodeType.ROOT:
                for child in node.children:
                    _walk(child)
                return

            # Index this node's display name
            result = SearchResult(
                display_text=node.display_name,
                node_type=node.node_type,
                node=node,
            )
            self._entries.append((node.display_name.lower(), result))

            if node.node_type == NodeType.SUBMOD and node.submod is not None:
                # Register for animation-filename lookups
                self._submod_node_map[id(node.submod)] = node

            for child in node.children:
                _walk(child)

        _walk(self._root)

        # Index animation filenames from conflict_map
        for anim_filename, competing_submods in self._conflict_map.items():
            for sm in competing_submods:
                tree_node = self._submod_node_map.get(id(sm))
                if tree_node is None:
                    continue
                result = SearchResult(
                    display_text=anim_filename,
                    node_type=NodeType.SUBMOD,
                    node=tree_node,
                )
                self._entries.append((anim_filename.lower(), result))

    def search(self, query: str) -> list[SearchResult]:
        """Return all indexed entries whose text contains *query*.

        The match is case-insensitive substring. An empty query returns an
        empty list immediately so the search bar stays clear when unfocused.

        Args:
            query: The string typed into the search bar.

        Returns:
            List of :class:`SearchResult` in index order (no additional
            ranking — callers may sort as needed).
        """
        if not query:
            return []

        q = query.lower()
        return [result for text, result in self._entries if q in text]
