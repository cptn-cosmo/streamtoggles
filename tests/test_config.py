"""Unit tests for StreamToggles configuration management."""

import json
import os
import tempfile
import unittest

from streamtoggles.config import ConfigManager, get_config_dir, get_config_file_path


class TestConfigManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "streamtoggles", "config.json")
        self.mgr = ConfigManager(self.config_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_initialization(self):
        """Verify default configuration is created when file does not exist."""
        self.assertTrue(os.path.exists(self.config_path))
        hosts = self.mgr.get_hosts()
        self.assertGreater(len(hosts), 0)
        self.assertEqual(hosts[0]["id"], "veadotube-default")

        buttons = self.mgr.get_buttons()
        self.assertGreater(len(buttons), 0)
        self.assertEqual(buttons[0]["id"], "toggle-veadotube-shirt")

    def test_atomic_save_and_reload(self):
        """Verify modifying config saves atomically and reloads accurately."""
        new_host = {
            "id": "obs-custom",
            "label": "OBS Custom",
            "host": "192.168.1.100",
            "port": 4455,
        }
        self.mgr.save_host(new_host)

        # Reload from another manager instance
        mgr2 = ConfigManager(self.config_path)
        found = mgr2.get_host_by_id("obs-custom")
        self.assertIsNotNone(found)
        self.assertEqual(found["label"], "OBS Custom")
        self.assertEqual(found["port"], 4455)

    def test_button_crud_and_reorder(self):
        """Test button creation, updating, reordering, and deletion."""
        btn_data = {
            "label": "Test Toggle",
            "shortcut": "<Control><Alt>9",
            "action_type": "command",
            "action_params": {"command_string": "echo hello"},
        }
        btn_id = self.mgr.save_button(btn_data)
        self.assertTrue(btn_id.startswith("btn_"))

        # Verify added
        retrieved = self.mgr.get_button_by_id(btn_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["label"], "Test Toggle")

        # Update
        retrieved["label"] = "Updated Toggle"
        self.mgr.save_button(retrieved)
        self.assertEqual(self.mgr.get_button_by_id(btn_id)["label"], "Updated Toggle")

        # Move left
        initial_buttons = [b["id"] for b in self.mgr.get_buttons()]
        last_id = initial_buttons[-1]
        self.mgr.move_button(last_id, -1)
        new_buttons = [b["id"] for b in self.mgr.get_buttons()]
        self.assertEqual(new_buttons[-2], last_id)

        # Delete
        self.assertTrue(self.mgr.delete_button(btn_id))
        self.assertIsNone(self.mgr.get_button_by_id(btn_id))

    def test_host_deletion(self):
        """Test deleting a host."""
        host = {"label": "Temporary Host", "host": "10.0.0.5", "port": 8080}
        hid = self.mgr.save_host(host)
        self.assertIsNotNone(self.mgr.get_host_by_id(hid))
        self.assertTrue(self.mgr.delete_host(hid))
        self.assertIsNone(self.mgr.get_host_by_id(hid))

    def test_groups_crud_and_cleanup(self):
        """Test group creation, retrieval, updating, and cascading cleanup when deleted."""
        # Create group
        grp = {"label": "Outfits"}
        gid = self.mgr.save_group(grp)
        self.assertTrue(gid.startswith("group_"))

        # Retrieve
        found = self.mgr.get_group_by_id(gid)
        self.assertIsNotNone(found)
        self.assertEqual(found["label"], "Outfits")

        # Assign button to this group
        btn = {
            "label": "Red Dress",
            "group_id": gid,
            "action_type": "toggle_http",
            "action_params": {"host_id": "test", "path_on": "/on", "path_off": "/off"},
        }
        bid = self.mgr.save_button(btn)
        self.assertEqual(self.mgr.get_button_by_id(bid)["group_id"], gid)

        # Delete group and verify button's group_id is cleaned up
        self.assertTrue(self.mgr.delete_group(gid))
        self.assertIsNone(self.mgr.get_group_by_id(gid))
        self.assertEqual(self.mgr.get_button_by_id(bid)["group_id"], "")

    def test_sections_crud_and_reorder(self):
        """Test section creation, retrieval, updating, and reordering."""
        # Create sections
        sec1 = {"title": "OBS Scenes"}
        sec2 = {"title": "Audio Controls"}
        sid1 = self.mgr.save_section(sec1)
        sid2 = self.mgr.save_section(sec2)

        self.assertTrue(sid1.startswith("section_"))
        self.assertTrue(sid2.startswith("section_"))

        # Retrieve
        found = self.mgr.get_section_by_id(sid1)
        self.assertIsNotNone(found)
        self.assertEqual(found["title"], "OBS Scenes")

        # Update
        found["title"] = "OBS Scenes & Sources"
        self.mgr.save_section(found)
        self.assertEqual(self.mgr.get_section_by_id(sid1)["title"], "OBS Scenes & Sources")

        # Reorder: move second section up (-1)
        self.assertTrue(self.mgr.move_section(sid2, -1))
        sections = self.mgr.get_sections()
        self.assertEqual(sections[0]["id"], sid2)
        self.assertEqual(sections[1]["id"], sid1)

        # Move first section down (+1)
        self.assertTrue(self.mgr.move_section(sid2, 1))
        sections = self.mgr.get_sections()
        self.assertEqual(sections[0]["id"], sid1)
        self.assertEqual(sections[1]["id"], sid2)

    def test_section_non_destructive_deletion(self):
        """Test that deleting a section does NOT delete buttons, but resets their section_id to empty."""
        sid = self.mgr.save_section({"title": "Temporary Section"})
        btn = {
            "label": "Scene 1",
            "section_id": sid,
            "action_type": "single_http",
            "action_params": {"host_id": "test", "path": "/scene1"},
        }
        bid = self.mgr.save_button(btn)

        # Confirm button is in section
        self.assertEqual(self.mgr.get_button_by_id(bid)["section_id"], sid)

        # Delete section
        self.assertTrue(self.mgr.delete_section(sid))
        self.assertIsNone(self.mgr.get_section_by_id(sid))

        # Button MUST still exist, with section_id reset to ""
        btn_after = self.mgr.get_button_by_id(bid)
        self.assertIsNotNone(btn_after)
        self.assertEqual(btn_after["section_id"], "")

    def test_move_button_in_section(self):
        """Test moving buttons within a specific section without affecting other sections."""
        sid1 = self.mgr.save_section({"title": "Section 1"})
        sid2 = self.mgr.save_section({"title": "Section 2"})

        b1 = self.mgr.save_button({"label": "S1-B1", "section_id": sid1})
        b2 = self.mgr.save_button({"label": "S2-B1", "section_id": sid2})
        b3 = self.mgr.save_button({"label": "S1-B2", "section_id": sid1})
        b4 = self.mgr.save_button({"label": "S2-B2", "section_id": sid2})

        # S1 buttons in order: [b1, b3]
        # Move b3 left (-1) in Section 1 -> b3 should swap with b1
        self.assertTrue(self.mgr.move_button_in_section(b3, -1))

        # Check button order in Section 1
        all_buttons = self.mgr.get_buttons()
        s1_btns = [b["id"] for b in all_buttons if b.get("section_id") == sid1]
        self.assertEqual(s1_btns, [b3, b1])

        # Check Section 2 buttons are undisturbed
        s2_btns = [b["id"] for b in all_buttons if b.get("section_id") == sid2]
        self.assertEqual(s2_btns, [b2, b4])

    def test_backwards_compatibility_missing_sections(self):
        """Verify that loading a config without a 'sections' key automatically defaults to empty list."""
        legacy_data = {
            "version": 1,
            "hosts": [],
            "buttons": [{"id": "b1", "label": "Legacy Btn"}],
            "groups": [],
        }
        legacy_file = os.path.join(self.temp_dir.name, "legacy_config.json")
        with open(legacy_file, "w") as f:
            json.dump(legacy_data, f)

        legacy_mgr = ConfigManager(legacy_file)
        self.assertEqual(legacy_mgr.get_sections(), [])
        self.assertEqual(len(legacy_mgr.get_buttons()), 1)

    def test_xdg_env_override(self):
        """Test XDG_CONFIG_HOME override behavior."""
        custom_xdg = os.path.join(self.temp_dir.name, "my_custom_config")
        old_env = os.environ.get("XDG_CONFIG_HOME")
        try:
            os.environ["XDG_CONFIG_HOME"] = custom_xdg
            expected_dir = os.path.join(custom_xdg, "streamtoggles")
            self.assertEqual(get_config_dir(), expected_dir)
            self.assertEqual(get_config_file_path(), os.path.join(expected_dir, "config.json"))
        finally:
            if old_env is not None:
                os.environ["XDG_CONFIG_HOME"] = old_env
            else:
                os.environ.pop("XDG_CONFIG_HOME", None)


if __name__ == "__main__":
    unittest.main()

