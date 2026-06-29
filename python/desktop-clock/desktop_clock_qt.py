#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DesktopClock Qt - Linux 透明背景增强版

说明：
- tkinter 的 -transparentcolor 在 Linux 下常常不生效。
- 这个版本使用 Qt 的 WA_TranslucentBackground 实现真正透明背景。
- 优先使用 PySide6，如果不存在则尝试 PyQt6。
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, Tuple

APP_NAME = "DesktopClockQt"
VERSION = "1.0.0"
MIN_WINDOW_WIDTH = 220
MIN_WINDOW_HEIGHT = 80
DEFAULT_WINDOW_WIDTH = 420
DEFAULT_WINDOW_HEIGHT = 150
RESIZE_HANDLE_SIZE = 22

DEFAULT_CONFIG = {
    "position": {"x": 100, "y": 100},
    "size": {"width": DEFAULT_WINDOW_WIDTH, "height": DEFAULT_WINDOW_HEIGHT},
    "font_size": 48,
    "opacity": 1.0,
    "background_opacity": 0.0,
    "always_on_top": True,
    "transparent_bg": True,
    "theme": "dark",
    "time_format": "%H:%M:%S",
    "date_format": "%Y-%m-%d",
    "show_date": True,
    "show_seconds": True,
    "font_family": "Consolas",
}

THEMES = {
    "dark": {"bg": "#1e1e1e", "fg": "#00ff00", "time_fg": "#00ff00", "date_fg": "#888888"},
    "light": {"bg": "#ffffff", "fg": "#333333", "time_fg": "#222222", "date_fg": "#666666"},
    "blue": {"bg": "#0a1628", "fg": "#00bfff", "time_fg": "#00bfff", "date_fg": "#4682b4"},
    "purple": {"bg": "#1a0a2e", "fg": "#bf00ff", "time_fg": "#bf00ff", "date_fg": "#8b008b"},
    "green": {"bg": "#0a1a0a", "fg": "#00ff7f", "time_fg": "#00ff7f", "date_fg": "#2e8b57"},
}

try:
    from PySide6.QtCore import QPoint, Qt, QTimer
    from PySide6.QtGui import QAction, QFont, QColor
    from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMenu, QSizePolicy, QVBoxLayout, QWidget
except ImportError:
    try:
        from PyQt6.QtCore import QPoint, Qt, QTimer
        from PyQt6.QtGui import QAction, QFont, QColor
        from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QMenu, QSizePolicy, QVBoxLayout, QWidget
    except ImportError as exc:
        raise SystemExit(
            "缺少 Qt 依赖。请先安装：\n"
            "  python3 -m pip install PySide6\n"
            "或：\n"
            "  python3 -m pip install PyQt6"
        ) from exc


def setup_logging():
    """配置日志系统"""
    log_dir = os.path.join(os.path.expanduser("~"), f".{APP_NAME.lower()}")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{APP_NAME.lower()}.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_file, encoding="utf-8")],
    )


class ConfigManager:
    """配置管理器"""

    def __init__(self):
        self.config_dir = os.path.join(os.path.expanduser("~"), f".{APP_NAME.lower()}")
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.config = DEFAULT_CONFIG.copy()
        self.load()

    def load(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self.config.update(json.load(f))
        except Exception as e:
            logging.error(f"加载配置失败：{e}")
        return self.config

    def save(self):
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            tmp_file = f"{self.config_file}.tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, self.config_file)
        except Exception as e:
            logging.error(f"保存配置失败：{e}")

    def get(self, key: str, default=None):
        return self.config.get(key, default)

    def set(self, key: str, value):
        self.config[key] = value


class DesktopClockQt(QMainWindow):
    """Qt 桌面时钟主窗口"""

    def __init__(self):
        super().__init__()
        self.config = ConfigManager()
        self.drag_pos = QPoint()
        self.resize_start_pos = QPoint()
        self.resize_start_size = self.size()
        self.resizing = False

        self.setWindowTitle(APP_NAME)
        self._init_window_flags()
        self._create_ui()
        self._apply_config()
        self._start_timer()

    def _init_window_flags(self):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self.config.get("always_on_top", True):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent;")

    def _create_ui(self):
        self.central = QWidget(self)
        self.central.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.central.setAutoFillBackground(False)
        self.setCentralWidget(self.central)

        self.layout = QVBoxLayout(self.central)
        self.layout.setContentsMargins(14, 10, 14, 10)
        self.layout.setSpacing(2)

        self.time_label = QLabel()
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.layout.addWidget(self.time_label, 3)

        self.date_label = QLabel()
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.layout.addWidget(self.date_label, 1)

        self.resize_handle = QLabel("◢", self)
        self.resize_handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.resize_handle.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.resize_handle.resize(RESIZE_HANDLE_SIZE, RESIZE_HANDLE_SIZE)

    def _apply_config(self):
        pos = self.config.get("position", {})
        size = self.config.get("size", {})
        self.resize(
            max(MIN_WINDOW_WIDTH, size.get("width", DEFAULT_WINDOW_WIDTH)),
            max(MIN_WINDOW_HEIGHT, size.get("height", DEFAULT_WINDOW_HEIGHT)),
        )
        self.move(pos.get("x", 100), pos.get("y", 100))
        self.setWindowOpacity(float(self.config.get("opacity", 1.0)))
        self._apply_theme()
        self._update_clock()

    def _apply_theme(self):
        theme = THEMES.get(self.config.get("theme", "dark"), THEMES["dark"])
        font_family = self.config.get("font_family", "Consolas")
        font_size = int(self.config.get("font_size", 48))
        date_size = max(12, font_size // 3)

        self.time_label.setFont(QFont(font_family, font_size, QFont.Weight.Bold))
        self.date_label.setFont(QFont(font_family, date_size))
        self.resize_handle.setFont(QFont(font_family, 12))

        if self.config.get("transparent_bg", True):
            central_bg = self._rgba_color(theme["bg"], float(self.config.get("background_opacity", 0.0)))
        else:
            central_bg = theme["bg"]

        self.setStyleSheet("background: transparent;")
        self.central.setStyleSheet(f"background-color: {central_bg}; border-radius: 8px;")
        self.time_label.setStyleSheet(f"color: {theme['time_fg']}; background: transparent;")
        self.date_label.setStyleSheet(f"color: {theme['date_fg']}; background: transparent;")
        self.resize_handle.setStyleSheet(f"color: {theme['date_fg']}; background: transparent;")
        self.date_label.setVisible(bool(self.config.get("show_date", True)))

    def _rgba_color(self, hex_color: str, opacity: float) -> str:
        """把主题背景色转换为 rgba，opacity 支持 0.0-1.0。
        
        Linux 下直接写 background: transparent 有些环境会退化为黑底，
        使用 rgba(r,g,b,0) 更明确地告诉 Qt 背景 alpha 为 0。
        """
        color = QColor(hex_color)
        alpha = max(0, min(255, int(opacity * 255)))
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"

    def _start_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_clock)
        self.timer.start(1000)

    def _update_clock(self):
        now = datetime.now()
        self.time_label.setText(now.strftime(self.config.get("time_format", "%H:%M:%S")))
        if self.config.get("show_date", True):
            weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            self.date_label.setText(f"{now.strftime(self.config.get('date_format', '%Y-%m-%d'))} {weekday_names[now.weekday()]}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_handle.move(self.width() - RESIZE_HANDLE_SIZE, self.height() - RESIZE_HANDLE_SIZE)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_on_resize_handle(event.position().toPoint()):
                self.resizing = True
                self.resize_start_pos = event.globalPosition().toPoint()
                self.resize_start_size = self.size()
            else:
                self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event):
        if self.resizing:
            delta = event.globalPosition().toPoint() - self.resize_start_pos
            self.resize(
                max(MIN_WINDOW_WIDTH, self.resize_start_size.width() + delta.x()),
                max(MIN_WINDOW_HEIGHT, self.resize_start_size.height() + delta.y()),
            )
            event.accept()
        elif event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.resizing = False
            self._save_geometry()
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_topmost()
            event.accept()

    def wheelEvent(self, event):
        self._change_font_size(2 if event.angleDelta().y() > 0 else -2)
        event.accept()

    def _is_on_resize_handle(self, pos: QPoint) -> bool:
        return pos.x() >= self.width() - RESIZE_HANDLE_SIZE and pos.y() >= self.height() - RESIZE_HANDLE_SIZE

    def _show_context_menu(self, pos: QPoint):
        menu = QMenu(self)
        menu.addAction("取消固定" if self.config.get("always_on_top", True) else "固定窗口", self._toggle_topmost)
        menu.addSeparator()

        font_menu = menu.addMenu(f"字体大小（当前 {self.config.get('font_size', 48)}px）")
        font_menu.addAction("放大 (+)", lambda: self._change_font_size(2))
        font_menu.addAction("缩小 (-)", lambda: self._change_font_size(-2))
        for size in [24, 36, 48, 60, 72]:
            font_menu.addAction(f"{size}px", lambda checked=False, s=size: self._set_font_size(s))

        size_menu = menu.addMenu(f"窗口大小（当前 {self.width()}x{self.height()}）")
        size_menu.addAction("自动适应文字", self._auto_fit_window)
        size_menu.addAction("放大窗口", lambda: self._resize_by(40, 20))
        size_menu.addAction("缩小窗口", lambda: self._resize_by(-40, -20))
        for width, height in [(360, 130), (420, 150), (520, 180), (640, 220)]:
            size_menu.addAction(f"{width} x {height}", lambda checked=False, w=width, h=height: self._set_window_size(w, h))

        menu.addSeparator()
        menu.addAction("隐藏日期" if self.config.get("show_date", True) else "显示日期", self._toggle_date)
        menu.addAction("关闭透明背景" if self.config.get("transparent_bg", True) else "开启透明背景", self._toggle_transparent_bg)
        menu.addAction("隐藏秒数" if self.config.get("show_seconds", True) else "显示秒数", self._toggle_seconds)

        theme_menu = menu.addMenu("主题")
        for theme_name in THEMES:
            theme_menu.addAction(theme_name.capitalize(), lambda checked=False, t=theme_name: self._set_theme(t))

        bg_opacity_menu = menu.addMenu("背景透明度")
        for opacity in [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]:
            bg_opacity_menu.addAction(
                f"{int(opacity * 100)}%",
                lambda checked=False, o=opacity: self._set_background_opacity(o),
            )

        opacity_menu = menu.addMenu("整体透明度")
        for opacity in [0.3, 0.5, 0.7, 0.8, 0.9, 1.0]:
            opacity_menu.addAction(f"{int(opacity * 100)}%", lambda checked=False, o=opacity: self._set_opacity(o))

        menu.addSeparator()
        menu.addAction("退出", self.close)
        menu.exec(pos)

    def _toggle_topmost(self):
        self.config.set("always_on_top", not self.config.get("always_on_top", True))
        self._save_geometry()
        self.hide()
        self._init_window_flags()
        self.show()

    def _change_font_size(self, delta: int):
        self._set_font_size(max(12, min(120, int(self.config.get("font_size", 48)) + delta)))

    def _set_font_size(self, font_size: int):
        self.config.set("font_size", font_size)
        self._apply_theme()
        self._ensure_window_can_show_text()
        self.config.save()

    def _resize_by(self, width_delta: int, height_delta: int):
        self.resize(max(MIN_WINDOW_WIDTH, self.width() + width_delta), max(MIN_WINDOW_HEIGHT, self.height() + height_delta))
        self._save_geometry()

    def _set_window_size(self, width: int, height: int):
        self.resize(max(MIN_WINDOW_WIDTH, width), max(MIN_WINDOW_HEIGHT, height))
        self._save_geometry()

    def _auto_fit_window(self):
        self._ensure_window_can_show_text(force=True)
        self.config.save()

    def _ensure_window_can_show_text(self, force: bool = False):
        required_width, required_height = self._estimate_required_size()
        width = required_width if force else max(self.width(), required_width)
        height = required_height if force else max(self.height(), required_height)
        self.resize(width, height)
        self._save_geometry()

    def _estimate_required_size(self) -> Tuple[int, int]:
        width = max(MIN_WINDOW_WIDTH, self.time_label.sizeHint().width() + 44)
        height = max(MIN_WINDOW_HEIGHT, self.time_label.sizeHint().height() + 36)
        if self.config.get("show_date", True):
            width = max(width, self.date_label.sizeHint().width() + 44)
            height += self.date_label.sizeHint().height() + 8
        return width, height

    def _toggle_date(self):
        self.config.set("show_date", not self.config.get("show_date", True))
        self._apply_theme()
        self._ensure_window_can_show_text()
        self.config.save()

    def _toggle_transparent_bg(self):
        transparent_bg = not self.config.get("transparent_bg", True)
        self.config.set("transparent_bg", transparent_bg)
        if transparent_bg:
            self.config.set("background_opacity", 0.0)
        self._apply_theme()
        self.config.save()

    def _toggle_seconds(self):
        show_seconds = not self.config.get("show_seconds", True)
        self.config.set("show_seconds", show_seconds)
        self.config.set("time_format", "%H:%M:%S" if show_seconds else "%H:%M")
        self._update_clock()
        self._ensure_window_can_show_text()
        self.config.save()

    def _set_theme(self, theme_name: str):
        self.config.set("theme", theme_name)
        self._apply_theme()
        self.config.save()

    def _set_background_opacity(self, opacity: float):
        """设置背景透明度，0% 只隐藏背景，不隐藏文字"""
        self.config.set("background_opacity", opacity)
        if opacity < 1.0:
            self.config.set("transparent_bg", True)
        self._apply_theme()
        self.config.save()

    def _set_opacity(self, opacity: float):
        self.config.set("opacity", opacity)
        self.setWindowOpacity(opacity)
        self.config.save()

    def _save_geometry(self):
        self.config.set("position", {"x": self.x(), "y": self.y()})
        self.config.set("size", {"width": self.width(), "height": self.height()})
        self.config.save()

    def closeEvent(self, event):
        self._save_geometry()
        super().closeEvent(event)


def main():
    setup_logging()
    app = QApplication(sys.argv)
    clock = DesktopClockQt()
    clock.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
