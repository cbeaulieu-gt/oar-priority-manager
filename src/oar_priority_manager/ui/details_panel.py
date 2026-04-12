"""Details panel — read-only metadata for the currently selected tree node.

See spec §7.3. Shows different content for mod/replacer/submod selection levels.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from oar_priority_manager.core.models import OverrideSource
from oar_priority_manager.ui.tree_model import NodeType, TreeNode


class DetailsPanel(QWidget):
    """Bottom section of left column — read-only metadata."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self._label = QLabel("Select an item in the tree to see details.")
        self._label.setWordWrap(True)
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._label)
        layout.addStretch()

    def update_selection(self, node: TreeNode | None) -> None:
        """Update display based on the selected tree node.

        Args:
            node: The selected TreeNode, or None to clear the panel.
                  For MOD nodes, aggregates data from child replacer/submod nodes.
                  For REPLACER nodes, aggregates data from child submod nodes.
                  For SUBMOD nodes, shows full metadata for the individual submod.
        """
        if node is None or node.node_type == NodeType.ROOT:
            self._label.setText("Select an item in the tree to see details.")
            return

        if node.node_type == NodeType.MOD:
            self._label.setText(self._render_mod(node))
        elif node.node_type == NodeType.REPLACER:
            self._label.setText(self._render_replacer(node))
        elif node.node_type == NodeType.SUBMOD:
            if node.submod is None:
                self._label.setText("Select an item in the tree to see details.")
            else:
                self._label.setText(self._render_submod(node))

    # ------------------------------------------------------------------
    # Per-level renderers
    # ------------------------------------------------------------------

    def _render_mod(self, node: TreeNode) -> str:
        """Build rich HTML for a MOD-level node.

        Aggregates counts across all descendant replacer and submod nodes.

        Args:
            node: A MOD-level TreeNode whose children are REPLACER nodes.

        Returns:
            An HTML string suitable for a QLabel in RichText mode.
        """
        replacer_nodes = node.children
        submod_nodes = [
            sub
            for rep in replacer_nodes
            for sub in rep.children
            if sub.submod is not None
        ]
        all_submods = [sn.submod for sn in submod_nodes if sn.submod is not None]

        n_replacers = len(replacer_nodes)
        n_submods = len(all_submods)
        n_animations = sum(len(sm.animations) for sm in all_submods)
        n_overridden = sum(1 for sm in all_submods if sm.is_overridden)
        n_disabled = sum(1 for sm in all_submods if sm.disabled)

        # Attempt to derive the filesystem path from the first submod's config_path.
        # config_path is e.g. .../mods/<Mo2Mod>/meshes/.../replacer/submod/config.json
        # We want the MO2 mod folder itself: config_path.parents[len(OAR_REL)+1+1+1]
        path_str = ""
        if all_submods:
            from oar_priority_manager.core.models import OAR_REL
            # OAR_REL has N parts; submod dir is at offset N+1 from the mod root,
            # and config.json is one more level down.
            oar_depth = len(OAR_REL.parts)  # e.g. 4 for meshes/actors/.../OpenAnimationReplacer
            # config.json -> submod dir -> replacer dir -> OAR_REL (oar_depth parts) -> mod root
            # That's 1 (config) + 1 (submod) + 1 (replacer) + oar_depth = oar_depth + 3
            try:
                mod_root = all_submods[0].config_path.parents[oar_depth + 2]
                path_str = str(mod_root)
            except IndexError:
                path_str = ""

        lines = [
            f"<b>{node.display_name}</b>",
        ]
        if path_str:
            lines.append(f"<span style='color:gray'>{path_str}</span>")
        lines.append(
            f"Replacers: <b>{n_replacers}</b> &nbsp;·&nbsp; "
            f"Submods: <b>{n_submods}</b> &nbsp;·&nbsp; "
            f"Animations: <b>{n_animations}</b>"
        )
        lines.append(
            f"Priority overrides: <b>{n_overridden}</b> of {n_submods} submods"
        )
        if n_disabled:
            lines.append(
                f"<span style='color:red'>Disabled: {n_disabled}</span>"
            )
        return "<br>".join(lines)

    def _render_replacer(self, node: TreeNode) -> str:
        """Build rich HTML for a REPLACER-level node.

        Aggregates counts across all child submod nodes.

        Args:
            node: A REPLACER-level TreeNode whose children are SUBMOD nodes.

        Returns:
            An HTML string suitable for a QLabel in RichText mode.
        """
        all_submods = [sn.submod for sn in node.children if sn.submod is not None]

        n_submods = len(all_submods)
        n_animations = sum(len(sm.animations) for sm in all_submods)
        n_overridden = sum(1 for sm in all_submods if sm.is_overridden)

        parent_name = node.parent.display_name if node.parent else ""

        priority_range_str = ""
        if all_submods:
            priorities = [sm.priority for sm in all_submods]
            p_min, p_max = min(priorities), max(priorities)
            if p_min == p_max:
                priority_range_str = f"Priority: <b>{p_min:,}</b>"
            else:
                priority_range_str = (
                    f"Priority range: <b>{p_min:,}</b> – <b>{p_max:,}</b>"
                )

        lines = [
            f"<b>{node.display_name}</b>",
        ]
        if parent_name:
            lines.append(f"<span style='color:gray'>in {parent_name}</span>")
        lines.append(
            f"Submods: <b>{n_submods}</b> &nbsp;·&nbsp; "
            f"Animations: <b>{n_animations}</b>"
        )
        if priority_range_str:
            lines.append(priority_range_str)
        lines.append(
            f"Priority overrides: <b>{n_overridden}</b> of {n_submods} submods"
        )
        return "<br>".join(lines)

    def _render_submod(self, node: TreeNode) -> str:
        """Build rich HTML for a SUBMOD-level node.

        Shows full metadata for the individual submod including override
        provenance, condition summary, and warning badges.

        Args:
            node: A SUBMOD-level TreeNode with a non-None submod field.

        Returns:
            An HTML string suitable for a QLabel in RichText mode.
        """
        submod = node.submod
        assert submod is not None  # caller guarantees this

        lines = [
            f"<b>{submod.name}</b>",
        ]

        # Filesystem path (parent of config.json = submod directory)
        lines.append(
            f"<span style='color:gray'>{submod.config_path.parent}</span>"
        )

        # Enabled / Disabled badge
        if submod.disabled:
            lines.append("<span style='color:red'><b>DISABLED</b></span>")

        # Overridden badge
        if submod.is_overridden:
            lines.append("<span style='color:#ccaa00'><b>OVERRIDDEN</b></span>")

        # Description (optional)
        if submod.description:
            lines.append(
                f"<i><span style='color:gray'>{submod.description}</span></i>"
            )

        # MO2 source
        lines.append(f"MO2 source: <code>{submod.mo2_mod}</code>")

        # Priority (with "was X" if overridden)
        priority_line = f"Priority: <b>{submod.priority:,}</b>"
        if submod.is_overridden:
            priority_line += (
                f" &nbsp;<span style='color:#aa4'>(was {submod.source_priority:,})</span>"
            )
        lines.append(priority_line)

        # Animation count
        lines.append(f"Animations: {len(submod.animations)} files")

        # Config-only indicator (no animations — pure toggle/flag submod)
        if submod.is_config_only:
            lines.append(
                "<span style='color:#6af'><b>CONFIG-ONLY</b>"
                " \u2014 toggle flag, no animations to replace</span>"
            )

        # Condition summary
        n_conditions = len(submod.conditions) if isinstance(submod.conditions, list) else (
            len(submod.conditions) if submod.conditions else 0
        )
        n_types = len(submod.condition_types_present)
        lines.append(f"Conditions: {n_conditions} entries · {n_types} types")

        # Override source label
        source_label = _override_source_label(submod.override_source)
        lines.append(f"<span style='color:gray'>{source_label}</span>")

        # External override badge
        if (
            submod.override_source == OverrideSource.OVERWRITE
            and not submod.override_is_ours
        ):
            lines.append(
                "<span style='color:orange'><b>&#9888; EXTERNAL OVERRIDE</b></span>"
            )

        return "<br>".join(lines)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _override_source_label(source: OverrideSource) -> str:
    """Map an OverrideSource enum value to a human-readable label.

    Args:
        source: The OverrideSource enum value to map.

    Returns:
        A human-readable string describing where the effective priority
        was read from.
    """
    if source == OverrideSource.OVERWRITE:
        return "Override source: MO2 Overwrite"
    if source == OverrideSource.USER_JSON:
        return "Override source: user.json in source"
    return "Override source: config.json"
