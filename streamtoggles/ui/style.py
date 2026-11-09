"""QSS and styling definitions for StreamToggles adhering to modern KDE Plasma HIG."""

from __future__ import annotations
from PyQt6.QtWidgets import QApplication

MODERN_KDE_STYLESHEET = """
/* Stream Deck Tile Card Styling */
QFrame#DeckTile {
    background-color: palette(button);
    border: 1px solid palette(mid);
    border-radius: 14px;
}

QFrame#DeckTile:hover {
    border: 1px solid palette(highlight);
    background-color: palette(light);
}

/* Pressed / Tactile Pulse Feedback */
QFrame#DeckTile[pressed="true"] {
    background-color: palette(midlight);
    border: 2px solid palette(highlight);
}

/* Active Toggle State */
QFrame#DeckTile[active="true"] {
    border: 2px solid palette(highlight);
    background-color: palette(midlight);
}

QFrame#DeckTile[active="true"]:hover {
    border: 2px solid palette(highlight);
}

/* Tile Icon Thumbnail */
QLabel#DeckTileIcon {
    margin-top: 4px;
    margin-bottom: 2px;
}

/* Label text below icon */
QLabel#DeckTileLabel {
    font-size: 11px;
    font-weight: 600;
    color: palette(button-text);
    padding: 0px 2px;
}

QLabel#DeckTileLabel[on_image="true"] {
    color: #ffffff;
    font-weight: 700;
    padding-bottom: 2px;
}

/* Shortcut badge pill */
QLabel#ShortcutBadge {
    font-size: 10px;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
    background-color: palette(button);
    color: palette(button-text);
    border: 1px solid palette(mid);
    border-bottom: 2px solid palette(dark);
}

/* Group indicator badge pill */
QLabel#GroupBadge {
    font-size: 10px;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 4px;
    background-color: palette(alternate-base);
    color: palette(text);
    border: 1px solid palette(mid);
}

/* Edit Mode Overlay */
QFrame#EditOverlayBar {
    background-color: rgba(30, 30, 30, 0.75);
    border-radius: 8px;
    padding: 2px;
}

QToolButton#EditActionBtn {
    background-color: transparent;
    border: none;
    border-radius: 4px;
    padding: 3px;
}

QToolButton#EditActionBtn:hover {
    background-color: rgba(255, 255, 255, 0.25);
}

QToolButton#EditDeleteBtn:hover {
    background-color: rgba(218, 68, 83, 0.7);
}

/* Canvas Sections */
QLabel#SectionTitle {
    font-size: 14px;
    font-weight: bold;
    color: palette(text);
    padding: 4px 0px;
}

QFrame#SectionSeparator {
    color: palette(mid);
    background-color: palette(mid);
}

QLabel#SectionEmptyHint {
    font-size: 12px;
    color: palette(placeholder-text);
    font-style: italic;
    padding: 8px 12px;
}

/* Toast Notification Overlay */
QFrame#ToastNotification {
    background-color: palette(highlight);
    color: palette(highlighted-text);
    border-radius: 10px;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 13px;
}

QLabel#ToastLabel {
    color: palette(highlighted-text);
    font-weight: 600;
}

/* Primary Suggested Action Buttons */
QPushButton[suggested="true"] {
    background-color: palette(highlight);
    color: palette(highlighted-text);
    font-weight: 600;
    border-radius: 6px;
    padding: 6px 14px;
}

QPushButton[suggested="true"]:hover {
    background-color: palette(highlight);
    opacity: 0.9;
}
"""


def load_application_styles(app: Optional[QApplication] = None) -> None:
    """Apply modern KDE Breeze-compatible application stylesheet and icon theme."""
    import os
    from PyQt6.QtGui import QIcon

    target_app = app or QApplication.instance()
    if target_app and hasattr(target_app, "setStyleSheet"):
        target_app.setStyleSheet(MODERN_KDE_STYLESHEET)

    # Ensure system icon directories are included for standard KDE Breeze icons
    paths = QIcon.themeSearchPaths()
    for p in ["/usr/share/icons", "/usr/local/share/icons", os.path.expanduser("~/.local/share/icons")]:
        if os.path.isdir(p) and p not in paths:
            paths.append(p)
    QIcon.setThemeSearchPaths(paths)

    if not QIcon.themeName():
        for name in ["breeze", "breeze-dark", "hicolor"]:
            if any(os.path.isdir(os.path.join(p, name)) for p in paths):
                QIcon.setThemeName(name)
                break
