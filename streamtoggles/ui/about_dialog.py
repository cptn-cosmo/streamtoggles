"""About dialog for StreamToggles adhering to modern KDE HIG."""

from __future__ import annotations
import os
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from streamtoggles import __app_id__, __version__


class AboutDialog(QDialog):
    """Modern KDE About Dialog for StreamToggles."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("About StreamToggles")
        self.setMinimumWidth(440)
        self.setModal(True)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header with Icon and Title
        header_layout = QHBoxLayout()
        header_layout.setSpacing(16)

        icon_label = QLabel()
        icon = QIcon.fromTheme(__app_id__)
        if icon.isNull():
            # Try bundled path
            data_icon_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "data", "icons", "com.github.streamtoggles.StreamToggles.svg"
            )
            if os.path.exists(data_icon_path):
                icon = QIcon(data_icon_path)
            else:
                icon = QIcon.fromTheme("applications-multimedia")

        icon_label.setPixmap(icon.pixmap(64, 64))
        header_layout.addWidget(icon_label)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)
        app_title = QLabel("StreamToggles")
        app_title.setStyleSheet("font-size: 20px; font-weight: bold;")
        ver_label = QLabel(f"Version {__version__}")
        ver_label.setStyleSheet("color: palette(placeholder-text); font-size: 12px;")
        title_layout.addWidget(app_title)
        title_layout.addWidget(ver_label)
        header_layout.addLayout(title_layout, stretch=1)

        layout.addLayout(header_layout)

        # Description
        desc_label = QLabel(
            "A native Linux macro pad and toggle controller designed for desktop streaming setups "
            "(veadotube mini, OBS Studio, PipeWire, audio toggles, and local scripts)."
        )
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Details
        meta_label = QLabel(
            "<b>Toolkit:</b> Qt 6 / KDE Plasma<br>"
            "<b>License:</b> MIT License<br>"
            "<b>Authors:</b> StreamToggles Contributors<br>"
            "<b>Website:</b> <a href='https://github.com/cptn-cosmo/streamtoggles'>https://github.com/cptn-cosmo/streamtoggles</a><br>"
            "<b>Issues:</b> <a href='https://github.com/cptn-cosmo/streamtoggles/issues'>GitHub Issue Tracker</a>"
        )
        meta_label.setOpenExternalLinks(True)
        meta_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(meta_label)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        about_qt_btn = QPushButton("About Qt")
        about_qt_btn.clicked.connect(lambda: QApplication.aboutQt())
        button_box.addButton(about_qt_btn, QDialogButtonBox.ButtonRole.ActionRole)
        button_box.rejected.connect(self.accept)
        layout.addWidget(button_box)

    def present(self, _parent: Optional[QWidget] = None) -> None:
        """Compatibility helper matching Libadwaita dialog presentation."""
        self.exec()
