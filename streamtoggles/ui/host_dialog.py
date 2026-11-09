"""Host Settings dialog for StreamToggles adhering to modern KDE HIG."""

from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from streamtoggles.obs import OBSClient


class HostEditDialog(QDialog):
    """Sub-dialog sheet for configuring a single target host."""

    def __init__(
        self,
        parent: Optional[QWidget],
        host_data: Optional[Dict[str, Any]],
        on_save_callback: Callable[[Dict[str, Any]], None],
    ):
        super().__init__(parent)
        self.host_data = host_data or {}
        self.on_save = on_save_callback
        self.obs_client = OBSClient()

        is_new = not bool(self.host_data.get("id"))
        self.setWindowTitle("Add Target Host" if is_new else "Edit Target Host")
        self.setMinimumWidth(440)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        desc_label = QLabel("Configure network details for OBS Studio (WebSocket/HTTP) and companion APIs.")
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: palette(placeholder-text);")
        layout.addWidget(desc_label)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setSpacing(10)

        # Host Type / Protocol
        self.type_combo = QComboBox()
        self.type_combo.addItem("OBS Studio (WebSocket v5)", "obs_websocket")
        self.type_combo.addItem("OBS Studio (HTTP POST Bridge)", "obs_http")
        self.type_combo.addItem("Standard HTTP (veadotube, Web APIs)", "http")

        # Determine initial selection
        curr_type = self.host_data.get("host_type", "")
        if not curr_type:
            port_val = int(self.host_data.get("port", 0))
            if port_val == 4455 or "obs" in self.host_data.get("label", "").lower():
                curr_type = "obs_websocket"
            elif port_val == 8080:
                curr_type = "obs_http"
            else:
                curr_type = "http"

        idx = self.type_combo.findData(curr_type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        form_layout.addRow("Protocol / Type:", self.type_combo)

        self.label_input = QLineEdit()
        self.label_input.setPlaceholderText("e.g. OBS Studio, veadotube mini")
        self.label_input.setText(self.host_data.get("label", ""))
        form_layout.addRow("Friendly Name:", self.label_input)

        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("127.0.0.1 or hostname")
        self.host_input.setText(self.host_data.get("host", "127.0.0.1"))
        form_layout.addRow("Hostname / IP:", self.host_input)

        default_port = 4455 if curr_type == "obs_websocket" else (8080 if curr_type == "obs_http" else 36939)
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(int(self.host_data.get("port", default_port)))
        form_layout.addRow("Port:", self.port_input)

        # OBS WebSocket Password
        self.password_label = QLabel("WebSocket Password:")
        self.password_box = QHBoxLayout()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Leave empty if auth is disabled in OBS")
        self.password_input.setText(self.host_data.get("password", ""))
        self.password_box.addWidget(self.password_input, stretch=1)

        self.toggle_pwd_btn = QToolButton()
        self.toggle_pwd_btn.setIcon(QIcon.fromTheme("view-visible", QIcon.fromTheme("view-hidden")))
        self.toggle_pwd_btn.setToolTip("Show / Hide password")
        self.toggle_pwd_btn.clicked.connect(self._toggle_password_echo)
        self.password_box.addWidget(self.toggle_pwd_btn)
        form_layout.addRow(self.password_label, self.password_box)

        # HTTP Endpoint Path (for obs_http)
        self.path_label = QLabel("Endpoint Path:")
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("/call")
        self.path_input.setText(self.host_data.get("path", "/call"))
        form_layout.addRow(self.path_label, self.path_input)

        # Test Connection button & status
        test_box = QHBoxLayout()
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.setIcon(QIcon.fromTheme("network-connect", QIcon.fromTheme("view-refresh")))
        self.test_btn.clicked.connect(self._on_test_connection)
        test_box.addWidget(self.test_btn)

        self.test_status = QLabel("")
        self.test_status.setWordWrap(True)
        self.test_status.setStyleSheet("font-size: 11px;")
        test_box.addWidget(self.test_status, stretch=1)
        form_layout.addRow("", test_box)

        layout.addLayout(form_layout)

        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        self._on_type_changed(self.type_combo.currentIndex(), update_port=False)

        # Dialog buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_btn = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_btn:
            save_btn.setProperty("suggested", True)
        self.button_box.accepted.connect(self._on_save_clicked)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _toggle_password_echo(self) -> None:
        if self.password_input.echoMode() == QLineEdit.EchoMode.Password:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

    def _on_type_changed(self, idx: int, update_port: bool = True) -> None:
        host_type = self.type_combo.currentData()
        is_ws = host_type == "obs_websocket"
        is_http_bridge = host_type == "obs_http"

        self.password_label.setVisible(is_ws)
        self.password_input.setVisible(is_ws)
        self.toggle_pwd_btn.setVisible(is_ws)

        self.path_label.setVisible(is_http_bridge)
        self.path_input.setVisible(is_http_bridge)

        if update_port:
            if is_ws:
                self.port_input.setValue(4455)
            elif is_http_bridge:
                self.port_input.setValue(8080)
            else:
                self.port_input.setValue(36939)

    def _on_test_connection(self) -> None:
        self.test_btn.setEnabled(False)
        self.test_status.setText("Testing connection…")
        self.test_status.setStyleSheet("color: palette(placeholder-text);")

        host = self.host_input.text().strip() or "127.0.0.1"
        port = self.port_input.value()
        host_type = self.type_combo.currentData()
        pwd = self.password_input.text().strip()
        path = self.path_input.text().strip() or "/call"

        host_info = {
            "host": host,
            "port": port,
            "host_type": host_type,
            "password": pwd,
            "path": path,
        }

        # Perform test asynchronously via QTimer to not freeze UI
        def do_test():
            res = self.obs_client.test_connection(host_info, timeout=2.0)
            self.test_btn.setEnabled(True)
            if res.get("success"):
                self.test_status.setText(f"✓ {res.get('message')}")
                self.test_status.setStyleSheet("color: #27ae60; font-weight: bold;")
            else:
                self.test_status.setText(f"✗ {res.get('message')}")
                self.test_status.setStyleSheet("color: #da4453;")

        QTimer.singleShot(50, do_test)

    def _on_save_clicked(self) -> None:
        label = self.label_input.text().strip()
        host = self.host_input.text().strip()
        port = self.port_input.value()
        host_type = self.type_combo.currentData()

        if not label:
            self.label_input.setStyleSheet("border: 1px solid palette(highlight);")
            self.label_input.setFocus()
            return
        if not host:
            self.host_input.setStyleSheet("border: 1px solid palette(highlight);")
            self.host_input.setFocus()
            return

        saved_data = {
            "id": self.host_data.get("id", ""),
            "label": label,
            "host": host,
            "port": port,
            "host_type": host_type,
            "password": self.password_input.text().strip() if host_type == "obs_websocket" else "",
            "path": self.path_input.text().strip() if host_type == "obs_http" else "",
        }
        self.on_save(saved_data)
        self.accept()


class HostSettingsDialog(QDialog):
    """Preferences dialog listing configured target hosts with CRUD actions."""

    def __init__(
        self,
        parent: Optional[QWidget],
        get_hosts_callback: Callable[[], List[Dict[str, Any]]],
        on_host_saved_callback: Callable[[Dict[str, Any]], None],
        on_host_deleted_callback: Callable[[str], None],
    ):
        super().__init__(parent)
        self.get_hosts = get_hosts_callback
        self.on_host_saved = on_host_saved_callback
        self.on_host_deleted = on_host_deleted_callback
        self._rows: List[QWidget] = []

        self.setWindowTitle("Target Host Settings")
        self.setMinimumWidth(500)
        self.resize(520, 460)

        self._build_ui()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)

        # Header bar with Add button
        header_layout = QHBoxLayout()
        title_label = QLabel("Configured Targets")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        add_btn = QPushButton("Add Target Host")
        add_btn.setIcon(QIcon.fromTheme("list-add"))
        add_btn.clicked.connect(lambda: self._open_edit_dialog(None))
        header_layout.addWidget(add_btn)

        main_layout.addLayout(header_layout)

        desc_label = QLabel("Manage local mini-servers, OBS plugins, and streaming companion APIs.")
        desc_label.setStyleSheet("color: palette(placeholder-text);")
        main_layout.addWidget(desc_label)

        # Scrollable host list
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

        self.refresh_host_list()

    def refresh_host_list(self) -> None:
        """Clear and repopulate rows with configured hosts."""
        for row in self._rows:
            self.list_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

        hosts = self.get_hosts()
        if not hosts:
            empty_lbl = QLabel("No Targets Configured\nClick '+ Add Target Host' above to add a local or remote target.")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet("color: palette(placeholder-text); padding: 24px;")
            self.list_layout.insertWidget(0, empty_lbl)
            self._rows.append(empty_lbl)
            return

        for i, host in enumerate(hosts):
            host_id = host.get("id", "")
            label = host.get("label", "Host")
            host_addr = host.get("host", "127.0.0.1")
            port = host.get("port", 80)

            row = QFrame()
            row.setFrameShape(QFrame.Shape.StyledPanel)
            row.setStyleSheet("QFrame { background-color: palette(base); border-radius: 8px; padding: 6px; }")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 6, 8, 6)

            info_layout = QVBoxLayout()
            info_layout.setSpacing(2)
            name_lbl = QLabel(label)
            name_lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
            host_type = host.get("host_type", "")
            if not host_type:
                if port == 4455 or "obs" in label.lower():
                    host_type = "obs_websocket"
                elif port == 8080:
                    host_type = "obs_http"
                else:
                    host_type = "http"

            if host_type == "obs_websocket":
                url_text = f"ws://{host_addr}:{port} (OBS WebSocket v5)"
            elif host_type == "obs_http":
                path = host.get("path", "/call")
                url_text = f"http://{host_addr}:{port}{path} (OBS HTTP POST)"
            else:
                url_text = f"http://{host_addr}:{port} (HTTP)"

            url_lbl = QLabel(url_text)
            url_lbl.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")
            info_layout.addWidget(name_lbl)
            info_layout.addWidget(url_lbl)
            row_layout.addLayout(info_layout, stretch=1)

            edit_btn = QToolButton()
            edit_btn.setIcon(QIcon.fromTheme("document-edit"))
            edit_btn.setToolTip("Edit Host")
            edit_btn.clicked.connect(lambda _, h=host: self._open_edit_dialog(h))
            row_layout.addWidget(edit_btn)

            del_btn = QToolButton()
            del_btn.setIcon(QIcon.fromTheme("edit-delete", QIcon.fromTheme("user-trash")))
            del_btn.setToolTip("Delete Host")
            del_btn.clicked.connect(lambda _, hid=host_id: self._on_delete_host(hid))
            row_layout.addWidget(del_btn)

            self.list_layout.insertWidget(i, row)
            self._rows.append(row)

    def _open_edit_dialog(self, host: Optional[Dict[str, Any]]) -> None:
        def on_saved(saved_host: Dict[str, Any]):
            self.on_host_saved(saved_host)
            self.refresh_host_list()

        dlg = HostEditDialog(self, host, on_saved)
        dlg.exec()

    def _on_delete_host(self, host_id: str) -> None:
        self.on_host_deleted(host_id)
        self.refresh_host_list()
