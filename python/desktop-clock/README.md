# DesktopClock - 跨平台桌面时钟工具

一个简洁、美观、功能强大的跨平台桌面时钟工具，使用 Python + tkinter 开发。

## ✨ 功能特性

### 🎯 核心功能
- **无边框设计**：简洁美观，不占用额外桌面空间
- **拖拽移动**：鼠标左键拖拽可移动到桌面任意位置
- **窗口固定**：双击可切换窗口置顶/取消置顶状态
- **配置持久化**：自动保存位置、大小、主题等设置

### 🎨 显示选项
- **多种时间格式**：支持显示/隐藏秒数
- **日期显示**：可选择显示或隐藏日期和星期
- **5 种预设主题**：深色、浅色、蓝色、紫色、绿色
- **自定义字体大小**：滚轮调节，支持 12-120px
- **窗口大小调节**：右下角拖拽缩放，或通过右键菜单选择预设大小/自动适应文字
- **透明度调节**：标准版支持整体透明度 30%-100%；Qt 版额外支持背景透明度 0%-100%
- **透明背景**：可一键隐藏窗口背景，仅保留时间/日期文字

### ⚙️ 系统集成
- **开机自启**：支持 Windows、macOS、Linux
- **右键菜单**：快速访问所有设置选项
- **跨平台兼容**：Windows、macOS、Linux 全平台支持

## 📦 安装依赖

### 标准 tkinter 版本

本工具默认版本使用 Python 标准库，无需额外安装依赖：

```bash
# 确保 Python 3.6+ 已安装
python3 --version

# 直接运行
python3 desktop_clock.py
```

### Linux 透明背景增强版

Linux 下 tkinter 的 `-transparentcolor` 通常受 Tk/窗口管理器限制，可能无法真正隐藏背景。若需要 **真正透明背景，仅显示文字**，推荐使用 Qt 版本：

```bash
# 安装 Qt 依赖，推荐 PySide6
python3 -m pip install -r requirements-qt.txt

# 运行 Linux 透明背景增强版
python3 desktop_clock_qt.py
```

Qt 版本默认启用透明背景，也支持右键菜单关闭透明背景。若背景变黑，可在右键菜单选择 **背景透明度 → 0%**。

## 🚀 快速开始

### 1. 运行程序

```bash
# 进入项目目录
cd python/desktop-clock

# 标准 tkinter 版本
python3 desktop_clock.py

# Linux 若需要真正透明背景，使用 Qt 版本
python3 desktop_clock_qt.py
```

### 2. 基本操作

| 操作 | 说明 |
|------|------|
| **左键拖拽** | 移动窗口位置 |
| **右下角 ◢ 拖拽** | 调整窗口大小 |
| **双击** | 切换窗口固定/取消固定 |
| **右键** | 显示设置菜单 |
| **滚轮** | 调节字体大小 |

### 3. 右键菜单功能

- **固定/取消固定**：切换窗口置顶状态
- **字体大小**：放大/缩小，或选择 24/36/48/60/72px 预设值
- **窗口大小**：自动适应文字、放大/缩小，或选择常用窗口尺寸
- **显示/隐藏日期**：控制日期显示
- **开启/关闭透明背景**：隐藏窗口背景，仅保留文字显示
- **显示/隐藏秒数**：控制秒数显示
- **主题**：切换预设主题（深色/浅色/蓝色/紫色/绿色）
- **背景透明度**：Qt 版本支持，只调整背景透明度，0% 时背景完全透明、文字保留
- **整体透明度**：调节整个窗口透明度（文字和背景一起变透明）
- **开机自启**：设置/取消开机自动启动
- **退出**：关闭程序

## 📁 配置文件

配置文件保存在用户主目录下：

- **Windows**: `C:\Users\<用户名>\.desktopclock\config.json`
- **macOS**: `~/.desktopclock/config.json`
- **Linux**: `~/.desktopclock/config.json`

### 配置项说明

```json
{
  "position": {"x": 100, "y": 100},      // 窗口位置
  "size": {"width": 420, "height": 150},  // 窗口大小
  "font_size": 48,                        // 字体大小
  "opacity": 0.9,                         // 整体透明度 (0.3-1.0)，文字和背景一起变化
  "background_opacity": 0.0,              // Qt 版背景透明度 (0.0-1.0)，0 表示仅隐藏背景
  "transparent_bg": false,                 // 是否启用透明背景
  "always_on_top": true,                  // 是否置顶
  "theme": "dark",                        // 主题名称
  "time_format": "%H:%M:%S",              // 时间格式
  "date_format": "%Y-%m-%d",              // 日期格式
  "show_date": true,                      // 是否显示日期
  "show_seconds": true,                   // 是否显示秒数
  "font_family": "Consolas",              // 字体
  "startup": false                        // 是否开机自启
}
```

## 🎨 主题预览

### 深色主题 (Dark)
- 背景：深灰色 (#1e1e1e)
- 时间：绿色 (#00ff00)
- 日期：灰色 (#888888)

### 浅色主题 (Light)
- 背景：白色 (#ffffff)
- 时间：深灰色 (#222222)
- 日期：灰色 (#666666)

### 蓝色主题 (Blue)
- 背景：深蓝色 (#0a1628)
- 时间：天蓝色 (#00bfff)
- 日期：钢蓝色 (#4682b4)

### 紫色主题 (Purple)
- 背景：深紫色 (#1a0a2e)
- 时间：紫色 (#bf00ff)
- 日期：暗紫色 (#8b008b)

### 绿色主题 (Green)
- 背景：深绿色 (#0a1a0a)
- 时间：春绿色 (#00ff7f)
- 日期：海绿色 (#2e8b57)

## 🔧 自定义开发

### 添加新主题

在 `desktop_clock.py` 的 `THEMES` 字典中添加：

```python
THEMES["custom"] = {
    "bg": "#your_background_color",
    "fg": "#your_foreground_color",
    "time_fg": "#your_time_color",
    "date_fg": "#your_date_color",
    "border": "#your_border_color",
}
```

### 修改时间格式

使用 Python 的 `strftime` 格式代码：

| 代码 | 说明 | 示例 |
|------|------|------|
| `%H` | 24小时制小时 | 00-23 |
| `%I` | 12小时制小时 | 01-12 |
| `%M` | 分钟 | 00-59 |
| `%S` | 秒数 | 00-59 |
| `%p` | AM/PM | AM, PM |
| `%Y` | 四位年份 | 2024 |
| `%m` | 月份 | 01-12 |
| `%d` | 日期 | 01-31 |
| `%A` | 星期全称 | Monday |
| `%a` | 星期简称 | Mon |

## 🐛 常见问题

### Q: 窗口被其他窗口遮挡怎么办？
A: 双击窗口或右键菜单选择"固定窗口"，启用置顶功能。

### Q: 如何恢复默认设置？
A: 删除配置文件 `~/.desktopclock/config.json`，重启程序即可。

### Q: 开机自启不生效？
A: 
- Windows：检查杀毒软件是否拦截了注册表修改
- macOS：检查系统偏好设置中的"登录项"
- Linux：检查 `~/.config/autostart/` 目录权限

### Q: 时间或日期显示不全怎么办？
A: 可以使用以下任一方式调整：
- 鼠标滚轮缩小字体
- 拖拽右下角 `◢` 手柄放大窗口
- 右键菜单选择 **窗口大小 → 自动适应文字**
- 右键菜单选择 **字体大小** 中的预设字号

### Q: 透明背景没有效果怎么办？
A: tkinter 版本使用的是 `-transparentcolor`，该能力在 Linux 下经常不生效。Linux 用户建议使用 Qt 透明背景增强版：

```bash
python3 -m pip install -r requirements-qt.txt
python3 desktop_clock_qt.py
```

Qt 版本使用 `WA_TranslucentBackground`，在 Linux 桌面环境下通常比 tkinter 更可靠。如果开启透明背景后看到黑底，请右键选择 **背景透明度 → 0%**，新版会使用 `rgba(r,g,b,0)` 避免透明背景被渲染成主题黑色。如果仍无效果，请确认系统没有强制禁用窗口合成/特效。

### Q: 字体显示不正常？
A: 修改配置文件中的 `font_family` 为系统已安装的字体，如：
- Windows: `Consolas`, `Courier New`, `微软雅黑`
- macOS: `Menlo`, `Monaco`, `苹方`
- Linux: `DejaVu Sans Mono`, `Noto Sans CJK SC`

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📝 更新日志

### v1.0.0 (2024-06-29)
- 初始版本发布
- 支持拖拽移动和窗口固定
- 支持 5 种预设主题
- 支持字体大小和透明度调节
- 支持开机自启（Windows/macOS/Linux）
- 支持配置持久化保存
