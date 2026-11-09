"""Unit tests for StreamToggles background action executor."""

import http.server
import os
import socket
import sys
import threading
import time
from typing import List
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt6.QtWidgets import QApplication

from streamtoggles.executor import ActionExecutor


class MockServerHandler(http.server.BaseHTTPRequestHandler):
    received_paths: List[str] = []

    def do_GET(self):
        MockServerHandler.received_paths.append(self.path)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        # Suppress server logging during tests
        pass


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class TestActionExecutor(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        MockServerHandler.received_paths = []
        cls.server_port = find_free_port()
        cls.server = http.server.HTTPServer(("127.0.0.1", cls.server_port), MockServerHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        MockServerHandler.received_paths.clear()
        self.toasts: List[str] = []

        self.hosts = {
            "test_host": {
                "id": "test_host",
                "label": "Test Service",
                "host": "127.0.0.1",
                "port": self.server_port,
            },
            "unreachable_host": {
                "id": "unreachable_host",
                "label": "Dead Service",
                "host": "127.0.0.1",
                "port": 59999,  # Unused port
            },
        }

        self.executor = ActionExecutor(
            get_host_callback=lambda hid: self.hosts.get(hid),
            notify_toast_callback=lambda msg: self.toasts.append(msg),
        )

    def tearDown(self):
        self.executor.shutdown()

    def drain_events(self, max_wait: float = 1.0):
        """Wait and process Qt event loop for queued signal deliveries."""
        start = time.time()
        while time.time() - start < max_wait:
            self.app.processEvents()
            if self.toasts:
                break
            time.sleep(0.05)
        self.app.processEvents()

    def test_single_http_success(self):
        """Test single HTTP request fires and hits endpoint."""
        button = {
            "label": "Single Test",
            "action_type": "single_http",
            "action_params": {
                "host_id": "test_host",
                "path": "/api/v1/trigger?foo=bar",
            },
        }
        self.executor.execute_button_action(button)
        time.sleep(0.3)
        self.drain_events(0.2)
        self.assertIn("/api/v1/trigger?foo=bar", MockServerHandler.received_paths)
        self.assertEqual(len(self.toasts), 0)

    def test_unreachable_host_triggers_toast(self):
        """Test unreachable host causes toast callback to be invoked."""
        button = {
            "label": "Fail Test",
            "action_type": "single_http",
            "action_params": {
                "host_id": "unreachable_host",
                "path": "/fail",
            },
        }
        self.executor.execute_button_action(button)
        self.drain_events(1.0)
        self.assertGreater(len(self.toasts), 0)
        self.assertTrue(any("Cannot reach Dead Service" in t for t in self.toasts))

    def test_double_http_success(self):
        """Test double HTTP request with delay."""
        button = {
            "label": "Double Test",
            "action_type": "double_http",
            "action_params": {
                "host_id": "test_host",
                "path1": "/step1",
                "delay_seconds": 0.2,
                "path2": "/step2",
            },
        }
        self.executor.execute_button_action(button)
        time.sleep(0.5)
        self.drain_events(0.2)
        self.assertIn("/step1", MockServerHandler.received_paths)
        self.assertIn("/step2", MockServerHandler.received_paths)

    def test_command_execution(self):
        """Test shell command execution."""
        button = {
            "label": "Echo Test",
            "action_type": "command",
            "action_params": {
                "command_string": "true",
            },
        }
        self.executor.execute_button_action(button)
        time.sleep(0.2)
        self.drain_events(0.2)
        self.assertEqual(len(self.toasts), 0)

    def test_failed_command_triggers_toast(self):
        """Test failing command triggers toast notification."""
        button = {
            "label": "Fail Cmd",
            "action_type": "command",
            "action_params": {
                "command_string": "false",
            },
        }
        self.executor.execute_button_action(button)
        self.drain_events(1.0)
        self.assertGreater(len(self.toasts), 0)
        self.assertTrue(any("failed" in t for t in self.toasts))


if __name__ == "__main__":
    unittest.main()
