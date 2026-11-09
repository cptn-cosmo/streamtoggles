"""Stream Deck button tile widget for StreamToggles adhering to modern KDE HIG."""

from __future__ import annotations
import os
from typing import Any, Callable, Dict, Optional

from PyQt6.QtCore import QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


def format_shortcut_for_display(shortcut: str) -> str:
    """Format GTK or raw shortcut string into clean, readable KDE accelerator text."""
    if not shortcut:
        return ""

    s = shortcut.strip()
    replacements = {
        "<Primary>": "Ctrl+",
        "<Control>": "Ctrl+",
        "<Alt>": "Alt+",
        "<Shift>": "Shift+",
        "<Super>": "Meta+",
        "<Meta>": "Meta+",
        "comma": ",",
        "period": ".",
        "question": "?",
        "slash": "/",
        "backslash": "\\",
        "plus": "+",
        "minus": "-",
        "equal": "=",
        "Return": "Enter",
        "space": "Space",
    }
    for old, new in replacements.items():
        s = s.replace(old, new)

    s = s.replace("><", "+").replace("<", "").replace(">", "")
    parts = [p.strip() for p in s.split("+") if p.strip()]
    if not parts:
        return ""

    normalized_parts = []
    for p in parts:
        lower_p = p.lower()
        if lower_p in ("ctrl", "control"):
            normalized_parts.append("Ctrl")
        elif lower_p == "alt":
            normalized_parts.append("Alt")
        elif lower_p == "shift":
            normalized_parts.append("Shift")
        elif lower_p in ("meta", "super"):
            normalized_parts.append("Meta")
        else:
            if len(p) == 1 and p.isalpha():
                normalized_parts.append(p.upper())
            else:
                normalized_parts.append(p)

    return "+".join(normalized_parts)


class StreamDeckTile(QFrame):
    """A single tile in the Stream Deck grid."""

    def __init__(
        self,
        button_data: Dict[str, Any],
        on_activate: Callable[[str], None],
        on_edit: Callable[[str], None],
        on_delete: Callable[[str], None],
        on_move: Callable[[str, int], None],
        group_label: Optional[str] = None,
    ):
        super().__init__()
        self.setObjectName("DeckTile")
        self.setFixedSize(132, 132)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.button_data = button_data
        self.button_id = button_data.get("id", "")
        self.group_label = group_label
        self.on_activate = on_activate
        self.on_edit = on_edit
        self.on_delete = on_delete
        self.on_move = on_move

        self.is_edit_mode = False
        self.is_active = False
        self.custom_pixmap: Optional[QPixmap] = None

        # Compatibility reference for tests
        self.main_btn = self

        self._build_ui()

    def has_css_class(self, class_name: str) -> bool:
        """Compatibility helper for class checks."""
        if class_name == "deck-tile-active":
            return self.is_active
        if class_name == "tile-pressed":
            return bool(self.property("pressed"))
        return False

    def _build_ui(self) -> None:
        """Construct the tile layout with badges, icon, title, and edit overlay."""
        # 1. Load icon or full-size custom image
        self.icon_label = QLabel()
        self.icon_label.setObjectName("DeckTileIcon")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setFixedSize(38, 38)
        self._load_icon()

        if self.custom_pixmap is not None:
            self.setProperty("has_image", True)

        # Main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(6, 6, 6, 6)
        self.main_layout.setSpacing(2)

        # 2. Badges row (Group pill and Shortcut pill)
        raw_shortcut = self.button_data.get("shortcut", "").strip()
        display_shortcut = format_shortcut_for_display(raw_shortcut)

        if display_shortcut or self.group_label:
            badges_layout = QHBoxLayout()
            badges_layout.setContentsMargins(0, 0, 0, 0)
            badges_layout.setSpacing(4)
            badges_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            if self.group_label:
                grp_text = self.group_label
                if len(grp_text) > 9:
                    grp_text = grp_text[:8] + "…"
                grp_lbl = QLabel(grp_text)
                grp_lbl.setObjectName("GroupBadge")
                grp_lbl.setToolTip(f"Group: {self.group_label}")
                grp_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                badges_layout.addWidget(grp_lbl)

            if display_shortcut:
                sh_lbl = QLabel(display_shortcut)
                sh_lbl.setObjectName("ShortcutBadge")
                sh_lbl.setToolTip(f"Global Shortcut: {display_shortcut}")
                sh_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                badges_layout.addWidget(sh_lbl)

            self.main_layout.addLayout(badges_layout)

        # 3. Middle Area (Fallback icon or stretch spacer for full image)
        if self.custom_pixmap is None:
            self.main_layout.addWidget(self.icon_label, alignment=Qt.AlignmentFlag.AlignCenter)
        else:
            self.main_layout.addStretch()

        # 4. Title Label (fills width, multi-line wrap, bottom alignment over image)
        title = self.button_data.get("label", "").strip()
        self.title_label = QLabel(title or "Toggle")
        self.title_label.setObjectName("DeckTileLabel")
        self.title_label.setWordWrap(True)
        self.title_label.setToolTip(title)

        if self.custom_pixmap is not None:
            self.title_label.setProperty("on_image", True)
            self.title_label.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)
            self.title_label.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Minimum,
            )
            # Ensure text is bright white and bold over the protective scrim gradient
            self.title_label.setStyleSheet("color: #ffffff; font-weight: 700;")
            if not title:
                self.title_label.hide()
        else:
            self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.title_label.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )

        self.main_layout.addWidget(self.title_label)

        # Set tooltip on tile as well for instant feedback
        tooltip_parts = [title] if title else []
        if self.group_label:
            tooltip_parts.append(f"Group: {self.group_label}")
        if display_shortcut:
            tooltip_parts.append(f"Shortcut: {display_shortcut}")
        if tooltip_parts:
            self.setToolTip(" • ".join(tooltip_parts))

        # --- Edit Mode Overlay Controls ---
        self._build_edit_overlay()

    def _build_edit_overlay(self) -> None:
        """Build edit mode overlay bar and controls."""
        self.overlay_widget = QWidget(self)
        self.overlay_widget.setGeometry(0, 0, self.width(), self.height())
        self.overlay_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        overlay_layout = QVBoxLayout(self.overlay_widget)
        overlay_layout.setContentsMargins(4, 4, 4, 4)
        overlay_layout.setSpacing(0)

        # Top Bar: Edit and Delete
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(2)
        top_bar.addStretch()

        top_container = QFrame()
        top_container.setObjectName("EditOverlayBar")
        top_container_layout = QHBoxLayout(top_container)
        top_container_layout.setContentsMargins(2, 2, 2, 2)
        top_container_layout.setSpacing(2)

        edit_btn = QToolButton()
        edit_btn.setObjectName("EditActionBtn")
        edit_btn.setIcon(QIcon.fromTheme("document-edit"))
        edit_btn.setToolTip("Edit Toggle")
        edit_btn.setIconSize(QSize(16, 16))
        edit_btn.clicked.connect(lambda: self.on_edit(self.button_id))
        top_container_layout.addWidget(edit_btn)

        del_btn = QToolButton()
        del_btn.setObjectName("EditDeleteBtn")
        del_btn.setIcon(QIcon.fromTheme("edit-delete", QIcon.fromTheme("user-trash")))
        del_btn.setToolTip("Delete Toggle")
        del_btn.setIconSize(QSize(16, 16))
        del_btn.clicked.connect(lambda: self.on_delete(self.button_id))
        top_container_layout.addWidget(del_btn)

        top_bar.addWidget(top_container)
        overlay_layout.addLayout(top_bar)
        overlay_layout.addStretch()

        # Bottom Bar: Reorder buttons
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 0, 0, 0)
        bottom_bar.setSpacing(2)
        bottom_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)

        bottom_container = QFrame()
        bottom_container.setObjectName("EditOverlayBar")
        bottom_container_layout = QHBoxLayout(bottom_container)
        bottom_container_layout.setContentsMargins(2, 2, 2, 2)
        bottom_container_layout.setSpacing(2)

        left_btn = QToolButton()
        left_btn.setObjectName("EditActionBtn")
        left_btn.setIcon(QIcon.fromTheme("go-previous"))
        left_btn.setToolTip("Move Left")
        left_btn.setIconSize(QSize(16, 16))
        left_btn.clicked.connect(lambda: self.on_move(self.button_id, -1))
        bottom_container_layout.addWidget(left_btn)

        right_btn = QToolButton()
        right_btn.setObjectName("EditActionBtn")
        right_btn.setIcon(QIcon.fromTheme("go-next"))
        right_btn.setToolTip("Move Right")
        right_btn.setIconSize(QSize(16, 16))
        right_btn.clicked.connect(lambda: self.on_move(self.button_id, 1))
        bottom_container_layout.addWidget(right_btn)

        bottom_bar.addWidget(bottom_container)
        overlay_layout.addLayout(bottom_bar)

        self.overlay_widget.setVisible(False)

    def _load_icon(self) -> None:
        """Load custom image covering button or fallback Breeze icon."""
        img_path = self.button_data.get("image_path", "").strip()
        if img_path and os.path.exists(img_path):
            pixmap = QPixmap(img_path)
            if not pixmap.isNull():
                self.custom_pixmap = pixmap
                self.icon_label.hide()
                return

        self.custom_pixmap = None
        self.icon_label.show()
        action_type = self.button_data.get("action_type", "single_http")
        obs_scene = self.button_data.get("obs_scene") or self.button_data.get("action_params", {}).get("obs_scene")
        if action_type == "command":
            icon_name = "utilities-terminal"
        elif action_type == "double_http":
            icon_name = "media-playlist-repeat"
        elif action_type == "toggle_http":
            icon_name = "view-refresh"
        elif action_type in ("obs_scene", "none") or obs_scene:
            icon_name = "video-display"
        else:
            icon_name = "network-server"

        icon = QIcon.fromTheme(icon_name)
        if not icon.isNull():
            self.icon_label.setPixmap(icon.pixmap(34, 34))
        else:
            fallback = QIcon.fromTheme("system-run", QIcon.fromTheme("application-x-executable"))
            self.icon_label.setPixmap(fallback.pixmap(34, 34))

    def set_active_state(self, is_active: bool) -> None:
        """Update in-memory active state and visual styling."""
        self.is_active = is_active
        self.setProperty("active", is_active)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def pulse(self) -> None:
        """Trigger immediate subtle visual press feedback in the UI."""
        self.setProperty("pressed", True)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        QTimer.singleShot(180, self._remove_press_effect)

    def _remove_press_effect(self) -> None:
        self.setProperty("pressed", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def set_edit_mode(self, enabled: bool) -> None:
        """Toggle edit mode display."""
        self.is_edit_mode = enabled
        self.overlay_widget.setVisible(enabled)

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        if self.custom_pixmap is not None:
            self.update()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        if self.custom_pixmap is not None:
            self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.custom_pixmap is None:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # 1. Clip to rounded rectangle (14px radius to match KDE Breeze card HIG)
        clip_path = QPainterPath()
        rect_f = QRectF(self.rect())
        clip_path.addRoundedRect(rect_f, 14.0, 14.0)
        painter.setClipPath(clip_path)

        # Fill background under transparent images with card background
        painter.fillPath(clip_path, self.palette().button())

        # 2. Scale image to cover the full button area (centered, aspect-ratio preserved)
        scaled = self.custom_pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)

        # 3. State Overlays
        is_pressed = bool(self.property("pressed"))
        is_hovered = self.underMouse()

        if is_pressed:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 75))
        elif self.is_active:
            hl = self.palette().highlight().color()
            painter.fillRect(self.rect(), QColor(hl.red(), hl.green(), hl.blue(), 55))
        elif is_hovered:
            painter.fillRect(self.rect(), QColor(255, 255, 255, 25))

        # 4. Protective bottom scrim gradient for title label legibility
        title = self.button_data.get("label", "").strip()
        if title:
            bot_grad = QLinearGradient(0, self.height() * 0.45, 0, self.height())
            bot_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
            bot_grad.setColorAt(0.4, QColor(0, 0, 0, 95))
            bot_grad.setColorAt(1.0, QColor(0, 0, 0, 215))
            painter.fillRect(self.rect(), bot_grad)

        # 5. Crisp Card Border (drawn on top of the image and scrim)
        painter.setClipping(False)
        if is_pressed or self.is_active:
            pen = QPen(self.palette().highlight().color(), 2.5)
        elif is_hovered:
            pen = QPen(self.palette().highlight().color(), 1.5)
        else:
            pen = QPen(self.palette().mid().color(), 1.0)

        half = pen.widthF() / 2.0
        border_rect = QRectF(half, half, self.width() - pen.widthF(), self.height() - pen.widthF())
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(border_rect, 14.0, 14.0)

        painter.end()

    def mousePressEvent(self, event) -> None:
        """Handle tile click."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_edit_mode:
                self.on_edit(self.button_id)
            else:
                self.pulse()
                self.on_activate(self.button_id)
        super().mousePressEvent(event)

    def resizeEvent(self, event) -> None:
        """Ensure overlay widget matches tile geometry."""
        super().resizeEvent(event)
        if hasattr(self, "overlay_widget"):
            self.overlay_widget.setGeometry(0, 0, self.width(), self.height())
