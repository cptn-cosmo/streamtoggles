"""Unit tests for toggle buttons and mutually exclusive button groups in StreamToggles."""

import os
import sys
import tempfile
import time
from typing import Any, Dict, List
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt6.QtWidgets import QApplication

from streamtoggles.config import ConfigManager
from streamtoggles.executor import ActionExecutor
from streamtoggles.ui.style import load_application_styles
from streamtoggles.ui.window import StreamTogglesWindow


class MockExecutor(ActionExecutor):
    """Mock executor tracking dispatched HTTP paths for verification."""

    def __init__(self):
        self.dispatched: List[tuple] = []
        super().__init__(get_host_callback=lambda hid: {"host": "127.0.0.1", "port": 80, "label": "Mock"})

    def perform_http_get_async(self, host_id: str, path: str) -> None:
        self.dispatched.append((host_id, path))

    def _perform_http_get(self, host_id: str, path: str, timeout: float = 2.5) -> bool:
        self.dispatched.append((host_id, path))
        return True


class TestToggleGroups(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        load_application_styles(cls.app)

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "config.json")
        self.config_mgr = ConfigManager(self.config_path)

        # Clear default buttons for a controlled test set
        self.config_mgr.data["buttons"] = []
        self.config_mgr.data["groups"] = []
        self.config_mgr.save()

        self.mock_executor = MockExecutor()

        self.window = StreamTogglesWindow(
            app=self.app,
            config_manager=self.config_mgr,
            executor=self.mock_executor,
            portal=None,
        )

    def tearDown(self):
        self.mock_executor.shutdown()
        self.temp_dir.cleanup()

    def test_standalone_toggle(self):
        """Verify standalone toggle dispatches path_on when turning on and path_off when turning off."""
        btn = {
            "id": "toggle-mic",
            "label": "Mic Toggle",
            "action_type": "toggle_http",
            "group_id": "",
            "action_params": {
                "host_id": "test_host",
                "path_on": "/mic/unmute",
                "path_off": "/mic/mute",
            },
        }
        self.config_mgr.save_button(btn)
        self.window.refresh_grid()

        # Initial state: inactive
        self.assertFalse(self.window.active_states.get("toggle-mic", False))
        tile = self.window.tiles_map["toggle-mic"]
        self.assertFalse(tile.is_active)
        self.assertFalse(tile.main_btn.has_css_class("deck-tile-active"))

        # 1. Turn ON
        self.window.handle_tile_activate("toggle-mic")
        self.assertTrue(self.window.active_states.get("toggle-mic"))
        self.assertTrue(tile.is_active)
        self.assertTrue(tile.main_btn.has_css_class("deck-tile-active"))
        self.assertEqual(self.mock_executor.dispatched[-1], ("test_host", "/mic/unmute"))

        # 2. Turn OFF
        self.window.handle_tile_activate("toggle-mic")
        self.assertFalse(self.window.active_states.get("toggle-mic"))
        self.assertFalse(tile.is_active)
        self.assertFalse(tile.main_btn.has_css_class("deck-tile-active"))
        self.assertEqual(self.mock_executor.dispatched[-1], ("test_host", "/mic/mute"))

    def test_mutually_exclusive_group_radio_behavior(self):
        """Verify mutually exclusive group radio behavior:
        - Activating B1 dispatches B1 path_on.
        - Activating B2 dispatches B1 path_off, then B2 path_on.
        - Clicking B2 again dispatches B2 path_off (leaving all inactive).
        """
        grp_id = self.config_mgr.save_group({"label": "Costumes"})

        btn1 = {
            "id": "btn-costume-a",
            "label": "Costume A",
            "action_type": "toggle_http",
            "group_id": grp_id,
            "action_params": {
                "host_id": "veadotube",
                "path_on": "/costume/a/on",
                "path_off": "/costume/a/off",
            },
        }
        btn2 = {
            "id": "btn-costume-b",
            "label": "Costume B",
            "action_type": "toggle_http",
            "group_id": grp_id,
            "action_params": {
                "host_id": "veadotube",
                "path_on": "/costume/b/on",
                "path_off": "/costume/b/off",
            },
        }
        self.config_mgr.save_button(btn1)
        self.config_mgr.save_button(btn2)
        self.window.refresh_grid()

        tile1 = self.window.tiles_map["btn-costume-a"]
        tile2 = self.window.tiles_map["btn-costume-b"]

        # Step 1: Click Costume A -> A turns ON
        self.window.handle_tile_activate("btn-costume-a")
        self.assertTrue(self.window.active_states.get("btn-costume-a"))
        self.assertFalse(self.window.active_states.get("btn-costume-b", False))
        self.assertTrue(tile1.is_active)
        self.assertFalse(tile2.is_active)
        self.assertIn(("veadotube", "/costume/a/on"), self.mock_executor.dispatched)

        # Step 2: Click Costume B -> A turns OFF (path_off), B turns ON (path_on)
        self.mock_executor.dispatched.clear()
        self.window.handle_tile_activate("btn-costume-b")
        self.assertFalse(self.window.active_states.get("btn-costume-a"))
        self.assertTrue(self.window.active_states.get("btn-costume-b"))
        self.assertFalse(tile1.is_active)
        self.assertTrue(tile2.is_active)

        self.assertEqual(
            self.mock_executor.dispatched,
            [
                ("veadotube", "/costume/a/off"),
                ("veadotube", "/costume/b/on"),
            ],
        )

        # Step 3: Click Costume B again (already active) -> B turns OFF, no active in group
        self.mock_executor.dispatched.clear()
        self.window.handle_tile_activate("btn-costume-b")
        self.assertFalse(self.window.active_states.get("btn-costume-a"))
        self.assertFalse(self.window.active_states.get("btn-costume-b"))
        self.assertFalse(tile1.is_active)
        self.assertFalse(tile2.is_active)
        self.assertEqual(self.mock_executor.dispatched, [("veadotube", "/costume/b/off")])

    def test_state_not_persisted_to_disk(self):
        """Verify active state is purely in-memory and never written to config.json."""
        btn = {
            "id": "toggle-test",
            "label": "Test",
            "action_type": "toggle_http",
            "group_id": "",
            "action_params": {"host_id": "h", "path_on": "/1", "path_off": "/0"},
        }
        self.config_mgr.save_button(btn)
        self.window.refresh_grid()

        # Turn ON in memory
        self.window.handle_tile_activate("toggle-test")
        self.assertTrue(self.window.active_states.get("toggle-test"))

        # Read config directly from disk
        reloaded = ConfigManager(self.config_path)
        disk_btn = reloaded.get_button_by_id("toggle-test")
        self.assertNotIn("is_active", disk_btn)

        # When app restarts with a fresh window, active state is False
        new_window = StreamTogglesWindow(
            app=self.app,
            config_manager=reloaded,
            executor=self.mock_executor,
            portal=None,
        )
        self.assertFalse(new_window.active_states.get("toggle-test", False))

    def test_exclusive_section_behavior(self):
        """Verify that buttons within an exclusive section are mutually exclusive and remove glow."""
        sec_id = self.config_mgr.save_section({"title": "Exclusive Modes", "exclusive": True})

        btn1 = {
            "id": "btn-mode-1",
            "label": "Mode 1",
            "action_type": "toggle_http",
            "section_id": sec_id,
            "action_params": {"host_id": "h", "path_on": "/m1/on", "path_off": "/m1/off"},
        }
        btn2 = {
            "id": "btn-mode-2",
            "label": "Mode 2",
            "action_type": "toggle_http",
            "section_id": sec_id,
            "action_params": {"host_id": "h", "path_on": "/m2/on", "path_off": "/m2/off"},
        }
        self.config_mgr.save_button(btn1)
        self.config_mgr.save_button(btn2)
        self.window.refresh_grid()

        tile1 = self.window.tiles_map["btn-mode-1"]
        tile2 = self.window.tiles_map["btn-mode-2"]

        # 1. Activate Mode 1 -> turns ON, glow active
        self.window.handle_tile_activate("btn-mode-1")
        self.assertTrue(self.window.active_states["btn-mode-1"])
        self.assertTrue(tile1.is_active)
        self.assertFalse(self.window.active_states.get("btn-mode-2", False))
        self.assertFalse(tile2.is_active)
        self.assertEqual(self.mock_executor.dispatched[-1], ("h", "/m1/on"))

        # 2. Activate Mode 2 -> Mode 1 turns OFF (glow removed, path_off), Mode 2 turns ON
        self.mock_executor.dispatched.clear()
        self.window.handle_tile_activate("btn-mode-2")
        self.assertFalse(self.window.active_states["btn-mode-1"])
        self.assertFalse(tile1.is_active)
        self.assertFalse(tile1.main_btn.has_css_class("deck-tile-active"))
        self.assertTrue(self.window.active_states["btn-mode-2"])
        self.assertTrue(tile2.is_active)
        self.assertTrue(tile2.main_btn.has_css_class("deck-tile-active"))
        self.assertEqual(self.mock_executor.dispatched, [("h", "/m1/off"), ("h", "/m2/on")])

    def test_button_in_both_button_group_and_radio_group(self):
        """Verify the user scenario:
        - Cat Button Group (section, exclusive) contains:
            - 'Head Cat' (also in 'Head Items' radio group)
            - 'Chat' (cat in chat location)
        - Items Button Group (section, non-exclusive) contains:
            - 'Headset' (in 'Head Items' radio group)
            - 'Controller' (in 'Hand Items' radio group)

        Rules:
        1. Only 1 item on head: 'Headset' and 'Head Cat' mutually exclusive.
        2. Unique cat: 'Head Cat' and 'Chat' mutually exclusive.
        3. 'Headset' and 'Chat' can both be active simultaneously.
        4. 'Controller' and 'Headset' can both be active simultaneously.
        """
        sec_cat = self.config_mgr.save_section({"title": "Cat", "exclusive": True})
        sec_items = self.config_mgr.save_section({"title": "Items", "exclusive": False})

        grp_head = self.config_mgr.save_group({"label": "Head Items"})
        grp_hand = self.config_mgr.save_group({"label": "Hand Items"})

        headset = {
            "id": "btn-headset",
            "label": "Headset",
            "section_id": sec_items,
            "group_id": grp_head,
            "action_type": "toggle_http",
            "action_params": {"host_id": "h", "path_on": "/headset/on", "path_off": "/headset/off"},
        }
        controller = {
            "id": "btn-controller",
            "label": "Controller",
            "section_id": sec_items,
            "group_id": grp_hand,
            "action_type": "toggle_http",
            "action_params": {"host_id": "h", "path_on": "/ctrl/on", "path_off": "/ctrl/off"},
        }
        head_cat = {
            "id": "btn-head-cat",
            "label": "Head Cat",
            "section_id": sec_cat,
            "group_id": grp_head,
            "action_type": "toggle_http",
            "action_params": {"host_id": "h", "path_on": "/cat_head/on", "path_off": "/cat_head/off"},
        }
        chat_cat = {
            "id": "btn-chat-cat",
            "label": "Chat Cat",
            "section_id": sec_cat,
            "group_id": "",
            "action_type": "toggle_http",
            "action_params": {"host_id": "h", "path_on": "/cat_chat/on", "path_off": "/cat_chat/off"},
        }

        for b in [headset, controller, head_cat, chat_cat]:
            self.config_mgr.save_button(b)
        self.window.refresh_grid()

        tile_headset = self.window.tiles_map["btn-headset"]
        tile_ctrl = self.window.tiles_map["btn-controller"]
        tile_head_cat = self.window.tiles_map["btn-head-cat"]
        tile_chat_cat = self.window.tiles_map["btn-chat-cat"]

        # Step 1: Turn ON Headset
        self.window.handle_tile_activate("btn-headset")
        self.assertTrue(tile_headset.is_active)
        self.assertFalse(tile_head_cat.is_active)

        # Step 2: Turn ON Head Cat -> Headset turns OFF (removed glow, path_off) because of Head Items radio group
        self.mock_executor.dispatched.clear()
        self.window.handle_tile_activate("btn-head-cat")
        self.assertFalse(tile_headset.is_active)
        self.assertTrue(tile_head_cat.is_active)
        self.assertFalse(tile_chat_cat.is_active)
        self.assertEqual(
            self.mock_executor.dispatched,
            [("h", "/headset/off"), ("h", "/cat_head/on")],
        )

        # Step 3: Turn ON Chat Cat -> Head Cat turns OFF (removed glow, path_off) because of Cat button group exclusivity
        self.mock_executor.dispatched.clear()
        self.window.handle_tile_activate("btn-chat-cat")
        self.assertFalse(tile_head_cat.is_active)
        self.assertTrue(tile_chat_cat.is_active)
        self.assertFalse(tile_headset.is_active)
        self.assertEqual(
            self.mock_executor.dispatched,
            [("h", "/cat_head/off"), ("h", "/cat_chat/on")],
        )

        # Step 4: Turn ON Headset -> Headset turns ON; Chat Cat REMAINS ON (both can be active!)
        self.mock_executor.dispatched.clear()
        self.window.handle_tile_activate("btn-headset")
        self.assertTrue(tile_headset.is_active)
        self.assertTrue(tile_chat_cat.is_active)
        self.assertFalse(tile_head_cat.is_active)
        self.assertEqual(self.mock_executor.dispatched, [("h", "/headset/on")])

        # Step 5: Turn ON Controller -> Controller turns ON; Headset AND Chat Cat remain ON
        self.mock_executor.dispatched.clear()
        self.window.handle_tile_activate("btn-controller")
        self.assertTrue(tile_headset.is_active)
        self.assertTrue(tile_chat_cat.is_active)
        self.assertTrue(tile_ctrl.is_active)
        self.assertFalse(tile_head_cat.is_active)
        self.assertEqual(self.mock_executor.dispatched, [("h", "/ctrl/on")])

        # Step 6: Turn ON Head Cat -> Headset turns OFF (radio group) AND Chat Cat turns OFF (section exclusivity)!
        # Controller remains ON!
        self.mock_executor.dispatched.clear()
        self.window.handle_tile_activate("btn-head-cat")
        self.assertFalse(tile_headset.is_active)
        self.assertFalse(tile_chat_cat.is_active)
        self.assertTrue(tile_head_cat.is_active)
        self.assertTrue(tile_ctrl.is_active)
        # Both headset and chat were turned off
        self.assertIn(("h", "/headset/off"), self.mock_executor.dispatched)
        self.assertIn(("h", "/cat_chat/off"), self.mock_executor.dispatched)
        self.assertIn(("h", "/cat_head/on"), self.mock_executor.dispatched)


if __name__ == "__main__":
    unittest.main()
