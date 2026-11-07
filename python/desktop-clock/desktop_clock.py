#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DesktopClock - 跨平台桌面时钟工具
功能特性：
1. 无边框、可拖拽移动的桌面时钟
2. 支持多种时间格式切换
3. 支持主题切换（深色/浅色/自定义）
4. 支持字体大小和透明度调节
5. 支置顶/取消置顶（固定/取消固定）
6. 支持开机自启（Windows/Mac/Linux）
7. 配置持久化保存
"""

import os
import shutil
import subprocess
import sys
import json
import platform
import subprocess
import logging
import threading
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

import tkinter as tk
from tkinter import Menu, messagebox

# --- 常量定义 ---
APP_NAME = "DesktopClock"
APP_AUTHOR = "zml"
VERSION = "1.0.0"
MIN_WINDOW_WIDTH = 220
MIN_WINDOW_HEIGHT = 80
DEFAULT_WINDOW_WIDTH = 420
DEFAULT_WINDOW_HEIGHT = 150
RESIZE_HANDLE_SIZE = 18
TRANSPARENT_COLOR = "#010203"

# 默认配置
DEFAULT_CONFIG = {
    "position": {"x": 100, "y": 100},
    "size": {"width": DEFAULT_WINDOW_WIDTH, "height": DEFAULT_WINDOW_HEIGHT},
    "font_size": 48,
    "opacity": 0.9,
    "transparent_bg": False,
    "layered_level": "topmost",
    "theme": "dark",
    "time_format": "%H:%M:%S",
    "date_format": "%Y-%m-%d",
    "show_date": True,
    "show_seconds": True,
    "font_family": "Consolas",
    "startup": False,
}

# 预设主题
THEMES = {
    "dark": {
        "bg": "#1e1e1e",
        "fg": "#00ff00",
        "time_fg": "#00ff00",
        "date_fg": "#888888",
        "border": "#333333",
    },
    "light": {
        "bg": "#ffffff",
        "fg": "#333333",
        "time_fg": "#222222",
        "date_fg": "#666666",
        "border": "#cccccc",
    },
    "blue": {
        "bg": "#0a1628",
        "fg": "#00bfff",
        "time_fg": "#00bfff",
        "date_fg": "#4682b4",
        "border": "#1a3a5c",
    },
    "purple": {
        "bg": "#1a0a2e",
        "fg": "#bf00ff",
        "time_fg": "#bf00ff",
        "date_fg": "#8b008b",
        "border": "#3d1a6e",
    },
    "green": {
        "bg": "#0a1a0a",
        "fg": "#00ff7f",
        "time_fg": "#00ff7f",
        "date_fg": "#2e8b57",
        "border": "#1a3a1a",
    },
}

# --- 日志配置 ---
def setup_logging():
    """配置日志系统"""
    log_dir = os.path.join(os.path.expanduser("~"), f".{APP_NAME.lower()}")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{APP_NAME.lower()}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8")
        ]
    )
    logging.info(f"{APP_NAME} 启动，版本：{VERSION}")

# --- 配置管理 ---
class ConfigManager:
    """配置管理器，负责加载和保存配置"""
    
    def __init__(self):
        self.config_dir = os.path.join(os.path.expanduser("~"), f".{APP_NAME.lower()}")
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.config = DEFAULT_CONFIG.copy()
        self.load()
    
    def load(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as f:
                    saved_config = json.load(f)
                    # 合并配置，保留默认值
                    self.config.update(saved_config)
                logging.info(f"配置已加载：{self.config_file}")
        except Exception as e:
            logging.error(f"加载配置失败：{e}")
        return self.config
    
    def save(self):
        """保存配置到文件（原子写入）"""
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            tmp_file = f"{self.config_file}.tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, self.config_file)
            logging.info(f"配置已保存：{self.config_file}")
        except Exception as e:
            logging.error(f"保存配置失败：{e}")
    
    def get(self, key: str, default=None):
        """获取配置项"""
        return self.config.get(key, default)

    def get_layered_level(self) -> str:
        """获取窗口图层级别，同时向前兼容旧的 always_on_top 布尔配置。"""
        raw = self.config.get("layered_level")
        if raw in ("normal", "topmost", "above_all"):
            return raw
        legacy = self.config.get("always_on_top")
        return "topmost" if legacy else "normal"

    def set(self, key: str, value):
        """设置配置项"""
        self.config[key] = value
    
    def update(self, updates: Dict[str, Any]):
        """批量更新配置"""
        self.config.update(updates)


# --- 开机自启管理 ---
class StartupManager:
    """开机自启管理器，支持 Windows、macOS、Linux"""
    
    def __init__(self, app_name: str):
        self.app_name = app_name
        self.system = platform.system()
    
    def is_enabled(self) -> bool:
        """检查是否已启用开机自启"""
        try:
            if self.system == "Windows":
                return self._check_windows_startup()
            elif self.system == "Darwin":
                return self._check_macos_startup()
            elif self.system == "Linux":
                return self._check_linux_startup()
        except Exception as e:
            logging.error(f"检查开机自启状态失败：{e}")
        return False
    
    def enable(self) -> bool:
        """启用开机自启"""
        try:
            if self.system == "Windows":
                return self._enable_windows_startup()
            elif self.system == "Darwin":
                return self._enable_macos_startup()
            elif self.system == "Linux":
                return self._enable_linux_startup()
        except Exception as e:
            logging.error(f"启用开机自启失败：{e}")
        return False
    
    def disable(self) -> bool:
        """禁用开机自启"""
        try:
            if self.system == "Windows":
                return self._disable_windows_startup()
            elif self.system == "Darwin":
                return self._disable_macos_startup()
            elif self.system == "Linux":
                return self._disable_linux_startup()
        except Exception as e:
            logging.error(f"禁用开机自启失败：{e}")
        return False
    
    def _get_executable_path(self) -> str:
        """获取当前脚本的可执行路径"""
        if getattr(sys, 'frozen', False):
            # 打包后的可执行文件
            return sys.executable
        else:
            # Python 脚本
            return os.path.abspath(sys.argv[0])
    
    # --- Windows 开机自启 ---
    def _check_windows_startup(self) -> bool:
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_READ
            )
            try:
                winreg.QueryValueEx(key, self.app_name)
                return True
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False
    
    def _enable_windows_startup(self) -> bool:
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_WRITE
            )
            exe_path = self._get_executable_path()
            winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, f'pythonw "{exe_path}"')
            winreg.CloseKey(key)
            logging.info("Windows 开机自启已启用")
            return True
        except Exception as e:
            logging.error(f"Windows 开机自启启用失败：{e}")
            return False
    
    def _disable_windows_startup(self) -> bool:
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_WRITE
            )
            try:
                winreg.DeleteValue(key, self.app_name)
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
            logging.info("Windows 开机自启已禁用")
            return True
        except Exception as e:
            logging.error(f"Windows 开机自启禁用失败：{e}")
            return False
    
    # --- macOS 开机自启 ---
    def _get_macos_plist_path(self) -> str:
        return os.path.expanduser(f"~/Library/LaunchAgents/com.{self.app_name.lower()}.plist")
    
    def _check_macos_startup(self) -> bool:
        return os.path.exists(self._get_macos_plist_path())
    
    def _enable_macos_startup(self) -> bool:
        plist_path = self._get_macos_plist_path()
        exe_path = self._get_executable_path()
        
        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.{self.app_name.lower()}</string>
    <key>ProgramArguments</key>
    <array>
        <string>python3</string>
        <string>{exe_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>"""
        
        os.makedirs(os.path.dirname(plist_path), exist_ok=True)
        with open(plist_path, "w") as f:
            f.write(plist_content)
        
        subprocess.run(["launchctl", "load", plist_path], check=True)
        logging.info("macOS 开机自启已启用")
        return True
    
    def _disable_macos_startup(self) -> bool:
        plist_path = self._get_macos_plist_path()
        if os.path.exists(plist_path):
            subprocess.run(["launchctl", "unload", plist_path], check=True)
            os.remove(plist_path)
            logging.info("macOS 开机自启已禁用")
        return True
    
    # --- Linux 开机自启 ---
    def _get_linux_desktop_path(self) -> str:
        autostart_dir = os.path.expanduser("~/.config/autostart")
        return os.path.join(autostart_dir, f"{self.app_name.lower()}.desktop")
    
    def _check_linux_startup(self) -> bool:
        return os.path.exists(self._get_linux_desktop_path())
    
    def _enable_linux_startup(self) -> bool:
        desktop_path = self._get_linux_desktop_path()
        exe_path = self._get_executable_path()
        
        desktop_content = f"""[Desktop Entry]
Type=Application
Name={self.app_name}
Exec=python3 {exe_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""
        
        os.makedirs(os.path.dirname(desktop_path), exist_ok=True)
        with open(desktop_path, "w") as f:
            f.write(desktop_content)
        
        os.chmod(desktop_path, 0o755)
        logging.info("Linux 开机自启已启用")
        return True
    
    def _disable_linux_startup(self) -> bool:
        desktop_path = self._get_linux_desktop_path()
        if os.path.exists(desktop_path):
            os.remove(desktop_path)
            logging.info("Linux 开机自启已禁用")
        return True


# --- 桌面时钟主应用 ---
class DesktopClock:
    """桌面时钟主应用"""
    
    def __init__(self):
        # 初始化配置
        self.config = ConfigManager()
        
        # 初始化开机自启管理器
        self.startup_manager = StartupManager(APP_NAME)
        
        # 创建主窗口
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        
        # 拖拽和缩放相关变量
        self.drag_data = {"x": 0, "y": 0}
        self.resize_data = {"x": 0, "y": 0, "width": 0, "height": 0}
        
        # 应用配置
        self._apply_config()
        
        # 创建 UI
        self._create_ui()
        
        # 绑定事件
        self._bind_events()
        
        # 启动时钟更新
        self._update_clock()
        
        logging.info(f"{APP_NAME} 初始化完成")
    
    def _apply_config(self):
        """应用配置到窗口"""
        # 设置窗口位置和大小
        x = self.config.get("position", {}).get("x", 100)
        y = self.config.get("position", {}).get("y", 100)
        width = max(MIN_WINDOW_WIDTH, self.config.get("size", {}).get("width", DEFAULT_WINDOW_WIDTH))
        height = max(MIN_WINDOW_HEIGHT, self.config.get("size", {}).get("height", DEFAULT_WINDOW_HEIGHT))
        
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        
        # 设置无边框和置顶
        self.root.overrideredirect(True)
        self._apply_layered()
        
        # 设置透明度
        self.root.attributes("-alpha", self.config.get("opacity", 0.9))
        
        # 设置窗口背景
        theme_name = self.config.get("theme", "dark")
        theme = THEMES.get(theme_name, THEMES["dark"])
        self.root.configure(bg=theme["bg"])
        self.root.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self._apply_transparent_background()
    
    def _get_background_color(self) -> str:
        """获取当前背景色，透明背景模式下使用可被系统抠除的颜色"""
        if self.config.get("transparent_bg", False):
            return TRANSPARENT_COLOR
        theme_name = self.config.get("theme", "dark")
        theme = THEMES.get(theme_name, THEMES["dark"])
        return theme["bg"]
    
    def _apply_transparent_background(self):
        """应用透明背景。
        
        tkinter 支持通过 -transparentcolor 抠除指定颜色。该能力在 Windows 上最稳定，
        部分 macOS/Linux 桌面环境可能不支持；不支持时会自动退化为普通背景。
        """
        try:
            if self.config.get("transparent_bg", False):
                self.root.attributes("-transparentcolor", TRANSPARENT_COLOR)
            else:
                self.root.attributes("-transparentcolor", "")
        except tk.TclError as e:
            logging.warning(f"当前系统不支持透明背景色：{e}")
    
    def _apply_layered(self):
        """应用窗口图层级别（普通 / 置顶 / 最上层）。"""
        level = self.config.get_layered_level()
        self._stop_keep_above_watcher()
        if level == "normal":
            self.root.attributes("-topmost", False)
        elif level == "topmost":
            self.root.attributes("-topmost", True)
        elif level == "above_all":
            self.root.attributes("-topmost", True)
            self.root.lift()
            self._raise_via_ewmh()
            self._start_keep_above_watcher()

    def _raise_via_ewmh(self):
        """通过 X11 EWMH 将窗口置到最高图层（覆盖输入法等特殊窗口）。
        
        优先用 python-xlib 直接设置 _NET_WM_STATE_ABOVE（最可靠，IME 切换也不会丢失）。
        缺 python-xlib 时回退到 xdotool/wmctrl。
        """
        if sys.platform not in ("linux", "linux2"):
            return
        try:
            wid = self.root.winfo_id()
        except Exception:
            return

        if self._xlib_set_above(wid):
            return
        # 回退到命令行工具
        self._raise_via_cli_tools(wid)

    def _xlib_set_above(self, wid) -> bool:
        """通过 python-xlib 设置 _NET_WM_STATE_ABOVE 并循环 raise。返回是否成功。"""
        try:
            from Xlib import display, X, Xatom
            from Xlib.protocol import event
        except Exception:
            return False
        try:
            d = display.Display()
            w = d.create_resource_object("window", int(wid))
            ABOVE = d.get_atom("_NET_WM_STATE_ABOVE")
            STATE = d.get_atom("_NET_WM_STATE")

            # 通过 ClientMessage 设置 _NET_WM_STATE = [_NET_WM_STATE_ABOVE, 1]
            root = d.screen().root
            ev = event.ClientMessage(
                window=w,
                client_type=STATE,
                data=(32, [1, ABOVE, 0, 1, 0]),
            )
            root.send_event(
                ev,
                event_mask=X.SubstructureNotifyMask | X.SubstructureRedirectMask,
            )
            d.sync()
            # 用 configure_window 的 stack_mode 直接置顶（raise）
            w.configure(stack_mode=X.Above)
            d.sync()
            return True
        except Exception as e:
            logging.warning(f"python-xlib EWMH raise failed: {e}")
            return False

    def _raise_via_cli_tools(self, wid):
        """命令行工具回退（xdotool / wmctrl / xprop）。"""
        raised = False

        # 策略 1：xprop 设 DOCK 类型
        if shutil.which("xprop"):
            try:
                subprocess.run(
                    ["xprop", "-f", "_NET_WM_WINDOW_TYPE", "32a",
                     "-id", str(wid), "-set", "_NET_WM_WINDOW_TYPE", "_NET_WM_WINDOW_TYPE_DOCK"],
                    check=False, capture_output=True,
                )
                raised = True
            except Exception as e:
                logging.warning(f"xprop set _NET_WM_WINDOW_TYPE failed: {e}")

        # 策略 2：wmctrl add,above
        if shutil.which("wmctrl"):
            try:
                subprocess.run(
                    ["wmctrl", "-i", "-r", str(wid), "-b", "add,above"],
                    check=False, capture_output=True,
                )
                raised = True
            except Exception:
                pass

        # 策略 3：xdotool layer
        if not raised and shutil.which("xdotool"):
            try:
                subprocess.run(
                    ["xdotool", "set-window", "--overrd", str(wid), "layer", "6"],
                    check=False, capture_output=True,
                )
            except Exception:
                pass

        # 最后 raise 一次
        if shutil.which("wmctrl"):
            subprocess.run(
                ["wmctrl", "-i", "-r", str(wid), "- activate"],
                check=False, capture_output=True,
            )
        elif shutil.which("xdotool"):
            subprocess.run(
                ["xdotool", "windowraise", str(wid)],
                check=False, capture_output=True,
            )

        if not raised:
            logging.warning("above_all: 所有工具均不可用，已回退到 topmost")

    def _start_keep_above_watcher(self):
        """启动后台守望：定时重新设置 _NET_WM_STATE_ABOVE，防止 IME 切换后被压。
        
        仅在 layered_level == 'above_all' 且 Linux 时生效。
        """
        if sys.platform not in ("linux", "linux2"):
            return
        if self.config.get_layered_level() != "above_all":
            return
        if getattr(self, "_keep_above_running", False):
            return
        try:
            wid = int(self.root.winfo_id())
        except Exception:
            return
        self._keep_above_running = True

        def _watch(wid):
            try:
                from Xlib import display, X
            except Exception:
                return
            try:
                d = display.Display()
                w = d.create_resource_object("window", wid)
                ABOVE = d.get_atom("_NET_WM_STATE_ABOVE")
                STATE = d.get_atom("_NET_WM_STATE")
                # 订阅结构变更（其他窗口激活时触发）
                w.change_attributes(event_mask=X.StructureNotifyMask | X.PropertyChangeMask)

                root = d.screen().root
                from Xlib.protocol import event as _ev
                while self._keep_above_running:
                    try:
                        cm = _ev.ClientMessage(
                            window=w,
                            client_type=STATE,
                            data=(32, [1, ABOVE, 0, 1, 0]),
                        )
                        root.send_event(
                            cm,
                            event_mask=X.SubstructureNotifyMask | X.SubstructureRedirectMask,
                        )
                        w.configure(stack_mode=X.Above)
                        d.sync()
                    except Exception:
                        pass
                    if d.pending_events():
                        d.next_event()
                    import time
                    time.sleep(0.3)
            except Exception as e:
                logging.warning(f"keep_above watcher exited: {e}")
                self._keep_above_running = False

        t = threading.Thread(target=_watch, args=(wid,), daemon=True)
        t.start()

    def _stop_keep_above_watcher(self):
        self._keep_above_running = False

    def _apply_widget_backgrounds(self):
        """同步窗口和各控件背景色"""
        bg_color = self._get_background_color()
        self.root.configure(bg=bg_color)
        if hasattr(self, "main_frame"):
            self.main_frame.configure(bg=bg_color)
            self.time_label.configure(bg=bg_color)
            self.date_label.configure(bg=bg_color)
            self.resize_handle.configure(bg=bg_color)
        self._apply_transparent_background()
    
    def _create_ui(self):
        """创建用户界面"""
        theme_name = self.config.get("theme", "dark")
        theme = THEMES.get(theme_name, THEMES["dark"])
        bg_color = self._get_background_color()
        
        # 创建主框架
        self.main_frame = tk.Frame(self.root, bg=bg_color)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.main_frame.grid_rowconfigure(0, weight=3)
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)
        
        # 时间显示
        self.time_var = tk.StringVar()
        self.time_label = tk.Label(
            self.main_frame,
            textvariable=self.time_var,
            font=(self.config.get("font_family", "Consolas"), 
                  self.config.get("font_size", 48), "bold"),
            fg=theme["time_fg"],
            bg=bg_color,
            anchor=tk.CENTER,
        )
        self.time_label.grid(row=0, column=0, sticky="nsew", padx=10, pady=(4, 0))
        
        # 日期显示
        self.date_var = tk.StringVar()
        self.date_label = tk.Label(
            self.main_frame,
            textvariable=self.date_var,
            font=(self.config.get("font_family", "Consolas"), 
                  max(12, self.config.get("font_size", 48) // 3), "normal"),
            fg=theme["date_fg"],
            bg=bg_color,
            anchor=tk.CENTER,
        )
        
        if self.config.get("show_date", True):
            self.date_label.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 4))
        
        # 右下角缩放手柄：无边框窗口没有系统边框，提供一个可拖拽的缩放区域
        self.resize_handle = tk.Label(
            self.root,
            text="◢",
            font=(self.config.get("font_family", "Consolas"), 12, "normal"),
            fg=theme["date_fg"],
            bg=bg_color,
            cursor="sizing",
        )
        self.resize_handle.place(
            relx=1.0,
            rely=1.0,
            x=-RESIZE_HANDLE_SIZE,
            y=-RESIZE_HANDLE_SIZE,
            width=RESIZE_HANDLE_SIZE,
            height=RESIZE_HANDLE_SIZE,
        )
    
    def _bind_events(self):
        """绑定事件处理"""
        # 递归绑定到子控件，避免鼠标在 Label 上时滚轮/右键不生效
        self._bind_common_events(self.root)
        self._bind_common_events(self.main_frame)
        self._bind_common_events(self.time_label)
        self._bind_common_events(self.date_label)
        
        # 缩放手柄事件
        self.resize_handle.bind("<Button-1>", self._start_resize)
        self.resize_handle.bind("<B1-Motion>", self._do_resize)
        self.resize_handle.bind("<ButtonRelease-1>", self._stop_resize)
        self.resize_handle.bind("<Button-3>", self._show_context_menu)
        
        # 窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _bind_common_events(self, widget):
        """为窗口和内容控件绑定通用交互事件"""
        widget.bind("<Button-1>", self._start_drag)
        widget.bind("<B1-Motion>", self._do_drag)
        widget.bind("<ButtonRelease-1>", self._stop_drag)
        widget.bind("<Button-3>", self._show_context_menu)
        widget.bind("<MouseWheel>", self._on_mouse_wheel)
        # Linux 滚轮事件
        widget.bind("<Button-4>", lambda e: self._on_mouse_wheel_linux(e, 1))
        widget.bind("<Button-5>", lambda e: self._on_mouse_wheel_linux(e, -1))
        widget.bind("<Double-Button-1>", self._toggle_topmost)
    
    def _start_drag(self, event):
        """开始拖拽"""
        self.drag_data["x"] = event.x_root
        self.drag_data["y"] = event.y_root
    
    def _do_drag(self, event):
        """执行拖拽"""
        dx = event.x_root - self.drag_data["x"]
        dy = event.y_root - self.drag_data["y"]
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f"+{x}+{y}")
        self.drag_data["x"] = event.x_root
        self.drag_data["y"] = event.y_root
    
    def _stop_drag(self, event):
        """停止拖拽，保存位置"""
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self.config.set("position", {"x": x, "y": y})
        self._save_window_size()
        self.config.save()
    
    def _start_resize(self, event):
        """开始缩放窗口"""
        self.resize_data = {
            "x": event.x_root,
            "y": event.y_root,
            "width": self.root.winfo_width(),
            "height": self.root.winfo_height(),
        }
        return "break"
    
    def _do_resize(self, event):
        """拖拽右下角手柄缩放窗口"""
        dx = event.x_root - self.resize_data["x"]
        dy = event.y_root - self.resize_data["y"]
        width = max(MIN_WINDOW_WIDTH, self.resize_data["width"] + dx)
        height = max(MIN_WINDOW_HEIGHT, self.resize_data["height"] + dy)
        self.root.geometry(f"{width}x{height}")
        return "break"
    
    def _stop_resize(self, event):
        """停止缩放，保存窗口大小"""
        self._save_window_size()
        self.config.save()
        return "break"
    
    def _save_window_size(self):
        """保存当前窗口大小"""
        width = max(MIN_WINDOW_WIDTH, self.root.winfo_width())
        height = max(MIN_WINDOW_HEIGHT, self.root.winfo_height())
        self.config.set("size", {"width": width, "height": height})
    
    def _toggle_topmost(self, event):
        """循环切换窗口图层级别：normal → topmost → above_all → normal"""
        order = ["normal", "topmost", "above_all"]
        cur = self.config.get_layered_level()
        nxt = order[(order.index(cur) + 1) % len(order)]
        self._set_layered(nxt)
    
    def _on_mouse_wheel(self, event):
        """鼠标滚轮调节字体大小（Windows/Mac）"""
        delta = event.delta
        if delta > 0:
            self._change_font_size(2)
        elif delta < 0:
            self._change_font_size(-2)
    
    def _on_mouse_wheel_linux(self, event, direction):
        """鼠标滚轮调节字体大小（Linux）"""
        self._change_font_size(2 * direction)
    
    def _change_font_size(self, delta: int):
        """改变字体大小"""
        current_size = self.config.get("font_size", 48)
        new_size = max(12, min(120, current_size + delta))
        
        if new_size != current_size:
            self.config.set("font_size", new_size)
            self._update_font()
            self._ensure_window_can_show_text()
            self.config.save()
            logging.info(f"字体大小：{new_size}")
    
    def _update_font(self):
        """更新字体"""
        font_size = self.config.get("font_size", 48)
        font_family = self.config.get("font_family", "Consolas")
        
        self.time_label.configure(font=(font_family, font_size, "bold"))
        self.date_label.configure(font=(font_family, max(12, font_size // 3), "normal"))
        self.resize_handle.configure(font=(font_family, 12, "normal"))
    
    def _estimate_required_size(self) -> Tuple[int, int]:
        """根据当前字体和文本估算不被裁剪的最小窗口大小"""
        self.root.update_idletasks()
        width = max(
            MIN_WINDOW_WIDTH,
            self.time_label.winfo_reqwidth() + 44,
            self.date_label.winfo_reqwidth() + 44 if self.config.get("show_date", True) else 0,
        )
        height = max(MIN_WINDOW_HEIGHT, self.time_label.winfo_reqheight() + 32)
        if self.config.get("show_date", True):
            height += self.date_label.winfo_reqheight() + 8
        return width, height
    
    def _ensure_window_can_show_text(self):
        """字体变大或显示内容变长时，自动放大窗口避免显示不全"""
        required_width, required_height = self._estimate_required_size()
        current_width = self.root.winfo_width()
        current_height = self.root.winfo_height()
        new_width = max(current_width, required_width)
        new_height = max(current_height, required_height)
        
        if new_width != current_width or new_height != current_height:
            self.root.geometry(f"{new_width}x{new_height}")
            self.config.set("size", {"width": new_width, "height": new_height})
        else:
            self._save_window_size()
    
    def _resize_by(self, width_delta: int, height_delta: int):
        """按固定步长调整窗口大小"""
        width = max(MIN_WINDOW_WIDTH, self.root.winfo_width() + width_delta)
        height = max(MIN_WINDOW_HEIGHT, self.root.winfo_height() + height_delta)
        self.root.geometry(f"{width}x{height}")
        self.config.set("size", {"width": width, "height": height})
        self.config.save()
        logging.info(f"窗口大小：{width}x{height}")
    
    def _auto_fit_window(self):
        """自动调整窗口到适合当前文字的大小"""
        width, height = self._estimate_required_size()
        self.root.geometry(f"{width}x{height}")
        self.config.set("size", {"width": width, "height": height})
        self.config.save()
        logging.info(f"窗口已自适应：{width}x{height}")
    
    def _show_context_menu(self, event):
        """显示右键菜单"""
        theme_name = self.config.get("theme", "dark")
        theme = THEMES.get(theme_name, THEMES["dark"])
        
        menu = Menu(self.root, tearoff=0,
                    bg=theme["bg"], fg=theme["fg"],
                    activebackground=theme["time_fg"],
                    activeforeground=theme["bg"])

        # 窗口位置（分层）子菜单
        layered_menu = Menu(menu, tearoff=0,
                           bg=theme["bg"], fg=theme["fg"],
                           activebackground=theme["time_fg"],
                           activeforeground=theme["bg"])
        current_level = self.config.get_layered_level()
        level_labels = {"normal": "普通窗口", "topmost": "窗口总在最上", "above_all": "最最最上层"}
        for level, label in level_labels.items():
            layered_menu.add_command(
                label=f"  {label}  " + (" ✓" if level == current_level else ""),
                command=lambda l=level: self._set_layered(l)
            )
        menu.add_cascade(label=f"窗口位置", menu=layered_menu)
        
        menu.add_separator()
        
        # 字体大小子菜单
        font_menu = Menu(menu, tearoff=0,
                         bg=theme["bg"], fg=theme["fg"],
                         activebackground=theme["time_fg"],
                         activeforeground=theme["bg"])
        font_menu.add_command(label="放大 (+)", command=lambda: self._change_font_size(2))
        font_menu.add_command(label="缩小 (-)", command=lambda: self._change_font_size(-2))
        for font_size in [24, 36, 48, 60, 72]:
            font_menu.add_command(
                label=f"{font_size}px",
                command=lambda s=font_size: self._set_font_size(s)
            )
        menu.add_cascade(label=f"字体大小（当前 {self.config.get('font_size', 48)}px）", menu=font_menu)
        
        # 窗口大小子菜单
        size_menu = Menu(menu, tearoff=0,
                         bg=theme["bg"], fg=theme["fg"],
                         activebackground=theme["time_fg"],
                         activeforeground=theme["bg"])
        size_menu.add_command(label="自动适应文字", command=self._auto_fit_window)
        size_menu.add_command(label="放大窗口", command=lambda: self._resize_by(40, 20))
        size_menu.add_command(label="缩小窗口", command=lambda: self._resize_by(-40, -20))
        for width, height in [(360, 130), (420, 150), (520, 180), (640, 220)]:
            size_menu.add_command(
                label=f"{width} x {height}",
                command=lambda w=width, h=height: self._set_window_size(w, h)
            )
        menu.add_cascade(label=f"窗口大小（当前 {self.root.winfo_width()}x{self.root.winfo_height()}）", menu=size_menu)
        
        menu.add_separator()
        
        # 显示日期开关
        show_date = self.config.get("show_date", True)
        date_text = "隐藏日期" if show_date else "显示日期"
        menu.add_command(label=date_text, command=self._toggle_date)
        
        # 透明背景开关
        transparent_bg = self.config.get("transparent_bg", False)
        transparent_text = "关闭透明背景" if transparent_bg else "开启透明背景"
        menu.add_command(label=transparent_text, command=self._toggle_transparent_bg)
        
        # 显示秒数开关
        show_seconds = self.config.get("show_seconds", True)
        seconds_text = "隐藏秒数" if show_seconds else "显示秒数"
        menu.add_command(label=seconds_text, command=self._toggle_seconds)
        
        menu.add_separator()
        
        # 主题子菜单
        theme_menu = Menu(menu, tearoff=0,
                         bg=theme["bg"], fg=theme["fg"],
                         activebackground=theme["time_fg"],
                         activeforeground=theme["bg"])
        
        for theme_name in THEMES.keys():
            theme_menu.add_command(
                label=theme_name.capitalize(),
                command=lambda t=theme_name: self._set_theme(t)
            )
        menu.add_cascade(label="主题", menu=theme_menu)
        
        menu.add_separator()
        
        # 透明度子菜单
        opacity_menu = Menu(menu, tearoff=0,
                           bg=theme["bg"], fg=theme["fg"],
                           activebackground=theme["time_fg"],
                           activeforeground=theme["bg"])
        
        for opacity in [0.3, 0.5, 0.7, 0.8, 0.9, 1.0]:
            opacity_menu.add_command(
                label=f"{int(opacity * 100)}%",
                command=lambda o=opacity: self._set_opacity(o)
            )
        menu.add_cascade(label="透明度", menu=opacity_menu)
        
        menu.add_separator()
        
        # 开机自启
        startup_enabled = self.startup_manager.is_enabled()
        startup_text = "取消开机自启" if startup_enabled else "开机自启"
        menu.add_command(label=startup_text, command=self._toggle_startup)
        
        menu.add_separator()
        
        # 退出
        menu.add_command(label="退出", command=self._on_close)
        
        # 显示菜单
        menu.tk_popup(event.x_root, event.y_root)
    
    def _set_font_size(self, font_size: int):
        """设置指定字体大小"""
        font_size = max(12, min(120, font_size))
        self.config.set("font_size", font_size)
        self._update_font()
        self._ensure_window_can_show_text()
        self.config.save()
        logging.info(f"字体大小：{font_size}")
    
    def _set_window_size(self, width: int, height: int):
        """设置指定窗口大小"""
        width = max(MIN_WINDOW_WIDTH, width)
        height = max(MIN_WINDOW_HEIGHT, height)
        self.root.geometry(f"{width}x{height}")
        self.config.set("size", {"width": width, "height": height})
        self.config.save()
        logging.info(f"窗口大小：{width}x{height}")
    
    def _toggle_transparent_bg(self):
        """切换透明背景"""
        transparent_bg = not self.config.get("transparent_bg", False)
        self.config.set("transparent_bg", transparent_bg)
        self._apply_theme()
        self.config.save()
        logging.info(f"透明背景：{'开启' if transparent_bg else '关闭'}")
        if transparent_bg and platform.system() not in ("Windows", "Darwin"):
            logging.warning("Linux 下透明背景依赖桌面环境/窗口管理器支持，如无效果请使用窗口透明度")
    
    def _toggle_date(self):
        """切换日期显示"""
        show_date = not self.config.get("show_date", True)
        self.config.set("show_date", show_date)
        
        if show_date:
            self.date_label.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 4))
        else:
            self.date_label.grid_forget()
        
        self._ensure_window_can_show_text()
        self.config.save()
        logging.info(f"日期显示：{'开启' if show_date else '关闭'}")
    
    def _toggle_seconds(self):
        """切换秒数显示"""
        show_seconds = not self.config.get("show_seconds", True)
        self.config.set("show_seconds", show_seconds)
        
        if show_seconds:
            self.config.set("time_format", "%H:%M:%S")
        else:
            self.config.set("time_format", "%H:%M")
        
        self.config.save()
        logging.info(f"秒数显示：{'开启' if show_seconds else '关闭'}")
    
    def _set_theme(self, theme_name: str):
        """设置主题"""
        self.config.set("theme", theme_name)
        self._apply_theme()
        self.config.save()
        logging.info(f"主题已切换：{theme_name}")
    
    def _apply_theme(self):
        """应用主题"""
        theme_name = self.config.get("theme", "dark")
        theme = THEMES.get(theme_name, THEMES["dark"])
        
        self._apply_widget_backgrounds()
        self.time_label.configure(fg=theme["time_fg"])
        self.date_label.configure(fg=theme["date_fg"])
        self.resize_handle.configure(fg=theme["date_fg"])
    
    def _set_opacity(self, opacity: float):
        """设置透明度"""
        self.config.set("opacity", opacity)
        self.root.attributes("-alpha", opacity)
        self.config.save()
        logging.info(f"透明度：{int(opacity * 100)}%")

    def _set_layered(self, level: str):
        """设置窗口图层级别并立即应用、持久化。"""
        self.config.set("layered_level", level)
        self._apply_layered()
        self._save_window_size()
        self.config.save()
        labels = {"normal": "普通窗口", "topmost": "窗口总在最上", "above_all": "最最最上层"}
        logging.info(f"窗口位置：{labels.get(level, level)}")

    def _toggle_startup(self):
        """切换开机自启"""
        if self.startup_manager.is_enabled():
            if self.startup_manager.disable():
                self.config.set("startup", False)
                messagebox.showinfo(APP_NAME, "开机自启已禁用")
        else:
            if self.startup_manager.enable():
                self.config.set("startup", True)
                messagebox.showinfo(APP_NAME, "开机自启已启用")
        
        self.config.save()
    
    def _update_clock(self):
        """更新时钟显示"""
        now = datetime.now()
        
        # 更新时间
        time_format = self.config.get("time_format", "%H:%M:%S")
        self.time_var.set(now.strftime(time_format))
        
        # 更新日期
        if self.config.get("show_date", True):
            date_format = self.config.get("date_format", "%Y-%m-%d")
            weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            weekday = weekday_names[now.weekday()]
            date_str = now.strftime(date_format)
            self.date_var.set(f"{date_str} {weekday}")
        
        # 每秒更新
        self.root.after(1000, self._update_clock)
    
    def _on_close(self):
        """窗口关闭处理"""
        # 保存当前位置和窗口大小
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self.config.set("position", {"x": x, "y": y})
        self._save_window_size()
        self.config.save()
        
        logging.info(f"{APP_NAME} 已退出")
        self.root.destroy()
    
    def run(self):
        """运行应用"""
        logging.info(f"{APP_NAME} 开始运行")
        self.root.mainloop()


# --- 程序入口 ---
def main():
    """主函数"""
    setup_logging()
    
    try:
        app = DesktopClock()
        app.run()
    except Exception as e:
        logging.error(f"程序异常退出：{e}")
        raise


if __name__ == "__main__":
    main()
