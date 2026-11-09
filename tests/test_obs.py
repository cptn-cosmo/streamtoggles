"""Unit tests for OBS Studio integration (WebSocket v5 and HTTP POST) in StreamToggles."""

from __future__ import annotations
import base64
import http.server
import json
import os
import socket
import struct
import sys
import threading
import time
from typing import Any, Dict, List, Optional
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt6.QtWidgets import QApplication, QWidget

from streamtoggles.config import ConfigManager
from streamtoggles.executor import ActionExecutor
from streamtoggles.obs import OBSClient
from streamtoggles.ui.button_dialog import ButtonEditorDialog
from streamtoggles.ui.style import load_application_styles
from streamtoggles.ui.window import StreamTogglesWindow


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def build_ws_frame(payload_bytes: bytes, opcode: int = 0x1, mask: bool = False) -> bytes:
    length = len(payload_bytes)
    header = bytearray([0x80 | (opcode & 0x0F)])
    if length < 126:
        header.append((0x80 if mask else 0) | length)
    elif length <= 65535:
        header.append((0x80 if mask else 0) | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append((0x80 if mask else 0) | 127)
        header.extend(struct.pack("!Q", length))
    if mask:
        mask_key = os.urandom(4)
        header.extend(mask_key)
        payload_bytes = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload_bytes))
    return bytes(header) + payload_bytes


class MockOBSWebSocketServer:
    """Mock server implementing the OBS WebSocket v5 handshake and requests."""

    def __init__(self, port: int, require_auth: bool = False, password: str = "secret123"):
        self.port = port
        self.require_auth = require_auth
        self.password = password
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind(("127.0.0.1", port))
        self.server_sock.listen(1)
        self.server_sock.settimeout(2.0)
        self.running = True
        self.received_requests: List[Dict[str, Any]] = []
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while self.running:
            try:
                conn, _ = self.server_sock.accept()
            except Exception:
                break
            self._handle_client(conn)

    def _handle_client(self, conn: socket.socket):
        conn.settimeout(2.5)
        try:
            # 1. Handshake
            data = conn.recv(2048)
            conn.sendall(
                b"HTTP/1.1 101 Switching Protocols\r\n"
                b"Upgrade: websocket\r\n"
                b"Connection: Upgrade\r\n"
                b"Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n\r\n"
            )

            # 2. Send Hello (op 0)
            hello_d: Dict[str, Any] = {"obsWebSocketVersion": "5.0.0", "rpcVersion": 1}
            if self.require_auth:
                hello_d["authentication"] = {
                    "challenge": "test_challenge_abc",
                    "salt": "test_salt_xyz",
                }
            conn.sendall(build_ws_frame(json.dumps({"op": 0, "d": hello_d}).encode("utf-8")))

            # 3. Read Identify (op 1)
            raw = self._read_ws_msg(conn)
            if not raw:
                return
            id_data = json.loads(raw)
            if id_data.get("op") != 1:
                return

            # Check auth if required
            if self.require_auth:
                auth_str = id_data.get("d", {}).get("authentication", "")
                import hashlib
                h1 = hashlib.sha256((self.password + "test_salt_xyz").encode("utf-8")).digest()
                sec = base64.b64encode(h1).decode("utf-8")
                h2 = hashlib.sha256((sec + "test_challenge_abc").encode("utf-8")).digest()
                expected_auth = base64.b64encode(h2).decode("utf-8")
                if auth_str != expected_auth:
                    conn.sendall(build_ws_frame(b"", opcode=0x8))
                    return

            # Send Identified (op 2)
            conn.sendall(build_ws_frame(json.dumps({"op": 2, "d": {"negotiatedRpcVersion": 1}}).encode("utf-8")))

            # 4. Handle requests (op 6)
            while self.running:
                try:
                    raw_req = self._read_ws_msg(conn)
                    if not raw_req:
                        break
                    req = json.loads(raw_req)
                    self.received_requests.append(req)
                    d = req.get("d", {})
                    req_type = d.get("requestType")
                    req_id = d.get("requestId", "1")

                    if req_type == "GetSceneList":
                        resp = {
                            "op": 7,
                            "d": {
                                "requestType": "GetSceneList",
                                "requestId": req_id,
                                "requestStatus": {"result": True, "code": 100},
                                "responseData": {
                                    "currentProgramSceneName": "Live",
                                    "scenes": [
                                        {"sceneName": "Starting Soon", "sceneIndex": 0},
                                        {"sceneName": "Live", "sceneIndex": 1},
                                        {"sceneName": "Ending", "sceneIndex": 2},
                                    ],
                                },
                            },
                        }
                        conn.sendall(build_ws_frame(json.dumps(resp).encode("utf-8")))
                    elif req_type == "SetCurrentProgramScene":
                        resp = {
                            "op": 7,
                            "d": {
                                "requestType": "SetCurrentProgramScene",
                                "requestId": req_id,
                                "requestStatus": {"result": True, "code": 100},
                            },
                        }
                        conn.sendall(build_ws_frame(json.dumps(resp).encode("utf-8")))
                except Exception:
                    break
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _read_ws_msg(self, conn: socket.socket) -> str:
        h = conn.recv(2)
        if not h or len(h) < 2:
            return ""
        masked = (h[1] & 0x80) != 0
        length = h[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", conn.recv(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", conn.recv(8))[0]
        mask_key = conn.recv(4) if masked else None
        payload = bytearray()
        while len(payload) < length:
            chunk = conn.recv(min(4096, length - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        if masked and mask_key:
            payload = bytearray(b ^ mask_key[i % 4] for i, b in enumerate(payload))
        return payload.decode("utf-8", errors="replace")

    def close(self):
        self.running = False
        try:
            self.server_sock.close()
        except Exception:
            pass


class MockOBSHTTPHandler(http.server.BaseHTTPRequestHandler):
    received_posts: List[Dict[str, Any]] = []

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {}
        MockOBSHTTPHandler.received_posts.append(parsed)

        req_type = parsed.get("request-type") or parsed.get("requestType")
        if req_type == "SetCurrentProgramScene":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"result": true}')
        elif req_type == "GetSceneList":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "scenes": [
                    {"sceneName": "Camera 1"},
                    {"sceneName": "Gaming"},
                ],
                "currentProgramSceneName": "Gaming",
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"result": true}')

    def log_message(self, format, *args):
        pass


class TestOBSIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        load_application_styles(cls.app)

    def test_obs_websocket_get_scenes_and_switch(self):
        """Test OBS WebSocket v5 scene list retrieval and scene switching."""
        port = find_free_port()
        server = MockOBSWebSocketServer(port=port, require_auth=False)
        time.sleep(0.05)

        try:
            client = OBSClient()
            host_info = {
                "host": "127.0.0.1",
                "port": port,
                "host_type": "obs_websocket",
            }

            # 1. Get scene list
            scenes = client.get_scene_list(host_info)
            self.assertEqual(scenes, ["Starting Soon", "Live", "Ending"])

            # 2. Switch scene
            success = client.switch_scene(host_info, "Live")
            self.assertTrue(success)
            self.assertTrue(any(r.get("d", {}).get("requestType") == "SetCurrentProgramScene" for r in server.received_requests))
        finally:
            server.close()

    def test_obs_websocket_authentication(self):
        """Test OBS WebSocket v5 with SHA-256 challenge/response authentication."""
        port = find_free_port()
        server = MockOBSWebSocketServer(port=port, require_auth=True, password="mysecretpassword")
        time.sleep(0.05)

        try:
            client = OBSClient()

            # 1. Correct password
            host_info_valid = {
                "host": "127.0.0.1",
                "port": port,
                "host_type": "obs_websocket",
                "password": "mysecretpassword",
            }
            res = client.test_connection(host_info_valid)
            self.assertTrue(res["success"])
            self.assertEqual(res["scene_count"], 3)

            # 2. Missing password triggers PermissionError
            host_info_no_pwd = {
                "host": "127.0.0.1",
                "port": port,
                "host_type": "obs_websocket",
                "password": "",
            }
            res_fail = client.test_connection(host_info_no_pwd)
            self.assertFalse(res_fail["success"])
        finally:
            server.close()

    def test_obs_http_post_get_scenes_and_switch(self):
        """Test OBS HTTP POST bridge (curl -X POST http://localhost:8080/call style)."""
        MockOBSHTTPHandler.received_posts.clear()
        port = find_free_port()
        httpd = http.server.HTTPServer(("127.0.0.1", port), MockOBSHTTPHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        try:
            client = OBSClient()
            host_info = {
                "host": "127.0.0.1",
                "port": port,
                "host_type": "obs_http",
                "path": "/call",
            }

            # 1. Fetch scenes via HTTP POST
            scenes = client.get_scene_list(host_info)
            self.assertEqual(scenes, ["Camera 1", "Gaming"])

            # 2. Switch scene via HTTP POST
            success = client.switch_scene(host_info, "Gaming")
            self.assertTrue(success)

            # Verify received POST payload format
            last_post = MockOBSHTTPHandler.received_posts[-1]
            self.assertEqual(last_post.get("request-type"), "SetCurrentProgramScene")
            self.assertEqual(last_post.get("sceneName"), "Gaming")
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_button_dialog_obs_scene_and_url_combination(self):
        """Test ButtonEditorDialog configuring both an OBS scene switch AND a URL call."""
        parent = QWidget()
        hosts = [
            {"id": "obs-host", "label": "OBS Studio", "host": "127.0.0.1", "port": 54455, "host_type": "obs_websocket"},
            {"id": "veadotube", "label": "veadotube", "host": "127.0.0.1", "port": 36939, "host_type": "http"},
        ]
        btn_data = {
            "id": "btn_scene_live",
            "label": "Live Scene",
            "action_type": "single_http",
            "action_params": {
                "obs_host_id": "obs-host",
                "obs_scene": "Live",
                "host_id": "veadotube",
                "path": "/avatar/live",
            },
        }

        saved = []
        dialog = ButtonEditorDialog(
            parent=parent,
            button_data=btn_data,
            hosts=hosts,
            on_save_callback=lambda d: saved.append(d),
        )

        self.assertTrue(dialog.obs_enable_check.isChecked())
        self.assertEqual(dialog.obs_scene_combo.currentText(), "Live")
        self.assertEqual(dialog.action_type_row.currentIndex(), 0)  # Single HTTP Request
        self.assertEqual(dialog.single_path_row.get_text(), "/avatar/live")

        # Save and verify both are preserved
        dialog._on_save_clicked(None)
        self.assertEqual(len(saved), 1)
        res_btn = saved[0]
        self.assertEqual(res_btn["action_type"], "single_http")
        self.assertEqual(res_btn["action_params"]["obs_scene"], "Live")
        self.assertEqual(res_btn["action_params"]["obs_host_id"], "obs-host")
        self.assertEqual(res_btn["action_params"]["path"], "/avatar/live")

    def test_button_dialog_obs_scene_only(self):
        """Test ButtonEditorDialog saving a button that ONLY switches an OBS scene."""
        parent = QWidget()
        hosts = [
            {"id": "obs-host", "label": "OBS Studio", "host": "127.0.0.1", "port": 54455, "host_type": "obs_websocket"},
        ]
        btn_data = {
            "id": "btn_brb",
            "label": "",
            "action_type": "obs_scene",
            "action_params": {
                "obs_host_id": "obs-host",
                "obs_scene": "BRB",
            },
        }

        saved = []
        dialog = ButtonEditorDialog(
            parent=parent,
            button_data=btn_data,
            hosts=hosts,
            on_save_callback=lambda d: saved.append(d),
        )

        self.assertTrue(dialog.obs_enable_check.isChecked())
        self.assertEqual(dialog.obs_scene_combo.currentText(), "BRB")
        self.assertEqual(dialog.action_type_row.currentIndex(), 4)  # None (OBS Scene Only)

        # Trigger save (Button Label should auto-default to scene if empty)
        dialog._on_save_clicked(None)
        self.assertEqual(len(saved), 1)
        res_btn = saved[0]
        self.assertEqual(res_btn["label"], "BRB")
        self.assertEqual(res_btn["action_type"], "obs_scene")
        self.assertEqual(res_btn["action_params"]["obs_scene"], "BRB")


if __name__ == "__main__":
    unittest.main()
