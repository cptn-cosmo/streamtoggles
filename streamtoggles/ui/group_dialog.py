"""Button Group Settings dialog for StreamToggles adhering to modern KDE HIG."""

from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class GroupEditDialog(QDialog):
    """Sub-dialog sheet for configuring a single button group."""

    def __init__(
        self,
        parent: Optional[QWidget],
        group_data: Optional[Dict[str, Any]],
        on_save_callback: Callable[[Dict[str, Any]], None],
    ):
        super().__init__(parent)
        self.group_data = group_data or {}
        self.on_save = on_save_callback

        is_new = not bool(self.group_data.get("id"))
        self.setWindowTitle("Add Button Group" if is_new else "Edit Button Group")
        self.setMinimumWidth(380)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        desc_label = QLabel(
            "Toggles in the same group operate with mutual exclusivity (radio button behavior)."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: palette(placeholder-text);")
        layout.addWidget(desc_label)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setSpacing(10)

        self.label_input = QLineEdit()
        self.label_input.setPlaceholderText("e.g. Outfits, Audio Modes")
        self.label_input.setText(self.group_data.get("label", ""))
        self.label_input.returnPressed.connect(self._on_save_clicked)
        form_layout.addRow("Group Label:", self.label_input)
        layout.addLayout(form_layout)

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

    def _on_save_clicked(self) -> None:
        label = self.label_input.text().strip()
        if not label:
            self.label_input.setStyleSheet("border: 1px solid palette(highlight);")
            self.label_input.setFocus()
            return

        saved_data = {
            "id": self.group_data.get("id", ""),
            "label": label,
        }
        self.on_save(saved_data)
        self.accept()


class GroupSettingsDialog(QDialog):
    """Preferences dialog listing configured button groups with CRUD actions."""

    def __init__(
        self,
        parent: Optional[QWidget],
        get_groups_callback: Callable[[], List[Dict[str, Any]]],
        get_buttons_callback: Callable[[], List[Dict[str, Any]]],
        on_group_saved_callback: Callable[[Dict[str, Any]], None],
        on_group_deleted_callback: Callable[[str], None],
    ):
        super().__init__(parent)
        self.get_groups = get_groups_callback
        self.get_buttons = get_buttons_callback
        self.on_group_saved = on_group_saved_callback
        self.on_group_deleted = on_group_deleted_callback
        self._rows: List[QWidget] = []

        self.setWindowTitle("Button Group Settings")
        self.setMinimumWidth(500)
        self.resize(520, 460)

        self._build_ui()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)

        # Header bar with Add button
        header_layout = QHBoxLayout()
        title_label = QLabel("Mutually Exclusive Groups")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        add_btn = QPushButton("Add Group")
        add_btn.setIcon(QIcon.fromTheme("list-add"))
        add_btn.clicked.connect(lambda: self._open_edit_dialog(None))
        header_layout.addWidget(add_btn)

        main_layout.addLayout(header_layout)

        desc_label = QLabel("Manage button groups. Only one toggle in a group can be active at a time.")
        desc_label.setStyleSheet("color: palette(placeholder-text);")
        main_layout.addWidget(desc_label)

        # Scrollable list
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.StyledPanel)

        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setSpacing(6)
        self.list_layout.setContentsMargins(8, 8, 8, 8)
        self.list_layout.addStretch()

        self.scroll_area.setWidget(self.list_container)
        main_layout.addWidget(self.scroll_area)

        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.accept)
        main_layout.addWidget(button_box)

        self.refresh_group_list()

    def refresh_group_list(self) -> None:
        """Clear and repopulate rows with configured groups."""
        for row in self._rows:
            self.list_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

        groups = self.get_groups()
        buttons = self.get_buttons()

        if not groups:
            empty_lbl = QLabel(
                "No Groups Configured\nClick '+ Add Group' above to create a mutually exclusive toggle group."
            )
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet("color: palette(placeholder-text); padding: 24px;")
            self.list_layout.insertWidget(0, empty_lbl)
            self._rows.append(empty_lbl)
            return

        for i, grp in enumerate(groups):
            grp_id = grp.get("id", "")
            label = grp.get("label", "Group")
            member_count = sum(
                1 for b in buttons
                if b.get("group_id") == grp_id or grp_id in b.get("group_ids", [])
            )
            count_text = f"{member_count} toggle{'s' if member_count != 1 else ''} assigned"

            row = QFrame()
            row.setFrameShape(QFrame.Shape.StyledPanel)
            row.setStyleSheet("QFrame { background-color: palette(base); border-radius: 8px; padding: 6px; }")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 6, 8, 6)

            info_layout = QVBoxLayout()
            info_layout.setSpacing(2)
            name_lbl = QLabel(label)
            name_lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
            cnt_lbl = QLabel(count_text)
            cnt_lbl.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")
            info_layout.addWidget(name_lbl)
            info_layout.addWidget(cnt_lbl)
            row_layout.addLayout(info_layout, stretch=1)

            edit_btn = QToolButton()
            edit_btn.setIcon(QIcon.fromTheme("document-edit"))
            edit_btn.setToolTip("Edit Group")
            edit_btn.clicked.connect(lambda _, g=grp: self._open_edit_dialog(g))
            row_layout.addWidget(edit_btn)

            del_btn = QToolButton()
            del_btn.setIcon(QIcon.fromTheme("edit-delete", QIcon.fromTheme("user-trash")))
            del_btn.setToolTip("Delete Group")
            del_btn.clicked.connect(lambda _, gid=grp_id: self._on_delete_group(gid))
            row_layout.addWidget(del_btn)

            self.list_layout.insertWidget(i, row)
            self._rows.append(row)

    def _open_edit_dialog(self, group: Optional[Dict[str, Any]]) -> None:
        def on_saved(saved_group: Dict[str, Any]):
            self.on_group_saved(saved_group)
            self.refresh_group_list()

        dlg = GroupEditDialog(self, group, on_saved)
        dlg.exec()

    def _on_delete_group(self, group_id: str) -> None:
        self.on_group_deleted(group_id)
        self.refresh_group_list()
