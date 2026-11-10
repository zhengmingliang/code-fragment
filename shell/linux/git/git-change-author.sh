#!/usr/bin/env bash
#
# git-change-author.sh
# ----------------------------------------------------------------------------
# 修改 Git 历史记录中「提交人（author）」的姓名和邮箱。
#
# 原理：使用 git filter-branch --env-filter 重写匹配的提交作者信息。
#
# 过滤 / 作用范围（可组合）：
#   * 按原作者定位：--old-name + --old-email（姓名与邮箱同时匹配才替换）
#   * 批量覆盖     ：--all   把【所有】提交的作者都改成新的
#   * 最近 N 次     ：--last N
#   * 时间范围      ：--since / --until （支持 git 可解析的任何日期格式）
#   * 指定分支      ：--branch <ref>（默认 --all）
#   * 交互式确认    ：--interactive  逐条列出候选提交，逐一 y/n 确认
#   * 列出作者      ：--list-authors  仅列出历史去重后的作者与邮箱（不修改）
#
# 注意：
#   * 这会重写提交哈希（整个历史），相当于产生一个全新历史。
#   * 执行前请确保工作区干净、并已备份（脚本自动备份到 refs/original）。
#   * 对已推送的远程仓库，重写后需 force push，请先与团队协调。
#
# 依赖：仅 git 自带命令（推荐 git 2.x）。无需 filter-repo。
# ----------------------------------------------------------------------------

set -euo pipefail

# ---------- 默认值 ----------
OLD_NAME=""
OLD_EMAIL=""
NEW_NAME=""
NEW_EMAIL=""
REPLACE_ALL=false
ALSO_COMMITTER=false
FORCE=false
INTERACTIVE=false
LAST_N=""
SINCE=""
UNTIL=""
BRANCH="--all"            # 默认重写所有分支/标签
BACKUP_REF="refs/original"
DRY_RUN=false             # 预览模式：只列出会改哪些，不实际改写
LIST_AUTHORS=false        # 仅列出历史中的作者与邮箱，不修改
LIST_LIMIT=""             # 列出作者时最多显示几位（空=全部）

# 列出当前仓库历史中的作者与邮箱（供交互式复用；不退出，可带 --limit 部分显示）
list_authors_preview() {
  local lim="${1:-}"        # 可选：最多显示几位，空=全部
  local lines total
  mapfile -t lines < <(git shortlog -sne --all | sed -E 's/^[[:space:]]*([0-9]+)[[:space:]]+(.*)$/\1\t\2/' | sort -rn)
  total=${#lines[@]}
  if [[ $total -eq 0 ]]; then
    echo "  （该仓库暂无提交记录）"
    return
  fi
  echo "------------------------------------------------------------------"
  printf '  %-7s %s\n' "提交数" "作者 <邮箱>"
  echo "------------------------------------------------------------------"
  if [[ -n "$lim" && $total -gt $lim ]]; then
    for ((i = 0; i < lim; i++)); do
      local line="${lines[$i]}"; local cnt="${line%%$'\t'*}"; local rest="${line#*$'\t'}"
      printf '  %-7s %s\n' "$cnt" "$rest"
    done
    echo "  ... 另有 $((total - lim)) 位未显示（可再次选择列出查看全部）"
  else
    for line in "${lines[@]}"; do
      local cnt="${line%%$'\t'*}"; local rest="${line#*$'\t'}"
      printf '  %-7s %s\n' "$cnt" "$rest"
    done
  fi
  echo "------------------------------------------------------------------"
  echo "  提示：复制其中一行的『姓名 <邮箱>』即可作为旧作者输入。"
}

usage() {
  cat <<EOF
用法: $0 [选项]

【目标身份（必填）】
  --new-name  <姓名>     新作者姓名
  --new-email <邮箱>     新作者邮箱

【定位要替换的作者（二选一）】
  --old-name  <姓名> + --old-email <邮箱>
                          只替换同时匹配「旧姓名 + 旧邮箱」的那位作者
  --all                  忽略匹配，把【所有】提交作者都改成新身份

【作用范围过滤（可任意组合）】
  --last <N>             仅最近 N 次提交（N 为正整数）
  --since <日期>         仅包含该日期之后的提交（git 可解析格式，如 "2024-01-01"）
  --until <日期>         仅包含该日期之前的提交
  --branch <ref>         只重写指定分支/引用（默认 --all 全部）

【行为选项】
  --also-committer       同时修改 committer（提交者）信息
  --list-authors         仅列出历史中出现的【作者与邮箱】及提交数（不修改历史）
  --limit <N>            列出作者/提交时最多显示 N 条；交互模式下较多时会先列部分
  --dry-run              预览模式：只列出「会被修改的提交」，不实际改写历史
  --interactive          交互式：逐条列出候选提交并 y/n 确认
                         交互时可用的按键： y=改本个  n=跳过  a=全部改  q=放弃退出
  --force                跳过最终确认提示，直接执行
  -h, --help             显示本帮助

示例:
  # 把 "张三 <zhangsan@old.com>" 改成 "李四 <lisi@new.com>"（精确匹配）
  $0 --old-name "张三" --old-email zhangsan@old.com \\
     --new-name "李四" --new-email lisi@new.com

  # 只改最近 5 次提交的作者，且交互式逐一确认
  $0 --all --new-name "DevTeam" --new-email dev@company.com \\
     --last 5 --interactive

  # 改成公司身份，仅限 2024 年内、当前分支的提交
  $0 --all --new-name "DevTeam" --new-email dev@company.com \\
     --since 2024-01-01 --until 2024-12-31 --branch master
EOF
}

# ---------- 解析参数 ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --old-name)       OLD_NAME="$2"; shift 2 ;;
    --old-email)      OLD_EMAIL="$2"; shift 2 ;;
    --new-name)       NEW_NAME="$2"; shift 2 ;;
    --new-email)      NEW_EMAIL="$2"; shift 2 ;;
    --all)            REPLACE_ALL=true; shift ;;
    --also-committer) ALSO_COMMITTER=true; shift ;;
    --dry-run)        DRY_RUN=true; shift ;;
    --list-authors)   LIST_AUTHORS=true; shift ;;
    --limit)          LIST_LIMIT="$2"; shift 2 ;;
    --interactive)    INTERACTIVE=true; shift ;;
    --last)           LAST_N="$2"; shift 2 ;;
    --since)          SINCE="$2"; shift 2 ;;
    --until)          UNTIL="$2"; shift 2 ;;
    --branch)         BRANCH="$2"; shift 2 ;;
    --force)          FORCE=true; shift ;;
    -h|--help)        usage; exit 0 ;;
    *) echo "未知参数: $1" >&2; usage >&2; exit 1 ;;
  esac
done

# ---------- 交互式补齐缺失参数（仅在标准终端下；非 TTY 时缺失必填项仍报错） ----------
TTY_MODE=false
[[ -t 0 ]] && TTY_MODE=true

# 列出作者模式为独立只读功能，无需补全姓名/邮箱/定位方式
if $LIST_AUTHORS; then
  : # 跳过下方补齐逻辑
elif $TTY_MODE; then
  # 1) 目标身份缺失 → 交互输入
  if [[ -z "$NEW_NAME" ]]; then
    read -r -p "请输入【新作者姓名】: " NEW_NAME
  fi
  if [[ -z "$NEW_EMAIL" ]]; then
    read -r -p "请输入【新作者邮箱】: " NEW_EMAIL
  fi
  # 2) 定位方式缺失 → 交互选择（全部替换 / 指定旧作者）
  if ! $REPLACE_ALL && [[ -z "$OLD_NAME" || -z "$OLD_EMAIL" ]]; then
    echo "请选择作者定位方式："
    echo "  a) 将所有提交的作者统一改为新身份"
    echo "  s) 仅替换指定的某位旧作者（需输入旧姓名+旧邮箱）"
    while true; do
      read -r -p "请选择 [a/s]: " loc
      case "$loc" in
        a|A) REPLACE_ALL=true; break ;;
        s|S)
          # 先询问是否列出当前项目的作者信息，方便复制准确姓名/邮箱
          while true; do
            read -r -p "是否先列出当前项目历史中的作者信息？[y/N] " show
            case "$show" in
              y|Y|yes|YES)
                echo "当前仓库历史中的作者与邮箱（按提交数降序）："
                list_authors_preview 10
                # 若较多，询问是否展开全部
                total=$(git shortlog -sne --all | wc -l)
                if [[ $total -gt 10 ]]; then
                  while true; do
                    read -r -p "是否显示全部 $total 位作者？[y/N] " all
                    case "$all" in
                      y|Y|yes|YES) list_authors_preview ""; break ;;
                      *) break ;;
                    esac
                  done
                fi
                break ;;
              n|N|"") echo "不列出，请直接输入。" ; break ;;
              *) echo "  请输入 y 或 n" ;;
            esac
          done
          read -r -p "请输入【旧作者姓名】: " OLD_NAME
          read -r -p "请输入【旧作者邮箱】: " OLD_EMAIL
          break ;;
        *) echo "  请输入 a 或 s" ;;
      esac
    done
  fi
fi

# ---------- 参数校验（非 TTY 下缺失必填项仍报错退出） ----------
# 仅「列出作者」模式可豁免 new-name/email 必填
if ! $LIST_AUTHORS && [[ -z "$NEW_NAME" || -z "$NEW_EMAIL" ]]; then
  echo "错误：必须提供 --new-name 和 --new-email（交互式终端运行可留空，由脚本提示输入）。" >&2
  exit 1
fi
if ! $REPLACE_ALL && ! $LIST_AUTHORS; then
  if [[ -z "$OLD_NAME" || -z "$OLD_EMAIL" ]]; then
    echo "错误：未使用 --all 时，必须提供 --old-name 和 --old-email，或交互式选择定位方式。" >&2
    exit 1
  fi
fi
if [[ -n "$LAST_N" ]]; then
  if ! [[ "$LAST_N" =~ ^[1-9][0-9]*$ ]]; then
    echo "错误：--last 必须是正整数。" >&2
    exit 1
  fi
fi

# ---------- 终端直接运行时，默认进入交互式逐条确认 ----------
# 非 TTY（管道/CI）或显式 --force / --dry-run 时不自动开启，避免卡死或重复。
if $TTY_MODE && ! $FORCE && ! $DRY_RUN; then
  INTERACTIVE=true
fi

# ---------- 环境校验 ----------
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "错误：当前目录不是 Git 仓库。" >&2
  exit 1
fi

# ---------- 列出作者模式（独立功能，打印后退出） ----------
# 逻辑：用 git shortlog 汇总每个 author 的提交数并去重，按提交数降序排列。
#   * 未指定 --limit：列出全部。
#   * 指定 --limit N：只列前 N 位，并提示其余数量（交互模式下可再展开全部）。
if $LIST_AUTHORS; then
  # 校验 --limit 合法性
  if [[ -n "$LIST_LIMIT" ]]; then
    if ! [[ "$LIST_LIMIT" =~ ^[1-9][0-9]*$ ]]; then
      echo "错误：--limit 必须是正整数。" >&2
      exit 1
    fi
  fi

  # 生成「提交数<TAB>姓名 <邮箱>」并按提交数降序排序
  mapfile -t AUTHOR_LINES < <(git shortlog -sne --all | sed -E 's/^[[:space:]]*([0-9]+)[[:space:]]+(.*)$/\1\t\2/' | sort -rn)
  TOTAL=${#AUTHOR_LINES[@]}

  if [[ $TOTAL -eq 0 ]]; then
    echo "该仓库暂无提交记录。"
    exit 0
  fi

  echo "=================================================================="
  echo "当前仓库历史中的作者与邮箱（按提交数降序，共 $TOTAL 位）："
  echo "=================================================================="
  printf '%-8s %s\n' "提交数" "作者 <邮箱>"
  echo "------------------------------------------------------------------"

  if [[ -n "$LIST_LIMIT" && $TOTAL -gt $LIST_LIMIT ]]; then
    # 只列前 LIMIT 位
    for ((i = 0; i < LIST_LIMIT; i++)); do
      line="${AUTHOR_LINES[$i]}"
      cnt="${line%%$'\t'*}"; rest="${line#*$'\t'}"
      printf '%-8s %s\n' "$cnt" "$rest"
    done
    echo "------------------------------------------------------------------"
    echo "（仅显示前 $LIST_LIMIT 位，另有 $((TOTAL - LIST_LIMIT)) 位未列出）"

    # 交互模式下，询问是否展开剩余全部
    if $TTY_MODE; then
      while true; do
        read -r -p "是否显示全部 $TOTAL 位作者？[y/N] " ext
        case "$ext" in
          y|Y|yes|YES)
            echo "------------------------------------------------------------------"
            for ((i = LIST_LIMIT; i < TOTAL; i++)); do
              line="${AUTHOR_LINES[$i]}"
              cnt="${line%%$'\t'*}"; rest="${line#*$'\t'}"
              printf '%-8s %s\n' "$cnt" "$rest"
            done
            break ;;
          *) break ;;
        esac
      done
    fi
  else
    # 全部列出
    for line in "${AUTHOR_LINES[@]}"; do
      cnt="${line%%$'\t'*}"; rest="${line#*$'\t'}"
      printf '%-8s %s\n' "$cnt" "$rest"
    done
  fi
  echo "------------------------------------------------------------------"
  echo "提示：复制其中一行的『姓名 <邮箱>』可作为 --old-name / --old-email 的参考。"
  exit 0
fi

# 仅检查「已跟踪文件」是否有未提交改动（含暂存区）。
# 未跟踪文件（未纳入版本管理）不影响历史重写，只做提示，不阻塞。
UNTRACKED=$(git ls-files --others --exclude-standard 2>/dev/null | head -n 50)
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
  echo "错误：存在未提交的【已跟踪文件】改动，请先 commit 或 git stash 后再执行。" >&2
  echo "（注意：git stash 默认不保存未跟踪文件，可用 git stash -u 一并暂存）" >&2
  exit 1
fi
if [[ -n "$UNTRACKED" ]]; then
  echo "提示：检测到未纳入版本管理的文件（不会被本次历史重写影响），例如："
  echo "$UNTRACKED" | sed 's/^/    /'
  echo "如需一并暂存可使用 git stash -u。"
  echo "------------------------------------------------------------------"
fi

# ---------- 构造 rev-list 作用范围参数 ----------
REV_ARGS=()
if [[ -n "$LAST_N" ]]; then REV_ARGS+=( --max-count="$LAST_N" ); fi
if [[ -n "$SINCE"  ]]; then REV_ARGS+=( --since="$SINCE" ); fi
if [[ -n "$UNTIL"  ]]; then REV_ARGS+=( --until="$UNTIL" ); fi

# ---------- 计算候选提交（满足范围 + 姓名/邮箱匹配） ----------
# 输出：每行一个完整 40 位提交哈希（由新到旧）
if $REPLACE_ALL; then
  mapfile -t RAW_CANDIDATES < <(git rev-list "${REV_ARGS[@]+"${REV_ARGS[@]}"}" $BRANCH)
else
  RAW_CANDIDATES=()
  while IFS= read -r c; do
    [[ -z "$c" ]] && continue
    an=$(git log -1 --format='%an' "$c")
    ae=$(git log -1 --format='%ae' "$c")
    if [[ "$an" = "$OLD_NAME" && "$ae" = "$OLD_EMAIL" ]]; then
      RAW_CANDIDATES+=("$c")
    fi
  done < <(git rev-list "${REV_ARGS[@]+"${REV_ARGS[@]}"}" $BRANCH)
fi

if [[ ${#RAW_CANDIDATES[@]} -eq 0 ]]; then
  echo "没有找到符合条件的提交，无需修改。脚本结束。"
  exit 0
fi

# ---------- 交互模式下，先列出历史作者概览（便于定位要替换的作者） ----------
if $INTERACTIVE; then
  mapfile -t SHORTLOG < <(git shortlog -sne --all | sed -E 's/^[[:space:]]*([0-9]+)[[:space:]]+(.*)$/\1\t\2/' | sort -rn)
  STOTAL=${#SHORTLOG[@]}
  echo "=================================================================="
  echo "当前历史中的作者概览（共 $STOTAL 位），供参考定位："
  echo "------------------------------------------------------------------"
  # 较多时只列前 10 位，提示可用 --limit / --list-authors 展开
  SHOW=10
  if [[ -n "$LIST_LIMIT" ]]; then SHOW=$LIST_LIMIT; fi
  if [[ $STOTAL -gt $SHOW ]]; then
    for ((i = 0; i < SHOW; i++)); do
      line="${SHORTLOG[$i]}"; cnt="${line%%$'\t'*}"; rest="${line#*$'\t'}"
      printf '  %-7s %s\n' "$cnt" "$rest"
    done
    echo "  ... 另有 $((STOTAL - SHOW)) 位未显示（可加 --limit N 或 --list-authors 查看全部）"
  else
    for line in "${SHORTLOG[@]}"; do
      cnt="${line%%$'\t'*}"; rest="${line#*$'\t'}"
      printf '  %-7s %s\n' "$cnt" "$rest"
    done
  fi
  echo "=================================================================="
fi

# ---------- 交互式确认（构建最终允许列表 ALLOW） ----------
ALLOW=()
if $INTERACTIVE; then
  echo "=================================================================="
  echo "共找到 ${#RAW_CANDIDATES[@]} 个候选提交，将逐条确认。"
  echo "按键： y=修改本个   n=跳过本个   a=修改剩余全部   q=放弃并退出"
  echo "=================================================================="
  REMAINING=${#RAW_CANDIDATES[@]}
  for c in "${RAW_CANDIDATES[@]}"; do
    REMAINING=$((REMAINING - 1))
    subj=$(git log -1 --format='%s' "$c")
    an=$(git log -1 --format='%an' "$c")
    ae=$(git log -1 --format='%ae' "$c")
    adate=$(git log -1 --format='%ci' "$c")
    printf '\n[%s…] %s\n  作者: %s <%s>\n  时间: %s\n  说明: %s\n' \
      "${c:0:8}" "$c" "$an" "$ae" "$adate" "$subj"
    while true; do
      if ! read -r -p "  是否修改此提交？(y/n/a/q，剩 $REMAINING) " ans; then
        echo ""; echo "输入结束（EOF），已放弃，未做任何修改。"
        exit 0
      fi
      case "$ans" in
        y|Y) ALLOW+=("$c"); break ;;
        n|N) break ;;
        a|A) ALLOW+=("$c"); for r in "${RAW_CANDIDATES[@]:${#ALLOW[@]}}"; do ALLOW+=("$r"); done; break 2 ;;
        q|Q) echo "已放弃，未做任何修改。"; exit 0 ;;
        *) echo "  请输入 y / n / a / q" ;;
      esac
    done
  done
else
  ALLOW=("${RAW_CANDIDATES[@]}")
fi

if [[ ${#ALLOW[@]} -eq 0 ]]; then
  echo "没有选择任何提交进行修改，脚本结束。"
  exit 0
fi

# ---------- 把允许列表写入临时文件（env-filter 用 grep -qxF 精确匹配） ----------
ALLOW_FILE="$(mktemp)"
trap 'rm -f "$ALLOW_FILE"' EXIT
printf '%s\n' "${ALLOW[@]}" > "$ALLOW_FILE"

# ---------- 组装 env-filter 脚本 ----------
ENV_FILTER="
DO_REWRITE=0
if printf '%s\n' \"\$GIT_COMMIT\" | grep -qxF -f '$ALLOW_FILE'; then
  DO_REWRITE=1
fi
if [ \"\$DO_REWRITE\" = \"1\" ]; then
  GIT_AUTHOR_NAME='$NEW_NAME'
  GIT_AUTHOR_EMAIL='$NEW_EMAIL'
"

if $ALSO_COMMITTER; then
  ENV_FILTER="$ENV_FILTER
  GIT_COMMITTER_NAME='$NEW_NAME'
  GIT_COMMITTER_EMAIL='$NEW_EMAIL'
"
fi

ENV_FILTER="$ENV_FILTER
fi
"

# ---------- 输出计划 ----------
echo "=================================================================="
echo "即将重写 Git 历史中的作者信息："
$REPLACE_ALL && echo "  模式        : 替换【全部】匹配的提交" || echo "  原作 者     : $OLD_NAME <$OLD_EMAIL>"
echo "  新作 者     : $NEW_NAME <$NEW_EMAIL>"
$ALSO_COMMITTER && echo "  同时修改    : committer（提交者）"
[[ -n "$LAST_N" ]] && echo "  最近 N 次   : $LAST_N"
[[ -n "$SINCE"  ]] && echo "  起始时间    : $SINCE"
[[ -n "$UNTIL"  ]] && echo "  截止时间    : $UNTIL"
echo "  重写范围    : $BRANCH"
echo "  候选提交数  : ${#RAW_CANDIDATES[@]}"
echo "  本次将修改  : ${#ALLOW[@]} 个提交"
echo "  自动备份到  : $BACKUP_REF"
echo "=================================================================="

# ---------- 预览模式：只展示会被修改的提交，不实际改写 ----------
if $DRY_RUN; then
  echo ""
  echo "【预览】以下 ${#ALLOW[@]} 个提交将会被改写（不执行实际修改）："
  echo "  旧作者/提交者 -> 新: $NEW_NAME <$NEW_EMAIL>"
  echo "------------------------------------------------------------------"
  printf '%-42s %-22s %s\n' "提交哈希" "当前作者 <邮箱>" "提交说明"
  echo "------------------------------------------------------------------"
  for c in "${ALLOW[@]}"; do
    an=$(git log -1 --format='%an' "$c")
    ae=$(git log -1 --format='%ae' "$c")
    subj=$(git log -1 --format='%s' "$c")
    printf '%-42s %-22s %s\n' "${c}" "$an <$ae>" "$subj"
  done
  echo "------------------------------------------------------------------"
  echo "预览结束，未对仓库做任何修改。去掉 --dry-run 后可正式执行。"
  exit 0
fi

if ! $FORCE; then
  read -r -p "确认执行？此操作会重写历史哈希！[y/N] " ans
  case "$ans" in
    y|Y|yes|YES) ;;
    *) echo "已取消。"; exit 0 ;;
  esac
fi

# ---------- 执行重写 ----------
echo ">>> 开始重写历史..."
git for-each-ref --format='%(refname)' "$BACKUP_REF" | while read -r r; do
  git update-ref -d "$r"
done

# 注意：filter-branch 的 "--" 之后是 rev-list 的「修订范围」参数（stdin 模式），
# 不支持 --max-count/--since/--until 等选项。因此这里只传分支/引用名，
# 让 filter-branch 遍历整条链（父哈希连锁变化必须重写整链），
# 真正的「最近 N 次 / 时间 / 作者」过滤已由 env-filter 的 case 精确控制。
FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch \
  --force \
  --env-filter "$ENV_FILTER" \
  --tag-name-filter cat \
  -- $BRANCH

echo ">>> 重写完成。"
echo ">>> 若需彻底清除旧对象并回收空间，可运行："
echo "      git reflog expire --expire=now --all && git gc --prune=now"
echo ">>> 如需推送到远程（会覆盖历史，请谨慎）："
echo "      git push --force --tags origin '$BRANCH'"
echo ">>> 如需回滚本次重写，可执行："
echo "      git reset --hard $BACKUP_REF/refs/heads/<分支名>"
