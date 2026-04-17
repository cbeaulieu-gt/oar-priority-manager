"""Non-modal log pane for scan warnings (issue #51, spec §7.8).

Presents every ``WarningEntry`` collected from the current submod list
in a five-column table. Double-clicking a row emits ``navigate_to_submod``
carrying the offending ``SubMod`` — the main window hooks this signal
up to ``TreePanel.select_submod`` so the tree highlights the entry.

The dialog is intentionally non-modal: the user can keep it open while
clicking around the tree and inspecting details. The main window caches
the instance so repeated clicks on the toolbar button re-focus rather
than spawn duplicates.

Public API
----------
ScanIssuesPane
"""
from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from oar_priority_manager.core.models import SubMod
from oar_priority_manager.core.warning_report import WarningEntry

_COLUMN_HEADERS: tuple[str, ...] = (
    "Severity",
    "Submod",
    "File",
    "Error type",
    "Line",
)
# QTableWidgetItem user-role slot that stores the SubMod for the row so
# we can round-trip from a clicked item back to the domain object.
_SUBMOD_ROLE = Qt.ItemDataRole.UserRole + 1


class ScanIssuesPane(QDialog):
    """Non-modal log pane listing every scan warning.

    Signals:
        navigate_to_submod: Emitted with a ``SubMod`` when the user
            double-clicks a row (or presses Enter on a selected row).

    Attributes:
        _entries: Current list of WarningEntry rendered in the table.
        _table: QTableWidget — five columns, one row per entry.
        _placeholder: QLabel shown when ``_entries`` is empty.
        _copy_btn: QPushButton — dumps the TSV-formatted rows to the
            system clipboard.
        _close_btn: QPushButton — closes the dialog.
    """

    navigate_to_submod = Signal(object)  # payload: SubMod

    def __init__(
        self,
        entries: Iterable[WarningEntry],
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the pane and populate rows from *entries*.

        Args:
            entries: Initial list of WarningEntry. May be empty — the
                pane shows a "No warnings" placeholder in that case.
            parent: Optional parent widget. Typically the MainWindow so
                the dialog inherits application icon and focus stacking.
        """
        super().__init__(parent)
        self.setWindowTitle("Scan Issues")
        self.setModal(False)
        self.resize(900, 500)

        self._entries: list[WarningEntry] = list(entries)
        self._build_ui()
        self._populate()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construct child widgets and layouts."""
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        self._placeholder = QLabel(
            "No warnings found in the current scan."
        )
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._placeholder)

        self._table = QTableWidget(0, len(_COLUMN_HEADERS))
        self._table.setHorizontalHeaderLabels(list(_COLUMN_HEADERS))
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.itemDoubleClicked.connect(self._on_row_activated)
        root.addWidget(self._table, stretch=1)

        # Button row
        btn_row = QHBoxLayout()
        self._copy_btn = QPushButton("Copy All")
        self._copy_btn.setToolTip(
            "Copy the entire warning list as tab-separated text."
        )
        self._copy_btn.clicked.connect(self._on_copy_all)
        btn_row.addWidget(self._copy_btn)
        btn_row.addStretch(1)
        self._close_btn = QPushButton("Close")
        self._close_btn.clicked.connect(self.close)
        btn_row.addWidget(self._close_btn)
        root.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Data population
    # ------------------------------------------------------------------

    def _populate(self) -> None:
        """Render ``self._entries`` into the table, swapping placeholder."""
        self._table.setRowCount(0)
        has_entries = bool(self._entries)
        self._placeholder.setVisible(not has_entries)
        self._table.setVisible(has_entries)

        for row, entry in enumerate(self._entries):
            self._table.insertRow(row)
            self._set_cell(row, 0, "\u26a0")
            self._set_cell(row, 1, entry.submod.display_path, entry.submod)
            self._set_cell(row, 2, str(entry.file_path))
            self._set_cell(row, 3, entry.error_type)
            line_text = str(entry.line) if entry.line is not None else "\u2014"
            self._set_cell(row, 4, line_text)
            # Tooltip on the full row points at the original message
            # so users can read long JSON error details without resizing.
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item is not None:
                    item.setToolTip(entry.message)

    def _set_cell(
        self,
        row: int,
        col: int,
        text: str,
        submod: SubMod | None = None,
    ) -> None:
        """Create a QTableWidgetItem with optional SubMod payload.

        Args:
            row: Zero-based row index (must already exist in the table).
            col: Zero-based column index.
            text: Display text.
            submod: When provided, stored under ``_SUBMOD_ROLE`` for the
                round-trip lookup in ``_on_row_activated``.
        """
        item = QTableWidgetItem(text)
        if submod is not None:
            item.setData(_SUBMOD_ROLE, submod)
        self._table.setItem(row, col, item)

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_row_activated(self, item: QTableWidgetItem) -> None:
        """Emit ``navigate_to_submod`` for the row's owning SubMod.

        The SubMod is stored on column-1's item under ``_SUBMOD_ROLE``.
        This handler resolves that regardless of which column the user
        actually double-clicked.
        """
        row = item.row()
        anchor = self._table.item(row, 1)
        if anchor is None:
            return
        submod = anchor.data(_SUBMOD_ROLE)
        if isinstance(submod, SubMod):
            self.navigate_to_submod.emit(submod)

    def _on_copy_all(self) -> None:
        """Copy the full table as TSV to the system clipboard."""
        lines = [
            "\t".join([
                entry.submod.display_path,
                str(entry.file_path),
                entry.error_type,
                str(entry.line) if entry.line is not None else "",
                entry.message,
            ])
            for entry in self._entries
        ]
        QGuiApplication.clipboard().setText("\n".join(lines))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_entries(self, entries: Iterable[WarningEntry]) -> None:
        """Replace the current rows with *entries* and re-render.

        Args:
            entries: New iterable of WarningEntry.
        """
        self._entries = list(entries)
        self._populate()
