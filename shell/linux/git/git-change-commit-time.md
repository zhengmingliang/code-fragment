# git-change-commit-time.sh

用于修改 Git 提交时间（作者时间与提交者时间）的命令行工具，支持交互模式和参数模式。

## 功能说明

修改一个或多个历史提交的时间戳。对最新提交使用 `git commit --amend`，对其它提交使用 `git filter-branch --env-filter`。

支持两种时间格式：

- `YYYY-MM-DD`：仅替换日期，原时分秒保留。
- `YYYY-MM-DD HH:MM:SS`：完整替换。

## 环境要求

- `bash` 4+
- `git`
- 当前目录必须在 Git 仓库内
- 工作区与暂存区需保持干净（脚本会给出提示并要求确认）

## 用法

```bash
git-change-commit-time.sh [选项]
```

### 选项

| 选项 | 说明 |
| --- | --- |
| `-c <序号>` | 要修改的提交序号，必填或留空进入交互输入 |
| `-d <时间>` | 新的时间，可选 |
| `-h` | 打印帮助 |

序号支持以下写法：

- 单个：`3`
- 多个：`1,3,5`
- 连续区间：`2-5`
- 混合：`1,3-5`

序号对应 `git log` 列出的最近 20 条提交。

### 时间格式

| 格式 | 含义 |
| --- | --- |
| `YYYY-MM-DD` | 仅替换日期，原时分秒保留 |
| `YYYY-MM-DD HH:MM:SS` | 完整替换作者时间与提交者时间 |

## 示例

进入交互模式，按提示选择提交并输入新时间：

```bash
./git-change-commit-time.sh
```

仅修改第 3 条提交的日期，时分秒不变：

```bash
./git-change-commit-time.sh -c 3 -d "2024-01-15"
```

修改第 1、3、5 条提交的完整时间：

```bash
./git-change-commit-time.sh -c 1,3,5 -d "2024-01-15 10:30:00"
```

修改第 2 到第 5 条提交的日期：

```bash
./git-change-commit-time.sh -c 2-5 -d "2024-01-15"
```

混合写法：修改第 1 条和第 3 到第 5 条：

```bash
./git-change-commit-time.sh -c 1,3-5 -d "2024-01-15"
```

## 执行流程

1. 检查 `git` 是否存在以及当前目录是否为 Git 仓库。
2. 如果有未提交变更，给出提示并询问是否继续。
3. 加载最近 20 条提交列表展示。
4. 解析 `-c` 或交互输入的序号。
5. 解析 `-d` 或交互输入的新时间。
6. 打印将受影响的提交与新时间，要求确认。
7. 执行修改：
   - 仅有 1 条且是 `HEAD`：`git commit --amend`
   - 其它情况：`git filter-branch --env-filter`
8. 展示修改后的最近 10 条提交。

## 修改后推送

修改历史提交会改变其哈希值，已推送到远程的分支需强制推送：

```bash
git push --force-with-lease
```

强制推送前请确认：

- 本地分支已是最新。
- 团队成员已同步，或确认不会与他人正在进行的提交产生冲突。
- 远程默认分支有适当保护限制时，需先解除。

强制推送会丢弃远程上对应的旧提交，谨慎操作。

## 常见问题

执行 `filter-branch` 失败，工作区或暂存区有未提交变更。
先提交或 `git stash`，再重试。

`filter-branch` 会留下 `refs/original/` 备份引用，确认无误后可手动清理：

```bash
git for-each-ref --format='delete %(refname)' refs/original | git update-ref --stdin
git reflog expire --expire=now --all
git gc --prune=now
```

日期被认为不合法。
脚本使用 `date -d` 校验，超出系统时间范围或写法不规范时会被拒绝，确认格式后重试。

修改后看不到变化。
检查是否只筛选到 `git log` 默认范围，确认 `git log -10` 中对应提交的日期已更新。
