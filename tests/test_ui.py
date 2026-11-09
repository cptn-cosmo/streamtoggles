"""UI integration smoke tests for StreamToggles adhering to Qt6/KDE."""

import os
import sys
import tempfile
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt6.QtWidgets import QApplication, QWidget

from streamtoggles.config import ConfigManager
from streamtoggles.executor import ActionExecutor
from streamtoggles.ui.button_dialog import ButtonEditorDialog
from streamtoggles.ui.group_dialog import GroupSettingsDialog
from streamtoggles.ui.host_dialog import HostSettingsDialog
from streamtoggles.ui.shortcuts_dialog import create_shortcuts_window
from streamtoggles.ui.style import load_application_styles
from streamtoggles.ui.tile import StreamDeckTile
from streamtoggles.ui.window import StreamTogglesWindow


class TestUIComponents(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        load_application_styles(cls.app)

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "config.json")
        self.config_mgr = ConfigManager(self.config_path)
        self.executor = ActionExecutor(get_host_callback=self.config_mgr.get_host_by_id)

    def tearDown(self):
        self.executor.shutdown()
        self.temp_dir.cleanup()

    def test_window_and_tiles(self):
        """Test creating main window, loading buttons, and toggling edit mode."""
        win = StreamTogglesWindow(
            app=self.app,
            config_manager=self.config_mgr,
            executor=self.executor,
            portal=None,
        )
        self.assertIsNotNone(win)

        # Check tiles map
        buttons = self.config_mgr.get_buttons()
        self.assertEqual(len(win.tiles_map), len(buttons))

        # Check tile pulse
        first_id = buttons[0]["id"]
        win.pulse_tile(first_id)

        # Test edit mode toggle
        self.assertFalse(win.is_edit_mode)
        win.toggle_edit_mode()
        self.assertTrue(win.is_edit_mode)
        self.assertTrue(win.tiles_map[first_id].is_edit_mode)

        # Toggle back
        win.toggle_edit_mode()
        self.assertFalse(win.is_edit_mode)

    def test_window_geometry_persistence(self):
        """Verify window size and geometry are persisted and restored across sessions."""
        win1 = StreamTogglesWindow(
            app=self.app,
            config_manager=self.config_mgr,
            executor=self.executor,
            portal=None,
        )
        # Default size is 760 x 560
        self.assertEqual(win1.width(), 760)
        self.assertEqual(win1.height(), 560)

        # Resize to custom dimensions
        win1.resize(650, 480)
        win1.save_window_state()

        # Re-instantiate window with same config directory
        win2 = StreamTogglesWindow(
            app=self.app,
            config_manager=self.config_mgr,
            executor=self.executor,
            portal=None,
        )
        self.assertEqual(win2.width(), 650)
        self.assertEqual(win2.height(), 480)

    def test_stream_deck_tile_image_coverage(self):
        """Test full button image coverage and fallback icon behavior."""
        from PyQt6.QtGui import QImage, QColor

        # 1. Test tile with image covering full button
        test_img_path = os.path.join(self.temp_dir.name, "test_button.png")
        img = QImage(200, 200, QImage.Format.Format_ARGB32)
        img.fill(QColor(255, 100, 50))
        img.save(test_img_path)

        button_with_img = {
            "id": "btn_img",
            "label": "Cover Toggle",
            "image_path": test_img_path,
            "shortcut": "<Control><Alt>K",
            "action_type": "toggle_http",
        }
        tile_with_img = StreamDeckTile(
            button_data=button_with_img,
            on_activate=lambda _: None,
            on_edit=lambda _: None,
            on_delete=lambda _: None,
            on_move=lambda *_: None,
            group_label="Media",
        )
        self.assertIsNotNone(tile_with_img.custom_pixmap)
        self.assertTrue(tile_with_img.property("has_image"))
        self.assertTrue(tile_with_img.icon_label.isHidden())
        self.assertTrue(tile_with_img.title_label.property("on_image"))
        self.assertEqual(tile_with_img.width(), 132)
        self.assertEqual(tile_with_img.height(), 132)

        # Ensure grab / paintEvent works cleanly without errors
        pix = tile_with_img.grab()
        self.assertEqual(pix.width(), 132)
        self.assertEqual(pix.height(), 132)

        # Test active state with image
        tile_with_img.set_active_state(True)
        self.assertTrue(tile_with_img.is_active)
        pix_active = tile_with_img.grab()
        self.assertFalse(pix_active.isNull())

        # 2. Test tile without image (fallback icon)
        button_no_img = {
            "id": "btn_no_img",
            "label": "Fallback Toggle",
            "image_path": "",
            "action_type": "command",
        }
        tile_no_img = StreamDeckTile(
            button_data=button_no_img,
            on_activate=lambda _: None,
            on_edit=lambda _: None,
            on_delete=lambda _: None,
            on_move=lambda *_: None,
        )
        self.assertIsNone(tile_no_img.custom_pixmap)
        self.assertFalse(bool(tile_no_img.property("has_image")))
        self.assertFalse(tile_no_img.icon_label.isHidden())
        self.assertFalse(bool(tile_no_img.title_label.property("on_image")))
        pix_fallback = tile_no_img.grab()
        self.assertFalse(pix_fallback.isNull())

    def test_button_dialog(self):
        """Test opening button editor dialog for existing and new toggle."""
        hosts = self.config_mgr.get_hosts()
        button_data = self.config_mgr.get_buttons()[0]

        saved_results = []
        parent = QWidget()
        dialog = ButtonEditorDialog(
            parent=parent,
            button_data=button_data,
            hosts=hosts,
            on_save_callback=lambda d: saved_results.append(d),
        )
        self.assertIsNotNone(dialog)
        self.assertEqual(dialog.label_row.get_text(), button_data["label"])

    def test_host_dialog(self):
        """Test opening host settings dialog."""
        saved_hosts = []
        deleted_hosts = []
        dialog = HostSettingsDialog(
            parent=QWidget(),
            get_hosts_callback=self.config_mgr.get_hosts,
            on_host_saved_callback=lambda h: saved_hosts.append(h),
            on_host_deleted_callback=lambda hid: deleted_hosts.append(hid),
        )
        self.assertIsNotNone(dialog)
        self.assertGreater(len(dialog._rows), 0)

    def test_group_dialog(self):
        """Test opening group settings dialog."""
        saved_groups = []
        deleted_groups = []
        self.config_mgr.save_group({"label": "Test Group"})
        dialog = GroupSettingsDialog(
            parent=QWidget(),
            get_groups_callback=self.config_mgr.get_groups,
            get_buttons_callback=self.config_mgr.get_buttons,
            on_group_saved_callback=lambda g: saved_groups.append(g),
            on_group_deleted_callback=lambda gid: deleted_groups.append(gid),
        )
        self.assertIsNotNone(dialog)
        self.assertGreater(len(dialog._rows), 0)

    def test_shortcuts_window(self):
        """Test shortcuts window generation."""
        parent = QWidget()
        shortcuts_win = create_shortcuts_window(parent)
        self.assertIsNotNone(shortcuts_win)


if __name__ == "__main__":
    unittest.main()
