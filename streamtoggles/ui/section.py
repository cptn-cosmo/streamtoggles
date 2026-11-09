"""Visual canvas sections and management controls for StreamToggles adhering to modern KDE HIG."""

from __future__ import annotations
from typing import Any, Callable, Dict, Optional

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from streamtoggles.ui.flow_layout import FlowLayout


class SectionTitleRow(QLineEdit):
    """QLineEdit with helper methods for API compatibility."""

    def get_text(self) -> str:
        return self.text()

    def set_text(self, text: str) -> None:
        self.setText(text)


class SectionEditDialog(QDialog):
    """Dialog for creating or renaming a canvas section."""

    def __init__(
        self,
        parent: Optional[QWidget],
        section_data: Optional[Dict[str, Any]],
        on_save_callback: Callable[[Dict[str, Any]], None],
    ):
        super().__init__(parent)
        self.section_data = section_data or {}
        self.on_save = on_save_callback

        is_new = not bool(self.section_data.get("id"))
        self.setWindowTitle("Add Section" if is_new else "Edit Section")
        self.setMinimumWidth(380)

        self._build_ui()

    def get_title(self) -> str:
        return self.windowTitle()

    def present(self, _parent: Optional[QWidget] = None) -> None:
        self.show()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        desc_label = QLabel(
            "Sections organize buttons into distinct visual grids on the canvas."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: palette(placeholder-text);")
        layout.addWidget(desc_label)

        form_layout = QHBoxLayout()
        form_label = QLabel("Section Title:")
        self.title_input = SectionTitleRow()
        self.title_input.setPlaceholderText("e.g. OBS Scenes, Audio Controls")
        self.title_input.setText(self.section_data.get("title", ""))
        self.title_input.returnPressed.connect(self._on_save_clicked)
        self.title_row = self.title_input

        form_layout.addWidget(form_label)
        form_layout.addWidget(self.title_input)
        layout.addLayout(form_layout)

        self.exclusive_checkbox = QCheckBox(
            "Mutually exclusive toggles (only one toggle active at a time)"
        )
        self.exclusive_checkbox.setToolTip(
            "When enabled, activating any toggle button in this section will automatically de-illuminate and turn off any other active toggles in this section."
        )
        self.exclusive_checkbox.setChecked(bool(self.section_data.get("exclusive", False)))
        layout.addWidget(self.exclusive_checkbox)

        # Standard dialog button box adhering to KDE HIG
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_btn = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_btn:
            save_btn.setProperty("suggested", True)
        self.button_box.accepted.connect(self._on_save_clicked)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _on_save_clicked(self, *args: Any) -> None:
        title = self.title_input.text().strip()
        if not title:
            self.title_input.setStyleSheet("border: 1px solid palette(highlight);")
            self.title_input.setFocus()
            return

        saved_data = {
            "id": self.section_data.get("id", ""),
            "title": title,
            "exclusive": self.exclusive_checkbox.isChecked(),
        }
        self.on_save(saved_data)
        self.accept()


class SectionContainer(QWidget):
    """Container representing a distinct visual canvas section with header and responsive tile layout."""

    def __init__(
        self,
        title: str,
        section_id: str,
        is_default: bool = False,
        exclusive: bool = False,
        on_edit: Optional[Callable[[str], None]] = None,
        on_move: Optional[Callable[[str, int], None]] = None,
        on_delete: Optional[Callable[[str], None]] = None,
    ):
        super().__init__()
        self.title = title
        self.section_id = section_id
        self.is_default = is_default
        self.exclusive = exclusive
        self.on_edit = on_edit
        self.on_move = on_move
        self.on_delete = on_delete
        self.tiles_count = 0
        self.controls_box: Optional[QWidget] = None

        self._build_ui()

    def _build_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(12, 6, 12, 6)
        self.main_layout.setSpacing(6)

        # 1. Header Box
        self.header_layout = QHBoxLayout()
        self.header_layout.setSpacing(8)

        # Title Label
        self.title_label = QLabel(self.title)
        self.title_label.setObjectName("SectionTitle")
        self.header_layout.addWidget(self.title_label)

        if self.exclusive:
            self.exclusive_badge = QLabel("Exclusive")
            self.exclusive_badge.setObjectName("GroupBadge")
            self.exclusive_badge.setToolTip("Mutually exclusive: Only one toggle in this section can be active at a time")
            self.header_layout.addWidget(self.exclusive_badge)

        # Subtle separator line stretching horizontally
        self.separator = QFrame()
        self.separator.setObjectName("SectionSeparator")
        self.separator.setFrameShape(QFrame.Shape.HLine)
        self.separator.setFrameShadow(QFrame.Shadow.Sunken)
        self.header_layout.addWidget(self.separator, stretch=1)

        # Edit Mode Management Controls (for configured custom sections)
        if not self.is_default:
            self.controls_box = QWidget()
            self.controls_box.get_visible = self.controls_box.isVisible
            controls_layout = QHBoxLayout(self.controls_box)
            controls_layout.setContentsMargins(0, 0, 0, 0)
            controls_layout.setSpacing(2)

            edit_btn = QToolButton()
            edit_btn.setIcon(QIcon.fromTheme("document-edit"))
            edit_btn.setToolTip("Rename Section")
            edit_btn.setIconSize(QSize(16, 16))
            if self.on_edit:
                edit_btn.clicked.connect(lambda: self.on_edit(self.section_id))
            controls_layout.addWidget(edit_btn)

            up_btn = QToolButton()
            up_btn.setIcon(QIcon.fromTheme("go-up"))
            up_btn.setToolTip("Move Section Up")
            up_btn.setIconSize(QSize(16, 16))
            if self.on_move:
                up_btn.clicked.connect(lambda: self.on_move(self.section_id, -1))
            controls_layout.addWidget(up_btn)

            down_btn = QToolButton()
            down_btn.setIcon(QIcon.fromTheme("go-down"))
            down_btn.setToolTip("Move Section Down")
            down_btn.setIconSize(QSize(16, 16))
            if self.on_move:
                down_btn.clicked.connect(lambda: self.on_move(self.section_id, 1))
            controls_layout.addWidget(down_btn)

            del_btn = QToolButton()
            del_btn.setIcon(QIcon.fromTheme("edit-delete", QIcon.fromTheme("user-trash")))
            del_btn.setToolTip("Delete Section")
            del_btn.setIconSize(QSize(16, 16))
            if self.on_delete:
                del_btn.clicked.connect(lambda: self.on_delete(self.section_id))
            controls_layout.addWidget(del_btn)

            self.controls_box.setVisible(False)
            self.controls_box.get_visible = lambda: not self.controls_box.isHidden()
            self.header_layout.addWidget(self.controls_box)

        self.main_layout.addLayout(self.header_layout)

        # 2. Flow Layout Grid for Tiles
        self.tiles_container = QWidget()
        self.flow_layout = FlowLayout(self.tiles_container, margin=0, h_spacing=12, v_spacing=12)
        # FlowBox compatibility reference for tests
        self.flowbox = self.flow_layout

        self.main_layout.addWidget(self.tiles_container)

        # 3. Empty hint label
        self.empty_hint = QLabel("No toggles assigned to this section yet.")
        self.empty_hint.setObjectName("SectionEmptyHint")
        self.empty_hint.get_visible = lambda: not self.empty_hint.isHidden()
        self.main_layout.addWidget(self.empty_hint)

    def append_tile(self, tile: QWidget) -> None:
        """Add a button tile to this section's flow layout."""
        self.flow_layout.addWidget(tile)
        self.tiles_count += 1
        self.empty_hint.setVisible(False)

    def set_edit_mode(self, enabled: bool) -> None:
        """Toggle edit mode controls on the section header."""
        if self.controls_box:
            self.controls_box.setVisible(enabled)
