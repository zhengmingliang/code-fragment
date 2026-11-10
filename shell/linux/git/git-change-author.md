# git-change-author.sh

用于修改 Git 历史提交中「提交人（author）」姓名与邮箱的命令行工具，支持交互模式和参数模式。

## 功能说明

使用 `git filter-branch --env-filter` 重写匹配提交的作者信息。支持以下定位与过滤方式，可任意组合：

- **按原作者定位**：旧姓名与旧邮箱同时匹配才替换（精确匹配，避免误伤同名作者）。
- **批量覆盖**：把所有提交的作者统一改成新身份。
- **最近 N 次**：仅最近 N 次提交。
- **时间范围**：仅某个日期之后 / 之前的提交（支持 git 可解析的任何日期格式）。
- **指定分支**：只重写指定分支 / 引用（默认重写所有分支和标签）。
- **交互式确认**：逐条列出候选提交，逐一 y/n 确认。
- **列出作者**：仅列出历史中去重后的作者与邮箱及提交数，不修改任何内容。

可选同时修改 committer（提交者）信息。

## 环境要求

- `bash` 4+
- `git`（仅使用 git 自带命令，无需安装 filter-repo）
- 当前目录必须在 Git 仓库内
- 工作区已跟踪文件需保持干净（有未提交改动会直接报错退出；未跟踪文件仅提示不阻塞）

## 用法

```bash
git-change-author.sh [选项]
```

### 选项

| 选项 | 说明 |
| --- | --- |
| `--new-name <姓名>` | 新作者姓名，必填（交互式终端可留空，由脚本提示输入） |
| `--new-email <邮箱>` | 新作者邮箱，必填（同上） |
| `--old-name <姓名>` | 旧作者姓名，与 `--old-email` 配合使用，二者同时匹配才替换 |
| `--old-email <邮箱>` | 旧作者邮箱，与 `--old-name` 配合使用 |
| `--all` | 忽略匹配，把所有提交作者都改成新身份 |
| `--last <N>` | 仅最近 N 次提交（N 为正整数） |
| `--since <日期>` | 仅包含该日期之后的提交（如 `2024-01-01`） |
| `--until <日期>` | 仅包含该日期之前的提交 |
| `--branch <ref>` | 只重写指定分支 / 引用（默认 `--all` 全部） |
| `--also-committer` | 同时修改 committer（提交者）信息 |
| `--list-authors` | 仅列出历史中的作者与邮箱及提交数，不修改历史 |
| `--limit <N>` | 列出作者时最多显示 N 条（空 = 全部） |
| `--dry-run` | 预览模式：只列出会被修改的提交，不实际改写 |
| `--interactive` | 交互式：逐条列出候选提交并 y/n 确认 |
| `--force` | 跳过最终确认提示，直接执行 |
| `-h`, `--help` | 显示帮助 |

定位方式二选一：`--old-name` + `--old-email`（精确匹配某位作者），或 `--all`（全部替换）。两者都未提供时，交互式终端会提示选择；非交互环境直接报错。

在终端直接运行（不带 `--force` / `--dry-run`）时，脚本默认进入交互模式：先补齐缺失的参数，再逐条确认候选提交。非 TTY（管道 / CI）环境不会自动开启，避免卡死。

### 交互模式按键

| 按键 | 含义 |
| --- | --- |
| `y` | 修改当前提交 |
| `n` | 跳过当前提交 |
| `a` | 修改剩余全部提交 |
| `q` | 放弃并退出（未做任何修改） |

交互过程中选择「指定旧作者」时，可先让脚本列出当前项目历史中的作者与邮箱（按提交数降序），直接复制某行的『姓名 <邮箱>』作为输入，避免手抖打错。

## 示例

进入交互模式，按提示补齐参数并逐条确认：

```bash
./git-change-author.sh
```

把 `张三 <zhangsan@old.com>` 改成 `李四 <lisi@new.com>`（精确匹配）：

```bash
./git-change-author.sh --old-name "张三" --old-email zhangsan@old.com \
   --new-name "李四" --new-email lisi@new.com
```

只改最近 5 次提交的作者，且交互式逐一确认：

```bash
./git-change-author.sh --all --new-name "DevTeam" --new-email dev@company.com \
   --last 5 --interactive
```

改成公司身份，仅限 2024 年内、master 分支的提交，同时修改提交者信息：

```bash
./git-change-author.sh --all --new-name "DevTeam" --new-email dev@company.com \
   --since 2024-01-01 --until 2024-12-31 --branch master --also-committer
```

先看看历史里有哪些作者（不修改任何内容）：

```bash
./git-change-author.sh --list-authors
```

预览哪些提交会被改写（不实际修改）：

```bash
./git-change-author.sh --old-name "张三" --old-email zhangsan@old.com \
   --new-name "李四" --new-email lisi@new.com --dry-run
```

## 执行流程

1. 解析参数；交互式终端下补齐缺失的新身份与定位方式。
2. 校验：必填项、`--last` / `--limit` 为正整数、当前目录是 Git 仓库。
3. 检查已跟踪文件是否有未提交改动，有则报错退出。
4. 按定位方式 + 范围过滤计算出候选提交列表。
5. 交互模式下先展示历史作者概览，再逐条确认候选提交（y/n/a/q），生成最终允许列表。
6. 打印执行计划（模式、新旧身份、范围、候选数、本次修改数、备份位置）；`--dry-run` 到此为止，列出将被改写的提交明细后退出。
7. 最终确认（`--force` 跳过）后执行 `git filter-branch --env-filter` 重写。
8. 打印后续操作提示（清理、强推、回滚）。

注意：由于父提交哈希会连锁变化，`filter-branch` 始终遍历整条提交链；「最近 N 次 / 时间 / 作者」的过滤由 env-filter 中的精确哈希允许列表控制，未命中的提交内容保持不变（仅哈希因父链变化而改变）。标签通过 `--tag-name-filter cat` 一并重写。

## 修改后推送

重写会改变提交哈希（整个历史），已推送到远程的分支需强制推送：

```bash
git push --force --tags origin <分支名>
```

强制推送前请确认：

- 本地分支已是最新。
- 团队成员已同步，或确认不会与他人正在进行的提交产生冲突。
- 远程默认分支有保护限制时，需先解除。

## 回滚与清理

脚本执行前会自动把旧历史备份到 `refs/original`（并清掉上一次遗留的备份）。确认重写无误后，如需彻底清除旧对象并回收空间：

```bash
git for-each-ref --format='delete %(refname)' refs/original | git update-ref --stdin
git reflog expire --expire=now --all
git gc --prune=now
```

如需回滚本次重写：

```bash
git reset --hard refs/original/refs/heads/<分支名>
```

## 常见问题

提示存在未提交的已跟踪文件改动。
先 commit 或 `git stash` 后再执行。注意 `git stash` 默认不保存未跟踪文件，可用 `git stash -u` 一并暂存。

没有找到符合条件的提交。
检查旧姓名与邮箱是否与历史完全一致（空格、大小写都算差异），可先用 `--list-authors` 查看准确值再复制。

只想改某一位作者，却把别人的提交也改了。
未使用 `--all` 时脚本按「旧姓名 + 旧邮箱」同时匹配定位，只会替换完全一致的那位作者；若误用了 `--all`，可通过 `refs/original` 备份回滚后重做。

只想看看会改哪些提交，不想动仓库。
加 `--dry-run`，脚本只列出将被改写的提交明细，不做任何修改。

`--branch` 与 `--last` 等范围选项是什么关系？
范围选项（`--last` / `--since` / `--until`）筛选候选提交，`--branch` 决定重写遍历哪些引用，默认 `--all`（所有分支和标签）。
