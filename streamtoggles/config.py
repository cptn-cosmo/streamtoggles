"""Configuration and persistence management for StreamToggles.

Adheres strictly to the XDG Base Directory specification:
$XDG_CONFIG_HOME/streamtoggles/config.json (fallback: ~/.config/streamtoggles/config.json).
Provides atomic writes, schema validation, and sensible defaults.
"""

from __future__ import annotations
import copy
import json
import logging
import os
import tempfile
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger("streamtoggles.config")

DEFAULT_HOSTS: List[Dict[str, Any]] = [
    {
        "id": "veadotube-default",
        "label": "veadotube mini",
        "host": "127.0.0.1",
        "port": 36939,
        "host_type": "http",
    },
    {
        "id": "obs-websocket-default",
        "label": "OBS Studio (WebSocket)",
        "host": "127.0.0.1",
        "port": 4455,
        "host_type": "obs_websocket",
        "password": "",
    },
    {
        "id": "obs-http-default",
        "label": "OBS Studio (HTTP POST)",
        "host": "127.0.0.1",
        "port": 8080,
        "host_type": "obs_http",
        "path": "/call",
    },
]

DEFAULT_BUTTONS: List[Dict[str, Any]] = [
    {
        "id": "toggle-veadotube-shirt",
        "label": "Swap Shirt",
        "image_path": "",
        "shortcut": "<Control><Alt>1",
        "action_type": "single_http",
        "action_params": {
            "host_id": "veadotube-default",
            "path": "/?cmd0=nodes&cmd1=stateEvents&cmd2=clothing&cmd3=push&cmd4=Black%20Shirt",
        },
    },
    {
        "id": "toggle-veadotube-surprise",
        "label": "Surprise Peek",
        "image_path": "",
        "shortcut": "<Control><Alt>2",
        "action_type": "double_http",
        "action_params": {
            "host_id": "veadotube-default",
            "path1": "/?cmd0=nodes&cmd1=stateEvents&cmd2=expression&cmd3=push&cmd4=Surprise",
            "delay_seconds": 2.0,
            "path2": "/?cmd0=nodes&cmd1=stateEvents&cmd2=expression&cmd3=push&cmd4=Normal",
        },
    },
    {
        "id": "toggle-mic-mute",
        "label": "Mute Mic",
        "image_path": "",
        "shortcut": "<Control><Alt>M",
        "action_type": "command",
        "action_params": {
            "command_string": "pactl set-source-mute @DEFAULT_SOURCE@ toggle",
        },
    },
]


def get_config_dir() -> str:
    """Return the StreamToggles configuration directory following XDG spec."""
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if not xdg_config_home or not os.path.isabs(xdg_config_home):
        xdg_config_home = os.path.expanduser("~/.config")
    return os.path.join(xdg_config_home, "streamtoggles")


def get_config_file_path() -> str:
    """Return the absolute path to the config.json file."""
    return os.path.join(get_config_dir(), "config.json")


class ConfigManager:
    """Manages reading, modifying, and atomically saving StreamToggles configuration."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = os.path.abspath(config_path) if config_path else get_config_file_path()
        self.config_dir = os.path.dirname(self.config_path)
        self.data: Dict[str, Any] = {
            "version": 1,
            "hosts": [],
            "buttons": [],
            "groups": [],
            "sections": [],
        }
        self.load()

    def _ensure_dir(self) -> None:
        """Ensure the configuration directory exists."""
        try:
            os.makedirs(self.config_dir, exist_ok=True)
        except OSError as e:
            logger.error("Failed to create config directory %s: %s", self.config_dir, e)

    def load(self) -> None:
        """Load configuration from disk, creating default config if missing."""
        self._ensure_dir()
        if not os.path.exists(self.config_path):
            logger.info("Config file not found at %s. Initializing defaults.", self.config_path)
            self.data = {
                "version": 1,
                "hosts": copy.deepcopy(DEFAULT_HOSTS),
                "buttons": copy.deepcopy(DEFAULT_BUTTONS),
                "groups": [],
                "sections": [],
            }
            self.save()
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                # Ensure keys exist
                if "hosts" not in loaded or not isinstance(loaded["hosts"], list):
                    loaded["hosts"] = copy.deepcopy(DEFAULT_HOSTS)
                if "buttons" not in loaded or not isinstance(loaded["buttons"], list):
                    loaded["buttons"] = copy.deepcopy(DEFAULT_BUTTONS)
                if "groups" not in loaded or not isinstance(loaded["groups"], list):
                    loaded["groups"] = []
                if "sections" not in loaded or not isinstance(loaded["sections"], list):
                    loaded["sections"] = []
                if "version" not in loaded:
                    loaded["version"] = 1
                self.data = loaded
            else:
                logger.warning("Config file did not contain a valid JSON object. Using defaults.")
                self.data = {
                    "version": 1,
                    "hosts": copy.deepcopy(DEFAULT_HOSTS),
                    "buttons": copy.deepcopy(DEFAULT_BUTTONS),
                    "groups": [],
                    "sections": [],
                }
                self.save()
        except Exception as e:
            logger.error("Error reading config file %s: %s. Loading defaults.", self.config_path, e)
            self.data = {
                "version": 1,
                "hosts": copy.deepcopy(DEFAULT_HOSTS),
                "buttons": copy.deepcopy(DEFAULT_BUTTONS),
                "groups": [],
                "sections": [],
            }

    def save(self) -> bool:
        """Atomically write the current configuration to disk."""
        self._ensure_dir()
        try:
            # Atomic write via temporary file in same directory
            dir_name = os.path.dirname(self.config_path)
            fd, tmp_path = tempfile.mkstemp(prefix="config_", suffix=".tmp", dir=dir_name)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.config_path)
            logger.debug("Configuration atomically saved to %s", self.config_path)
            return True
        except Exception as e:
            logger.error("Failed to save configuration to %s: %s", self.config_path, e)
            return False

    # --- Hosts Management ---

    def get_hosts(self) -> List[Dict[str, Any]]:
        """Return list of configured network target hosts."""
        return self.data.setdefault("hosts", [])

    def get_host_by_id(self, host_id: str) -> Optional[Dict[str, Any]]:
        """Find a target host by its unique ID."""
        for host in self.get_hosts():
            if host.get("id") == host_id:
                return host
        return None

    def save_host(self, host_dict: Dict[str, Any]) -> str:
        """Insert or update a host. Returns the host ID."""
        hosts = self.get_hosts()
        host_id = host_dict.get("id")
        if not host_id:
            host_id = f"host_{uuid.uuid4().hex[:8]}"
            host_dict["id"] = host_id

        # Update existing or append
        for i, existing in enumerate(hosts):
            if existing.get("id") == host_id:
                hosts[i] = copy.deepcopy(host_dict)
                self.save()
                return host_id

        hosts.append(copy.deepcopy(host_dict))
        self.save()
        return host_id

    def delete_host(self, host_id: str) -> bool:
        """Delete a host by ID. Returns True if removed."""
        hosts = self.get_hosts()
        before_len = len(hosts)
        self.data["hosts"] = [h for h in hosts if h.get("id") != host_id]
        if len(self.data["hosts"]) != before_len:
            self.save()
            return True
        return False

    # --- Buttons Management ---

    def get_buttons(self) -> List[Dict[str, Any]]:
        """Return ordered list of button definitions."""
        return self.data.setdefault("buttons", [])

    def get_button_by_id(self, button_id: str) -> Optional[Dict[str, Any]]:
        """Find a button definition by its unique ID."""
        for btn in self.get_buttons():
            if btn.get("id") == button_id:
                return btn
        return None

    def save_button(self, button_dict: Dict[str, Any]) -> str:
        """Insert or update a button. Returns the button ID."""
        buttons = self.get_buttons()
        btn_id = button_dict.get("id")
        if not btn_id:
            btn_id = f"btn_{uuid.uuid4().hex[:8]}"
            button_dict["id"] = btn_id

        for i, existing in enumerate(buttons):
            if existing.get("id") == btn_id:
                buttons[i] = copy.deepcopy(button_dict)
                self.save()
                return btn_id

        buttons.append(copy.deepcopy(button_dict))
        self.save()
        return btn_id

    def delete_button(self, button_id: str) -> bool:
        """Delete a button by ID. Returns True if removed."""
        buttons = self.get_buttons()
        before_len = len(buttons)
        self.data["buttons"] = [b for b in buttons if b.get("id") != button_id]
        if len(self.data["buttons"]) != before_len:
            self.save()
            return True
        return False

    def move_button(self, button_id: str, direction: int) -> bool:
        """Move button left (-1) or right (+1) in the list."""
        buttons = self.get_buttons()
        idx = -1
        for i, btn in enumerate(buttons):
            if btn.get("id") == button_id:
                idx = i
                break
        if idx == -1:
            return False

        target_idx = idx + direction
        if 0 <= target_idx < len(buttons):
            buttons[idx], buttons[target_idx] = buttons[target_idx], buttons[idx]
            self.save()
            return True
        return False

    # --- Groups Management ---

    def get_groups(self) -> List[Dict[str, Any]]:
        """Return list of configured button groups."""
        return self.data.setdefault("groups", [])

    def get_group_by_id(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Find a group by its unique ID."""
        for grp in self.get_groups():
            if grp.get("id") == group_id:
                return grp
        return None

    def save_group(self, group_dict: Dict[str, Any]) -> str:
        """Insert or update a group. Returns the group ID."""
        groups = self.get_groups()
        grp_id = group_dict.get("id")
        if not grp_id:
            grp_id = f"group_{uuid.uuid4().hex[:8]}"
            group_dict["id"] = grp_id

        for i, existing in enumerate(groups):
            if existing.get("id") == grp_id:
                groups[i] = copy.deepcopy(group_dict)
                self.save()
                return grp_id

        groups.append(copy.deepcopy(group_dict))
        self.save()
        return grp_id

    def delete_group(self, group_id: str) -> bool:
        """Delete a group by ID and clean up references in any buttons. Returns True if removed."""
        groups = self.get_groups()
        before_len = len(groups)
        self.data["groups"] = [g for g in groups if g.get("id") != group_id]
        if len(self.data["groups"]) != before_len:
            # Clean up button assignments
            for btn in self.get_buttons():
                if btn.get("group_id") == group_id:
                    btn["group_id"] = ""
                if "group_ids" in btn and isinstance(btn["group_ids"], list):
                    btn["group_ids"] = [g for g in btn["group_ids"] if g != group_id]
            self.save()
            return True
        return False

    # --- Sections Management ---

    def get_sections(self) -> List[Dict[str, Any]]:
        """Return list of configured canvas sections."""
        return self.data.setdefault("sections", [])

    def get_section_by_id(self, section_id: str) -> Optional[Dict[str, Any]]:
        """Find a canvas section by its unique ID."""
        for sec in self.get_sections():
            if sec.get("id") == section_id:
                return sec
        return None

    def save_section(self, section_dict: Dict[str, Any]) -> str:
        """Insert or update a section. Returns the section ID."""
        sections = self.get_sections()
        sec_id = section_dict.get("id")
        if not sec_id:
            sec_id = f"section_{uuid.uuid4().hex[:8]}"
            section_dict["id"] = sec_id

        section_dict.setdefault("exclusive", False)

        for i, existing in enumerate(sections):
            if existing.get("id") == sec_id:
                sections[i] = copy.deepcopy(section_dict)
                self.save()
                return sec_id

        sections.append(copy.deepcopy(section_dict))
        self.save()
        return sec_id

    def delete_section(self, section_id: str) -> bool:
        """Delete a section by ID without deleting buttons.

        Reassigns buttons belonging to this section to "" (Uncategorized).
        """
        sections = self.get_sections()
        before_len = len(sections)
        self.data["sections"] = [s for s in sections if s.get("id") != section_id]
        if len(self.data["sections"]) != before_len:
            for btn in self.get_buttons():
                if btn.get("section_id") == section_id:
                    btn["section_id"] = ""
            self.save()
            return True
        return False

    def move_section(self, section_id: str, direction: int) -> bool:
        """Move section up (-1) or down (+1)."""
        sections = self.get_sections()
        idx = -1
        for i, s in enumerate(sections):
            if s.get("id") == section_id:
                idx = i
                break
        if idx == -1:
            return False

        target_idx = idx + direction
        if 0 <= target_idx < len(sections):
            sections[idx], sections[target_idx] = sections[target_idx], sections[idx]
            self.save()
            return True
        return False

    def move_button_in_section(self, button_id: str, direction: int) -> bool:
        """Move button left (-1) or right (+1) relative to other buttons within the same section."""
        buttons = self.get_buttons()
        btn = self.get_button_by_id(button_id)
        if not btn:
            return False

        sec_id = btn.get("section_id") or ""
        # Find all buttons in same section
        sec_buttons = [b for b in buttons if (b.get("section_id") or "") == sec_id]
        sec_idx = -1
        for i, b in enumerate(sec_buttons):
            if b.get("id") == button_id:
                sec_idx = i
                break
        if sec_idx == -1:
            return False

        target_sec_idx = sec_idx + direction
        if 0 <= target_sec_idx < len(sec_buttons):
            other_btn = sec_buttons[target_sec_idx]
            idx1 = buttons.index(btn)
            idx2 = buttons.index(other_btn)
            buttons[idx1], buttons[idx2] = buttons[idx2], buttons[idx1]
            self.save()
            return True
        return False


