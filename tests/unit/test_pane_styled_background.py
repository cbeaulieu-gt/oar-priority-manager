"""Regression tests for WA_StyledBackground on panel root widgets (issue #98).

Root cause: Qt silently skips painting `background:` CSS rules on plain
QWidget subclasses unless WA_StyledBackground is set.  Borders rendered
correctly (different drawing path) but fills did not — making the three-tone
pane-hierarchy from custom.qss invisible.

These tests verify that the attribute is set at construction time so the QSS
`background:` rules in custom.qss can actually be painted.

See: https://doc.qt.io/qt-6/qt.html#WidgetAttribute-enum  (WA_StyledBackground)
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from oar_priority_manager.ui.conditions_panel import ConditionsPanel
from oar_priority_manager.ui.details_panel import DetailsPanel
from oar_priority_manager.ui.stacks_panel import StacksPanel


@pytest.fixture(scope="session")
def qapp():
    """Ensure a QApplication exists for widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestWAStyledBackground:
    """All three pane root widgets must have WA_StyledBackground enabled.

    Without it the QSS ``background:`` rule in custom.qss is silently
    ignored — borders render but fills do not.
    """

    def test_stacks_panel_has_styled_background(self, qapp, qtbot):
        """StacksPanel root must have WA_StyledBackground so custom.qss fills render."""
        panel = StacksPanel({})
        qtbot.addWidget(panel)
        assert panel.testAttribute(Qt.WidgetAttribute.WA_StyledBackground), (
            "StacksPanel is missing WA_StyledBackground — "
            "the QWidget#StacksPanel_root background: rule in custom.qss will be ignored"
        )

    def test_conditions_panel_has_styled_background(self, qapp, qtbot):
        """ConditionsPanel root must have WA_StyledBackground so custom.qss fills render."""
        panel = ConditionsPanel()
        qtbot.addWidget(panel)
        assert panel.testAttribute(Qt.WidgetAttribute.WA_StyledBackground), (
            "ConditionsPanel is missing WA_StyledBackground — "
            "the QWidget#ConditionsPanel_root background: rule in custom.qss will be ignored"
        )

    def test_details_panel_has_styled_background(self, qapp, qtbot):
        """DetailsPanel root must have WA_StyledBackground so custom.qss fills render."""
        panel = DetailsPanel()
        qtbot.addWidget(panel)
        assert panel.testAttribute(Qt.WidgetAttribute.WA_StyledBackground), (
            "DetailsPanel is missing WA_StyledBackground — "
            "the QWidget#DetailsPanel_root background: rule in custom.qss will be ignored"
        )

    def test_stacks_panel_object_name(self, qapp, qtbot):
        """StacksPanel must still have the correct object name for QSS targeting."""
        panel = StacksPanel({})
        qtbot.addWidget(panel)
        assert panel.objectName() == "StacksPanel_root"

    def test_conditions_panel_object_name(self, qapp, qtbot):
        """ConditionsPanel must still have the correct object name for QSS targeting."""
        panel = ConditionsPanel()
        qtbot.addWidget(panel)
        assert panel.objectName() == "ConditionsPanel_root"

    def test_details_panel_object_name(self, qapp, qtbot):
        """DetailsPanel must still have the correct object name for QSS targeting."""
        panel = DetailsPanel()
        qtbot.addWidget(panel)
        assert panel.objectName() == "DetailsPanel_root"
