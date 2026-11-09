"""Action execution engine for StreamToggles.

Uses a dedicated concurrent.futures.ThreadPoolExecutor to run all HTTP requests
and shell commands asynchronously, ensuring the Qt GUI event loop is never blocked.
Unreachable hosts or execution failures trigger user-friendly toasts via Qt signals.
"""

from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import logging
import subprocess
import time
from typing import Any, Callable, Dict, Optional
import urllib.error
import urllib.request

from PyQt6.QtCore import QObject, pyqtSignal

from streamtoggles.obs import OBSClient

logger = logging.getLogger("streamtoggles.executor")


class _ToastEmitter(QObject):
    """Thread-safe Qt signal emitter for cross-thread toast notifications."""
    toast_signal = pyqtSignal(str)


class ActionExecutor:
    """Dispatches HTTP requests, OBS scene switching, and commands in background threads without blocking the Qt event loop."""

    def __init__(
        self,
        get_host_callback: Callable[[str], Optional[Dict[str, Any]]],
        notify_toast_callback: Optional[Callable[[str], None]] = None,
        max_workers: int = 4,
    ):
        self.get_host = get_host_callback
        self.notify_toast = notify_toast_callback
        self.pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="StreamTogglesWorker")
        self._emitter = _ToastEmitter()
        self.obs_client = OBSClient()
        if notify_toast_callback:
            self._emitter.toast_signal.connect(notify_toast_callback)

    def shutdown(self) -> None:
        """Shut down the background thread pool cleanly."""
        self.pool.shutdown(wait=False)

    def _show_toast(self, message: str) -> None:
        """Safely trigger a toast notification on the Qt main thread via thread-safe signal."""
        if self.notify_toast:
            self._emitter.toast_signal.emit(message)

    def execute_button_action(self, button: Dict[str, Any]) -> None:
        """Parse button definition and submit its action to the thread pool."""
        action_type = button.get("action_type", "single_http")
        params = button.get("action_params", {})
        label = button.get("label", "Toggle")

        logger.info("Triggering action for '%s' (type: %s)", label, action_type)

        # 1. OBS Scene Switch if configured
        obs_host_id = params.get("obs_host_id") or button.get("obs_host_id", "")
        obs_scene = params.get("obs_scene") or button.get("obs_scene", "")
        if obs_scene:
            self.pool.submit(self._run_obs_scene_switch, obs_host_id, obs_scene)

        # 2. Dispatch primary action
        if action_type == "single_http":
            self.pool.submit(self._run_single_http, label, params)
        elif action_type == "double_http":
            self.pool.submit(self._run_double_http, label, params)
        elif action_type == "command":
            self.pool.submit(self._run_command, label, params)
        elif action_type in ("obs_scene", "none"):
            pass
        else:
            logger.warning("Unknown action type '%s' for button '%s'", action_type, label)

    def perform_obs_scene_switch_async(self, obs_host_id: str, scene_name: str) -> None:
        """Submit an OBS scene switch request directly to the thread pool."""
        self.pool.submit(self._run_obs_scene_switch, obs_host_id, scene_name)

    def _run_obs_scene_switch(self, obs_host_id: str, scene_name: str) -> bool:
        """Execute OBS scene switch via WebSocket v5 or HTTP POST bridge."""
        if not scene_name:
            return False

        host_info = self.get_host(obs_host_id) if obs_host_id else None
        if not host_info:
            # Fallback: look for default OBS host
            for hid in ("obs-default", "obs-websocket-default", "obs-http-default"):
                host_info = self.get_host(hid)
                if host_info:
                    break

        if not host_info:
            # If no host configured, try local default 127.0.0.1:4455
            host_info = {"host": "127.0.0.1", "port": 4455, "label": "OBS Studio"}

        label = host_info.get("label", "OBS Studio")
        logger.info("Switching OBS scene to '%s' via %s", scene_name, label)
        try:
            success = self.obs_client.switch_scene(host_info, scene_name)
            if not success:
                self._show_toast(f"Cannot switch OBS to '{scene_name}'")
            return success
        except Exception as e:
            logger.warning("Failed to switch OBS scene to '%s': %s", scene_name, e)
            self._show_toast(f"OBS switch failed: {e}")
            return False

    def perform_http_post_async(
        self, host_id: str, path: str, json_data: Any = None, headers: Optional[Dict[str, str]] = None
    ) -> None:
        """Submit a single HTTP POST request directly to the thread pool."""
        self.pool.submit(self._perform_http_post, host_id, path, json_data, headers)

    def _perform_http_post(
        self,
        host_id: str,
        path: str,
        json_data: Any = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 2.5,
    ) -> bool:
        """Execute a single HTTP POST request with JSON body."""
        host_info = self.get_host(host_id)
        if not host_info:
            err_msg = f"Host configuration '{host_id}' not found"
            logger.error(err_msg)
            self._show_toast(err_msg)
            return False

        host_name = host_info.get("host", "127.0.0.1")
        port = host_info.get("port", 80)
        label = host_info.get("label", host_id)

        if not path.startswith("/"):
            path = "/" + path

        url = f"http://{host_name}:{port}{path}"
        logger.debug("Dispatching HTTP POST: %s", url)

        req_headers = {
            "User-Agent": "StreamToggles/1.0 (Qt6; KDE)",
            "Content-Type": "application/json",
            "Accept": "application/json, */*",
        }
        if headers:
            req_headers.update(headers)

        body_bytes = None
        if json_data is not None:
            if isinstance(json_data, (bytes, bytearray)):
                body_bytes = bytes(json_data)
            elif isinstance(json_data, str):
                body_bytes = json_data.encode("utf-8")
            else:
                body_bytes = json.dumps(json_data).encode("utf-8")

        req = urllib.request.Request(url, data=body_bytes, headers=req_headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                logger.debug("HTTP POST response from %s: %s", url, response.status)
                return True
        except urllib.error.HTTPError as e:
            logger.debug("HTTP %s from %s (treated as processed by server)", e.code, url)
            return True
        except urllib.error.URLError as e:
            reason = e.reason
            logger.warning("Unreachable host '%s' at %s:%s - %s", label, host_name, port, reason)
            self._show_toast(f"Cannot reach {label} ({host_name}:{port})")
            return False
        except Exception as e:
            logger.warning("Unexpected network error contacting %s (%s:%s): %s", label, host_name, port, e)
            self._show_toast(f"Error reaching {label}: {e}")
            return False

    def perform_http_get_async(self, host_id: str, path: str) -> None:
        """Submit a single HTTP GET request directly to the thread pool."""
        self.pool.submit(self._perform_http_get, host_id, path)

    def _perform_http_get(self, host_id: str, path: str, timeout: float = 2.5) -> bool:
        """Execute a single HTTP GET request.

        Returns True on success (including acceptable 2xx/3xx/404 from mini-servers).
        Returns False and notifies user via Toast if the host is unreachable.
        """
        host_info = self.get_host(host_id)
        if not host_info:
            err_msg = f"Host configuration '{host_id}' not found"
            logger.error(err_msg)
            self._show_toast(err_msg)
            return False

        host_name = host_info.get("host", "127.0.0.1")
        port = host_info.get("port", 80)
        label = host_info.get("label", host_id)

        # Normalize path
        if not path.startswith("/"):
            path = "/" + path

        url = f"http://{host_name}:{port}{path}"
        logger.debug("Dispatching HTTP GET: %s", url)

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "StreamToggles/1.0 (Qt6; KDE)",
                "Accept": "*/*",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                logger.debug("HTTP response from %s: %s", url, response.status)
                return True
        except urllib.error.HTTPError as e:
            # Many mini-servers (e.g., veadotube mini, simple toggle APIs) return 404 or other codes
            # but still trigger the event successfully. Log cleanly.
            logger.debug("HTTP %s from %s (treated as processed by server)", e.code, url)
            return True
        except urllib.error.URLError as e:
            # Genuine connection failure (ConnectionRefusedError, DNS failure, timeout)
            reason = e.reason
            logger.warning("Unreachable host '%s' at %s:%s - %s", label, host_name, port, reason)
            self._show_toast(f"Cannot reach {label} ({host_name}:{port})")
            return False
        except Exception as e:
            logger.warning("Unexpected network error contacting %s (%s:%s): %s", label, host_name, port, e)
            self._show_toast(f"Error reaching {label}: {e}")
            return False

    def _run_single_http(self, button_label: str, params: Dict[str, Any]) -> None:
        """Handle single HTTP GET request action."""
        host_id = params.get("host_id", "")
        path = params.get("path", "/")
        self._perform_http_get(host_id, path)

    def _run_double_http(self, button_label: str, params: Dict[str, Any]) -> None:
        """Handle double HTTP GET request with non-blocking delay in background thread."""
        host_id = params.get("host_id", "")
        path1 = params.get("path1", "/")
        delay = float(params.get("delay_seconds", 1.0))
        path2 = params.get("path2", "/")

        ok1 = self._perform_http_get(host_id, path1)
        if not ok1:
            # If the first request failed because host is down, don't execute second
            return

        if delay > 0:
            time.sleep(delay)

        self._perform_http_get(host_id, path2)

    def _run_command(self, button_label: str, params: Dict[str, Any]) -> None:
        """Execute a shell command asynchronously."""
        cmd = params.get("command_string", "").strip()
        if not cmd:
            logger.warning("Empty command string for button '%s'", button_label)
            return

        logger.info("Executing command for '%s': %s", button_label, cmd)
        try:
            res = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=15.0,
            )
            if res.returncode != 0:
                logger.warning("Command '%s' exited with code %s: %s", cmd, res.returncode, res.stderr.strip())
                self._show_toast(f"'{button_label}' command failed (exit {res.returncode})")
            else:
                logger.debug("Command completed successfully: %s", cmd)
        except subprocess.TimeoutExpired:
            logger.warning("Command '%s' timed out after 15s", cmd)
            self._show_toast(f"'{button_label}' command timed out")
        except Exception as e:
            logger.error("Failed to run command '%s': %s", cmd, e)
            self._show_toast(f"Error executing '{button_label}': {e}")
