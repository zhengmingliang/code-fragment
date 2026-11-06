#!/usr/bin/env bash
#
# git-purge-history.sh
# 交互式地从 Git 全部历史中移除指定的文件 / 目录（密钥、大文件等），
# 其余文件的提交历史保持不变。
#
# 用法:
#   ./git-purge-history.sh                 # 在仓库内运行，进入交互菜单
#   ./git-purge-history.sh .env secrets/   # 预先指定要移除的路径
#
# 优先使用 git-filter-repo（推荐: pip install git-filter-repo），
# 未安装时自动回退到 git filter-branch。
#
set -o pipefail

if [ -t 1 ]; then
  R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; B=$'\033[36m'; N=$'\033[0m'
else
  R=''; G=''; Y=''; B=''; N=''
fi
info() { printf '%s[i]%s %s\n' "$B" "$N" "$*"; }
ok()   { printf '%s[✓]%s %s\n' "$G" "$N" "$*"; }
warn() { printf '%s[!]%s %s\n' "$Y" "$N" "$*" >&2; }
die()  { printf '%s[x]%s %s\n' "$R" "$N" "$*" >&2; exit 1; }

usage() {
  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}
case "${1:-}" in -h|--help) usage ;; esac

PATHS=()
LIST_NAMES=()
LIST_LABELS=()

# ---------- 基础检查 ----------
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "当前目录不在 Git 仓库内"
TOP=$(git rev-parse --show-toplevel) || die "无法定位仓库根目录"
cd "$TOP" || die "无法进入 $TOP"
git rev-parse --verify HEAD >/dev/null 2>&1 || die "仓库还没有任何提交"

if git filter-repo --version >/dev/null 2>&1; then
  HAS_FR=1
else
  HAS_FR=0
fi

# ---------- 工具函数 ----------
is_glob() { case "$1" in *[\*\?\[]*) return 0 ;; *) return 1 ;; esac; }

# 生成 git pathspec（用于预览/校验）
spec_of() {
  if is_glob "$1"; then printf ':(glob)%s' "$1"; else printf ':(literal)%s' "$1"; fi
}

human() {
  awk -v s="$1" 'BEGIN{split("B KB MB GB TB",u," ");i=1;while(s>=1024&&i<5){s/=1024;i++}printf "%.1f%s",s,u[i]}'
}

add_path() {
  local p="$1" x
  p="${p#"${p%%[![:space:]]*}"}"   # 去前导空白
  p="${p%"${p##*[![:space:]]}"}"   # 去尾部空白
  p="${p#./}"
  [ -z "$p" ] && return
  for x in "${PATHS[@]}"; do
    [ "$x" = "$p" ] && { warn "已存在: $p"; return; }
  done
  PATHS+=("$p")
  ok "已添加: $p"
}

show_paths() {
  if [ ${#PATHS[@]} -eq 0 ]; then
    info "当前未选择任何路径"
    return
  fi
  info "待移除的路径（共 ${#PATHS[@]} 项）:"
  local i
  for i in "${!PATHS[@]}"; do
    printf '   %2d) %s%s\n' "$((i+1))" "${PATHS[$i]}" "$(is_glob "${PATHS[$i]}" && echo '   (通配符)')"
  done
}

# 从 LIST_NAMES / LIST_LABELS 中让用户按编号挑选
pick_from_list() {
  local i sel
  if [ ${#LIST_NAMES[@]} -eq 0 ]; then
    warn "没有找到结果"
    return
  fi
  for i in "${!LIST_NAMES[@]}"; do
    printf '  %3d) %s%s\n' "$((i+1))" "${LIST_LABELS[$i]}" "${LIST_NAMES[$i]}"
  done
  read -r -p "输入要加入移除列表的编号（空格分隔，如 1 3 5；a=全部；回车跳过）: " sel
  [ -z "$sel" ] && return
  if [ "$sel" = "a" ] || [ "$sel" = "A" ]; then
    for i in "${!LIST_NAMES[@]}"; do add_path "${LIST_NAMES[$i]}"; done
    return
  fi
  for i in $sel; do
    case "$i" in ''|*[!0-9]*) continue ;; esac
    if [ "$i" -ge 1 ] && [ "$i" -le ${#LIST_NAMES[@]} ]; then
      add_path "${LIST_NAMES[$((i-1))]}"
    fi
  done
}

# ---------- 菜单功能 ----------
scan_large() {
  local n size name
  read -r -p "列出历史中体积最大的前几个文件? [20] " n
  n=${n:-20}
  case "$n" in ''|*[!0-9]*) n=20 ;; esac
  info "正在扫描所有分支/标签的历史对象（大仓库可能较慢）..."
  LIST_NAMES=(); LIST_LABELS=()
  while IFS=$'\t' read -r size name; do
    [ -z "$name" ] && continue
    LIST_NAMES+=("$name")
    LIST_LABELS+=("$(printf '%9s  ' "$(human "$size")")")
  done < <(
    git rev-list --objects --all \
      | git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)' \
      | sed -n 's/^blob \([0-9][0-9]*\) /\1\t/p' \
      | awk -F'\t' '$2 != ""' \
      | sort -t$'\t' -k1,1nr \
      | awk -F'\t' '!seen[$2]++' \
      | head -n "$n"
  )
  pick_from_list
}

search_names() {
  local kw name
  read -r -p "输入文件名关键字（不区分大小写，如 .env / id_rsa / .pem）: " kw
  [ -z "$kw" ] && return
  info "正在搜索历史中出现过的文件路径..."
  LIST_NAMES=(); LIST_LABELS=()
  while IFS= read -r name; do
    [ -z "$name" ] && continue
    LIST_NAMES+=("$name"); LIST_LABELS+=("")
  done < <(
    git log --all --name-only --pretty=format: 2>/dev/null \
      | awk 'NF' | sort -u | grep -i -F -- "$kw" | head -n 200
  )
  pick_from_list
}

manual_input() {
  local line
  info "逐行输入文件或目录（相对仓库根目录），支持通配符如 'config/*.key'；空行结束。"
  while true; do
    read -r -p "  路径> " line
    [ -z "$line" ] && break
    add_path "$line"
  done
}

edit_paths() {
  show_paths
  [ ${#PATHS[@]} -eq 0 ] && return
  local sel i new=()
  read -r -p "输入要删除的编号（空格分隔），c=清空全部，回车返回: " sel
  [ -z "$sel" ] && return
  if [ "$sel" = "c" ] || [ "$sel" = "C" ]; then PATHS=(); ok "已清空"; return; fi
  for i in "${!PATHS[@]}"; do
    local drop=0 s
    for s in $sel; do [ "$s" = "$((i+1))" ] && drop=1; done
    [ $drop -eq 0 ] && new+=("${PATHS[$i]}")
  done
  PATHS=("${new[@]}")
  ok "已更新"
}

preview() {
  if [ ${#PATHS[@]} -eq 0 ]; then warn "尚未选择任何路径"; return 1; fi
  local total p spec c
  total=$(git rev-list --all --count)
  info "仓库所有引用共 $total 个提交；各路径涉及的提交数:"
  for p in "${PATHS[@]}"; do
    spec=$(spec_of "$p")
    c=$(git rev-list --all --count -- "$spec" 2>/dev/null || echo 0)
    if git ls-files --error-unmatch -- "$spec" >/dev/null 2>&1; then
      printf '   %-40s 涉及 %s 个提交  %s[当前仍被跟踪，重写后工作区文件会被删除]%s\n' "$p" "$c" "$Y" "$N"
    else
      printf '   %-40s 涉及 %s 个提交\n' "$p" "$c"
    fi
    if [ "$c" = "0" ]; then warn "  └ 历史中没有找到 '$p'，请检查路径是否正确（区分大小写、相对仓库根目录）"; fi
  done
}

# ---------- 执行重写 ----------
run_filter_repo() {
  local args=() p
  for p in "${PATHS[@]}"; do
    if is_glob "$p"; then args+=(--path-glob "$p"); else args+=(--path "$p"); fi
  done
  git filter-repo --force --invert-paths "${args[@]}"
}

run_filter_branch() {
  local quoted="" p
  for p in "${PATHS[@]}"; do quoted+=" $(printf '%q' "$p")"; done
  export FILTER_BRANCH_SQUELCH_WARNING=1
  git filter-branch --force \
    --index-filter "git rm -r -q --cached --ignore-unmatch --${quoted}" \
    --prune-empty --tag-name-filter cat -- --all || return 1
  info "清理旧对象（refs/original、reflog、gc）..."
  rm -rf .git/refs/original
  git reflog expire --expire=now --all
  git gc --prune=now --aggressive -q
}

run_purge() {
  [ ${#PATHS[@]} -eq 0 ] && { warn "尚未选择任何路径"; return 1; }

  if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    warn "工作区有未提交的修改，请先提交或 stash 后再运行。"
    return 1
  fi

  show_paths
  preview
  echo
  if [ $HAS_FR -eq 1 ]; then
    info "将使用: git filter-repo（推荐方式）"
  else
    warn "未检测到 git-filter-repo，将回退到 git filter-branch（较慢）。可 pip install git-filter-repo 后重试。"
  fi
  warn "此操作会【重写全部提交历史】，所有受影响提交的哈希都会改变；不可逆（但会先自动备份）。"

  # 备份
  local ts base bundle keep
  ts=$(date +%Y%m%d-%H%M%S)
  base="$(dirname "$TOP")/$(basename "$TOP")"
  bundle="${base}-backup-${ts}.bundle"
  keep="${base}-keep-${ts}.tar"

  local ans
  read -r -p "输入 yes 确认继续（其他任意输入取消）: " ans
  [ "$ans" = "yes" ] || { info "已取消"; return 1; }

  git bundle create "$bundle" --all >/dev/null 2>&1 || { warn "创建备份 bundle 失败，已中止"; return 1; }
  ok "完整备份: $bundle   (恢复: git clone '$bundle' restored-repo)"

  # 备份当前仍被跟踪的目标文件（重写后工作区会删除它们）
  local existing=() p
  for p in "${PATHS[@]}"; do
    if ! is_glob "$p" && [ -e "$p" ] && git ls-files --error-unmatch -- "$(spec_of "$p")" >/dev/null 2>&1; then
      existing+=("$p")
    fi
  done
  if [ ${#existing[@]} -gt 0 ]; then
    if tar -cf "$keep" -- "${existing[@]}" 2>/dev/null; then
      ok "当前版本的目标文件已另存: $keep"
    fi
  fi

  # 记录远程（filter-repo 会移除 remote 配置）
  local rnames=() rurls=() n u
  while IFS=$'\t' read -r n u; do
    [ -z "$n" ] && continue
    rnames+=("$n"); rurls+=("$u")
  done < <(git remote -v | awk '$3=="(fetch)"{print $1"\t"$2}')

  info "开始重写历史..."
  if [ $HAS_FR -eq 1 ]; then
    run_filter_repo || { warn "filter-repo 失败；可用备份恢复: $bundle"; return 1; }
  else
    run_filter_branch || { warn "filter-branch 失败；可用备份恢复: $bundle"; return 1; }
  fi

  # 恢复远程
  local i
  for i in "${!rnames[@]}"; do
    git remote get-url "${rnames[$i]}" >/dev/null 2>&1 \
      || { git remote add "${rnames[$i]}" "${rurls[$i]}" && ok "已恢复 remote: ${rnames[$i]} -> ${rurls[$i]}"; }
  done

  # 校验
  echo
  info "校验结果:"
  local all_clean=1 c
  for p in "${PATHS[@]}"; do
    c=$(git rev-list --all --count -- "$(spec_of "$p")" 2>/dev/null || echo 0)
    if [ "$c" = "0" ]; then ok "  $p  历史中已不存在"; else warn "  $p  仍有 $c 个提交涉及（可能是 refs/stash 或其他引用）"; all_clean=0; fi
  done
  [ $all_clean -eq 1 ] && ok "全部目标已从历史中清除"

  push_step "${rnames[@]}"
  after_notes "$keep"
  return 0
}

push_step() {
  [ $# -eq 0 ] && return
  echo
  local r ans
  for r in "$@"; do
    read -r -p "是否现在强制推送到 remote '$r'（所有分支 + 标签）? 输入 yes 确认，其他跳过: " ans
    if [ "$ans" = "yes" ]; then
      git push "$r" --force --all  && git push "$r" --force --tags \
        && ok "已强制推送到 $r" || warn "推送到 $r 失败（可能是受保护分支，需先在平台上临时关闭保护）"
    else
      info "已跳过 $r，之后可手动执行: git push $r --force --all && git push $r --force --tags"
    fi
  done
}

after_notes() {
  cat <<EOF

${Y}—— 后续必做 ——${N}
 1. 若移除的是密钥/令牌: 立刻到对应平台【吊销并轮换】。只要曾经推送过，就应视为已泄露。
 2. 如果还没推送，请执行: git push <remote> --force --all && git push <remote> --force --tags
 3. 通知协作者: 删除旧本地仓库后重新 clone（不要 pull/merge，否则旧历史会被带回来）。
 4. GitHub/GitLab 上的旧 PR 引用、缓存视图、fork 里仍可能保留旧对象，
    需联系平台支持清理（GitHub: Support → 移除敏感数据）。
 5. 把这些路径加入 .gitignore，避免再次提交。${1:+
 6. 当前版本的文件副本在: $1}
EOF
}

# ---------- 入口 ----------
for a in "$@"; do add_path "$a"; done

while true; do
  echo
  echo "================ Git 历史清理工具 ================"
  echo " 仓库: $TOP"
  echo " 引擎: $([ $HAS_FR -eq 1 ] && echo 'git filter-repo' || echo 'git filter-branch (回退)')"
  echo " 已选路径: ${#PATHS[@]} 项"
  echo "--------------------------------------------------"
  echo " 1) 扫描历史中最大的文件并挑选"
  echo " 2) 按文件名关键字搜索历史并挑选（如 .env、.pem）"
  echo " 3) 手动输入文件/目录路径"
  echo " 4) 查看 / 修改已选路径"
  echo " 5) 预览影响范围"
  echo " 6) 备份并执行移除"
  echo " 0) 退出"
  read -r -p "请选择: " choice
  case "$choice" in
    1) scan_large ;;
    2) search_names ;;
    3) manual_input ;;
    4) edit_paths ;;
    5) preview ;;
    6) run_purge && break ;;
    0|q|Q) info "已退出，未做任何修改"; break ;;
    *) warn "无效选项" ;;
  esac
done
