"""Main application window for StreamToggles adhering to modern KDE HIG."""

from __future__ import annotations
import logging
import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from PyQt6.QtCore import QByteArray, QPoint, QRect, QSettings, QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from streamtoggles import __app_id__
from streamtoggles.ui.about_dialog import AboutDialog
from streamtoggles.ui.button_dialog import ButtonEditorDialog
from streamtoggles.ui.group_dialog import GroupSettingsDialog
from streamtoggles.ui.host_dialog import HostSettingsDialog
from streamtoggles.ui.section import SectionContainer, SectionEditDialog
from streamtoggles.ui.shortcuts_dialog import create_shortcuts_window
from streamtoggles.ui.tile import StreamDeckTile

if TYPE_CHECKING:
    from streamtoggles.config import ConfigManager
    from streamtoggles.executor import ActionExecutor
    from streamtoggles.portal import GlobalShortcutsPortal

logger = logging.getLogger("streamtoggles.ui.window")


class CompatibleStackedWidget(QStackedWidget):
    """QStackedWidget with helper method for GTK stack compatibility."""

    def get_visible_child_name(self) -> str:
        return "empty" if self.currentIndex() == 0 else "grid"

    def set_visible_child_name(self, name: str) -> None:
        self.setCurrentIndex(0 if name == "empty" else 1)


class ToastOverlay(QFrame):
    """Modern floating toast notification overlay banner."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("ToastNotification")
        self.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        self.label = QLabel("")
        self.label.setObjectName("ToastLabel")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, message: str, timeout_ms: int = 3200) -> None:
        self.label.setText(message)
        self.adjustSize()
        # Center horizontally at the bottom of the parent window
        parent = self.parentWidget()
        if parent:
            x = (parent.width() - self.width()) // 2
            y = parent.height() - self.height() - 28
            self.move(max(10, x), max(10, y))
        self.raise_()
        self.show()
        self._timer.start(timeout_ms)


class StreamTogglesWindow(QMainWindow):
    """Main window with modern KDE toolbar, responsive sectioned canvas, and toast notifications."""

    def __init__(
        self,
        app: Optional[QApplication],
        config_manager: ConfigManager,
        executor: ActionExecutor,
        portal: Optional[GlobalShortcutsPortal] = None,
    ):
        super().__init__()
        self.app = app
        self.config_manager = config_manager
        self.executor = executor
        self.portal = portal

        self.setWindowTitle("StreamToggles")
        self.resize(760, 560)
        self.setMinimumSize(420, 360)

        # Set window icon
        icon = QIcon.fromTheme(__app_id__)
        if icon.isNull():
            data_icon_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "data", "icons", "com.github.streamtoggles.StreamToggles.svg"
            )
            if os.path.exists(data_icon_path):
                icon = QIcon(data_icon_path)
        if not icon.isNull():
            self.setWindowIcon(icon)

        self.is_edit_mode: bool = False
        self.tiles_map: Dict[str, StreamDeckTile] = {}
        self.section_containers: List[SectionContainer] = []
        # In-memory toggle state tracking (never persisted to config.json)
        self.active_states: Dict[str, bool] = {}

        # Geometry debounce save timer (saves 500ms after user finishes resizing)
        self._save_geometry_timer = QTimer(self)
        self._save_geometry_timer.setSingleShot(True)
        self._save_geometry_timer.timeout.connect(self.save_window_state)

        self._build_ui()
        self.refresh_grid()
        self.restore_window_state()

    def _build_ui(self) -> None:
        """Construct the modern KDE application layout."""
        # Top Toolbar
        self.toolbar = QToolBar("Main Toolbar", self)
        self.toolbar.setObjectName("MainToolBar")
        self.toolbar.setMovable(False)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(self.toolbar)

        # Edit Mode Toggle Action
        self.edit_action = QAction(QIcon.fromTheme("document-edit"), "Edit Mode", self)
        self.edit_action.setCheckable(True)
        self.edit_action.setShortcut(QKeySequence("Ctrl+E"))
        self.edit_action.setToolTip("Toggle Edit Mode (Ctrl+E)")
        self.edit_action.toggled.connect(self._on_edit_toggled)
        self.toolbar.addAction(self.edit_action)

        # Add Section Action (visible in Edit Mode)
        self.add_section_action = QAction(QIcon.fromTheme("folder-new"), "Add Section", self)
        self.add_section_action.setToolTip("Add Canvas Section")
        self.add_section_action.triggered.connect(self.open_add_section_dialog)
        self.add_section_action.setVisible(False)
        self.add_section_action.get_visible = self.add_section_action.isVisible
        self.add_section_btn = self.add_section_action
        self.toolbar.addAction(self.add_section_action)

        # Spacer between left and right toolbar items
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.toolbar.addWidget(spacer)

        # Add Button (Primary suggested action)
        self.add_action = QAction(QIcon.fromTheme("list-add"), "Add Toggle", self)
        self.add_action.setShortcut(QKeySequence("Ctrl+N"))
        self.add_action.setToolTip("Add New Toggle (Ctrl+N)")
        self.add_action.triggered.connect(self.open_add_dialog)
        self.toolbar.addAction(self.add_action)

        # Hamburger Menu Button
        self.menu_btn = QToolButton(self)
        self.menu_btn.setIcon(QIcon.fromTheme("open-menu", QIcon.fromTheme("application-menu")))
        self.menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu_btn.setToolTip("Main Menu")

        self.main_menu = QMenu(self)
        self.host_settings_action = self.main_menu.addAction(
            QIcon.fromTheme("network-server"), "Target Host Settings"
        )
        self.host_settings_action.setShortcut(QKeySequence("Ctrl+,"))
        self.host_settings_action.triggered.connect(self.open_host_settings)

        self.group_settings_action = self.main_menu.addAction(
            QIcon.fromTheme("format-list-ordered"), "Button Groups"
        )
        self.group_settings_action.triggered.connect(self.open_group_settings)

        self.main_menu.addSeparator()

        self.shortcuts_action = self.main_menu.addAction(
            QIcon.fromTheme("help-about"), "Keyboard Shortcuts"
        )
        self.shortcuts_action.setShortcut(QKeySequence("Ctrl+?"))
        self.shortcuts_action.triggered.connect(self.open_shortcuts_dialog)

        self.about_action = self.main_menu.addAction(
            QIcon.fromTheme("help-about"), "About StreamToggles"
        )
        self.about_action.triggered.connect(self.open_about_dialog)

        self.main_menu.addSeparator()

        self.quit_action = self.main_menu.addAction(
            QIcon.fromTheme("application-exit"), "Quit"
        )
        self.quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self.quit_action.triggered.connect(lambda: QApplication.instance().quit())

        self.menu_btn.setMenu(self.main_menu)
        self.toolbar.addWidget(self.menu_btn)

        # Also add keyboard actions directly to the window so shortcuts work anywhere
        self.addAction(self.edit_action)
        self.addAction(self.add_action)
        self.addAction(self.host_settings_action)
        self.addAction(self.shortcuts_action)
        self.addAction(self.quit_action)

        # Central Stack switching between Empty State and Canvas Grid
        self.central_container = QWidget(self)
        self.central_layout = QVBoxLayout(self.central_container)
        self.central_layout.setContentsMargins(0, 0, 0, 0)
        self.central_layout.setSpacing(0)

        self.stack = CompatibleStackedWidget(self.central_container)

        # 1. Empty State Page
        self.empty_page = QWidget()
        empty_layout = QVBoxLayout(self.empty_page)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(14)

        empty_icon = QLabel()
        empty_icon.setPixmap(
            QIcon.fromTheme("input-gaming", QIcon.fromTheme("applications-multimedia")).pixmap(64, 64)
        )
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)

        empty_title = QLabel("No Toggles Yet")
        empty_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)

        empty_desc = QLabel("Click 'Add Toggle' to configure your first toggle and start controlling your stream setup.")
        empty_desc.setStyleSheet("color: palette(placeholder-text);")
        empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_desc)

        empty_btn_box = QHBoxLayout()
        empty_btn_box.setSpacing(10)
        empty_btn_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_add_btn = QPushButton("Add Toggle")
        empty_add_btn.setIcon(QIcon.fromTheme("list-add"))
        empty_add_btn.setProperty("suggested", True)
        empty_add_btn.clicked.connect(self.open_add_dialog)
        empty_btn_box.addWidget(empty_add_btn)

        empty_sec_btn = QPushButton("Add Section")
        empty_sec_btn.setIcon(QIcon.fromTheme("folder-new"))
        empty_sec_btn.clicked.connect(self.open_add_section_dialog)
        empty_btn_box.addWidget(empty_sec_btn)

        empty_layout.addLayout(empty_btn_box)
        self.stack.addWidget(self.empty_page)

        # 2. Canvas Grid Scrolled Window
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        self.canvas_widget = QWidget()
        self.canvas_layout = QVBoxLayout(self.canvas_widget)
        self.canvas_layout.setContentsMargins(12, 12, 12, 16)
        self.canvas_layout.setSpacing(16)
        self.canvas_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.canvas_widget)
        self.stack.addWidget(self.scroll_area)

        self.central_layout.addWidget(self.stack)
        self.setCentralWidget(self.central_container)

        # Toast overlay notification widget
        self.toast = ToastOverlay(self)

    def resizeEvent(self, event) -> None:
        """Reposition toast when window is resized and schedule geometry persistence."""
        super().resizeEvent(event)
        if hasattr(self, "toast") and self.toast.isVisible():
            x = (self.width() - self.toast.width()) // 2
            y = self.height() - self.toast.height() - 28
            self.toast.move(max(10, x), max(10, y))

        if hasattr(self, "_save_geometry_timer") and not self.isMinimized():
            self._save_geometry_timer.start(500)

    def changeEvent(self, event) -> None:
        """Track window state changes (such as maximize/restore)."""
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            if hasattr(self, "_save_geometry_timer"):
                self._save_geometry_timer.start(500)

    def closeEvent(self, event) -> None:
        """Save window state before closing."""
        if hasattr(self, "_save_geometry_timer"):
            self._save_geometry_timer.stop()
        self.save_window_state()
        super().closeEvent(event)

    def _get_settings(self) -> QSettings:
        """Return QSettings instance scoped to configuration directory."""
        if hasattr(self, "config_manager") and self.config_manager and getattr(self.config_manager, "config_dir", None):
            ini_path = os.path.join(self.config_manager.config_dir, "window.ini")
            return QSettings(ini_path, QSettings.Format.IniFormat)
        return QSettings("StreamToggles", "StreamToggles")

    def save_window_state(self) -> None:
        """Persist window geometry and size."""
        settings = self._get_settings()
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        if not self.isMaximized() and not self.isMinimized():
            settings.setValue("window_width", self.width())
            settings.setValue("window_height", self.height())
        settings.setValue("is_maximized", self.isMaximized())
        settings.sync()

    def restore_window_state(self) -> None:
        """Restore window geometry and size from previous session."""
        settings = self._get_settings()
        geom = settings.value("geometry")

        # Fallback to global QSettings if directory-scoped window.ini is missing geometry
        if geom is None:
            fallback = QSettings("StreamToggles", "StreamToggles")
            geom = fallback.value("geometry")
            if geom is not None:
                settings = fallback

        if geom is not None and isinstance(geom, (QByteArray, bytes)):
            if self.restoreGeometry(geom):
                state = settings.value("windowState")
                if state is not None and isinstance(state, (QByteArray, bytes)):
                    self.restoreState(state)
                return

        w = settings.value("window_width", None, type=int)
        h = settings.value("window_height", None, type=int)
        if w and h and w >= 420 and h >= 360:
            self.resize(w, h)

        if settings.value("is_maximized", False, type=bool):
            self.showMaximized()

    def refresh_grid(self) -> None:
        """Repopulate the canvas with section containers and button tiles."""
        # Clear existing canvas widgets
        while self.canvas_layout.count():
            item = self.canvas_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.tiles_map.clear()
        self.section_containers.clear()

        sections = self.config_manager.get_sections()
        buttons = self.config_manager.get_buttons()

        if not buttons and not sections:
            self.stack.setCurrentIndex(0)
            return

        self.stack.setCurrentIndex(1)

        # Partition buttons by section_id
        sec_buttons: Dict[str, List[Dict[str, Any]]] = {s["id"]: [] for s in sections if s.get("id")}
        uncategorized: List[Dict[str, Any]] = []

        for btn in buttons:
            s_id = btn.get("section_id") or ""
            if s_id and s_id in sec_buttons:
                sec_buttons[s_id].append(btn)
            else:
                uncategorized.append(btn)

        # 1. Render configured sections
        for sec in sections:
            s_id = sec.get("id", "")
            if not s_id:
                continue
            title = sec.get("title", "Untitled Section")
            container = SectionContainer(
                title=title,
                section_id=s_id,
                is_default=False,
                exclusive=bool(sec.get("exclusive", False)),
                on_edit=self.open_edit_section_dialog,
                on_move=self.handle_section_move,
                on_delete=self.handle_section_delete,
            )
            container.set_edit_mode(self.is_edit_mode)
            self._populate_section_tiles(container, sec_buttons.get(s_id, []))
            self.section_containers.append(container)
            self.canvas_layout.addWidget(container)

        # 2. Render uncategorized buttons if any exist
        if uncategorized:
            default_title = "Uncategorized" if sections else "Toggles"
            container = SectionContainer(
                title=default_title,
                section_id="",
                is_default=True,
                exclusive=False,
            )
            container.set_edit_mode(self.is_edit_mode)
            self._populate_section_tiles(container, uncategorized)
            self.section_containers.append(container)
            self.canvas_layout.addWidget(container)

        # 3. Bottom "Add Section" footer button in Edit Mode
        self.canvas_add_section_container = QWidget()
        bottom_sec_layout = QHBoxLayout(self.canvas_add_section_container)
        bottom_sec_layout.setContentsMargins(0, 8, 0, 16)
        bottom_sec_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        add_sec_btn = QPushButton("Add Section")
        add_sec_btn.setIcon(QIcon.fromTheme("folder-new"))
        add_sec_btn.clicked.connect(self.open_add_section_dialog)
        bottom_sec_layout.addWidget(add_sec_btn)

        self.canvas_add_section_container.setVisible(self.is_edit_mode)
        self.canvas_layout.addWidget(self.canvas_add_section_container)

    def _populate_section_tiles(
        self, container: SectionContainer, buttons: List[Dict[str, Any]]
    ) -> None:
        """Instantiate and attach StreamDeckTiles to a section container."""
        for btn_data in buttons:
            btn_id = btn_data.get("id", "")
            group_labels = []
            gid = btn_data.get("group_id")
            if gid and isinstance(gid, str) and gid.strip():
                grp = self.config_manager.get_group_by_id(gid.strip())
                if grp and grp.get("label"):
                    group_labels.append(grp.get("label"))
            for g in btn_data.get("group_ids", []):
                if g and isinstance(g, str) and g.strip() and g.strip() != gid:
                    grp = self.config_manager.get_group_by_id(g.strip())
                    if grp and grp.get("label") and grp.get("label") not in group_labels:
                        group_labels.append(grp.get("label"))
            group_label = ", ".join(group_labels) if group_labels else None

            tile = StreamDeckTile(
                button_data=btn_data,
                on_activate=self.handle_tile_activate,
                on_edit=self.open_edit_dialog,
                on_delete=self.handle_tile_delete,
                on_move=self.handle_tile_move,
                group_label=group_label,
            )
            tile.set_edit_mode(self.is_edit_mode)
            # Restore in-memory active state
            is_active = self.active_states.get(btn_id, False)
            tile.set_active_state(is_active)

            self.tiles_map[btn_id] = tile
            container.append_tile(tile)

    def show_toast(self, message: str) -> None:
        """Display non-blocking toast notification banner."""
        self.toast.show_message(message)

    def handle_tile_activate(self, button_id: str) -> None:
        """Execute button action with toggle, section exclusivity, and mutually exclusive radio group logic."""
        btn_data = self.config_manager.get_button_by_id(button_id)
        if not btn_data:
            return

        action_type = btn_data.get("action_type", "single_http")
        params = btn_data.get("action_params", {})
        obs_host_id = params.get("obs_host_id") or btn_data.get("obs_host_id", "")
        obs_scene = params.get("obs_scene") or btn_data.get("obs_scene", "")
        host_id = params.get("host_id", "")
        path_on = params.get("path_on", "")
        path_off = params.get("path_off", "")
        single_path = params.get("path", "")

        # Collect group IDs for the clicked button
        btn_group_ids: set[str] = set()
        gid = btn_data.get("group_id")
        if gid and isinstance(gid, str) and gid.strip():
            btn_group_ids.add(gid.strip())
        for g in btn_data.get("group_ids", []):
            if g and isinstance(g, str) and g.strip():
                btn_group_ids.add(g.strip())

        # Check section exclusivity
        btn_section_id = btn_data.get("section_id", "")
        btn_sec = self.config_manager.get_section_by_id(btn_section_id) if btn_section_id else None
        is_section_exclusive = bool(btn_sec.get("exclusive", False)) if btn_sec else False

        has_exclusivity = bool(btn_group_ids) or is_section_exclusive
        is_stateful = (action_type == "toggle_http") or (has_exclusivity and (action_type == "obs_scene" or bool(obs_scene)))

        if not is_stateful:
            # Momentary action
            self.executor.execute_button_action(btn_data)
            return

        current_active = self.active_states.get(button_id, False)

        if not current_active:
            # Turning button ON:
            if has_exclusivity:
                # Deactivate any conflicting active buttons in the same radio group or exclusive section
                for other_btn in self.config_manager.get_buttons():
                    other_id = other_btn.get("id", "")
                    if not other_id or other_id == button_id:
                        continue

                    # Check group conflict
                    other_group_ids: set[str] = set()
                    ogid = other_btn.get("group_id")
                    if ogid and isinstance(ogid, str) and ogid.strip():
                        other_group_ids.add(ogid.strip())
                    for g in other_btn.get("group_ids", []):
                        if g and isinstance(g, str) and g.strip():
                            other_group_ids.add(g.strip())

                    shares_radio_group = bool(btn_group_ids & other_group_ids)

                    # Check exclusive section conflict
                    other_section_id = other_btn.get("section_id", "")
                    other_sec = self.config_manager.get_section_by_id(other_section_id) if other_section_id else None
                    other_sec_exclusive = bool(other_sec.get("exclusive", False)) if other_sec else False

                    shares_exclusive_section = (
                        bool(btn_section_id)
                        and btn_section_id == other_section_id
                        and (is_section_exclusive or other_sec_exclusive)
                    )

                    if shares_radio_group or shares_exclusive_section:
                        if self.active_states.get(other_id, False):
                            self.active_states[other_id] = False
                            other_tile = self.tiles_map.get(other_id)
                            if other_tile:
                                other_tile.set_active_state(False)
                            other_params = other_btn.get("action_params", {})
                            other_host = other_params.get("host_id", "")
                            other_path_off = other_params.get("path_off", "")
                            if other_path_off and other_host:
                                self.executor.perform_http_get_async(other_host, other_path_off)

            # Activate clicked button
            self.active_states[button_id] = True
            tile = self.tiles_map.get(button_id)
            if tile:
                tile.set_active_state(True)
            if obs_scene:
                self.executor.perform_obs_scene_switch_async(obs_host_id, obs_scene)
            if path_on and host_id:
                self.executor.perform_http_get_async(host_id, path_on)
            elif single_path and host_id and action_type == "single_http":
                self.executor.perform_http_get_async(host_id, single_path)
        else:
            # Clicking an already active button deactivates it
            self.active_states[button_id] = False
            tile = self.tiles_map.get(button_id)
            if tile:
                tile.set_active_state(False)
            if path_off and host_id:
                self.executor.perform_http_get_async(host_id, path_off)

    def pulse_tile(self, button_id: str) -> None:
        """Trigger visual press feedback on a specific tile (e.g. from portal shortcut)."""
        tile = self.tiles_map.get(button_id)
        if tile:
            tile.pulse()

    def handle_tile_delete(self, button_id: str) -> None:
        """Delete button, refresh grid, and update portal shortcuts."""
        self.active_states.pop(button_id, None)
        self.config_manager.delete_button(button_id)
        self.refresh_grid()
        if self.portal:
            self.portal.bind_configured_shortcuts()
        self.show_toast("Toggle deleted")

    def handle_tile_move(self, button_id: str, direction: int) -> None:
        """Move button left (-1) or right (+1) within its current section."""
        if self.config_manager.move_button_in_section(button_id, direction):
            self.refresh_grid()

    def _on_edit_toggled(self, checked: bool) -> None:
        self.is_edit_mode = checked
        self.add_section_action.setVisible(checked)
        if hasattr(self, "canvas_add_section_container"):
            self.canvas_add_section_container.setVisible(checked)
        for container in self.section_containers:
            container.set_edit_mode(checked)
        for tile in self.tiles_map.values():
            tile.set_edit_mode(checked)

    def toggle_edit_mode(self) -> None:
        """Toggle edit mode programmatically or via shortcut."""
        self.edit_action.setChecked(not self.edit_action.isChecked())

    def open_add_dialog(self) -> None:
        """Open Button Editor modal for creating a new toggle."""
        hosts = self.config_manager.get_hosts()
        groups = self.config_manager.get_groups()
        sections = self.config_manager.get_sections()

        def on_saved(new_data: Dict[str, Any]):
            self.config_manager.save_button(new_data)
            self.refresh_grid()
            if self.portal:
                self.portal.bind_configured_shortcuts()
            self.show_toast(f"Added toggle '{new_data.get('label')}'")

        dialog = ButtonEditorDialog(self, None, hosts, groups, sections, on_saved)
        dialog.exec()

    def open_edit_dialog(self, button_id: str) -> None:
        """Open Button Editor modal for an existing toggle."""
        btn_data = self.config_manager.get_button_by_id(button_id)
        if not btn_data:
            return
        hosts = self.config_manager.get_hosts()
        groups = self.config_manager.get_groups()
        sections = self.config_manager.get_sections()

        def on_saved(updated_data: Dict[str, Any]):
            self.config_manager.save_button(updated_data)
            self.refresh_grid()
            if self.portal:
                self.portal.bind_configured_shortcuts()
            self.show_toast(f"Updated toggle '{updated_data.get('label')}'")

        dialog = ButtonEditorDialog(self, btn_data, hosts, groups, sections, on_saved)
        dialog.exec()

    def open_add_section_dialog(self) -> None:
        """Open Section Editor dialog for creating a new canvas section."""
        def on_saved(section_dict: Dict[str, Any]):
            self.config_manager.save_section(section_dict)
            self.refresh_grid()
            self.show_toast(f"Added section '{section_dict.get('title')}'")

        dialog = SectionEditDialog(self, None, on_saved)
        dialog.exec()

    def open_edit_section_dialog(self, section_id: str) -> None:
        """Open Section Editor dialog for editing an existing canvas section."""
        sec_data = self.config_manager.get_section_by_id(section_id)
        if not sec_data:
            return

        def on_saved(updated_dict: Dict[str, Any]):
            self.config_manager.save_section(updated_dict)
            self.refresh_grid()
            self.show_toast(f"Updated section '{updated_dict.get('title')}'")

        dialog = SectionEditDialog(self, sec_data, on_saved)
        dialog.exec()

    def handle_section_move(self, section_id: str, direction: int) -> None:
        """Move section up (-1) or down (+1)."""
        if self.config_manager.move_section(section_id, direction):
            self.refresh_grid()

    def handle_section_delete(self, section_id: str) -> None:
        """Delete section non-destructively (buttons moved to Uncategorized)."""
        sec = self.config_manager.get_section_by_id(section_id)
        title = sec.get("title", "Section") if sec else "Section"
        if self.config_manager.delete_section(section_id):
            self.refresh_grid()
            self.show_toast(f"Deleted section '{title}' (buttons moved to Uncategorized)")

    def open_host_settings(self) -> None:
        """Open Target Host Settings dialog."""
        def on_saved(host_dict: Dict[str, Any]):
            self.config_manager.save_host(host_dict)
            self.show_toast(f"Host '{host_dict.get('label')}' saved")

        def on_deleted(host_id: str):
            self.config_manager.delete_host(host_id)
            self.show_toast("Host removed")

        dialog = HostSettingsDialog(
            parent=self,
            get_hosts_callback=self.config_manager.get_hosts,
            on_host_saved_callback=on_saved,
            on_host_deleted_callback=on_deleted,
        )
        dialog.exec()

    def open_group_settings(self) -> None:
        """Open Button Group Settings dialog."""
        def on_saved(group_dict: Dict[str, Any]):
            self.config_manager.save_group(group_dict)
            self.refresh_grid()
            self.show_toast(f"Group '{group_dict.get('label')}' saved")

        def on_deleted(group_id: str):
            self.config_manager.delete_group(group_id)
            self.refresh_grid()
            self.show_toast("Group deleted")

        dialog = GroupSettingsDialog(
            parent=self,
            get_groups_callback=self.config_manager.get_groups,
            get_buttons_callback=self.config_manager.get_buttons,
            on_group_saved_callback=on_saved,
            on_group_deleted_callback=on_deleted,
        )
        dialog.exec()

    def open_shortcuts_dialog(self) -> None:
        """Open Keyboard Shortcuts help window."""
        win = create_shortcuts_window(self)
        win.exec()

    def open_about_dialog(self) -> None:
        """Present modern KDE About dialog."""
        about = AboutDialog(self)
        about.exec()

    def present(self) -> None:
        """Present the main application window."""
        self.show()
        self.raise_()
        self.activateWindow()
