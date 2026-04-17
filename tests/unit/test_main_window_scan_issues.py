"""Tests for MainWindow's Scan issues wiring (issue #51, Task 4).

Uses the MagicMock-as-self pattern from test_main_window_advanced.py —
we do NOT instantiate a real MainWindow because that pulls in MO2
instance plumbing the unit tests do not have.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from oar_priority_manager.core.models import OverrideSource, SubMod
from oar_priority_manager.ui.main_window import MainWindow


def _sm(name: str, warnings: list[str]) -> SubMod:
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
        warnings=warnings,
    )


class TestRefreshWarningCount:
    def test_counts_submods_with_warnings(self) -> None:
        mock_self = MagicMock()
        mock_self._submods = [
            _sm("a", []),
            _sm("b", ["boom"]),
            _sm("c", ["x", "y"]),
        ]
        MainWindow._refresh_warning_count(mock_self)
        mock_self._search_bar.set_scan_issues_count.assert_called_once_with(2)
        assert mock_self._warning_count == 2

    def test_zero_when_no_warnings(self) -> None:
        mock_self = MagicMock()
        mock_self._submods = [_sm("a", [])]
        MainWindow._refresh_warning_count(mock_self)
        mock_self._search_bar.set_scan_issues_count.assert_called_once_with(0)


class TestOnScanIssuesRequested:
    def test_opens_new_pane_first_time(self) -> None:
        mock_self = MagicMock()
        mock_self._submods = [_sm("a", ["File not found: C:/x"])]
        mock_self._scan_issues_pane = None
        with patch(
            "oar_priority_manager.ui.main_window.ScanIssuesPane"
        ) as PaneCls:
            pane_inst = MagicMock()
            PaneCls.return_value = pane_inst
            MainWindow._on_scan_issues_requested(mock_self)
            # ScanIssuesPane was instantiated with the entry list and self as parent
            assert PaneCls.call_count == 1
            args, kwargs = PaneCls.call_args
            assert kwargs["parent"] is mock_self
            # navigate_to_submod connected to the bridge slot
            pane_inst.navigate_to_submod.connect.assert_called_once_with(
                mock_self._navigate_from_scan_issues
            )
            pane_inst.show.assert_called_once()
            pane_inst.raise_.assert_called_once()
            pane_inst.activateWindow.assert_called_once()
            assert mock_self._scan_issues_pane is pane_inst

    def test_reuses_existing_pane_and_refreshes_entries(self) -> None:
        mock_self = MagicMock()
        mock_self._submods = [_sm("a", ["File not found: C:/x"])]
        existing = MagicMock()
        mock_self._scan_issues_pane = existing
        with patch(
            "oar_priority_manager.ui.main_window.ScanIssuesPane"
        ) as PaneCls:
            MainWindow._on_scan_issues_requested(mock_self)
            # Should NOT construct a second pane
            PaneCls.assert_not_called()
            existing.set_entries.assert_called_once()
            existing.show.assert_called_once()
            existing.raise_.assert_called_once()
            existing.activateWindow.assert_called_once()


class TestNavigateFromScanIssues:
    def test_delegates_to_tree_panel_select_submod(self) -> None:
        mock_self = MagicMock()
        sm = _sm("nav", [])
        MainWindow._navigate_from_scan_issues(mock_self, sm)
        mock_self._tree_panel.select_submod.assert_called_once_with(sm)
