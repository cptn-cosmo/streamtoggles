"""XDG Desktop Portal GlobalShortcuts integration for StreamToggles.

Communicates with org.freedesktop.portal.GlobalShortcuts via QtDBus / Gio
to register and listen for system-wide keyboard shortcuts across KDE Plasma, Wayland, and Linux desktops.
Includes graceful fallbacks when running without portal support.
"""

from __future__ import annotations
import logging
import os
import random
import subprocess
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import QObject, pyqtSlot
from PyQt6.QtDBus import QDBusConnection, QDBusMessage

logger = logging.getLogger("streamtoggles.portal")

PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
PORTAL_OBJECT_PATH = "/org/freedesktop/portal/desktop"
PORTAL_INTERFACE = "org.freedesktop.portal.GlobalShortcuts"
REQUEST_INTERFACE = "org.freedesktop.portal.Request"


class GlobalShortcutsPortal(QObject):
    """Manages global shortcut registration and signal handling via XDG Desktop Portal."""

    def __init__(
        self,
        on_activated_callback: Callable[[str], None],
        get_buttons_callback: Callable[[], List[Dict[str, Any]]],
    ):
        super().__init__()
        self.on_activated = on_activated_callback
        self.get_buttons = get_buttons_callback
        self._is_available: bool = False
        self.session_handle: Optional[str] = None
        self._gio_portal = None
        self._init_portal()

    @property
    def is_available(self) -> bool:
        return self._is_available

    def _init_portal(self) -> None:
        """Establish DBus connection and initialize the GlobalShortcuts proxy."""
        # Try Gio if available for portal proxy
        try:
            from gi.repository import Gio, GLib  # type: ignore
            self._init_gio_portal(Gio, GLib)
            return
        except Exception as e:
            logger.debug("Gio portal fallback unavailable (%s), trying QtDBus", e)

        # Fallback to QtDBus
        try:
            self.bus = QDBusConnection.sessionBus()
            if not self.bus.isConnected():
                logger.warning("Session D-Bus is not connected. Global shortcuts disabled.")
                self._is_available = False
                return

            # Listen for Activated signal
            ok = self.bus.connect(
                PORTAL_BUS_NAME,
                PORTAL_OBJECT_PATH,
                PORTAL_INTERFACE,
                "Activated",
                self._on_qtdbus_activated,
            )
            if ok:
                self._is_available = True
                logger.info("GlobalShortcuts portal connected via QtDBus.")
                self._create_qtdbus_session()
            else:
                self._is_available = False
        except Exception as e:
            logger.warning(
                "GlobalShortcuts portal unavailable or not supported on this compositor: %s. "
                "Global shortcuts will be disabled; local UI toggles will continue working normally.",
                e,
            )
            self._is_available = False

    def _init_gio_portal(self, Gio, GLib) -> None:
        """Use Gio for portal communication if python-gobject is installed."""
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            proxy = Gio.DBusProxy.new_sync(
                bus,
                Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES,
                None,
                PORTAL_BUS_NAME,
                PORTAL_OBJECT_PATH,
                PORTAL_INTERFACE,
                None,
            )
            self._gio_bus = bus
            self._gio_proxy = proxy
            self._gio_GLib = GLib
            self._gio_Gio = Gio
            self._gio_activated_sub_id = 0
            self._gio_session_sub_id = 0
            self._gio_bind_sub_id = 0

            # Subscribe Activated
            def on_activated(conn, s_name, o_path, iface, sig, params, u_data):
                try:
                    s_handle, shortcut_id, timestamp, options = params.unpack()
                    logger.info("Portal shortcut activated: '%s'", shortcut_id)
                    if self.on_activated:
                        self.on_activated(shortcut_id)
                except Exception as ex:
                    logger.error("Error unpacking portal Activated signal: %s", ex)

            self._gio_activated_sub_id = bus.signal_subscribe(
                PORTAL_BUS_NAME,
                PORTAL_INTERFACE,
                "Activated",
                PORTAL_OBJECT_PATH,
                None,
                Gio.DBusSignalFlags.NONE,
                on_activated,
                None,
            )

            self._is_available = True
            logger.info("GlobalShortcuts portal connected via Gio.")
            self._create_gio_session()
        except Exception as e:
            logger.warning("Gio portal initialization failed: %s", e)
            self._is_available = False

    def _create_gio_session(self) -> None:
        """Request new GlobalShortcuts session via Gio."""
        if not hasattr(self, "_gio_proxy") or not self._gio_proxy:
            return

        Gio = self._gio_Gio
        GLib = self._gio_GLib
        session_token = f"st_sess_{os.getpid()}_{random.randint(10000, 99999)}"
        req_token = f"st_req_{os.getpid()}_{random.randint(10000, 99999)}"
        sender = self._gio_bus.get_unique_name().replace(".", "_").replace(":", "")
        req_path = f"/org/freedesktop/portal/desktop/request/{sender}/{req_token}"

        def on_session_response(conn, s_name, o_path, iface, sig, params, u_data):
            try:
                code, results = params.unpack()
                if self._gio_session_sub_id and self._gio_bus:
                    self._gio_bus.signal_unsubscribe(self._gio_session_sub_id)
                    self._gio_session_sub_id = 0
                if code == 0 and "session_handle" in results:
                    self.session_handle = results["session_handle"]
                    logger.info("GlobalShortcuts session created: %s", self.session_handle)
                    self.bind_configured_shortcuts()
            except Exception as ex:
                logger.error("Error in CreateSession response handler: %s", ex)

        try:
            self._gio_session_sub_id = self._gio_bus.signal_subscribe(
                PORTAL_BUS_NAME,
                REQUEST_INTERFACE,
                "Response",
                req_path,
                None,
                Gio.DBusSignalFlags.NONE,
                on_session_response,
                None,
            )
            options = {
                "session_handle_token": GLib.Variant("s", session_token),
                "handle_token": GLib.Variant("s", req_token),
            }
            self._gio_proxy.CreateSession("(a{sv})", options)
        except Exception as e:
            logger.warning("Failed to invoke CreateSession via Gio: %s", e)

    def _create_qtdbus_session(self) -> None:
        """Create GlobalShortcuts session via busctl/QtDBus."""
        session_token = f"st_sess_{os.getpid()}_{random.randint(10000, 99999)}"
        req_token = f"st_req_{os.getpid()}_{random.randint(10000, 99999)}"

        try:
            res = subprocess.run(
                [
                    "busctl", "--user", "call",
                    PORTAL_BUS_NAME, PORTAL_OBJECT_PATH,
                    PORTAL_INTERFACE, "CreateSession",
                    "a{sv}", "2",
                    "session_handle_token", "s", session_token,
                    "handle_token", "s", req_token,
                ],
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if res.returncode == 0:
                logger.debug("CreateSession sent: %s", res.stdout.strip())
        except Exception as e:
            logger.debug("QtDBus CreateSession attempt: %s", e)

    @pyqtSlot(QDBusMessage)
    def _on_qtdbus_activated(self, message: QDBusMessage) -> None:
        """Handle Activated signal from portal via QtDBus."""
        try:
            args = message.arguments()
            if len(args) >= 2:
                shortcut_id = str(args[1])
                logger.info("Portal shortcut activated (QtDBus): %s", shortcut_id)
                if self.on_activated:
                    self.on_activated(shortcut_id)
        except Exception as e:
            logger.error("Error handling QtDBus Activated signal: %s", e)

    def bind_configured_shortcuts(self) -> None:
        """Bind all shortcuts defined in the current buttons config."""
        if hasattr(self, "_gio_proxy") and self._gio_proxy and self.session_handle:
            self._bind_gio_shortcuts()
            return

    def _bind_gio_shortcuts(self) -> None:
        """Bind shortcuts via Gio backend."""
        Gio = self._gio_Gio
        GLib = self._gio_GLib
        buttons = self.get_buttons()
        shortcuts_list = []
        for btn in buttons:
            shortcut_str = btn.get("shortcut", "").strip()
            if shortcut_str:
                btn_id = btn.get("id", "")
                label = btn.get("label", "Toggle")
                opts = {
                    "description": GLib.Variant("s", label),
                    "preferred_trigger": GLib.Variant("s", shortcut_str),
                }
                shortcuts_list.append((btn_id, opts))

        if not shortcuts_list:
            return

        bind_token = f"st_bind_{os.getpid()}_{random.randint(10000, 99999)}"
        sender = self._gio_bus.get_unique_name().replace(".", "_").replace(":", "")
        req_path = f"/org/freedesktop/portal/desktop/request/{sender}/{bind_token}"

        def on_bind_response(conn, s_name, o_path, iface, sig, params, u_data):
            try:
                code, results = params.unpack()
                if self._gio_bind_sub_id and self._gio_bus:
                    self._gio_bus.signal_unsubscribe(self._gio_bind_sub_id)
                    self._gio_bind_sub_id = 0
                logger.info("BindShortcuts finished with code %s (bound: %s)", code, len(shortcuts_list))
            except Exception as ex:
                logger.error("Error in BindShortcuts response: %s", ex)

        try:
            if self._gio_bind_sub_id and self._gio_bus:
                self._gio_bus.signal_unsubscribe(self._gio_bind_sub_id)
                self._gio_bind_sub_id = 0

            self._gio_bind_sub_id = self._gio_bus.signal_subscribe(
                PORTAL_BUS_NAME,
                REQUEST_INTERFACE,
                "Response",
                req_path,
                None,
                Gio.DBusSignalFlags.NONE,
                on_bind_response,
                None,
            )

            options = {"handle_token": GLib.Variant("s", bind_token)}
            self._gio_proxy.BindShortcuts(
                "(oa(sa{sv})sa{sv})",
                self.session_handle,
                shortcuts_list,
                "",
                options,
            )
        except Exception as e:
            logger.warning("Failed to invoke BindShortcuts: %s", e)

    def close(self) -> None:
        """Clean up signal subscriptions and portal session."""
        if hasattr(self, "_gio_bus") and self._gio_bus:
            for sub_id_attr in ("_gio_activated_sub_id", "_gio_session_sub_id", "_gio_bind_sub_id"):
                sub_id = getattr(self, sub_id_attr, 0)
                if sub_id:
                    try:
                        self._gio_bus.signal_unsubscribe(sub_id)
                    except Exception:
                        pass
                    setattr(self, sub_id_attr, 0)
