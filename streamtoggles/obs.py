"""OBS Studio integration service for StreamToggles.

Supports both:
1. Native OBS Studio WebSocket v5 protocol (JSON over WebSocket, default port 4455)
   - Follows RFC 6455 framing with standard library sockets (no external dependencies).
   - Handles Hello (op 0), Identify (op 1 with SHA-256 challenge auth), Identified (op 2).
   - GetSceneList (op 6) and SetCurrentProgramScene (op 6).
2. HTTP POST requests (e.g. obs-websocket-http bridge, default port 8080)
   - POST /call with JSON payload:
     {"request-type": "SetCurrentProgramScene", "sceneName": "YourSceneName"}
   - POST /call or GET /call/GetSceneList for retrieving scene lists.
"""

from __future__ import annotations
import base64
import hashlib
import json
import logging
import os
import socket
import struct
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("streamtoggles.obs")


class OBSClient:
    """Client for controlling OBS Studio via WebSocket v5 or HTTP POST bridge."""

    def __init__(self):
        pass

    @staticmethod
    def is_websocket_host(host_info: Dict[str, Any]) -> bool:
        """Determine whether the configured host should use WebSocket v5 or HTTP POST."""
        host_type = host_info.get("host_type", "").lower()
        if host_type in ("obs_websocket", "websocket", "ws"):
            return True
        if host_type in ("obs_http", "http", "http_post"):
            return False

        port = int(host_info.get("port", 0))
        if port == 4455:
            return True
        if port == 8080:
            return False

        label = host_info.get("label", "").lower()
        host_id = host_info.get("id", "").lower()
        if "websocket" in label or "websocket" in host_id:
            return True
        if "http" in label or "http" in host_id:
            return False

        # Default to WebSocket for OBS Studio v28+ standard
        return True

    def switch_scene(self, host_info: Dict[str, Any], scene_name: str, timeout: float = 2.5) -> bool:
        """Switch the current program scene in OBS Studio."""
        if not scene_name:
            logger.warning("switch_scene called with empty scene_name")
            return False

        host = host_info.get("host", "127.0.0.1")
        port = int(host_info.get("port", 4455))
        password = host_info.get("password", "")
        path = host_info.get("path", "/call")

        is_ws = self.is_websocket_host(host_info)

        if is_ws:
            try:
                return self._ws_switch_scene(host, port, password, scene_name, timeout)
            except Exception as e:
                logger.warning("OBS WebSocket switch_scene failed on %s:%s: %s", host, port, e)
                # If host_type wasn't explicitly set, try HTTP POST fallback
                if not host_info.get("host_type"):
                    try:
                        return self._http_switch_scene(host, port, path, password, scene_name, timeout)
                    except Exception:
                        pass
                raise
        else:
            try:
                return self._http_switch_scene(host, port, path, password, scene_name, timeout)
            except Exception as e:
                logger.warning("OBS HTTP POST switch_scene failed on %s:%s%s: %s", host, port, path, e)
                if not host_info.get("host_type"):
                    try:
                        return self._ws_switch_scene(host, port, password, scene_name, timeout)
                    except Exception:
                        pass
                raise

    def get_scene_list(self, host_info: Dict[str, Any], timeout: float = 2.5) -> List[str]:
        """Fetch the list of scene names from OBS Studio."""
        host = host_info.get("host", "127.0.0.1")
        port = int(host_info.get("port", 4455))
        password = host_info.get("password", "")
        path = host_info.get("path", "/call")

        is_ws = self.is_websocket_host(host_info)

        if is_ws:
            try:
                return self._ws_get_scenes(host, port, password, timeout)
            except Exception as e:
                logger.warning("OBS WebSocket get_scene_list failed on %s:%s: %s", host, port, e)
                if not host_info.get("host_type"):
                    try:
                        return self._http_get_scenes(host, port, path, password, timeout)
                    except Exception:
                        pass
                raise
        else:
            try:
                return self._http_get_scenes(host, port, path, password, timeout)
            except Exception as e:
                logger.warning("OBS HTTP POST get_scene_list failed on %s:%s%s: %s", host, port, path, e)
                if not host_info.get("host_type"):
                    try:
                        return self._ws_get_scenes(host, port, password, timeout)
                    except Exception:
                        pass
                raise

    def test_connection(self, host_info: Dict[str, Any], timeout: float = 2.5) -> Dict[str, Any]:
        """Test connection to OBS Studio and return status information."""
        try:
            scenes = self.get_scene_list(host_info, timeout=timeout)
            protocol = "WebSocket v5" if self.is_websocket_host(host_info) else "HTTP POST"
            return {
                "success": True,
                "protocol": protocol,
                "scene_count": len(scenes),
                "scenes": scenes,
                "message": f"Connected via {protocol}. Found {len(scenes)} scenes.",
            }
        except Exception as e:
            return {
                "success": False,
                "protocol": "WebSocket v5" if self.is_websocket_host(host_info) else "HTTP POST",
                "scene_count": 0,
                "scenes": [],
                "message": str(e),
            }

    # =========================================================================
    # WebSocket v5 Protocol Implementation (RFC 6455)
    # =========================================================================

    def _build_ws_frame(self, payload_bytes: bytes, opcode: int = 0x1, mask: bool = True) -> bytes:
        """Construct an RFC 6455 WebSocket frame."""
        length = len(payload_bytes)
        header = bytearray([0x80 | (opcode & 0x0F)])  # FIN = 1
        mask_bit = 0x80 if mask else 0x00

        if length < 126:
            header.append(mask_bit | length)
        elif length <= 65535:
            header.append(mask_bit | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(mask_bit | 127)
            header.extend(struct.pack("!Q", length))

        if mask:
            mask_key = os.urandom(4)
            header.extend(mask_key)
            masked_payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload_bytes))
            return bytes(header) + masked_payload
        return bytes(header) + payload_bytes

    def _recv_ws_frame(self, sock: socket.socket, buffer: bytearray, timeout: float = 2.5) -> Tuple[int, bytes]:
        """Read a single RFC 6455 frame from the socket buffer."""
        sock.settimeout(timeout)
        while len(buffer) < 2:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("WebSocket connection closed by server")
            buffer.extend(chunk)

        byte0 = buffer[0]
        byte1 = buffer[1]
        opcode = byte0 & 0x0F
        masked = (byte1 & 0x80) != 0
        payload_len = byte1 & 0x7F

        header_len = 2
        if payload_len == 126:
            while len(buffer) < 4:
                chunk = sock.recv(4096)
                if not chunk:
                    raise ConnectionError("WebSocket closed while reading 16-bit length")
                buffer.extend(chunk)
            payload_len = struct.unpack("!H", buffer[2:4])[0]
            header_len = 4
        elif payload_len == 127:
            while len(buffer) < 10:
                chunk = sock.recv(4096)
                if not chunk:
                    raise ConnectionError("WebSocket closed while reading 64-bit length")
                buffer.extend(chunk)
            payload_len = struct.unpack("!Q", buffer[2:10])[0]
            header_len = 10

        mask_key = None
        if masked:
            while len(buffer) < header_len + 4:
                chunk = sock.recv(4096)
                if not chunk:
                    raise ConnectionError("WebSocket closed while reading mask key")
                buffer.extend(chunk)
            mask_key = buffer[header_len : header_len + 4]
            header_len += 4

        total_frame_len = header_len + payload_len
        while len(buffer) < total_frame_len:
            chunk = sock.recv(min(65536, total_frame_len - len(buffer)))
            if not chunk:
                raise ConnectionError("WebSocket closed while reading payload")
            buffer.extend(chunk)

        payload = buffer[header_len:total_frame_len]
        del buffer[:total_frame_len]

        if masked and mask_key:
            payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

        return opcode, bytes(payload)

    def _recv_ws_text(self, sock: socket.socket, buffer: bytearray, timeout: float = 2.5) -> str:
        """Receive the next text message, handling control frames (ping/pong)."""
        while True:
            opcode, payload = self._recv_ws_frame(sock, buffer, timeout=timeout)
            if opcode == 0x8:  # Close
                raise ConnectionError("WebSocket closed by server")
            elif opcode == 0x9:  # Ping
                pong_frame = self._build_ws_frame(payload, opcode=0xA, mask=True)
                sock.sendall(pong_frame)
                continue
            elif opcode == 0x1:  # Text
                return payload.decode("utf-8", errors="replace")

    def _ws_connect_and_identify(
        self, host: str, port: int, password: str, timeout: float = 2.5
    ) -> Tuple[socket.socket, bytearray]:
        """Establish WebSocket connection and complete OBS v5 Hello/Identify handshake."""
        sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        handshake = (
            f"GET / HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(handshake.encode("utf-8"))

        # Read HTTP handshake response
        buffer = bytearray()
        while b"\r\n\r\n" not in buffer:
            chunk = sock.recv(4096)
            if not chunk:
                sock.close()
                raise ConnectionError("Connection closed before WebSocket handshake completed")
            buffer.extend(chunk)

        header_bytes, _, leftover = buffer.partition(b"\r\n\r\n")
        first_line = header_bytes.split(b"\r\n")[0].decode("utf-8", errors="replace")
        if "101" not in first_line:
            sock.close()
            raise ConnectionError(f"WebSocket handshake rejected by server: {first_line}")

        # Buffer now holds any leftover bytes from the initial frame
        buffer = bytearray(leftover)

        # 1. Server sends Hello (op 0)
        hello_msg = self._recv_ws_text(sock, buffer, timeout=timeout)
        hello_data = json.loads(hello_msg)
        if hello_data.get("op") != 0:
            sock.close()
            raise ConnectionError(f"Expected Hello (op 0), got: {hello_data}")

        d = hello_data.get("d", {})
        auth_info = d.get("authentication")

        # 2. Client sends Identify (op 1)
        identify_d: Dict[str, Any] = {"rpcVersion": 1}
        if auth_info:
            salt = auth_info.get("salt", "")
            challenge = auth_info.get("challenge", "")
            if not password:
                sock.close()
                raise PermissionError("OBS Studio requires authentication, but no password was provided")
            # obs-websocket v5 auth formula
            h1 = hashlib.sha256((password + salt).encode("utf-8")).digest()
            secret = base64.b64encode(h1).decode("utf-8")
            h2 = hashlib.sha256((secret + challenge).encode("utf-8")).digest()
            auth_str = base64.b64encode(h2).decode("utf-8")
            identify_d["authentication"] = auth_str

        identify_pkt = json.dumps({"op": 1, "d": identify_d})
        sock.sendall(self._build_ws_frame(identify_pkt.encode("utf-8"), opcode=0x1, mask=True))

        # 3. Server sends Identified (op 2)
        identified_msg = self._recv_ws_text(sock, buffer, timeout=timeout)
        identified_data = json.loads(identified_msg)
        if identified_data.get("op") != 2:
            sock.close()
            raise ConnectionError(f"Authentication/Identify failed: {identified_data}")

        return sock, buffer

    def _ws_switch_scene(
        self, host: str, port: int, password: str, scene_name: str, timeout: float = 2.5
    ) -> bool:
        """Switch scene using OBS WebSocket v5."""
        sock, buffer = self._ws_connect_and_identify(host, port, password, timeout=timeout)
        try:
            req_id = f"switch-{uuid.uuid4().hex[:8]}"
            req = {
                "op": 6,
                "d": {
                    "requestType": "SetCurrentProgramScene",
                    "requestId": req_id,
                    "requestData": {
                        "sceneName": scene_name,
                    },
                },
            }
            sock.sendall(self._build_ws_frame(json.dumps(req).encode("utf-8"), opcode=0x1, mask=True))
            resp_msg = self._recv_ws_text(sock, buffer, timeout=timeout)
            resp = json.loads(resp_msg)
            req_status = resp.get("d", {}).get("requestStatus", {})
            return bool(req_status.get("result", True))
        finally:
            try:
                # Send close frame
                sock.sendall(self._build_ws_frame(b"", opcode=0x8, mask=True))
            except Exception:
                pass
            sock.close()

    def _ws_get_scenes(self, host: str, port: int, password: str, timeout: float = 2.5) -> List[str]:
        """Fetch list of scene names using OBS WebSocket v5."""
        sock, buffer = self._ws_connect_and_identify(host, port, password, timeout=timeout)
        try:
            req_id = f"scenes-{uuid.uuid4().hex[:8]}"
            req = {
                "op": 6,
                "d": {
                    "requestType": "GetSceneList",
                    "requestId": req_id,
                },
            }
            sock.sendall(self._build_ws_frame(json.dumps(req).encode("utf-8"), opcode=0x1, mask=True))
            resp_msg = self._recv_ws_text(sock, buffer, timeout=timeout)
            resp = json.loads(resp_msg)
            resp_data = resp.get("d", {}).get("responseData", {})
            scenes = resp_data.get("scenes", [])
            names: List[str] = []
            for s in scenes:
                if isinstance(s, dict) and "sceneName" in s:
                    names.append(s["sceneName"])
                elif isinstance(s, str):
                    names.append(s)
            return names
        finally:
            try:
                sock.sendall(self._build_ws_frame(b"", opcode=0x8, mask=True))
            except Exception:
                pass
            sock.close()

    # =========================================================================
    # HTTP POST Bridge Protocol Implementation (e.g. obs-websocket-http)
    # =========================================================================

    def _http_switch_scene(
        self, host: str, port: int, path: str, password: str, scene_name: str, timeout: float = 2.5
    ) -> bool:
        """Switch scene using HTTP POST bridge (e.g. curl -X POST http://localhost:8080/call)."""
        if not path.startswith("/"):
            path = "/" + path
        url = f"http://{host}:{port}{path}"

        # Send both 'request-type' and 'requestType' for bridge compatibility
        payload = {
            "request-type": "SetCurrentProgramScene",
            "requestType": "SetCurrentProgramScene",
            "sceneName": scene_name,
            "requestData": {
                "sceneName": scene_name,
            },
        }
        body_bytes = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "StreamToggles/1.0",
        }
        if password:
            headers["Authorization"] = f"Bearer {password}"

        req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.status in (200, 201, 204)
        except urllib.error.HTTPError as e:
            logger.warning("HTTP error %s from OBS bridge %s: %s", e.code, url, e.read().decode("utf-8", "ignore"))
            # Many bridges return 200 or return error codes with message
            return False

    def _http_get_scenes(
        self, host: str, port: int, path: str, password: str, timeout: float = 2.5
    ) -> List[str]:
        """Fetch list of scenes from HTTP POST bridge."""
        if not path.startswith("/"):
            path = "/" + path
        url = f"http://{host}:{port}{path}"

        payload = {
            "request-type": "GetSceneList",
            "requestType": "GetSceneList",
        }
        body_bytes = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "StreamToggles/1.0",
        }
        if password:
            headers["Authorization"] = f"Bearer {password}"

        # 1. Try POST to /call
        parsed = None
        try:
            req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as response:
                content = response.read().decode("utf-8")
                parsed = json.loads(content)
        except Exception:
            # 2. Try GET to /call/GetSceneList
            alt_url = f"http://{host}:{port}{path.rstrip('/')}/GetSceneList"
            try:
                alt_req = urllib.request.Request(alt_url, headers=headers, method="GET")
                with urllib.request.urlopen(alt_req, timeout=timeout) as response:
                    content = response.read().decode("utf-8")
                    parsed = json.loads(content)
            except Exception as e:
                logger.error("Failed to query OBS HTTP scenes on %s: %s", url, e)
                raise

        if not parsed:
            return []

        # Parse scenes array from various known bridge response structures
        scenes_data = None
        if isinstance(parsed, list):
            scenes_data = parsed
        elif isinstance(parsed, dict):
            if "scenes" in parsed:
                scenes_data = parsed["scenes"]
            elif "responseData" in parsed and "scenes" in parsed["responseData"]:
                scenes_data = parsed["responseData"]["scenes"]
            elif "d" in parsed and "responseData" in parsed["d"] and "scenes" in parsed["d"]["responseData"]:
                scenes_data = parsed["d"]["responseData"]["scenes"]
            elif "scene-names" in parsed:
                scenes_data = parsed["scene-names"]
            elif "sceneNames" in parsed:
                scenes_data = parsed["sceneNames"]

        names: List[str] = []
        if isinstance(scenes_data, list):
            for s in scenes_data:
                if isinstance(s, dict) and "sceneName" in s:
                    names.append(s["sceneName"])
                elif isinstance(s, str):
                    names.append(s)

        return names
