"""Integration tests for visual organizational sections on the canvas."""

import os
import sys
import tempfile
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget

from streamtoggles.config import ConfigManager
from streamtoggles.executor import ActionExecutor
from streamtoggles.ui.button_dialog import ButtonEditorDialog
from streamtoggles.ui.section import SectionContainer, SectionEditDialog
from streamtoggles.ui.style import load_application_styles
from streamtoggles.ui.window import StreamTogglesWindow


class TestSections(unittest.TestCase):

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

    def test_default_canvas_without_custom_sections(self):
        """When no custom sections are configured, buttons appear in default 'Toggles' section."""
        self.assertEqual(len(self.config_mgr.get_sections()), 0)
        buttons = self.config_mgr.get_buttons()
        self.assertGreater(len(buttons), 0)

        win = StreamTogglesWindow(
            app=self.app,
            config_manager=self.config_mgr,
            executor=self.executor,
        )
        self.assertEqual(win.stack.get_visible_child_name(), "grid")
        # 1 default container for uncategorized/all buttons
        self.assertEqual(len(win.section_containers), 1)
        self.assertEqual(win.section_containers[0].title, "Toggles")
        self.assertTrue(win.section_containers[0].is_default)
        self.assertEqual(win.section_containers[0].tiles_count, len(buttons))

    def test_canvas_with_multiple_sections(self):
        """Buttons assigned to sections appear in their respective SectionContainers."""
        sec1_id = self.config_mgr.save_section({"title": "OBS Scenes"})
        sec2_id = self.config_mgr.save_section({"title": "Audio Controls"})

        b1_id = self.config_mgr.save_button({
            "label": "Scene Main",
            "section_id": sec1_id,
            "action_type": "single_http",
            "action_params": {"host_id": "test", "path": "/scene_main"},
        })
        b2_id = self.config_mgr.save_button({
            "label": "Mute Mic",
            "section_id": sec2_id,
            "action_type": "single_http",
            "action_params": {"host_id": "test", "path": "/mute"},
        })

        win = StreamTogglesWindow(
            app=self.app,
            config_manager=self.config_mgr,
            executor=self.executor,
        )
        # Should have 3 containers: OBS Scenes, Audio Controls, and Uncategorized (for default buttons)
        self.assertEqual(len(win.section_containers), 3)

        titles = [c.title for c in win.section_containers]
        self.assertIn("OBS Scenes", titles)
        self.assertIn("Audio Controls", titles)
        self.assertIn("Uncategorized", titles)

        # Verify tile placement in SectionContainers
        obs_container = next(c for c in win.section_containers if c.section_id == sec1_id)
        self.assertEqual(obs_container.tiles_count, 1)

        audio_container = next(c for c in win.section_containers if c.section_id == sec2_id)
        self.assertEqual(audio_container.tiles_count, 1)

    def test_empty_section_placeholder(self):
        """An empty section displays an empty hint until a tile is appended."""
        sec_id = self.config_mgr.save_section({"title": "Empty Section"})
        container = SectionContainer(title="Empty Section", section_id=sec_id)
        self.assertTrue(container.empty_hint.get_visible())

        # When a tile is added, the empty hint hides
        btn_widget = QPushButton("Test")
        container.append_tile(btn_widget)
        self.assertFalse(container.empty_hint.get_visible())
        self.assertEqual(container.tiles_count, 1)

    def test_section_edit_mode_toggle(self):
        """Toggling Edit Mode on window reveals management controls on section containers."""
        sec_id = self.config_mgr.save_section({"title": "Gaming Controls"})
        win = StreamTogglesWindow(
            app=self.app,
            config_manager=self.config_mgr,
            executor=self.executor,
        )

        custom_container = next(c for c in win.section_containers if c.section_id == sec_id)
        self.assertIsNotNone(custom_container.controls_box)
        self.assertFalse(custom_container.controls_box.get_visible())
        self.assertFalse(win.add_section_btn.get_visible())

        # Enable edit mode
        win.toggle_edit_mode()
        self.assertTrue(custom_container.controls_box.get_visible())
        self.assertTrue(win.add_section_btn.get_visible())

        # Disable edit mode
        win.toggle_edit_mode()
        self.assertFalse(custom_container.controls_box.get_visible())
        self.assertFalse(win.add_section_btn.get_visible())

    def test_non_destructive_section_deletion_in_ui(self):
        """Deleting a section via window handler reassigns buttons to Uncategorized."""
        sec_id = self.config_mgr.save_section({"title": "Lighting"})
        b_id = self.config_mgr.save_button({
            "label": "Key Light",
            "section_id": sec_id,
            "action_type": "single_http",
            "action_params": {"host_id": "test", "path": "/light"},
        })

        win = StreamTogglesWindow(
            app=self.app,
            config_manager=self.config_mgr,
            executor=self.executor,
        )

        # Delete the Lighting section
        win.handle_section_delete(sec_id)

        # Section is gone from config
        self.assertIsNone(self.config_mgr.get_section_by_id(sec_id))

        # Button still exists in config with section_id = ""
        btn = self.config_mgr.get_button_by_id(b_id)
        self.assertIsNotNone(btn)
        self.assertEqual(btn["section_id"], "")

        # Button is still present in window tiles map
        self.assertIn(b_id, win.tiles_map)

    def test_section_edit_dialog(self):
        """Test SectionEditDialog creating and renaming a section."""
        parent = QWidget()
        saved_sections = []
        dialog = SectionEditDialog(
            parent=parent,
            section_data=None,
            on_save_callback=lambda d: saved_sections.append(d),
        )
        dialog.present(parent)
        self.assertEqual(dialog.get_title(), "Add Section")
        dialog.title_row.set_text("Stream Audio")
        dialog._on_save_clicked(QPushButton())

        self.assertEqual(len(saved_sections), 1)
        self.assertEqual(saved_sections[0]["title"], "Stream Audio")

        # Edit existing section
        renamed_sections = []
        dialog2 = SectionEditDialog(
            parent=parent,
            section_data={"id": "sec_123", "title": "Old Name"},
            on_save_callback=lambda d: renamed_sections.append(d),
        )
        dialog2.present(parent)
        self.assertEqual(dialog2.get_title(), "Edit Section")
        self.assertEqual(dialog2.title_row.get_text(), "Old Name")
        dialog2.title_row.set_text("New Name")
        dialog2._on_save_clicked(QPushButton())

        self.assertEqual(len(renamed_sections), 1)
        self.assertEqual(renamed_sections[0]["id"], "sec_123")
        self.assertEqual(renamed_sections[0]["title"], "New Name")

    def test_button_dialog_section_assignment(self):
        """Test assigning a section to a button via ButtonEditorDialog."""
        sec_id = self.config_mgr.save_section({"title": "Cameras"})
        sections = self.config_mgr.get_sections()
        hosts = self.config_mgr.get_hosts()
        parent = QWidget()

        saved_buttons = []
        dialog = ButtonEditorDialog(
            parent=parent,
            button_data={"label": "Cam 1", "section_id": sec_id},
            hosts=hosts,
            sections=sections,
            on_save_callback=lambda d: saved_buttons.append(d),
        )
        dialog.present(parent)

        # Section combo row should be index 1 (since 0 is 'None (Uncategorized)')
        self.assertEqual(dialog.section_combo_row.get_selected(), 1)

        # Change to None (Uncategorized)
        dialog.section_combo_row.set_selected(0)
        dialog._on_save_clicked(QPushButton())

        self.assertEqual(len(saved_buttons), 1)
        self.assertEqual(saved_buttons[0]["section_id"], "")

    def test_section_edit_dialog_exclusive_toggle(self):
        """Test toggling the exclusive checkbox in SectionEditDialog."""
        parent = QWidget()
        saved_sections = []
        dialog = SectionEditDialog(
            parent=parent,
            section_data={"id": "sec_cat", "title": "Cat", "exclusive": False},
            on_save_callback=lambda d: saved_sections.append(d),
        )
        self.assertFalse(dialog.exclusive_checkbox.isChecked())
        dialog.exclusive_checkbox.setChecked(True)
        dialog._on_save_clicked(QPushButton())

        self.assertEqual(len(saved_sections), 1)
        self.assertEqual(saved_sections[0]["title"], "Cat")
        self.assertTrue(saved_sections[0]["exclusive"])

    def test_section_container_exclusive_badge(self):
        """Test that an exclusive section displays an 'Exclusive' badge."""
        non_exclusive_container = SectionContainer(title="General", section_id="s1", exclusive=False)
        self.assertFalse(hasattr(non_exclusive_container, "exclusive_badge"))

        exclusive_container = SectionContainer(title="Cat", section_id="s2", exclusive=True)
        self.assertTrue(hasattr(exclusive_container, "exclusive_badge"))
        self.assertEqual(exclusive_container.exclusive_badge.text(), "Exclusive")


if __name__ == "__main__":
    unittest.main()
