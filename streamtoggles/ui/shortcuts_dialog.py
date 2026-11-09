"""Keyboard Shortcuts and help window for StreamToggles adhering to KDE HIG."""

from __future__ import annotations
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ShortcutsDialog(QDialog):
    """Modal dialog displaying keyboard shortcuts."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts — StreamToggles")
        self.setMinimumWidth(480)
        self.resize(520, 420)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        # 1. Application Shortcuts Group
        app_group = QGroupBox("Application Shortcuts")
        app_layout = QVBoxLayout(app_group)

        shortcuts = [
            ("Add New Toggle", "Ctrl+N"),
            ("Toggle Edit Mode", "Ctrl+E"),
            ("Target Host Settings", "Ctrl+,"),
            ("Show Keyboard Shortcuts", "Ctrl+? / F1"),
            ("Quit Application", "Ctrl+Q"),
        ]

        table = QTableWidget(len(shortcuts), 2)
        table.setHorizontalHeaderLabels(["Action", "Shortcut"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setShowGrid(False)
        table.setStyleSheet("QTableWidget { background-color: transparent; border: none; }")

        for row, (action, shortcut) in enumerate(shortcuts):
            action_item = QTableWidgetItem(action)
            shortcut_item = QTableWidgetItem(shortcut)
            shortcut_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            shortcut_item.setForeground(self.palette().highlight())
            table.setItem(row, 0, action_item)
            table.setItem(row, 1, shortcut_item)

        app_layout.addWidget(table)
        layout.addWidget(app_group)

        # 2. Global Shortcuts Group
        global_group = QGroupBox("Global Shortcuts (Wayland / KDE Plasma)")
        global_layout = QVBoxLayout(global_group)

        global_info = QLabel(
            "<b>Configured global hotkeys</b> allow toggles to fire system-wide—even when "
            "StreamToggles is minimized, unfocused, or when running full-screen games/OBS Studio."
        )
        global_info.setWordWrap(True)
        global_info.setStyleSheet("color: palette(placeholder-text);")
        global_layout.addWidget(global_info)

        layout.addWidget(global_group)

        # Dialog button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.accept)
        layout.addWidget(button_box)

    def present(self) -> None:
        """Compatibility helper matching Libadwaita dialog presentation."""
        self.show()
        self.raise_()
        self.activateWindow()


def create_shortcuts_window(parent: Optional[QWidget] = None) -> ShortcutsDialog:
    """Factory function for backward-compatible shortcut window creation."""
    return ShortcutsDialog(parent)
