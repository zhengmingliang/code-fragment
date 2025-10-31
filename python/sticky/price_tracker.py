import requests
import json
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
import time

import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.animation import FuncAnimation
import matplotlib.dates as mdates

# --- 0. 新增：创建自定义工具栏 ---
class CustomToolbar(NavigationToolbar2Tk):
    def __init__(self, canvas, window, app_instance):
        super().__init__(canvas, window)
        self.app = app_instance

    def zoom(self, *args):
        # 当用户点击放大镜按钮时，禁用自动缩放
        super().zoom(*args)
        self.app.autoscale_enabled = False
        print("Zoom mode activated. Autoscaling disabled.")

    def pan(self, *args):
        # 当用户点击平移按钮时，禁用自动缩放
        super().pan(*args)
        self.app.autoscale_enabled = False
        print("Pan mode activated. Autoscaling disabled.")
        
    def home(self, *args):
        # 当用户点击Home按钮时，启用自动缩放
        super().home(*args)
        self.app.autoscale_enabled = True
        print("Home view restored. Autoscaling enabled.")
        # 我们需要手动触发一次更新来应用自动缩放
        self.app.update_plot(None) 


# --- 1. 数据获取函数 (与之前相同) ---
def fetch_price_data(product_sku="1961543816"):
    # ... (代码与之前完全相同，此处省略) ...
    url = f'https://api.jdjygold.com/gw2/generic/jrm/h5/m/stdTodayLatestPrices?timeStr&productSku={product_sku}'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    payload = {'reqData': json.dumps({"timeStr": "", "productSku": product_sku})}
    try:
        response = requests.post(url, headers=headers, data=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("success") and data.get("resultData", {}).get("status") == "SUCCESS":
            return data['resultData']['datas']
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] API返回错误: {data.get('resultMsg', '未知错误')}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 请求失败: {e}")
        return None
    except json.JSONDecodeError:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 解析JSON响应失败")
        return None


# --- 2. GUI应用类 ---
class RealTimePriceChart:
    def __init__(self, root, product_sku):
        self.root = root
        self.product_sku = product_sku
        
        # --- 新增：用于控制缩放状态的标志 ---
        self.autoscale_enabled = True
        
        self.root.title(f"产品 {self.product_sku} 实时价格监控")
        self.root.geometry("900x600")
        self.root.attributes('-topmost', True)
        
        self.fig = Figure(figsize=(15, 7), dpi=100)
        self.ax = self.fig.add_subplot(111)
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # --- 修改：使用我们自定义的工具栏 ---
        self.toolbar = CustomToolbar(self.canvas, self.root, self)
        self.toolbar.update()
        
        matplotlib.rcParams['font.sans-serif'] = ['SimHei']
        matplotlib.rcParams['axes.unicode_minus'] = False
        
        self.annot = self.ax.annotate("", xy=(0,0), xytext=(20,20),
                                       textcoords="offset points",
                                       bbox=dict(boxstyle="round", fc="yellow", ec="black", lw=1, alpha=0.8),
                                       arrowprops=dict(arrowstyle="->"))
        self.annot.set_visible(False)

        self.fig.canvas.mpl_connect("motion_notify_event", self.on_hover)
        # --- 修改：当用户使用滚轮缩放时，也禁用自动缩放 ---
        self.fig.canvas.mpl_connect('scroll_event', self.on_scroll)

        self.ani = FuncAnimation(self.fig, self.update_plot, interval=20000, cache_frame_data=False)
    
    # --- 新增：处理鼠标滚轮事件 ---
    def on_scroll(self, event):
        self.autoscale_enabled = False
        print("Mouse scroll detected. Autoscaling disabled.")

    def parse_and_plot(self, price_data):
        # ... (此函数内部逻辑与之前完全相同，此处省略) ...
        if not price_data:
            self.ax.text(0.5, 0.5, '暂无数据或获取失败', horizontalalignment='center', verticalalignment='center', transform=self.ax.transAxes)
            self.canvas.draw()
            return

        timestamps, prices = [], []
        high_point, low_point = None, None

        for item in price_data:
            value_list = item['value']
            dt_object = datetime.strptime(value_list[0], '%Y-%m-%d %H:%M:%S')
            price = float(value_list[1])
            timestamps.append(dt_object)
            prices.append(price)

            if len(value_list) > 2:
                if value_list[2] == 'highKey': high_point = (dt_object, price)
                elif value_list[2] == 'lowKey': low_point = (dt_object, price)
        
        self.line, = self.ax.plot(timestamps, prices, label='实时价格', color='dodgerblue', linewidth=1.5)
        
        if high_point:
            self.ax.plot(high_point[0], high_point[1], 'ro', markersize=8)
            self.ax.annotate(f'最高\n{high_point[1]}', xy=high_point, xytext=(-30, 20), textcoords='offset points',
                             arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=.2"),
                             bbox=dict(boxstyle="round,pad=0.3", fc="red", lw=1, alpha=0.7))
        if low_point:
            self.ax.plot(low_point[0], low_point[1], 'go', markersize=8)
            self.ax.annotate(f'最低\n{low_point[1]}', xy=low_point, xytext=(-30, -30), textcoords='offset points',
                             arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=-.2"),
                             bbox=dict(boxstyle="round,pad=0.3", fc="green", lw=1, alpha=0.7))
                             
        self.ax.set_title(f'产品 (SKU: {self.product_sku}) 今日价格走势 (每20秒刷新)', fontsize=14)
        self.ax.set_xlabel('时间', fontsize=12)
        self.ax.set_ylabel('价格 (元/克)', fontsize=12)
        self.ax.grid(True, linestyle='--', alpha=0.6)
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        self.fig.autofmt_xdate()
        self.ax.legend()
        self.fig.tight_layout()
        
    def update_plot(self, frame):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在刷新数据...")
        
        # --- 修改：在清空前保存视图范围 ---
        if not self.autoscale_enabled:
            xlim = self.ax.get_xlim()
            ylim = self.ax.get_ylim()
        
        self.ax.clear()
        price_data = fetch_price_data(self.product_sku)
        self.parse_and_plot(price_data)
        
        self.ax.add_artist(self.annot)
        
        # --- 修改：在绘制后恢复视图范围 ---
        if not self.autoscale_enabled:
            self.ax.set_xlim(xlim)
            self.ax.set_ylim(ylim)
        
        self.canvas.draw()
        
    def on_hover(self, event):
        # ... (此函数内部逻辑与之前完全相同，此处省略) ...
        if event.inaxes == self.ax:
            x_data, y_data = event.xdata, event.ydata
            self.annot.xy = (x_data, y_data)
            ax_width = self.ax.get_window_extent().width
            x_pixel = event.x
            
            if x_pixel > ax_width / 2:
                self.annot.set_x(-90)
            else:
                self.annot.set_x(20)

            time_str = mdates.num2date(x_data).strftime('%Y-%m-%d %H:%M:%S')
            price_str = f"{y_data:.2f}"
            self.annot.set_text(f"时间: {time_str}\n价格: {price_str}")
            
            self.annot.set_visible(True)
            self.fig.canvas.draw_idle()
        else:
            if self.annot.get_visible():
                self.annot.set_visible(False)
                self.fig.canvas.draw_idle()

# --- 3. 主程序入口 (与之前相同) ---
if __name__ == "__main__":
    try:
        root = tk.Tk()
        product_sku_to_fetch = "1961543816"
        app = RealTimePriceChart(root, product_sku_to_fetch)
        root.mainloop()
    except ImportError:
        messagebox.showerror("依赖错误", "Tkinter库未找到，请确保您的Python环境已正确安装。")
    except Exception as e:
        messagebox.showerror("未知错误", f"程序发生错误: {e}")
