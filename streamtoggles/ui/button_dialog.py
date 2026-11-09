"""Button Editor dialog for StreamToggles adhering to modern KDE HIG."""

from __future__ import annotations
import os
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from streamtoggles.obs import OBSClient


class EntryRow(QLineEdit):
    """QLineEdit with helper methods for API compatibility."""

    def get_text(self) -> str:
        return self.text()

    def set_text(self, text: str) -> None:
        self.setText(text)


class ButtonEditorDialog(QDialog):
    """Modal dialog for creating or editing a toggle button configuration."""

    def __init__(
        self,
        parent: Optional[QWidget],
        button_data: Optional[Dict[str, Any]],
        hosts: List[Dict[str, Any]],
        groups: Optional[List[Dict[str, Any]]] = None,
        sections: Optional[List[Dict[str, Any]]] = None,
        on_save_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        super().__init__(parent)
        self.button_data = button_data or {}
        self.hosts = hosts
        self.groups = groups or []
        self.sections = sections or []
        self.on_save = on_save_callback or (lambda _: None)
        self.selected_image_path: str = self.button_data.get("image_path", "")
        self.obs_client = OBSClient()

        is_new = not bool(self.button_data.get("id"))
        self.setWindowTitle("Add Toggle" if is_new else "Edit Toggle")
        self.setMinimumWidth(520)
        self.resize(560, 680)

        self._build_ui()
        self._populate_fields()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(16)

        # --- Group 1: General Details ---
        general_group = QGroupBox("General Appearance")
        general_layout = QFormLayout(general_group)
        general_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        general_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        general_layout.setSpacing(10)

        self.label_row = EntryRow()
        self.label_row.setPlaceholderText("e.g. Mute Mic, OBS Main Scene")
        general_layout.addRow("Button Label:", self.label_row)

        self.section_combo_row = QComboBox()
        self.section_combo_row.addItem("None (Uncategorized)", "")
        for s in self.sections:
            self.section_combo_row.addItem(s.get("title", s.get("id")), s.get("id"))
        self.section_combo_row.get_selected = self.section_combo_row.currentIndex
        self.section_combo_row.set_selected = self.section_combo_row.setCurrentIndex
        general_layout.addRow("Canvas Section:", self.section_combo_row)

        self.group_combo_row = QComboBox()
        self.group_combo_row.addItem("None (Ungrouped)", "")
        for g in self.groups:
            self.group_combo_row.addItem(g.get("label", g.get("id")), g.get("id"))
        self.group_combo_row.get_selected = self.group_combo_row.currentIndex
        self.group_combo_row.set_selected = self.group_combo_row.setCurrentIndex
        general_layout.addRow("Radio Group:", self.group_combo_row)

        self.extra_group_combo_row = QComboBox()
        self.extra_group_combo_row.addItem("None", "")
        for g in self.groups:
            self.extra_group_combo_row.addItem(g.get("label", g.get("id")), g.get("id"))
        general_layout.addRow("Additional Radio Group:", self.extra_group_combo_row)

        # Tile Icon picker
        icon_box = QHBoxLayout()
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(32, 32)
        self.icon_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_preview.setStyleSheet("border: 1px solid palette(mid); border-radius: 6px;")
        icon_box.addWidget(self.icon_preview)

        self.icon_path_label = QLabel("Default symbolic icon")
        self.icon_path_label.setStyleSheet("color: palette(placeholder-text);")
        icon_box.addWidget(self.icon_path_label, stretch=1)

        choose_btn = QPushButton("Choose Image…")
        choose_btn.clicked.connect(self._on_choose_image_clicked)
        icon_box.addWidget(choose_btn)

        self.clear_icon_btn = QToolButton()
        self.clear_icon_btn.setIcon(QIcon.fromTheme("edit-clear"))
        self.clear_icon_btn.setToolTip("Clear custom icon")
        self.clear_icon_btn.clicked.connect(self._on_clear_icon_clicked)
        icon_box.addWidget(self.clear_icon_btn)

        general_layout.addRow("Tile Icon:", icon_box)

        self.shortcut_row = EntryRow()
        self.shortcut_row.setPlaceholderText("e.g. <Control><Alt>1 or Ctrl+Shift+M")
        general_layout.addRow("Global Shortcut:", self.shortcut_row)

        content_layout.addWidget(general_group)

        # --- Group 2: OBS Studio Scene Switching (Optional) ---
        obs_group = QGroupBox("OBS Studio Scene Switching")
        obs_layout = QFormLayout(obs_group)
        obs_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        obs_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        obs_layout.setSpacing(10)

        self.obs_enable_check = QCheckBox("Switch OBS Scene on activate")
        self.obs_enable_check.toggled.connect(self._on_obs_toggled)
        obs_layout.addRow("", self.obs_enable_check)

        self.obs_host_combo = QComboBox()
        for h in self.hosts:
            host_label = h.get("label", "Host")
            host_addr = h.get("host", "127.0.0.1")
            port = h.get("port", 4455)
            self.obs_host_combo.addItem(f"{host_label} ({host_addr}:{port})", h.get("id"))
        if not self.hosts:
            self.obs_host_combo.addItem("No hosts configured", "")
        self.obs_host_combo.currentIndexChanged.connect(self._on_obs_host_changed)
        self.obs_host_label = QLabel("OBS Target Host:")
        obs_layout.addRow(self.obs_host_label, self.obs_host_combo)

        scene_box = QHBoxLayout()
        self.obs_scene_combo = QComboBox()
        self.obs_scene_combo.setEditable(True)
        self.obs_scene_combo.setPlaceholderText("Select or enter scene name…")
        self.obs_scene_combo.currentTextChanged.connect(self._on_obs_scene_text_changed)
        scene_box.addWidget(self.obs_scene_combo, stretch=1)

        self.obs_fetch_btn = QPushButton("Fetch Scenes")
        self.obs_fetch_btn.setIcon(QIcon.fromTheme("view-refresh"))
        self.obs_fetch_btn.setToolTip("Connect to OBS Studio and dynamically list available scenes")
        self.obs_fetch_btn.clicked.connect(self._fetch_obs_scenes)
        scene_box.addWidget(self.obs_fetch_btn)

        self.obs_scene_label = QLabel("Program Scene:")
        obs_layout.addRow(self.obs_scene_label, scene_box)

        self.obs_status_lbl = QLabel("")
        self.obs_status_lbl.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")
        self.obs_status_lbl.setWordWrap(True)
        obs_layout.addRow("", self.obs_status_lbl)

        content_layout.addWidget(obs_group)

        # --- Group 3: Action Configuration (URL or Command) ---
        action_group = QGroupBox("Action (Optional URL / Command)")
        action_layout = QFormLayout(action_group)
        action_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        action_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        action_layout.setSpacing(10)

        self.action_type_row = QComboBox()
        self.action_types = [
            "Single HTTP Request",
            "Double HTTP Request",
            "Toggle HTTP (On/Off)",
            "Custom Command",
            "None (OBS Scene Only)",
        ]
        self.action_type_row.addItems(self.action_types)
        self.action_type_row.currentIndexChanged.connect(self._on_action_type_changed)
        action_layout.addRow("Action Type:", self.action_type_row)

        self.host_combo_row = QComboBox()
        for h in self.hosts:
            self.host_combo_row.addItem(
                f"{h.get('label', 'Host')} ({h.get('host')}:{h.get('port')})",
                h.get("id"),
            )
        if not self.hosts:
            self.host_combo_row.addItem("No hosts configured", "")
        self.host_label_widget = QLabel("Target Host:")
        action_layout.addRow(self.host_label_widget, self.host_combo_row)

        # Single HTTP endpoint
        self.single_path_label = QLabel("Endpoint:")
        self.single_path_row = EntryRow()
        self.single_path_row.setPlaceholderText("/?cmd0=nodes&cmd1=stateEvents...")
        action_layout.addRow(self.single_path_label, self.single_path_row)

        # Double HTTP fields
        self.double_path1_label = QLabel("First Endpoint:")
        self.double_path1_row = EntryRow()
        self.double_path1_row.setPlaceholderText("/?cmd0=nodes&cmd1=stateEvents&cmd2=expression...")
        action_layout.addRow(self.double_path1_label, self.double_path1_row)

        self.double_delay_label = QLabel("Delay (seconds):")
        self.double_delay_row = QDoubleSpinBox()
        self.double_delay_row.setRange(0.1, 60.0)
        self.double_delay_row.setSingleStep(0.5)
        self.double_delay_row.setValue(1.0)
        action_layout.addRow(self.double_delay_label, self.double_delay_row)

        self.double_path2_label = QLabel("Second Endpoint:")
        self.double_path2_row = EntryRow()
        self.double_path2_row.setPlaceholderText("/?cmd0=nodes&cmd1=stateEvents&cmd2=expression&cmd3=Normal")
        action_layout.addRow(self.double_path2_label, self.double_path2_row)

        # Toggle HTTP fields
        self.toggle_path_on_label = QLabel("On Endpoint:")
        self.toggle_path_on_row = EntryRow()
        self.toggle_path_on_row.setPlaceholderText("/?cmd0=nodes&cmd1=stateEvents&cmd2=clothing&cmd3=push&cmd4=Black")
        action_layout.addRow(self.toggle_path_on_label, self.toggle_path_on_row)

        self.toggle_path_off_label = QLabel("Off Endpoint:")
        self.toggle_path_off_row = EntryRow()
        self.toggle_path_off_row.setPlaceholderText("/?cmd0=nodes&cmd1=stateEvents&cmd2=clothing&cmd3=push&cmd4=Default")
        action_layout.addRow(self.toggle_path_off_label, self.toggle_path_off_row)

        # Command field
        self.command_label = QLabel("Shell Command:")
        self.command_row = EntryRow()
        self.command_row.setPlaceholderText("pactl set-source-mute @DEFAULT_SOURCE@ toggle")
        action_layout.addRow(self.command_label, self.command_row)

        content_layout.addWidget(action_group)
        content_layout.addStretch()

        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)

        # Standard dialog button box adhering to KDE HIG
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_btn = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_btn:
            save_btn.setProperty("suggested", True)
        self.button_box.accepted.connect(self._on_save_clicked)
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)

    def _on_obs_toggled(self, checked: bool) -> None:
        self.obs_host_label.setVisible(checked)
        self.obs_host_combo.setVisible(checked)
        self.obs_scene_label.setVisible(checked)
        self.obs_scene_combo.setVisible(checked)
        self.obs_fetch_btn.setVisible(checked)
        self.obs_status_lbl.setVisible(checked)

        if checked and self.obs_scene_combo.count() == 0:
            self._fetch_obs_scenes()

    def _on_obs_host_changed(self, idx: int) -> None:
        if self.obs_enable_check.isChecked():
            self._fetch_obs_scenes()

    def _on_obs_scene_text_changed(self, text: str) -> None:
        clean_text = text.strip()
        if clean_text and not self.label_row.text().strip():
            self.label_row.setText(clean_text)

    def _fetch_obs_scenes(self) -> None:
        selected_host_id = self.obs_host_combo.currentData() or ""
        host_info = None
        for h in self.hosts:
            if h.get("id") == selected_host_id:
                host_info = h
                break
        if not host_info:
            host_info = {"host": "127.0.0.1", "port": 4455, "label": "OBS"}

        self.obs_fetch_btn.setEnabled(False)
        self.obs_status_lbl.setText("Connecting to OBS Studio and fetching scenes…")
        self.obs_status_lbl.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")

        import threading

        def bg():
            try:
                scenes = self.obs_client.get_scene_list(host_info, timeout=2.0)
                QTimer.singleShot(0, lambda: self._on_scenes_fetched(scenes, None))
            except Exception as e:
                QTimer.singleShot(0, lambda: self._on_scenes_fetched([], str(e)))

        t = threading.Thread(target=bg, daemon=True)
        t.start()

    def _on_scenes_fetched(self, scenes: List[str], error: Optional[str]) -> None:
        self.obs_fetch_btn.setEnabled(True)
        if error:
            self.obs_status_lbl.setText(f"Could not connect to OBS: {error}. You can type scene name manually.")
            self.obs_status_lbl.setStyleSheet("color: #da4453; font-size: 11px;")
            return

        current_val = self.obs_scene_combo.currentText().strip()
        self.obs_scene_combo.blockSignals(True)
        self.obs_scene_combo.clear()
        for s in scenes:
            self.obs_scene_combo.addItem(s)
        if current_val:
            idx = self.obs_scene_combo.findText(current_val)
            if idx >= 0:
                self.obs_scene_combo.setCurrentIndex(idx)
            else:
                self.obs_scene_combo.setEditText(current_val)
        elif scenes and not self.label_row.text().strip():
            self.obs_scene_combo.setCurrentIndex(0)
            self.label_row.setText(scenes[0])
        self.obs_scene_combo.blockSignals(False)

        self.obs_status_lbl.setText(f"✓ Found {len(scenes)} scenes in OBS Studio")
        self.obs_status_lbl.setStyleSheet("color: #27ae60; font-size: 11px; font-weight: bold;")

    def _update_icon_display(self) -> None:
        """Update subtitle and preview image for icon row."""
        if self.selected_image_path and os.path.exists(self.selected_image_path):
            self.icon_path_label.setText(os.path.basename(self.selected_image_path))
            self.clear_icon_btn.setEnabled(True)
            pix = QPixmap(self.selected_image_path)
            if not pix.isNull():
                self.icon_preview.setPixmap(
                    pix.scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                )
            else:
                self.icon_preview.setPixmap(QIcon.fromTheme("image-x-generic").pixmap(24, 24))
        else:
            self.icon_path_label.setText("Default symbolic icon")
            self.clear_icon_btn.setEnabled(False)
            self.icon_preview.setPixmap(QIcon.fromTheme("image-x-generic").pixmap(24, 24))

    def _on_clear_icon_clicked(self) -> None:
        self.selected_image_path = ""
        self._update_icon_display()

    def _on_choose_image_clicked(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Tile Icon",
            "",
            "Images (*.png *.jpg *.jpeg *.svg);;All Files (*)",
        )
        if file_path:
            self.selected_image_path = file_path
            self._update_icon_display()

    def _populate_fields(self) -> None:
        """Populate controls with current button data."""
        self.label_row.setText(self.button_data.get("label", ""))
        self.shortcut_row.setText(self.button_data.get("shortcut", ""))
        self._update_icon_display()

        # Pre-select section
        curr_sec_id = self.button_data.get("section_id", "")
        idx = self.section_combo_row.findData(curr_sec_id)
        if idx >= 0:
            self.section_combo_row.setCurrentIndex(idx)

        # Pre-select group
        curr_grp_id = self.button_data.get("group_id", "")
        idx = self.group_combo_row.findData(curr_grp_id)
        if idx >= 0:
            self.group_combo_row.setCurrentIndex(idx)

        group_ids = self.button_data.get("group_ids", [])
        extra_gids = [g for g in group_ids if g != curr_grp_id]
        if extra_gids:
            idx2 = self.extra_group_combo_row.findData(extra_gids[0])
            if idx2 >= 0:
                self.extra_group_combo_row.setCurrentIndex(idx2)

        action_type = self.button_data.get("action_type", "single_http")
        params = self.button_data.get("action_params", {})

        # Pre-select OBS options
        obs_scene = params.get("obs_scene") or self.button_data.get("obs_scene", "")
        obs_host_id = params.get("obs_host_id") or self.button_data.get("obs_host_id", "")

        # Select OBS host
        if obs_host_id:
            idx = self.obs_host_combo.findData(obs_host_id)
            if idx >= 0:
                self.obs_host_combo.setCurrentIndex(idx)
        else:
            # Auto-select first OBS host if available
            for i in range(self.obs_host_combo.count()):
                hid = self.obs_host_combo.itemData(i)
                h = next((h for h in self.hosts if h.get("id") == hid), None)
                if h and (
                    h.get("host_type") in ("obs_websocket", "obs_http")
                    or "obs" in h.get("label", "").lower()
                    or h.get("port") in (4455, 8080)
                ):
                    self.obs_host_combo.setCurrentIndex(i)
                    break

        if obs_scene:
            self.obs_enable_check.setChecked(True)
            self.obs_scene_combo.setEditText(obs_scene)
        else:
            self.obs_enable_check.setChecked(False)

        self._on_obs_toggled(self.obs_enable_check.isChecked())

        if action_type == "double_http":
            self.action_type_row.setCurrentIndex(1)
            self.double_path1_row.setText(params.get("path1", "/"))
            self.double_delay_row.setValue(float(params.get("delay_seconds", 1.0)))
            self.double_path2_row.setText(params.get("path2", "/"))
        elif action_type == "toggle_http":
            self.action_type_row.setCurrentIndex(2)
            self.toggle_path_on_row.setText(params.get("path_on", "/"))
            self.toggle_path_off_row.setText(params.get("path_off", "/"))
        elif action_type == "command":
            self.action_type_row.setCurrentIndex(3)
            self.command_row.setText(params.get("command_string", ""))
        elif action_type in ("obs_scene", "none"):
            self.action_type_row.setCurrentIndex(4)
        else:
            self.action_type_row.setCurrentIndex(0)
            self.single_path_row.setText(params.get("path", "/"))

        # Pre-select host
        host_id = params.get("host_id", "")
        idx = self.host_combo_row.findData(host_id)
        if idx >= 0:
            self.host_combo_row.setCurrentIndex(idx)

        self._on_action_type_changed(self.action_type_row.currentIndex())

    def _on_action_type_changed(self, idx: int) -> None:
        """Show and hide input rows based on action type."""
        is_single = idx == 0
        is_double = idx == 1
        is_toggle = idx == 2
        is_command = idx == 3
        is_none = idx == 4

        show_host = is_single or is_double or is_toggle
        self.host_label_widget.setVisible(show_host)
        self.host_combo_row.setVisible(show_host)

        self.single_path_label.setVisible(is_single)
        self.single_path_row.setVisible(is_single)

        self.double_path1_label.setVisible(is_double)
        self.double_path1_row.setVisible(is_double)
        self.double_delay_label.setVisible(is_double)
        self.double_delay_row.setVisible(is_double)
        self.double_path2_label.setVisible(is_double)
        self.double_path2_row.setVisible(is_double)

        self.toggle_path_on_label.setVisible(is_toggle)
        self.toggle_path_on_row.setVisible(is_toggle)
        self.toggle_path_off_label.setVisible(is_toggle)
        self.toggle_path_off_row.setVisible(is_toggle)

        self.command_label.setVisible(is_command)
        self.command_row.setVisible(is_command)

    def present(self, _parent: Optional[QWidget] = None) -> None:
        self.show()

    def _on_save_clicked(self, *args: Any) -> None:
        """Validate input and emit save callback."""
        label = self.label_row.text().strip()
        is_obs = self.obs_enable_check.isChecked()
        obs_scene = self.obs_scene_combo.currentText().strip() if is_obs else ""
        obs_host_id = self.obs_host_combo.currentData() or "" if is_obs else ""

        if not label:
            if obs_scene:
                label = obs_scene
                self.label_row.setText(label)
            else:
                self.label_row.setStyleSheet("border: 1px solid palette(highlight);")
                self.label_row.setFocus()
                return

        action_idx = self.action_type_row.currentIndex()

        if is_obs and not obs_scene:
            self.obs_scene_combo.setStyleSheet("border: 1px solid palette(highlight);")
            self.obs_scene_combo.setFocus()
            return

        if not is_obs and action_idx == 4:
            # Neither OBS scene nor URL action selected
            self.label_row.setStyleSheet("border: 1px solid palette(highlight);")
            self.label_row.setFocus()
            return

        shortcut = self.shortcut_row.text().strip()

        primary_group = self.group_combo_row.currentData() or ""
        extra_group = self.extra_group_combo_row.currentData() or ""
        group_ids = []
        if primary_group:
            group_ids.append(primary_group)
        if extra_group and extra_group not in group_ids:
            group_ids.append(extra_group)

        button_dict: Dict[str, Any] = {
            "id": self.button_data.get("id", ""),
            "label": label,
            "image_path": self.selected_image_path,
            "shortcut": shortcut,
            "section_id": self.section_combo_row.currentData() or "",
            "group_id": primary_group,
            "group_ids": group_ids,
        }

        selected_host_id = self.host_combo_row.currentData() or ""

        if action_idx == 0:
            button_dict["action_type"] = "single_http"
            button_dict["action_params"] = {
                "host_id": selected_host_id,
                "path": self.single_path_row.text().strip() or "/",
            }
        elif action_idx == 1:
            button_dict["action_type"] = "double_http"
            button_dict["action_params"] = {
                "host_id": selected_host_id,
                "path1": self.double_path1_row.text().strip() or "/",
                "delay_seconds": round(self.double_delay_row.value(), 2),
                "path2": self.double_path2_row.text().strip() or "/",
            }
        elif action_idx == 2:
            button_dict["action_type"] = "toggle_http"
            button_dict["action_params"] = {
                "host_id": selected_host_id,
                "path_on": self.toggle_path_on_row.text().strip() or "/",
                "path_off": self.toggle_path_off_row.text().strip() or "/",
            }
        elif action_idx == 3:
            button_dict["action_type"] = "command"
            button_dict["action_params"] = {
                "command_string": self.command_row.text().strip(),
            }
        else:
            button_dict["action_type"] = "obs_scene"
            button_dict["action_params"] = {}

        if is_obs and obs_scene:
            button_dict["action_params"]["obs_host_id"] = obs_host_id
            button_dict["action_params"]["obs_scene"] = obs_scene

        self.on_save(button_dict)
        self.accept()
