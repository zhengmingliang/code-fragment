import tkinter as tk
from tkinter import messagebox
import requests
import threading
import time
from datetime import datetime
import json
import os

# --- 1. 全局配置 ---
API_CONFIG = {
    "url": "https://api.jdjygold.com/gw2/generic/jrm/h5/m/stdLatestPrice?productSku=1961543816",
    "method": "POST",
    "headers": {
        "authority": "api.jdjygold.com",
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "no-cache",
        "cookie": "qid_uid=0e1bed8d-3488-40cd-bbec-2741a693a901; qid_fs=1744480640560; qid_ls=1744480640560; qid_ts=1744480640576; qid_vis=1; qid_sid=0e1bed8d-3488-40cd-bbec-2741a693a901-1; 3AB9D23F7A4B3CSS=jdd035NYXGTYVO6Z4WOWZX5XGXYKAIZ7KPVVOJYOUKKKY2A3CKWDS6RYX6UPXFXLXUMUDEH6OVX4TVLNFQ35NV6CSRIZW4YAAAAMWFMTB7UYAAAAADD532CYYQVMGQAX; 3AB9D23F7A4B3C9B=5NYXGTYVO6Z4WOWZX5XGXYKAIZ7KPVVOJYOUKKKY2A3CKWDS6RYX6UPXFXLXUMUDEH6OVX4TVLNFQ35NV6CSRIZW4Y; _gia_d=1; pt_key=AAJn-TFPADA9LEOfyrr9OTEhiQyb3RdUZXprp4lXodOd5hf5oSqeYzL7X6TUJiFewLT_9-1Vhs4; pt_pin=jd_56b59ca1452b8; pt_token=rl8dny7v; pwdt_id=jd_56b59ca1452b8; sfstoken=tk01mae7c1ba0a8sMXgyNHVkenM0FLJAqUlBrxDuBIasKpV/yYEnOZ0PLiMc4QCeB+/OCPTc3aM8xWs7zNIK53W/Gwgq; qid_seq=4; qid_evord=95",
        # <--- 在这里填入你完整的cookie字符串
        "origin": "https://m.jdjygold.com",
        "pragma": "no-cache",
        "referer": "https://m.jdjygold.com/",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
    },
    "data": {"reqData": '{"productSku":"1961543816"}'}
}
UPDATE_INTERVAL_MS = 10000
SELLING_FEE_RATE = 0.004
CONFIG_FILE = "config.json"

# --- 2. 窗口外观配置 ---
COLOR_BG = "#2B2B2B"
COLOR_TEXT_NORMAL = "#E0E0E0"
COLOR_UP = "#FF5733"
COLOR_DOWN = "#33FF57"
COLOR_LABEL = "#9E9E9E"

# --- 3. 持仓配置管理 ---
def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"buy_total_cost": 0.0, "buy_total_weight": 0.0}
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"buy_total_cost": 0.0, "buy_total_weight": 0.0}

def save_config(data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# --- 4. 基础可拖动窗口类 ---
class DraggableWindow:
    def __init__(self, master, geometry):
        self.master = tk.Toplevel(master)
        self.master.overrideredirect(True)
        self.master.attributes("-topmost", True)
        self.master.geometry(geometry)
        self.master.configure(bg=COLOR_BG)
        self.offset_x = 0
        self.offset_y = 0
        self.master.bind("<Button-1>", self.start_drag)
        self.master.bind("<B1-Motion>", self.do_drag)

    def start_drag(self, event): self.offset_x, self.offset_y = event.x, event.y

    def do_drag(self, event): self.master.geometry(
        f"+{self.master.winfo_pointerx() - self.offset_x}+{self.master.winfo_pointery() - self.offset_y}")

# --- 5. 设置窗口 ---
class SettingsWindow(tk.Toplevel):
    def __init__(self, parent, portfolio_app_instance):
        super().__init__(parent)
        self.portfolio_app = portfolio_app_instance
        self.title("设置持仓信息")
        self.geometry("300x220")
        self.configure(bg="#F0F0F0")
        self.resizable(False, False)
        self.transient(parent)

        config = load_config()
        tk.Label(self, text="买入总成本 (元):", bg="#F0F0F0").pack(pady=(15, 0))
        self.cost_entry = tk.Entry(self)
        self.cost_entry.insert(0, str(config.get("buy_total_cost", 0.0)))
        self.cost_entry.pack(pady=5, padx=20, fill='x')
        tk.Label(self, text="买入总数量 (克):", bg="#F0F0F0").pack()
        self.weight_entry = tk.Entry(self)
        self.weight_entry.insert(0, str(config.get("buy_total_weight", 0.0)))
        self.weight_entry.pack(pady=5, padx=20, fill='x')

        btn_frame = tk.Frame(self, bg="#F0F0F0")
        tk.Button(btn_frame, text="保存", command=self.save_and_close, width=8).pack(side="left", padx=10)
        tk.Button(btn_frame, text="取消", command=self.destroy, width=8).pack(side="left", padx=10)
        btn_frame.pack(pady=15)

        self.grab_set()
        self.cost_entry.focus_set()
        self.bind('<Return>', lambda event: self.save_and_close())

    def save_and_close(self):
        try:
            new_cost = float(self.cost_entry.get().strip())
            new_weight = float(self.weight_entry.get().strip())
            if new_cost < 0 or new_weight < 0: raise ValueError("成本和数量不能为负数")
            save_config({"buy_total_cost": new_cost, "buy_total_weight": new_weight})
            self.portfolio_app.update_metrics_from_config()
            self.destroy()
        except ValueError as e:
            messagebox.showerror("输入错误", f"请输入有效的数字！\n{e}", parent=self)

# --- 6. 持仓分析标签 (PortfolioTrackerApp) ---
class PortfolioTrackerApp(DraggableWindow):
    def __init__(self, master):
        super().__init__(master, "250x190+420+100")
        self.master.title("持仓分析")
        self.master.grid_rowconfigure(list(range(5)), weight=1)
        self.master.grid_columnconfigure(0, weight=1)
        self.master.grid_columnconfigure(1, weight=2)

        self.vars = {
            "total_value": tk.StringVar(value="--"),
            "selling_fee": tk.StringVar(value="--"),
            "avg_cost": tk.StringVar(value="--"),
            "profit": tk.StringVar(value="--"),
            "gross_profit": tk.StringVar(value="--"),
        }

        # --- 新增：闪烁状态管理 ---
        self.is_blinking = False
        self.blink_job_id = None

        self.create_label_value_pair(0, "总价值:", self.vars["total_value"])
        self.create_label_value_pair(1, "手续费:", self.vars["selling_fee"])
        self.create_label_value_pair(2, "成本均价:", self.vars["avg_cost"])
        self.profit_value_label = self.create_label_value_pair(3, "净收益:", self.vars["profit"], is_profit=True)
        self.gross_profit_value_label = self.create_label_value_pair(4, "毛收益:", self.vars["gross_profit"],
                                                                     is_profit=True)

        self.menu = tk.Menu(self.master, tearoff=0)
        self.menu.add_command(label="设置持仓...", command=self.open_settings)
        self.menu.add_separator()
        self.menu.add_command(label="退出程序", command=master.quit)
        self.master.bind("<Button-3>", lambda e: self.menu.post(e.x_root, e.y_root))

        self.current_price = 0.0
        self.update_metrics_from_config()

    def create_label_value_pair(self, row, text, var, is_profit=False):
        tk.Label(self.master, text=text, font=("Arial", 10), bg=COLOR_BG, fg=COLOR_LABEL, anchor="e").grid(row=row,
                                                                                                           column=0,
                                                                                                           sticky="ew",
                                                                                                           padx=(10, 0))
        lbl = tk.Label(self.master, textvariable=var, font=("Arial", 12, "bold" if is_profit else "normal"),
                       bg=COLOR_BG, fg=COLOR_TEXT_NORMAL, anchor="w")
        lbl.grid(row=row, column=1, sticky="ew", padx=(5, 10))
        return lbl

    # --- 优化：独立的闪烁循环和控制方法 ---
    def _start_blinking(self):
        """启动闪烁循环"""
        if self.blink_job_id:  # 先确保之前的任务已取消
            self.master.after_cancel(self.blink_job_id)
        self.is_blinking = True
        self._toggle_blink_color()

    def _stop_blinking(self):
        """停止闪烁循环并恢复颜色"""
        if self.blink_job_id:
            self.master.after_cancel(self.blink_job_id)
            self.blink_job_id = None
        self.is_blinking = False
        # 恢复到非闪烁状态的颜色
        self.gross_profit_value_label.config(fg=COLOR_UP)

    def _toggle_blink_color(self):
        """闪烁的核心逻辑，递归调用自身"""
        if not self.is_blinking:  # 如果状态变为停止，则退出循环
            return
        current_color = self.gross_profit_value_label.cget("fg")
        next_color = COLOR_BG if current_color == COLOR_DOWN else COLOR_DOWN
        self.gross_profit_value_label.config(fg=next_color)
        self.blink_job_id = self.master.after(500, self._toggle_blink_color)

    def open_settings(self):
        SettingsWindow(self.master, self)

    def update_metrics(self, price_data):
        try:
            self.current_price = float(price_data.get("price", 0.0))
            self.update_metrics_from_config()
        except (ValueError, TypeError):
            pass

    def update_metrics_from_config(self):
        config = load_config()
        cost, weight = config.get("buy_total_cost", 0.0), config.get("buy_total_weight", 0.0)

        if self.current_price > 0 and weight > 0:
            total_value = self.current_price * weight
            selling_fee = total_value * SELLING_FEE_RATE
            avg_cost = cost / weight

            gross_profit = total_value - cost
            net_profit = gross_profit - selling_fee

            self.vars["total_value"].set(f"¥ {total_value:,.2f}")
            self.vars["selling_fee"].set(f"¥ {selling_fee:,.2f}")
            self.vars["avg_cost"].set(f"¥ {avg_cost:,.2f}")
            self.vars["profit"].set(f"¥ {net_profit:,.2f}")
            self.vars["gross_profit"].set(f"¥ {gross_profit:,.2f}")

            self.profit_value_label.config(fg=COLOR_UP if net_profit >= 0 else COLOR_DOWN)

            # --- 优化：基于状态变化的闪烁控制 ---
            if gross_profit < 0:
                # 状态：毛利为负
                if not self.is_blinking:
                    # 如果之前没在闪，则启动闪烁
                    self._start_blinking()
                # 如果已经在闪了，就什么也不做，让它继续闪
            else:
                # 状态：毛利为正或零
                if self.is_blinking:
                    # 如果之前在闪，则停止闪烁
                    self._stop_blinking()
                else:
                    # 如果之前没在闪，确保颜色是正确的
                    self.gross_profit_value_label.config(fg=COLOR_UP)

        else:
            # 重置状态
            if self.is_blinking:
                self._stop_blinking()
            for key, var in self.vars.items():
                if key != "avg_cost": var.set("--")
            self.vars["avg_cost"].set(f"¥ {(cost / weight if weight > 0 else 0):.2f}")
            self.profit_value_label.config(fg=COLOR_TEXT_NORMAL)
            self.gross_profit_value_label.config(fg=COLOR_TEXT_NORMAL)

# --- 7. 金价行情标签 (PriceTrackerApp) ---
class PriceTrackerApp(DraggableWindow):
    def __init__(self, master, update_callback):
        super().__init__(master, "300x150+100+100")
        self.master.title("金价行情")
        self.update_callback = update_callback
        self.price_var, self.change_var, self.time_var = tk.StringVar(value="--.--"), tk.StringVar(
            value="-.-% (-.-)"), tk.StringVar(value="加载中...")
        self.price_label = tk.Label(self.master, textvariable=self.price_var, font=("Arial", 32, "bold"), bg=COLOR_BG,
                                    fg=COLOR_TEXT_NORMAL, pady=5)
        self.price_label.pack(expand=True, fill='x')
        self.change_label = tk.Label(self.master, textvariable=self.change_var, font=("Arial", 16), bg=COLOR_BG,
                                     fg=COLOR_TEXT_NORMAL)
        self.change_label.pack(expand=True, fill='x')
        tk.Label(self.master, textvariable=self.time_var, font=("Arial", 10), bg=COLOR_BG, fg="#888888", pady=5).pack(
            side='bottom', fill='x')
        self.master.bind("<Double-Button-1>", lambda e: master.quit())
        self.update_content()

    def fetch_api_data(self):
        try:
            resp = requests.request(method=API_CONFIG["method"], url=API_CONFIG["url"], headers=API_CONFIG["headers"],
                                    data=API_CONFIG["data"], timeout=10)
            resp.raise_for_status()
            api_data = resp.json()
            if not api_data.get("success"): raise ValueError(api_data.get("resultMsg", "API返回失败"))
            data = api_data["resultData"]["datas"]
            amt, rate = data.get("upAndDownAmt", "N/A"), data.get("upAndDownRate", "N/A")
            change_color = COLOR_UP if "-" not in str(amt) else COLOR_DOWN
            self.price_var.set(f"{data.get('price', 'N/A')}")
            self.change_var.set(f"{rate} ({amt})")
            self.price_label.config(fg=change_color)
            self.change_label.config(fg=change_color)
            self.time_var.set(f"更新于: {datetime.fromtimestamp(int(data.get('time', 0)) / 1000).strftime('%H:%M:%S')}")
            if self.update_callback: self.update_callback(data)
        except Exception as e:
            self.price_var.set("错误");
            self.change_var.set("检查Cookie或网络");
            print(f"错误: {e}")
        finally:
            self.master.after(UPDATE_INTERVAL_MS, self.update_content)

    def update_content(self):
        threading.Thread(target=self.fetch_api_data, daemon=True).start()

# --- 8. 主程序入口 ---
if __name__ == "__main__":
    if "pt_key=..." in API_CONFIG["headers"]["cookie"]: print("\n[错误] 请在代码中更新你的有效Cookie！\n")
    root = tk.Tk()
    root.withdraw()
    portfolio_app = PortfolioTrackerApp(root)
    price_app = PriceTrackerApp(root, update_callback=portfolio_app.update_metrics)
    root.mainloop()
