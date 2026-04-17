"""Tests for the Scan issues button on SearchBar (issue #51, Task 2)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from oar_priority_manager.ui.search_bar import SearchBar


class TestScanIssuesButton:
    def test_button_exists_with_object_name(self, qtbot) -> None:
        bar = SearchBar()
        qtbot.addWidget(bar)
        btn = bar.findChild(type(bar._refresh_btn), "scan-issues-btn")
        assert btn is not None, "scan-issues-btn not found on SearchBar"

    def test_default_label_is_zero_and_disabled(self, qtbot) -> None:
        bar = SearchBar()
        qtbot.addWidget(bar)
        assert bar._scan_issues_btn.text() == "Scan issues (0)"
        assert not bar._scan_issues_btn.isEnabled()

    def test_set_count_updates_label_and_enables(self, qtbot) -> None:
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.set_scan_issues_count(7)
        assert bar._scan_issues_btn.text() == "Scan issues (7)"
        assert bar._scan_issues_btn.isEnabled()

    def test_set_count_zero_disables_button(self, qtbot) -> None:
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.set_scan_issues_count(3)
        bar.set_scan_issues_count(0)
        assert bar._scan_issues_btn.text() == "Scan issues (0)"
        assert not bar._scan_issues_btn.isEnabled()

    def test_click_emits_signal(self, qtbot) -> None:
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.set_scan_issues_count(1)
        with qtbot.waitSignal(bar.scan_issues_requested, timeout=500):
            bar._scan_issues_btn.click()

    def test_button_order_is_advanced_scan_refresh(self, qtbot) -> None:
        """Scan issues button sits between Advanced... and Refresh."""
        bar = SearchBar()
        qtbot.addWidget(bar)
        layout = bar.layout()
        # Locate widget indices for the three buttons.
        indices: dict[str, int] = {}
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if w is bar._advanced_btn:
                indices["advanced"] = i
            elif w is bar._scan_issues_btn:
                indices["scan"] = i
            elif w is bar._refresh_btn:
                indices["refresh"] = i
        assert indices["advanced"] < indices["scan"] < indices["refresh"]
