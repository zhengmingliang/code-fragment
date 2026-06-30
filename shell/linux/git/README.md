# Git 提交时间修改工具

`git-change-commit-time.sh` 用于修改一个或多个 Git 提交的时间戳，支持交互模式和命令行模式。

两种时间格式：

- `YYYY-MM-DD`：仅替换日期，原时分秒保留。
- `YYYY-MM-DD HH:MM:SS`：完整替换作者时间与提交者时间。

最简单的用法是直接运行脚本，按提示选择提交并输入新时间：

```bash
./git-change-commit-time.sh
```

## 详细文档

- [脚本说明](git-change-commit-time.md)：选项、序号写法、示例、执行流程、推送注意事项、常见问题
- [脚本源文件](git-change-commit-time.sh)