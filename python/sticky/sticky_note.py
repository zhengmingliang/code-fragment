import tkinter as tk
import requests
import threading
import time

# --- 可配置参数 ---

# API接口，需要返回一个JSON。我们将从中提取一个字段来显示。
# 示例API (一言): https://v1.hitokoto.cn/
# 它返回的JSON格式: {"id":..., "hitokoto":"这里是名言", "from":"出处", ...}
# 我们要提取 'hitokoto' 和 'from' 字段。
API_URL = "https://v1.hitokoto.cn/?c=i&encode=json"

# 从JSON中提取内容的键名 (Key)
# 如果内容是嵌套的，例如 {"data": {"text": "你好"}}, 可以用 "data.text" 的形式
CONTENT_KEY = "hitokoto"
SOURCE_KEY = "from"

# 更新内容的时间间隔（毫秒）
UPDATE_INTERVAL_MS = 20000  # 20秒

# 便签外观设置
GEOMETRY = "350x120+100+100"  # 初始尺寸和位置 (宽x高+X坐标+Y坐标)
BACKGROUND_COLOR = "#FFFFE0"  # 淡黄色背景 #FFFF99
FOREGROUND_COLOR = "#333333"  # 深灰色文字
FONT_CONFIG = ("Noto Sans CJK SC", 12, "normal") # 字体 (可替换为你系统有的中文字体)
SOURCE_FONT_CONFIG = ("Noto Sans CJK SC", 10, "italic")

# --- 主应用代码 ---

class StickyNoteApp:
    def __init__(self, master):
        self.master = master
        self.offset_x = 0
        self.offset_y = 0

        # 配置窗口
        self.master.title("置顶便签")
        self.master.geometry(GEOMETRY)
        self.master.configure(bg=BACKGROUND_COLOR)
        
        # 设置窗口无边框和置顶
        self.master.overrideredirect(True)  # 移除窗口边框和标题栏
        self.master.attributes("-topmost", True)  # 设置窗口置顶

        # 创建用于显示内容的Label
        self.content_var = tk.StringVar()
        self.source_var = tk.StringVar()
        
        self.content_label = tk.Label(
            self.master,
            textvariable=self.content_var,
            wraplength=330,  # 文本自动换行宽度
            justify=tk.LEFT,
            bg=BACKGROUND_COLOR,
            fg=FOREGROUND_COLOR,
            font=FONT_CONFIG,
            padx=10,
            pady=10
        )
        self.content_label.pack(expand=True, fill='both')

        self.source_label = tk.Label(
            self.master,
            textvariable=self.source_var,
            justify=tk.RIGHT,
            bg=BACKGROUND_COLOR,
            fg=FOREGROUND_COLOR,
            font=SOURCE_FONT_CONFIG,
            padx=10,
        )
        self.source_label.pack(fill='x', side='bottom')

        # 绑定鼠标事件以实现拖动
        self.master.bind("<Button-1>", self.start_drag)
        self.master.bind("<B1-Motion>", self.do_drag)
        self.master.bind("<Double-Button-1>", lambda e: master.quit())

        # 首次启动时获取内容，然后开始定时更新
        self.update_content()

    def start_drag(self, event):
        """记录鼠标点击时的相对位置"""
        self.offset_x = event.x
        self.offset_y = event.y

    def do_drag(self, event):
        """根据鼠标移动更新窗口位置"""
        x = self.master.winfo_pointerx() - self.offset_x
        y = self.master.winfo_pointery() - self.offset_y
        self.master.geometry(f"+{x}+{y}")

    def fetch_api_data(self):
        """从API获取数据并更新UI"""
        try:
            # 设置超时以防网络请求卡死
            response = requests.get(API_URL, timeout=10)
            response.raise_for_status()  # 如果请求失败 (例如 404, 500)，则抛出异常
            data = response.json()
            
            # 解析JSON并更新文本变量
            content = data.get(CONTENT_KEY, "内容加载失败...")
            source = data.get(SOURCE_KEY, "未知来源")
            
            self.content_var.set(content)
            self.source_var.set(f"—— {source}")

        except requests.exceptions.RequestException as e:
            self.content_var.set("网络错误...")
            self.source_var.set(str(e))
        except Exception as e:
            self.content_var.set("程序或API解析错误")
            self.source_var.set(str(e))
        finally:
            # 无论成功与否，都安排下一次更新
            self.master.after(UPDATE_INTERVAL_MS, self.update_content)

    def update_content(self):
        """在后台线程中获取数据，以防UI卡顿"""
        # 显示“正在加载...”提示
        self.content_var.set("正在加载...")
        self.source_var.set("")
        
        # 使用线程来执行网络请求，防止阻塞GUI主循环
        thread = threading.Thread(target=self.fetch_api_data)
        thread.daemon = True  # 设置为守护线程，主程序退出时线程也退出
        thread.start()


if __name__ == "__main__":
    root = tk.Tk()
    app = StickyNoteApp(root)
    root.mainloop()
