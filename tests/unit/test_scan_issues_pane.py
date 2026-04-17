"""Tests for ScanIssuesPane (issue #51, Task 3)."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.core.warning_report import WarningEntry
from oar_priority_manager.ui.scan_issues_pane import ScanIssuesPane


def _sm(name: str = "bad") -> SubMod:
    return SubMod(
        mo2_mod="ModA",
        replacer="Rep",
        name=name,
        description="",
        priority=100,
        source_priority=100,
        disabled=False,
        config_path=Path(f"C:/mods/ModA/Rep/{name}/config.json"),
        override_source=OverrideSource.SOURCE,
        override_is_ours=False,
        raw_dict={},
        warnings=[],
    )


def _entry(
    sm: SubMod | None = None,
    file_path: Path | None = None,
    error_type: str = "JSON parse error",
    line: int | None = 12,
    message: str = "JSON parse error in C:/x/config.json: bad",
) -> WarningEntry:
    sm = sm or _sm()
    return WarningEntry(
        submod=sm,
        file_path=file_path or sm.config_path,
        error_type=error_type,
        line=line,
        message=message,
    )


class TestScanIssuesPane:
    def test_non_modal(self, qtbot) -> None:
        pane = ScanIssuesPane(entries=[])
        qtbot.addWidget(pane)
        # A non-modal dialog reports Qt.NonModal / Qt.WindowModal-or-less.
        assert pane.isModal() is False

    def test_empty_entries_shows_placeholder(self, qtbot) -> None:
        pane = ScanIssuesPane(entries=[])
        qtbot.addWidget(pane)
        pane.show()  # isVisible() propagates parent state; show first
        # Placeholder label visible; table row count is zero.
        assert pane._table.rowCount() == 0
        assert pane._placeholder.isVisible()

    def test_table_has_five_columns(self, qtbot) -> None:
        pane = ScanIssuesPane(entries=[_entry()])
        qtbot.addWidget(pane)
        pane.show()  # placeholder visibility requires a visible window tree
        assert pane._table.columnCount() == 5
        headers = [
            pane._table.horizontalHeaderItem(i).text()
            for i in range(pane._table.columnCount())
        ]
        assert headers == [
            "Severity", "Submod", "File", "Error type", "Line",
        ]

    def test_populates_rows_from_entries(self, qtbot) -> None:
        sm = _sm("bad1")
        entries = [_entry(sm=sm, line=12)]
        pane = ScanIssuesPane(entries=entries)
        qtbot.addWidget(pane)
        assert pane._table.rowCount() == 1
        row = 0
        assert pane._table.item(row, 1).text() == sm.display_path
        assert pane._table.item(row, 3).text() == "JSON parse error"
        assert pane._table.item(row, 4).text() == "12"

    def test_line_column_shows_dash_when_none(self, qtbot) -> None:
        entries = [_entry(line=None)]
        pane = ScanIssuesPane(entries=entries)
        qtbot.addWidget(pane)
        assert pane._table.item(0, 4).text() == "—"

    def test_double_click_emits_navigate_to_submod(self, qtbot) -> None:
        sm = _sm("nav")
        entries = [_entry(sm=sm)]
        pane = ScanIssuesPane(entries=entries)
        qtbot.addWidget(pane)
        with qtbot.waitSignal(pane.navigate_to_submod, timeout=500) as blocker:
            pane._table.itemDoubleClicked.emit(pane._table.item(0, 1))
        assert blocker.args == [sm]

    def test_close_button_closes_dialog(self, qtbot) -> None:
        pane = ScanIssuesPane(entries=[_entry()])
        qtbot.addWidget(pane)
        pane.show()
        assert pane.isVisible()
        pane._close_btn.click()
        assert not pane.isVisible()

    def test_copy_all_writes_tsv_to_clipboard(self, qtbot) -> None:
        sm = _sm("copy")
        entries = [
            _entry(sm=sm, error_type="Read error", line=None,
                   message="File not found: C:/x/user.json",
                   file_path=Path("C:/x/user.json")),
        ]
        pane = ScanIssuesPane(entries=entries)
        qtbot.addWidget(pane)
        pane._copy_btn.click()
        clipboard = QApplication.clipboard().text()
        # Format: <display_path>\t<file_path>\t<error_type>\t<line>\t<message>
        assert sm.display_path in clipboard
        assert "C:/x/user.json".replace("/", "\\") in clipboard or "C:/x/user.json" in clipboard
        assert "Read error" in clipboard
        assert "File not found" in clipboard

    def test_set_entries_replaces_rows(self, qtbot) -> None:
        pane = ScanIssuesPane(entries=[_entry()])
        qtbot.addWidget(pane)
        assert pane._table.rowCount() == 1
        pane.set_entries([_entry(), _entry(), _entry()])
        assert pane._table.rowCount() == 3
        pane.set_entries([])
        assert pane._table.rowCount() == 0
