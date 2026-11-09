"""Main application entry point for StreamToggles adhering to modern KDE HIG."""

from __future__ import annotations
import logging
import signal
import sys
from typing import Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from streamtoggles import __app_id__, __version__
from streamtoggles.config import ConfigManager
from streamtoggles.executor import ActionExecutor
from streamtoggles.portal import GlobalShortcutsPortal
from streamtoggles.ui.style import load_application_styles
from streamtoggles.ui.window import StreamTogglesWindow

logger = logging.getLogger("streamtoggles")


class StreamTogglesApp:
    """The Qt6 application managing lifecycle, actions, and window state."""

    def __init__(self, config_path: Optional[str] = None, args: Optional[list] = None):
        self.config_path = config_path
        self.qapp = QApplication.instance() or QApplication(args or sys.argv)
        self.qapp.setApplicationName("StreamToggles")
        self.qapp.setApplicationDisplayName("StreamToggles")
        self.qapp.setApplicationVersion(__version__)
        self.qapp.setDesktopFileName(__app_id__)

        self.config_manager: Optional[ConfigManager] = None
        self.executor: Optional[ActionExecutor] = None
        self.portal: Optional[GlobalShortcutsPortal] = None
        self.window: Optional[StreamTogglesWindow] = None

        self._init_services()

    def _init_services(self) -> None:
        """Initialize styles, config, executor, portal, and main window."""
        load_application_styles(self.qapp)

        # Config manager
        self.config_manager = ConfigManager(self.config_path)

        # Action Executor
        self.executor = ActionExecutor(
            get_host_callback=self.config_manager.get_host_by_id,
            notify_toast_callback=self._on_executor_toast,
        )

        # Portal Global Shortcuts
        self.portal = GlobalShortcutsPortal(
            on_activated_callback=self._on_portal_shortcut_activated,
            get_buttons_callback=self.config_manager.get_buttons,
        )

        # Main Window
        self.window = StreamTogglesWindow(
            app=self.qapp,
            config_manager=self.config_manager,
            executor=self.executor,
            portal=self.portal,
        )

        # Hook application clean shutdown
        self.qapp.aboutToQuit.connect(self.shutdown)

        # Allow Python to handle Ctrl+C in terminal gracefully
        self._sigint_timer = QTimer()
        self._sigint_timer.timeout.connect(lambda: None)
        self._sigint_timer.start(500)
        signal.signal(signal.SIGINT, lambda *_: self.qapp.quit())

    def run(self, args: Optional[list] = None) -> int:
        """Present main window and execute Qt main loop."""
        if self.window:
            self.window.show()
        return self.qapp.exec()

    def shutdown(self) -> None:
        """Clean up portal subscriptions and background threads on exit."""
        if self.window:
            self.window.save_window_state()
        if self.portal:
            self.portal.close()
        if self.executor:
            self.executor.shutdown()

    def _on_executor_toast(self, message: str) -> None:
        """Forward background executor notifications to active window toast banner."""
        if self.window:
            self.window.show_toast(message)

    def _on_portal_shortcut_activated(self, button_id: str) -> None:
        """Triggered when a global portal shortcut fires."""
        logger.info("Global shortcut fired for button_id: %s", button_id)
        if self.window:
            self.window.pulse_tile(button_id)
            self.window.handle_tile_activate(button_id)


def main(args: Optional[list] = None) -> int:
    """CLI entrypoint."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    )
    if args is None:
        args = sys.argv

    app = StreamTogglesApp(args=args)
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
