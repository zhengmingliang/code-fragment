#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeskReminder (Tkinter) 优化版
已实现优化：
1. 添加中文代码注释（在关键位置）
2. 添加日志输出（控制台 + 文件）
3. 新建任务成功后自动清空输入框
4. 输入框支持 Home / End 键快速跳转
5. 测试播放按钮可以切换为“停止播放”
6. 调整提醒管理列表行高，中文底部不被遮盖
7. [修复] 针对 Deepin/Linux 托盘图标右键菜单不显示的问题
8. [修复] Cron 表达式现在基于本地时区进行计算和显示
9. [修复] 使用自定义样式强制设置Treeview行高，解决中文字体被遮盖问题
"""

import os
import sys
import json
import uuid
import time
import heapq
import math
import signal
import threading
import platform
import subprocess
import shutil
import logging
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Dict, Any, Tuple

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# --- 托盘修复：针对 Linux 桌面环境 (如 Deepin) ---
# 在某些Linux桌面环境中，pystray 默认选择的后端可能导致右键菜单无法显示。
# 在导入 pystray 之前设置环境变量，可以强制其使用更兼容的 'appindicator' 后端。
# 这必须在 'import pystray' 语句之前执行。
if platform.system() == "Linux":
    os.environ.setdefault('PYSTRAY_BACKEND', 'appindicator')

# Optional deps
try:
    from croniter import croniter

    HAVE_CRONITER = True
except Exception:
    HAVE_CRONITER = False

try:
    from appdirs import user_data_dir

    HAVE_APPDIRS = True
except Exception:
    HAVE_APPDIRS = False

try:
    import simpleaudio as sa

    HAVE_SIMPLEAUDIO = True
except Exception:
    HAVE_SIMPLEAUDIO = False

try:
    import pystray
    from PIL import Image, ImageDraw

    HAVE_TRAY = True
except Exception as e:
    HAVE_TRAY = False
    print(f"[-] 托盘图标库加载失败，托盘功能将不可用。错误信息: {e}")

try:
    from plyer import notification as plyer_notification

    HAVE_PLYER = True
except Exception:
    HAVE_PLYER = False

try:
    from win10toast import ToastNotifier

    HAVE_WIN10TOAST = True
except Exception:
    HAVE_WIN10TOAST = False

try:
    from screeninfo import get_monitors

    HAVE_SCREENINFO = True
except Exception:
    HAVE_SCREENINFO = False

try:
    import pygame

    HAVE_PYGAME = True
except Exception:
    HAVE_PYGAME = False

APP_NAME = "DeskReminder"
APP_AUTHOR = "zml"
VERSION = "1.3.2"  # 版本号更新


# 返回当前 UTC 时间（带时区）
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# 将 datetime 转为 Unix 时间戳（秒）
def to_unix_ts(dt: datetime) -> float:
    return dt.timestamp()


# 将 Unix 时间戳（秒）转换为带时区的 datetime 对象
def from_unix_ts(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


# 将传入的 datetime 对象转换为本地时区的 datetime（若无 tzinfo 则假定为本地时间）
def localize(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).astimezone()
    return dt.astimezone()


# 解析本地日期和时间字符串（YYYY-MM-DD HH:MM），并返回 UTC 时区的 datetime（解析失败返回 None）
def parse_local_datetime(date_str: str, time_str: str) -> Optional[datetime]:
    try:
        dt = datetime.strptime(f"{date_str.strip()} {time_str.strip()}", "%Y-%m-%d %H:%M")
        # 创建一个本地时区感知的 datetime 对象
        local_tz = datetime.now().astimezone().tzinfo
        local_dt = dt.replace(tzinfo=local_tz)
        # 转换为 UTC
        return local_dt.astimezone(timezone.utc)
    except Exception:
        return None


# 确保目录存在（不存在则创建）
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


# 获取默认的数据目录（优先使用 appdirs，若不可用则放到用户主目录下的隐藏文件夹）
def default_data_dir() -> str:
    if HAVE_APPDIRS:
        d = user_data_dir(APP_NAME, APP_AUTHOR)
    else:
        home = os.path.expanduser("~")
        d = os.path.join(home, f".{APP_NAME.lower()}")
    ensure_dir(d)
    return d


DATA_DIR = default_data_dir()
DATA_FILE = os.path.join(DATA_DIR, "reminders.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
LOG_FILE = os.path.join(DATA_DIR, "deskreminder.log")


# 原子方式写入 JSON（先写临时文件再替换），减少写入过程中损坏的风险
def atomic_write_json(path: str, data: Any):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ---------------- 日志系统 ----------------
def setup_logging():
    """初始化日志（同时输出到控制台与文件）"""
    ensure_dir(DATA_DIR)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_FILE, encoding="utf-8")
        ]
    )
    logging.info("DeskReminder 启动，版本：%s", VERSION)
    logging.info("数据目录：%s", DATA_DIR)


# 立即初始化日志
setup_logging()


# 提醒数据模型（序列化/反序列化用于持久化）
@dataclass
class Reminder:
    id: str
    title: str
    message: str
    kind: str  # 'delay' | 'datetime' | 'cron'
    delay_minutes: Optional[int] = None
    run_at_ts: Optional[float] = None
    cron_expr: Optional[str] = None

    enabled: bool = True
    use_sound: bool = True
    created_at: float = field(default_factory=lambda: to_unix_ts(now_utc()))
    updated_at: float = field(default_factory=lambda: to_unix_ts(now_utc()))
    last_triggered_at: Optional[float] = None

    next_run_ts: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Reminder":
        return Reminder(**d)


# 应用设置数据模型（可序列化为 settings.json）
@dataclass
class Settings:
    sound_enabled: bool = True
    sound_file: Optional[str] = None  # WAV/MP3
    close_to_tray: bool = True
    always_on_top_alert: bool = True
    theme: str = "clam"
    default_snooze_minutes: int = 5
    system_notification_enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Settings":
        s = Settings()
        s.__dict__.update({**s.__dict__, **d})
        return s


# 存储管理类：负责加载和保存 reminders.json 与 settings.json
class Storage:
    def __init__(self):
        self.reminders: Dict[str, Reminder] = {}
        self.settings: Settings = Settings()

    def load(self):
        logging.info('加载数据：%s', DATA_FILE)
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                items = data if isinstance(data, list) else data.get("reminders", [])
                for it in items:
                    r = Reminder.from_dict(it)
                    self.reminders[r.id] = r
            except Exception as e:
                print(f"Failed to load reminders: {e}", file=sys.stderr)
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.settings = Settings.from_dict(data)
            except Exception as e:
                print(f"Failed to load settings: {e}", file=sys.stderr)

    def save(self):
        logging.info('保存 %d 条提醒到 %s', len(self.reminders), DATA_FILE)
        data = [r.to_dict() for r in self.reminders.values()]
        try:
            atomic_write_json(DATA_FILE, data)
            atomic_write_json(SETTINGS_FILE, self.settings.to_dict())
        except Exception as e:
            logging.exception('保存数据失败: %s', e)
            raise


# 调度器线程：负责维护一个最小堆，计算最近的提醒并按时触发
class Scheduler(threading.Thread):
    def __init__(self, storage: Storage, on_fire_callback):
        super().__init__(daemon=True)
        self.storage = storage
        self.on_fire_callback = on_fire_callback
        self._stop_event = threading.Event()
        self._rebuild_event = threading.Event()
        self._lock = threading.Lock()
        self._heap: List[Tuple[float, str, int]] = []
        self._seq = 0

    def stop(self):
        self._stop_event.set()
        self._rebuild_event.set()

    def rebuild(self):
        self._rebuild_event.set()

    def compute_next_run(self, r: Reminder, base: Optional[datetime] = None) -> Optional[float]:
        base_utc = base or now_utc()
        if not r.enabled:
            return None
        if r.kind == "delay":
            mins = r.delay_minutes or 0
            if mins <= 0:
                return None
            return to_unix_ts(base_utc + timedelta(minutes=mins))
        elif r.kind == "datetime":
            if r.run_at_ts is None:
                return None
            if r.last_triggered_at is not None and r.run_at_ts <= r.last_triggered_at:
                return None
            if r.run_at_ts <= to_unix_ts(base_utc):
                return to_unix_ts(base_utc) + 1.0
            return r.run_at_ts
        elif r.kind == "cron":
            if not HAVE_CRONITER or not r.cron_expr:
                return None
            try:
                # 使用本地时间作为 croniter 的计算基准，以符合用户的直观感受。
                # 1. 获取本地时区的基准时间
                base_local = base_utc.astimezone()
                # 2. 用本地时间初始化 croniter，它会按本地时区解析表达式
                itr = croniter(r.cron_expr, base_local)
                # 3. get_next() 将返回一个带本地时区的 datetime 对象
                nxt_local = itr.get_next(datetime)
                # 4. 将计算出的本地时间转换回 UTC 时间戳，以便在调度器中统一处理
                return to_unix_ts(nxt_local.astimezone(timezone.utc))
            except Exception:
                logging.exception('计算 cron 下次执行时间失败: %s', r.cron_expr)
                return None
        return None

    def _fill_heap(self):
        with self._lock:
            self._heap.clear()
            self._seq = 0
            now_ts = to_unix_ts(now_utc())
            for r in self.storage.reminders.values():
                nxt = self.compute_next_run(r)
                r.next_run_ts = nxt
                if nxt is not None and nxt >= now_ts - 1:
                    heapq.heappush(self._heap, (nxt, r.id, self._seq))
                    self._seq += 1

    def run(self):
        self._fill_heap()
        while not self._stop_event.is_set():
            if self._rebuild_event.is_set():
                self._rebuild_event.clear()
                self._fill_heap()
            if not self._heap:
                self._rebuild_event.wait(timeout=0.5)
                continue
            nxt_ts, rid, _ = self._heap[0]
            now_ts = to_unix_ts(now_utc())
            wait_sec = max(0.0, min(3600.0, nxt_ts - now_ts))
            signaled = self._rebuild_event.wait(timeout=wait_sec)
            if signaled:
                self._rebuild_event.clear()
                self._fill_heap()
                continue
            now_ts = to_unix_ts(now_utc())
            if self._heap and self._heap[0][0] <= now_ts + 0.1:
                _, rid, _ = heapq.heappop(self._heap)
                r = self.storage.reminders.get(rid)
                if not r or not r.enabled:
                    continue

                def after_fire(rem: Reminder):
                    try:
                        self.on_fire_callback(rem)
                    except Exception as e:
                        logging.exception('on_fire_callback error: %s', e)

                r.last_triggered_at = now_ts
                if r.kind == "cron":
                    # 注意：这里传递的基准时间必须是 UTC，compute_next_run 内部会做转换
                    nxt = self.compute_next_run(r, base=now_utc())
                    r.next_run_ts = nxt
                    if nxt is not None:
                        with self._lock:
                            heapq.heappush(self._heap, (nxt, r.id, self._seq))
                            self._seq += 1
                else:
                    r.next_run_ts = None
                    r.enabled = False
                try:
                    atomic_write_json(DATA_FILE, [x.to_dict() for x in self.storage.reminders.values()])
                except Exception:
                    pass
                after_fire(r)
            else:
                continue


def _which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)


# 声音播放类：非阻塞播放，优先使用 simpleaudio（WAV），对 MP3 使用外部播放器或 pygame 回退
class SoundPlayer:
    """
    Non-blocking sound player (background thread).
    - WAV: simpleaudio preferred; fallback to system bell.
    - MP3/other: external players (cvlc/mpg123/mpv/ffplay) preferred; optional pygame.mixer.
    """

    def __init__(self, settings: Settings, tk_root: Optional[tk.Tk] = None):
        self.settings = settings
        self._tk_root = tk_root
        self._lock = threading.Lock()
        self._sa_play_obj = None
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = False
        self._pygame_ready = False

    def stop(self):
        with self._lock:
            self._stop_flag = True
            logging.info('停止播放声音')
            # Stop external process
            if self._proc and self._proc.poll() is None:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
                # Ensure kill if not exited
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
            # Stop simpleaudio
            if self._sa_play_obj:
                try:
                    self._sa_play_obj.stop()
                except Exception:
                    pass
                self._sa_play_obj = None
            # Stop pygame
            if HAVE_PYGAME and self._pygame_ready:
                try:
                    pygame.mixer.music.stop()
                except Exception:
                    pass
            self._thread = None

    @staticmethod
    def _ext(path: Optional[str]) -> str:
        return os.path.splitext(path or "")[1].lower()

    def _gen_default_wave(self, seconds=1.0, freq=880.0, volume=0.35):
        import struct
        sample_rate = 44100
        n_samples = int(seconds * sample_rate)
        data = bytearray()
        for i in range(n_samples):
            t = i / sample_rate
            amp = volume * (1.0 if t < seconds * 0.8 else max(0.0, 1 - (t - seconds * 0.8) / (seconds * 0.2)))
            val = int(amp * 32767.0 * math.sin(2 * math.pi * freq * t))
            data += struct.pack("<h", val)
        wav = bytearray()
        wav += b"RIFF";
        wav += struct.pack("<I", 36 + len(data));
        wav += b"WAVE"
        wav += b"fmt ";
        wav += struct.pack("<I", 16);
        wav += struct.pack("<H", 1)
        wav += struct.pack("<H", 1);
        wav += struct.pack("<I", sample_rate)
        wav += struct.pack("<I", sample_rate * 2);
        wav += struct.pack("<H", 2);
        wav += struct.pack("<H", 16)
        wav += b"data";
        wav += struct.pack("<I", len(data));
        wav += data
        return bytes(wav)

    def _bell_safe(self):
        if self._tk_root is not None:
            try:
                # call from main thread
                self._tk_root.after(0, self._tk_root.bell)
            except Exception:
                pass

    def _play_worker(self, sound_file: Optional[str]):
        try:
            with self._lock:
                self._stop_flag = False
                # Cleanup previous
                if self._proc and self._proc.poll() is None:
                    try:
                        self._proc.terminate()
                    except Exception:
                        pass
                self._proc = None
                if self._sa_play_obj:
                    try:
                        self._sa_play_obj.stop()
                    except Exception:
                        pass
                self._sa_play_obj = None

            if sound_file and os.path.exists(sound_file):
                ext = self._ext(sound_file)
                # WAV via simpleaudio (non-blocking)
                if ext in (".wav", ".aiff", ".aif") and HAVE_SIMPLEAUDIO:
                    try:
                        with self._lock:
                            self._sa_play_obj = sa.WaveObject.from_wave_file(sound_file).play()
                        return
                    except Exception:
                        pass
                # Try external players for MP3/others (best effort, non-blocking)
                candidates = []
                if _which("cvlc"):
                    candidates.append(
                        ["cvlc", "--intf", "dummy", "--no-video", "--quiet", "--play-and-exit", sound_file])
                if _which("mpg123"):
                    candidates.append(["mpg123", "-q", sound_file])
                if _which("mpv"):
                    candidates.append(
                        ["mpv", "--no-video", "--really-quiet", "--idle=no", "--keep-open=no", sound_file])
                if _which("ffplay"):
                    candidates.append(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", sound_file])

                for cmd in candidates:
                    try:
                        with self._lock:
                            self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        return
                    except Exception:
                        continue

                # Optional pygame fallback (non-blocking)
                if HAVE_PYGAME:
                    try:
                        if not self._pygame_ready:
                            pygame.mixer.init(frequency=44100, channels=2)
                            self._pygame_ready = True
                        pygame.mixer.music.load(sound_file)
                        pygame.mixer.music.play()
                        return
                    except Exception:
                        pass

                # Windows: last resort open default player
                if platform.system() == "Windows":
                    try:
                        os.startfile(sound_file)  # non-blocking
                        return
                    except Exception:
                        pass

            # No file or all failed: play a generated beep via simpleaudio; else bell
            if HAVE_SIMPLEAUDIO:
                try:
                    wav_bytes = self._gen_default_wave(seconds=1.2)
                    with self._lock:
                        self._sa_play_obj = sa.WaveObject(wav_bytes, 1, 2, 44100).play()
                    return
                except Exception:
                    pass
            self._bell_safe()
        except Exception as e:
            print(f"Sound play error: {e}", file=sys.stderr)
            self._bell_safe()

    def play_once(self, sound_file: Optional[str] = None):
        if not self.settings.sound_enabled:
            return
        # Always play in background to avoid UI freeze
        self.stop()
        t = threading.Thread(target=self._play_worker, args=(sound_file,), daemon=True)
        with self._lock:
            self._thread = t
        t.start()


# 系统通知封装：根据平台选择合适的通知方式（plyer / Windows toast / macOS applescript / notify-send）
class Notifier:
    def __init__(self, app_name: str):
        self.app_name = app_name
        self._win_toaster = ToastNotifier() if (HAVE_WIN10TOAST and platform.system() == "Windows") else None

    @staticmethod
    def _escape_applescript(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"')

    def notify(self, title: str, message: str, enable: bool = True):
        if not enable:
            logging.info('系统通知已禁用，跳过通知')
            return
        try:
            if HAVE_PLYER:
                plyer_notification.notify(title=title or "提醒", message=message or "", app_name=self.app_name,
                                          timeout=10)
                return
            sysname = platform.system()
            if sysname == "Windows" and self._win_toaster:
                try:
                    self._win_toaster.show_toast(title or "提醒", message or "", duration=8, threaded=True)
                    return
                except Exception:
                    pass
            if sysname == "Darwin":
                t = self._escape_applescript(title or "提醒")
                m = self._escape_applescript(message or "")
                script = f'display notification "{m}" with title "{t}"'
                subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            if sysname == "Linux":
                try:
                    subprocess.Popen(["notify-send", "-a", self.app_name, title or "提醒", message or ""],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                except Exception:
                    pass
        except Exception as e:
            print(f"System notify error: {e}", file=sys.stderr)


def center_on_relevant_monitor(toplevel: tk.Toplevel, width: int, height: int):
    try:
        parent = toplevel.master
        if parent is not None and parent.winfo_ismapped():
            ref_x = parent.winfo_rootx() + max(1, parent.winfo_width()) // 2
            ref_y = parent.winfo_rooty() + max(1, parent.winfo_height()) // 2
        else:
            ref_x = toplevel.winfo_pointerx()
            ref_y = toplevel.winfo_pointery()
        if HAVE_SCREENINFO:
            monitors = get_monitors()
            chosen = None
            for m in monitors:
                if m.x <= ref_x < m.x + m.width and m.y <= ref_y < m.y + m.height:
                    chosen = m;
                    break
            if chosen is None and monitors:
                chosen = monitors[0]
            if chosen:
                x = int(chosen.x + (chosen.width - width) / 2)
                y = int(chosen.y + (chosen.height - height) / 2)
                return x, y
        x = int(ref_x - width / 2)
        y = int(ref_y - height / 2)
        return x, y
    except Exception:
        sw = toplevel.winfo_screenwidth()
        sh = toplevel.winfo_screenheight()
        x = int((sw - width) / 2)
        y = int((sh - height) / 2)
        return x, y


# 弹窗提醒对话框：居中多显示内容，提供停止/重放铃声功能
class AlertDialog(tk.Toplevel):
    def __init__(self, master, reminder: Reminder, settings: Settings, sound_player: SoundPlayer, on_close=None):
        super().__init__(master)
        self.reminder = reminder
        self.settings = settings
        self.sound_player = sound_player
        self.on_close = on_close

        # Window setup: use theme defaults to avoid rendering issues
        self.withdraw()
        self.title("提醒")
        self.resizable(False, False)
        try:
            self.attributes("-topmost", True if settings.always_on_top_alert else False)
        except Exception:
            pass

        # Layout: use pack (no custom dark bg)
        container = ttk.Frame(self, padding=12)
        container.pack(fill="both", expand=True)

        title_text = reminder.title.strip() if reminder.title.strip() else "(未命名提醒)"
        lbl_title = ttk.Label(container, text=title_text, font=("Segoe UI", 16, "bold"))
        lbl_title.pack(pady=(4, 8))

        msg = reminder.message.strip() or ""
        txt = tk.Text(container, width=56, height=8, wrap="word")
        txt.insert("1.0", msg)
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True, pady=(0, 10))

        btns = ttk.Frame(container)
        btns.pack(fill="x")
        ttk.Button(btns, text="知道了（关闭）", command=self._close).pack(side="left", padx=6)
        if self.settings.sound_enabled and reminder.use_sound:
            ttk.Button(btns, text="停止铃声", command=self._stop_sound).pack(side="left", padx=6)
            ttk.Button(btns, text="重放铃声", command=self._replay_sound).pack(side="left", padx=6)

        self.bind("<Escape>", lambda e: self._close())

        # Size and center after widgets are laid out
        self.update_idletasks()
        w = max(520, self.winfo_reqwidth() + 24)
        h = max(300, self.winfo_reqheight() + 24)
        x, y = center_on_relevant_monitor(self, w, h)
        self.geometry(f"{w}x{h}+{x}+{y}")

        self.deiconify()
        self.grab_set()

        # Play sound (non-blocking)
        self.sound_player.play_once(master.storage.settings.sound_file if reminder.use_sound else None)

    def _stop_sound(self):
        self.sound_player.stop()

    def _replay_sound(self):
        self.sound_player.play_once(self.master.storage.settings.sound_file if self.reminder.use_sound else None)

    def _close(self):
        self.sound_player.stop()
        if self.on_close:
            try:
                self.on_close(self.reminder)
            except Exception:
                pass
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


# 可滚动面板组件：包含 Canvas + 内嵌 Frame，支持鼠标滚轮
class ScrollableFrame(ttk.Frame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas)
        self.inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self._bind_mousewheel(self.canvas)
        self._bind_mousewheel(self.inner)

    def _on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.inner_id, width=event.width)

    def _on_mousewheel(self, event):
        if event.num == 4 or event.delta > 0:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.canvas.yview_scroll(1, "units")

    def _bind_mousewheel(self, widget):
        system = platform.system()
        if system == "Darwin":
            widget.bind_all("<MouseWheel>", self._on_mousewheel)
        else:
            widget.bind_all("<MouseWheel>", self._on_mousewheel)
            widget.bind_all("<Button-4>", self._on_mousewheel)
            widget.bind_all("<Button-5>", self._on_mousewheel)


# 主应用窗口：初始化存储、调度器、声音、UI 以及托盘等功能
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{VERSION}")
        self.geometry("900x600")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.minsize(820, 540)

        # Storage, sound, scheduler, notifier
        self.storage = Storage()
        self.storage.load()
        self.sound_player = SoundPlayer(self.storage.settings, tk_root=self)
        self.notifier = Notifier(APP_NAME)
        self.scheduler = Scheduler(self.storage, on_fire_callback=self.on_reminder_fire)
        self.scheduler.start()

        # Theme
        try:
            style = ttk.Style(self)

            # --- MODIFICATION START ---
            # 使用一个独立的、自定义的样式来配置Treeview，以确保行高和字体设置能覆盖主题默认值

            # 1. 定义字体
            tree_font = ("TkDefaultFont", 11)  # 默认字体
            try:
                if platform.system() == "Windows":
                    tree_font = ("Microsoft YaHei", 11)
                elif platform.system() == "Darwin":
                    tree_font = ("PingFang SC", 12)
                else:
                    # Linux 下常见的中文字体
                    tree_font = ("Noto Sans CJK SC", 11)
            except tk.TclError:
                # 如果指定字体不存在，则使用默认字体
                tree_font = ("TkDefaultFont", 11)

            fsize = tree_font[1] if isinstance(tree_font, tuple) and len(tree_font) > 1 else 11

            # 2. 创建并配置自定义Treeview样式
            # 这个新样式 "Custom.Treeview" 独立于默认的 "Treeview" 样式
            custom_treeview_style_name = "Custom.Treeview"
            style.configure(
                custom_treeview_style_name,
                font=tree_font,
                rowheight=max(40, int(fsize * 3.0))  # 强制设置一个足够大的行高
            )

            # 3. 确保表头也使用合适的字体
            try:
                heading_font = (tree_font[0], max(10, int(fsize * 0.95)))
                style.configure(f"{custom_treeview_style_name}.Heading", font=heading_font)
            except Exception:
                pass

            # --- MODIFICATION END ---

            themes = style.theme_names()
            style.theme_use(self.storage.settings.theme if self.storage.settings.theme in themes else "clam")
            style.configure("TLabel", padding=2)
            style.configure("TButton", padding=(10, 6))
            style.configure("TEntry", padding=4)
            style.configure("Card.TFrame", relief="ridge", borderwidth=1, padding=10)
        except Exception:
            pass

        # UI
        self._build_ui()

        # 绑定全局快捷键：全选 / Home / End
        self._bind_shortcuts()

        # Tray (optional)
        self.tray_icon = None
        if HAVE_TRAY:
            self.after(500, self._init_tray)

        # Select-all
        for seq in ("<Control-a>", "<Control-A>", "<Command-a>", "<Command-A>"):
            self.bind_all(seq, self._select_all)

        try:
            signal.signal(signal.SIGINT, lambda s, f: self.destroy())
        except Exception:
            pass

        self.scheduler.rebuild()

    def _bind_shortcuts(self):
        """绑定全局快捷键：全选、Home、End 等"""
        for seq in ("<Control-a>", "<Control-A>", "<Command-a>", "<Command-A>"):
            self.bind_all(seq, self._select_all)
        # Home / End 键支持
        self.bind_all("<Home>", self._go_home)
        self.bind_all("<End>", self._go_end)

    def _go_home(self, event):
        widget = self.focus_get()
        try:
            if isinstance(widget, tk.Entry) or isinstance(widget, ttk.Entry):
                widget.icursor(0)
            elif isinstance(widget, tk.Text):
                widget.mark_set("insert", "1.0")
        except Exception:
            pass
        return "break"

    def _go_end(self, event):
        widget = self.focus_get()
        try:
            if isinstance(widget, tk.Entry) or isinstance(widget, ttk.Entry):
                widget.icursor("end")
            elif isinstance(widget, tk.Text):
                widget.mark_set("insert", "end-1c")
        except Exception:
            pass
        return "break"

    def _build_ui(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        tab_create = ttk.Frame(nb)
        nb.add(tab_create, text="新建提醒")
        self._build_create_tab(tab_create)

        tab_manage = ttk.Frame(nb)
        nb.add(tab_manage, text="提醒管理")
        self._build_manage_tab(tab_manage)

        tab_settings = ttk.Frame(nb)
        nb.add(tab_settings, text="设置")
        self._build_settings_tab(tab_settings)

    def _build_create_tab(self, parent):
        sf = ScrollableFrame(parent)
        sf.pack(fill="both", expand=True)
        f = sf.inner

        card = ttk.Frame(f, style="Card.TFrame")
        card.pack(fill="x", pady=8)

        row = ttk.Frame(card)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text="标题").pack(side="left", padx=(0, 8))
        self.ent_title = ttk.Entry(row)
        self.ent_title.pack(side="left", fill="x", expand=True)

        row2 = ttk.Frame(card)
        row2.pack(fill="both", pady=6)
        ttk.Label(row2, text="内容").pack(side="top", anchor="w", padx=(0, 8))
        self.txt_message = tk.Text(row2, height=5, wrap="word")
        self.txt_message.pack(fill="x", expand=True)

        row3 = ttk.Frame(card)
        row3.pack(fill="x", pady=12)
        ttk.Label(row3, text="提醒类型").pack(side="left")
        self.kind_var = tk.StringVar(value="delay")
        kinds = [("延迟（分钟）", "delay"), ("指定时间", "datetime"), ("Cron 表达式", "cron")]
        for text, val in kinds:
            ttk.Radiobutton(row3, text=text, variable=self.kind_var, value=val, command=self._on_kind_change).pack(
                side="left", padx=10)

        self.panel_delay = ttk.Frame(card)
        self.panel_datetime = ttk.Frame(card)
        self.panel_cron = ttk.Frame(card)

        self._build_delay_panel(self.panel_delay)
        self._build_datetime_panel(self.panel_datetime)
        self._build_cron_panel(self.panel_cron)

        self.panel_delay.pack(fill="x")

        row4 = ttk.Frame(card)
        row4.pack(fill="x", pady=8)
        self.use_sound_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row4, text="使用铃声", variable=self.use_sound_var).pack(side="left", padx=(0, 12))

        row5 = ttk.Frame(card)
        row5.pack(fill="x", pady=10)
        ttk.Button(row5, text="保存提醒", command=self.save_new_reminder).pack(side="left")
        ttk.Button(row5, text="清空输入", command=self._clear_create_form).pack(side="left", padx=8)

    def _build_delay_panel(self, parent):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text="延迟分钟").pack(side="left", padx=(0, 8))
        self.ent_delay = ttk.Entry(row, width=10)
        self.ent_delay.pack(side="left")
        ttk.Label(row, text="分钟后提醒").pack(side="left", padx=6)

    def _build_datetime_panel(self, parent):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text="日期").pack(side="left", padx=(0, 8))
        self.ent_date = ttk.Entry(row, width=12)
        self.ent_date.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self.ent_date.pack(side="left", padx=(0, 16))
        ttk.Label(row, text="时间").pack(side="left", padx=(0, 8))
        self.ent_time = ttk.Entry(row, width=8)
        now_local = datetime.now()
        minute = ((now_local.minute + 5) // 5) * 5
        hour = now_local.hour + (minute // 60)
        minute = minute % 60
        self.ent_time.insert(0, f"{hour % 24:02d}:{minute:02d}")
        self.ent_time.pack(side="left")

    def _build_cron_panel(self, parent):
        info = ttk.Label(parent, text="Cron（分 时 日 月 周），按本地时区计算。例如 “*/5 * * * *” 每5分钟",
                         foreground="#606060")
        info.pack(anchor="w", pady=(0, 4))
        row = ttk.Frame(parent);
        row.pack(fill="x", pady=6)
        ttk.Label(row, text="Cron 表达式").pack(side="left", padx=(0, 8))
        self.ent_cron = ttk.Entry(row, width=28)
        self.ent_cron.insert(0, "*/5 * * * *")
        self.ent_cron.pack(side="left")
        self.ent_cron.bind("<KeyRelease>", lambda e: self._update_cron_preview())

        row2 = ttk.Frame(parent);
        row2.pack(fill="x", pady=6)
        ttk.Label(row2, text="最近10次执行：").pack(side="left", padx=(0, 8))
        self.cmb_cron_preview = ttk.Combobox(row2, width=40, state="readonly")
        self.cmb_cron_preview.pack(side="left", padx=(0, 8))
        self._update_cron_preview()

        if not HAVE_CRONITER:
            warn = ttk.Label(parent, text="未安装 croniter，Cron 功能不可用（pip install croniter）", foreground="#b22222")
            warn.pack(anchor="w", pady=6)
            for w in [self.ent_cron, self.cmb_cron_preview]:
                w.configure(state="disabled")

    def _build_manage_tab(self, parent):
        topbar = ttk.Frame(parent)
        topbar.pack(fill="x", padx=6, pady=6)
        ttk.Button(topbar, text="刷新", command=self._refresh_tree).pack(side="left")
        ttk.Button(topbar, text="启用", command=self._enable_selected).pack(side="left", padx=6)
        ttk.Button(topbar, text="禁用", command=self._disable_selected).pack(side="left", padx=6)
        ttk.Button(topbar, text="编辑", command=self._edit_selected).pack(side="left", padx=6)
        ttk.Button(topbar, text="删除", command=self._delete_selected).pack(side="left", padx=6)

        columns = ("title", "kind", "schedule", "next", "enabled")

        # --- MODIFICATION START ---
        # 在创建Treeview时，明确指定使用我们自定义的样式 "Custom.Treeview"
        tree = ttk.Treeview(
            parent,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="Custom.Treeview"
        )
        # --- MODIFICATION END ---

        tree.heading("title", text="标题")
        tree.heading("kind", text="类型")
        tree.heading("schedule", text="计划/表达式")
        tree.heading("next", text="下次执行")
        tree.heading("enabled", text="启用")
        tree.column("title", width=240)
        tree.column("kind", width=80, anchor="center")
        tree.column("schedule", width=260)
        tree.column("next", width=160, anchor="center")
        tree.column("enabled", width=60, anchor="center")
        tree.pack(fill="both", expand=True, padx=6, pady=6)
        self.tree = tree
        self._refresh_tree()
        tree.bind("<Double-1>", lambda e: self._edit_selected())

    def _build_settings_tab(self, parent):
        card = ttk.Frame(parent, style="Card.TFrame")
        card.pack(fill="x", padx=8, pady=8)
        s = self.storage.settings

        row = ttk.Frame(card);
        row.pack(fill="x", pady=6)
        self.var_sound_enabled = tk.BooleanVar(value=s.sound_enabled)
        ttk.Checkbutton(row, text="开启铃声提醒（全局）", variable=self.var_sound_enabled,
                        command=self._update_settings).pack(side="left")

        row2 = ttk.Frame(card);
        row2.pack(fill="x", pady=6)
        ttk.Label(row2, text="默认铃声文件（WAV/MP3）：").pack(side="left", padx=(0, 8))
        self.ent_sound_file = ttk.Entry(row2)
        if s.sound_file: self.ent_sound_file.insert(0, s.sound_file)
        self.ent_sound_file.pack(side="left", fill="x", expand=True)
        ttk.Button(row2, text="浏览…", command=self._choose_sound_file).pack(side="left", padx=6)
        self.btn_test_play = ttk.Button(row2, text="测试播放", command=self._test_play_sound)
        self.btn_test_play.pack(side="left", padx=6)

        row3 = ttk.Frame(card);
        row3.pack(fill="x", pady=6)
        self.var_close_to_tray = tk.BooleanVar(value=s.close_to_tray and HAVE_TRAY)
        chk = ttk.Checkbutton(row3, text="关闭窗口最小化到系统托盘（需安装 pystray + Pillow）",
                              variable=self.var_close_to_tray, command=self._update_settings)
        chk.pack(side="left")
        if not HAVE_TRAY:
            chk.configure(state="disabled")

        row4 = ttk.Frame(card);
        row4.pack(fill="x", pady=6)
        self.var_on_top = tk.BooleanVar(value=s.always_on_top_alert)
        ttk.Checkbutton(row4, text="提醒弹框置顶", variable=self.var_on_top, command=self._update_settings).pack(
            side="left")

        row4b = ttk.Frame(card);
        row4b.pack(fill="x", pady=6)
        self.var_sys_notify = tk.BooleanVar(value=s.system_notification_enabled)
        ttk.Checkbutton(row4b, text="启用系统通知（建议安装 plyer）", variable=self.var_sys_notify,
                        command=self._update_settings).pack(side="left")

        row5 = ttk.Frame(card);
        row5.pack(fill="x", pady=6)
        ttk.Label(row5, text="主题").pack(side="left", padx=(0, 8))
        themes = ttk.Style().theme_names()
        self.cmb_theme = ttk.Combobox(row5, values=themes, state="readonly", width=16)
        self.cmb_theme.set(s.theme if s.theme in themes else ttk.Style().theme_use())
        self.cmb_theme.pack(side="left")
        ttk.Button(row5, text="应用主题", command=self._apply_theme).pack(side="left", padx=6)

        note = ttk.Label(parent, text="提示：MP3 推荐安装 vlc 或 mpg123 或 mpv（系统包），或安装 pygame。",
                         foreground="#606060")
        note.pack(anchor="w", padx=12)

    # ---------------- UI helpers ----------------

    def _on_kind_change(self):
        for p in (self.panel_delay, self.panel_datetime, self.panel_cron):
            p.pack_forget()
        k = self.kind_var.get()
        if k == "delay":
            self.panel_delay.pack(fill="x")
        elif k == "datetime":
            self.panel_datetime.pack(fill="x")
        else:
            self.panel_cron.pack(fill="x")
        self.update_idletasks()

    def _update_cron_preview(self):
        if not HAVE_CRONITER:
            return
        expr = self.ent_cron.get().strip()
        values = []
        ok = True
        try:
            # 使用本地时间作为预览的基准
            base_local = datetime.now().astimezone()
            it = croniter(expr, base_local)
            for _ in range(10):
                # get_next() 返回的是本地时区的 datetime 对象
                dt_local = it.get_next(datetime)
                values.append(dt_local.strftime("%Y-%m-%d %H:%M"))
        except Exception:
            ok = False
        self.cmb_cron_preview["values"] = values
        if values:
            self.cmb_cron_preview.set(values[0])
        self.ent_cron.configure(foreground="black" if ok else "#b22222")

    def _select_all(self, event):
        widget = self.focus_get()
        try:
            if isinstance(widget, tk.Entry) or isinstance(widget, ttk.Entry):
                widget.select_range(0, 'end')
                widget.icursor('end')
                return "break"
            elif isinstance(widget, tk.Text):
                widget.tag_add("sel", "1.0", "end-1c")
                return "break"
        except Exception:
            pass

    def _apply_theme(self):
        theme = self.cmb_theme.get()
        try:
            ttk.Style().theme_use(theme)
            self.storage.settings.theme = theme
            self.storage.save()
        except Exception as e:
            messagebox.showerror("错误", f"无法应用主题：{e}")

    def _choose_sound_file(self):
        path = filedialog.askopenfilename(
            title="选择铃声文件（WAV/MP3）",
            filetypes=[("音频文件", "*.wav *.mp3 *.aiff *.aif"), ("所有文件", "*.*")]
        )
        if path:
            self.ent_sound_file.delete(0, "end")
            self.ent_sound_file.insert(0, path)
            self._update_settings()

    def _test_play_sound(self):
        """测试播放按钮：点击开始播放，再次点击停止播放（切换状态）"""
        try:
            if getattr(self, "_test_playing", False):
                # 如果正在测试，则停止播放并恢复按钮文字
                self.sound_player.stop()
                try:
                    self.btn_test_play.config(text="测试播放")
                except Exception:
                    pass
                self._test_playing = False
                logging.info("测试铃声已停止")
                return
            # 否则开始测试播放
            self._update_settings()
            # 如果未指定铃声文件，则使用默认生成音
            sf = self.storage.settings.sound_file
            logging.info("开始测试播放铃声: %s", sf)
            # 非阻塞播放
            self.after(0, lambda: self.sound_player.play_once(sf))
            try:
                self.btn_test_play.config(text="停止播放")
            except Exception:
                pass
            self._test_playing = True
        except Exception as e:
            logging.exception('测试播放发生错误: %s', e)

    def _update_settings(self):
        s = self.storage.settings
        s.sound_enabled = self.var_sound_enabled.get()
        s.sound_file = (self.ent_sound_file.get().strip() or None)
        s.close_to_tray = bool(self.var_close_to_tray.get()) and HAVE_TRAY
        s.always_on_top_alert = self.var_on_top.get()
        s.system_notification_enabled = self.var_sys_notify.get()
        self.sound_player.settings = s
        logging.info('更新设置: sound_enabled=%s, sound_file=%s', s.sound_enabled, s.sound_file)
        self.storage.save()

    # ---------------- Create / Save ----------------

    def _clear_create_form(self):
        self.ent_title.delete(0, "end")
        self.txt_message.delete("1.0", "end")
        self.kind_var.set("delay")
        self.ent_delay.delete(0, "end")
        self.ent_delay.insert(0, "10")
        self.ent_date.delete(0, "end")
        self.ent_date.insert(0, datetime.now().strftime("%Y-%m-%d"))
        now_local = datetime.now()
        minute = ((now_local.minute + 5) // 5) * 5
        hour = now_local.hour + (minute // 60)
        minute = minute % 60
        self.ent_time.delete(0, "end")
        self.ent_time.insert(0, f"{hour % 24:02d}:{minute:02d}")
        self.ent_cron.delete(0, "end")
        self.ent_cron.insert(0, "*/5 * * * *")
        self.use_sound_var.set(True)
        self._on_kind_change()
        self._update_cron_preview()

    def save_new_reminder(self):
        title = self.ent_title.get().strip()
        message = self.txt_message.get("1.0", "end").strip()
        kind = self.kind_var.get()

        if kind == "delay":
            delay_str = self.ent_delay.get().strip()
            if not delay_str.isdigit():
                messagebox.showerror("错误", "延迟分钟须为正整数")
                return
            delay = int(delay_str)
            if delay <= 0:
                messagebox.showerror("错误", "延迟分钟须大于 0")
                return
            r = Reminder(
                id=str(uuid.uuid4()),
                title=title,
                message=message,
                kind="delay",
                delay_minutes=delay,
                use_sound=self.use_sound_var.get(),
            )
            r.next_run_ts = self.scheduler.compute_next_run(r)
        elif kind == "datetime":
            date_str = self.ent_date.get().strip()
            time_str = self.ent_time.get().strip()
            dt = parse_local_datetime(date_str, time_str)
            if not dt:
                messagebox.showerror("错误", "日期或时间格式不正确（日期：YYYY-MM-DD，时间：HH:MM）")
                return
            r = Reminder(
                id=str(uuid.uuid4()),
                title=title,
                message=message,
                kind="datetime",
                run_at_ts=to_unix_ts(dt),
                use_sound=self.use_sound_var.get(),
            )
            r.next_run_ts = self.scheduler.compute_next_run(r)
        else:
            if not HAVE_CRONITER:
                messagebox.showerror("错误", "未安装 croniter，无法使用 Cron 表达式")
                return
            expr = self.ent_cron.get().strip()
            if not expr:
                messagebox.showerror("错误", "Cron 表达式不能为空")
                return
            try:
                _ = croniter(expr, datetime.now().astimezone()).get_next(datetime)
            except Exception:
                messagebox.showerror("错误", "Cron 表达式不合法（示例：*/5 * * * *）")
                return
            r = Reminder(
                id=str(uuid.uuid4()),
                title=title,
                message=message,
                kind="cron",
                cron_expr=expr,
                use_sound=self.use_sound_var.get(),
            )
            r.next_run_ts = self.scheduler.compute_next_run(r)

        self.storage.reminders[r.id] = r
        self.storage.save()
        self.scheduler.rebuild()
        self._refresh_tree()
        messagebox.showinfo("成功", "提醒已保存")
        # 保存成功后自动清空新建表单
        try:
            self._clear_create_form()
        except Exception:
            pass
        logging.info('新提醒保存并已清空输入表单')

    # ---------------- Manage ----------------

    def _refresh_tree(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for r in sorted(self.storage.reminders.values(), key=lambda x: x.updated_at, reverse=True):
            kind_map = {"delay": "延迟", "datetime": "时间点", "cron": "Cron"}
            schedule = ""
            if r.kind == "delay":
                schedule = f"{r.delay_minutes} 分钟后"
            elif r.kind == "datetime":
                dt = localize(from_unix_ts(r.run_at_ts)) if r.run_at_ts else None
                schedule = dt.strftime("%Y-%m-%d %H:%M") if dt else "-"
            elif r.kind == "cron":
                schedule = r.cron_expr or ""
            next_run = "-"
            if r.next_run_ts:
                next_run = localize(from_unix_ts(r.next_run_ts)).strftime("%Y-%m-%d %H:%M")
            self.tree.insert("", "end", iid=r.id, values=(
                r.title or "(未命名)",
                kind_map.get(r.kind, r.kind),
                schedule,
                next_run,
                "是" if r.enabled else "否"
            ))

    def _selected_id(self) -> Optional[str]:
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选择一个提醒")
            return None
        return sel[0]

    def _enable_selected(self):
        rid = self._selected_id()
        if not rid: return
        r = self.storage.reminders.get(rid)
        if not r: return
        r.enabled = True
        r.next_run_ts = self.scheduler.compute_next_run(r)
        r.updated_at = to_unix_ts(now_utc())
        self.storage.save()
        self.scheduler.rebuild()
        self._refresh_tree()

    def _disable_selected(self):
        rid = self._selected_id()
        if not rid: return
        r = self.storage.reminders.get(rid)
        if not r: return
        r.enabled = False
        r.next_run_ts = None
        r.updated_at = to_unix_ts(now_utc())
        self.storage.save()
        self.scheduler.rebuild()
        self._refresh_tree()

    def _delete_selected(self):
        rid = self._selected_id()
        if not rid: return
        if messagebox.askyesno("确认删除", "确定删除该提醒吗？"):
            self.storage.reminders.pop(rid, None)
            self.storage.save()
            self.scheduler.rebuild()
            self._refresh_tree()

    def _edit_selected(self):
        rid = self._selected_id()
        if not rid: return
        r = self.storage.reminders.get(rid)
        if not r: return
        self._open_edit_dialog(r)

    def _open_edit_dialog(self, r: Reminder):
        dlg = tk.Toplevel(self)
        dlg.title("编辑提醒")
        dlg.transient(self)
        dlg.resizable(True, True)

        # Layout: top scrollable content + bottom fixed bar
        content_frame = ttk.Frame(dlg)
        content_frame.pack(side="top", fill="both", expand=True)
        sf = ScrollableFrame(content_frame)
        sf.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        inner = sf.inner

        row = ttk.Frame(inner);
        row.pack(fill="x", pady=6)
        ttk.Label(row, text="标题").pack(side="left", padx=(0, 8))
        ent_title = ttk.Entry(row)
        ent_title.insert(0, r.title)
        ent_title.pack(side="left", fill="x", expand=True)

        row2 = ttk.Frame(inner);
        row2.pack(fill="both", pady=6)
        ttk.Label(row2, text="内容").pack(side="top", anchor="w")
        txt_msg = tk.Text(row2, height=6, wrap="word")
        txt_msg.insert("1.0", r.message or "")
        txt_msg.pack(fill="x", expand=True)

        row3 = ttk.Frame(inner);
        row3.pack(fill="x", pady=6)
        ttk.Label(row3, text="类型").pack(side="left", padx=(0, 8))
        kind_var = tk.StringVar(value=r.kind)
        kinds = [("延迟", "delay"), ("时间点", "datetime"), ("Cron", "cron")]
        for t, v in kinds:
            ttk.Radiobutton(row3, text=t, variable=kind_var, value=v).pack(side="left", padx=10)

        pan_delay = ttk.Frame(inner);
        pan_datetime = ttk.Frame(inner);
        pan_cron = ttk.Frame(inner)

        rowd = ttk.Frame(pan_delay);
        rowd.pack(fill="x", pady=6)
        ttk.Label(rowd, text="延迟分钟").pack(side="left", padx=(0, 8))
        ent_delay = ttk.Entry(rowd, width=10)
        ent_delay.insert(0, str(r.delay_minutes or 10))
        ent_delay.pack(side="left")

        rowt = ttk.Frame(pan_datetime);
        rowt.pack(fill="x", pady=6)
        ttk.Label(rowt, text="日期").pack(side="left", padx=(0, 8))
        ent_date = ttk.Entry(rowt, width=12)
        if r.run_at_ts:
            ent_date.insert(0, localize(from_unix_ts(r.run_at_ts)).strftime("%Y-%m-%d"))
        else:
            ent_date.insert(0, datetime.now().strftime("%Y-%m-%d"))
        ent_date.pack(side="left", padx=(0, 16))
        ttk.Label(rowt, text="时间").pack(side="left", padx=(0, 8))
        ent_time = ttk.Entry(rowt, width=8)
        if r.run_at_ts:
            ent_time.insert(0, localize(from_unix_ts(r.run_at_ts)).strftime("%H:%M"))
        else:
            ent_time.insert(0, "09:00")
        ent_time.pack(side="left")

        rowc = ttk.Frame(pan_cron);
        rowc.pack(fill="x", pady=6)
        ttk.Label(rowc, text="Cron").pack(side="left", padx=(0, 8))
        ent_cron = ttk.Entry(rowc, width=28)
        ent_cron.insert(0, r.cron_expr or "*/5 * * * *")
        ent_cron.pack(side="left")
        prev = ttk.Combobox(pan_cron, width=40, state="readonly");
        prev.pack(pady=6)

        def refresh_panels(*args):
            for p in (pan_delay, pan_datetime, pan_cron): p.pack_forget()
            k = kind_var.get()
            if k == "delay":
                pan_delay.pack(fill="x")
            elif k == "datetime":
                pan_datetime.pack(fill="x")
            else:
                pan_cron.pack(fill="x")

        refresh_panels()
        for rb in row3.winfo_children():
            if isinstance(rb, ttk.Radiobutton):
                rb.configure(command=refresh_panels)

        def update_prev(*args):
            if not HAVE_CRONITER: return
            expr = ent_cron.get().strip()
            vals = []
            try:
                # 使用本地时间作为编辑预览的基准
                base_local = datetime.now().astimezone()
                it = croniter(expr, base_local)
                for _ in range(10):
                    dt_local = it.get_next(datetime)
                    vals.append(dt_local.strftime("%Y-%m-%d %H:%M"))
            except Exception:
                pass
            prev["values"] = vals
            if vals: prev.set(vals[0])

        update_prev()
        ent_cron.bind("<KeyRelease>", lambda e: update_prev())

        rowopt = ttk.Frame(inner);
        rowopt.pack(fill="x", pady=8)
        use_sound_var = tk.BooleanVar(value=r.use_sound)
        ttk.Checkbutton(rowopt, text="使用铃声", variable=use_sound_var).pack(side="left")

        # Bottom fixed buttons
        bottom = ttk.Frame(dlg)
        bottom.pack(side="bottom", fill="x", padx=10, pady=10)

        def save_edit():
            title = ent_title.get().strip()
            message = txt_msg.get("1.0", "end").strip()
            k = kind_var.get()
            r.title = title
            r.message = message
            r.kind = k
            r.last_triggered_at = None
            r.enabled = True
            if k == "delay":
                val = ent_delay.get().strip()
                if not val.isdigit() or int(val) <= 0:
                    messagebox.showerror("错误", "延迟分钟须为正整数")
                    return
                r.delay_minutes = int(val)
                r.run_at_ts = None
                r.cron_expr = None
            elif k == "datetime":
                dt = parse_local_datetime(ent_date.get().strip(), ent_time.get().strip())
                if not dt:
                    messagebox.showerror("错误", "日期或时间格式不正确（YYYY-MM-DD 和 HH:MM）")
                    return
                r.run_at_ts = to_unix_ts(dt)
                r.delay_minutes = None
                r.cron_expr = None
            else:
                if not HAVE_CRONITER:
                    messagebox.showerror("错误", "未安装 croniter，无法使用 Cron 表达式")
                    return
                expr = ent_cron.get().strip()
                try:
                    _ = croniter(expr, datetime.now().astimezone()).get_next(datetime)
                except Exception:
                    messagebox.showerror("错误", "Cron 表达式不合法")
                    return
                r.cron_expr = expr
                r.delay_minutes = None
                r.run_at_ts = None
            r.use_sound = use_sound_var.get()
            r.updated_at = to_unix_ts(now_utc())
            r.next_run_ts = self.scheduler.compute_next_run(r)
            self.storage.save()
            self.scheduler.rebuild()
            self._refresh_tree()
            dlg.destroy()

        ttk.Button(bottom, text="保存", command=save_edit).pack(side="left")
        ttk.Button(bottom, text="取消", command=dlg.destroy).pack(side="left", padx=8)

        # Center dialog based on required size
        dlg.update_idletasks()
        req_w = max(560, dlg.winfo_reqwidth())
        req_h = max(420, dlg.winfo_reqheight())
        # Limit size to 80% of monitor; still resizable
        x, y = center_on_relevant_monitor(dlg, req_w, req_h)
        dlg.geometry(f"{req_w}x{req_h}+{x}+{y}")
        dlg.grab_set()

        # Select-all bindings inside dialog
        for seq in ("<Control-a>", "<Control-A>", "<Command-a>", "<Command-A>"):
            dlg.bind_all(seq, self._select_all)

    # ---------------- Tray ----------------

    def _create_tray_image(self, size=64):
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        cx, cy, r = size // 2, size // 2, int(size * 0.32)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 205, 0, 255), outline=(200, 160, 0, 255), width=3)
        d.rectangle((cx - r // 3, cy + r - 6, cx + r // 3, cy + r + 6), fill=(255, 205, 0, 255))
        return img

    def _init_tray(self):
        if not HAVE_TRAY:
            return

        if platform.system() == "Linux":
            logging.info("正在初始化 Linux 托盘图标。已尝试设置 'appindicator' 后端以增强兼容性。")

        image = self._create_tray_image(64)
        menu = pystray.Menu(
            pystray.MenuItem("显示窗口", self._tray_show),
            pystray.MenuItem("退出", self._tray_quit),
        )

        # 【优化】在这里添加 left_click_action
        self.tray_icon = pystray.Icon(
            APP_NAME,
            image,
            APP_NAME,
            menu,
            # 当左键单击时，也调用显示窗口的函数
            left_click=self._tray_show
        )

        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _tray_show(self, icon, item):
        self.after(0, self._restore_from_tray)

    def _tray_quit(self, icon, item):
        self.after(0, self._quit_app)

    def _restore_from_tray(self):
        self.deiconify()
        self.state("normal")
        self.lift()
        self.focus_force()

    # ---------------- Reminders firing ----------------

    def on_reminder_fire(self, reminder: Reminder):
        logging.info('提醒触发: %s', reminder.title if reminder.title else reminder.id)
        self.after(0, lambda: self._on_fire_main(reminder))

    def _on_fire_main(self, reminder: Reminder):
        # 1) System notification
        self.notifier.notify(reminder.title or "提醒", (reminder.message or "").strip(),
                             enable=self.storage.settings.system_notification_enabled)
        # 2) Centered alert dialog with non-blocking sound
        self._show_alert(reminder)

    def _show_alert(self, reminder: Reminder):
        AlertDialog(self, reminder, self.storage.settings, self.sound_player, on_close=self._on_alert_closed)

    def _on_alert_closed(self, reminder: Reminder):
        self.storage.save()
        self._refresh_tree()

    # ---------------- Window lifecycle ----------------

    def on_close(self):
        if self.storage.settings.close_to_tray and HAVE_TRAY:
            self.withdraw()
        else:
            self._quit_app()

    def _quit_app(self):
        try:
            if self.tray_icon:
                self.tray_icon.stop()
        except Exception as e:
            logging.error(f"退出过程中系统托盘图标停止时发生错误: {e}")
            pass
        try:
            self.scheduler.stop()
        except Exception as e:
            logging.error(f"退出过程中调度器停止时发生错误: {e}")
            pass
        try:
            self.sound_player.stop()
        except Exception as e:
            logging.error(f"退出过程中声音播放器停止时发生错误: {e}")
            pass
        try:
            self.storage.save()
        except Exception as e:
            logging.error(f"退出过程中存储保存时发生错误: {e}")
            pass
        self.destroy()


# 程序入口：创建 App 实例并进入主循环
def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
