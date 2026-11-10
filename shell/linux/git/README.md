# Git 工具脚本

| 脚本 | 用途 |
| --- | --- |
| `git-change-commit-time.sh` | 修改一个或多个 Git 提交的时间戳（绝对时间 / 相对偏移），支持交互模式和命令行模式 |
| `git-purge-history.sh` | 交互式地从全部历史中移除指定的文件 / 目录（密钥、大文件等），优先 `git-filter-repo`，回退 `filter-branch` |
| `git-change-author.sh` | 修改 Git 历史提交的作者姓名与邮箱，支持按旧作者精确匹配 / 全量替换、时间范围过滤、交互式逐条确认与预览模式 |

## 快速开始

```bash
# 修改提交时间：直接运行脚本，按提示选择提交并输入新时间
./git-change-commit-time.sh

# 清理历史：直接运行脚本进入交互菜单
./git-purge-history.sh

# 修改作者：直接运行脚本，按提示补齐参数并逐条确认
./git-change-author.sh
```

## 详细文档

- [修改提交时间说明](git-change-commit-time.md)：选项、序号写法、示例、执行流程、推送注意事项、常见问题
- [历史清理说明](git-purge-history.md)：功能特性、菜单、示例、执行流程、备份恢复、执行后必做事项、常见问题
- [修改作者说明](git-change-author.md)：选项、交互按键、示例、执行流程、回滚清理、常见问题
