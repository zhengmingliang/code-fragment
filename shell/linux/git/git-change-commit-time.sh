#!/usr/bin/env bash
# ============================================================
#  git-change-commit-date.sh
#  一键修改 Git 提交时间（支持多选、仅改日期、相对偏移）
# ============================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }

usage() {
  cat <<EOF
${BOLD}用法：${RESET}
  $0 [选项]

${BOLD}选项：${RESET}
  -c <选择>    提交序号，支持：单个(3)、多个(1,3,5)、范围(2-5)、混合(1,3-5)
  -d <时间>    绝对时间，两种格式（与 -o 互斥）：
               仅日期：YYYY-MM-DD           → 时分秒保留原值
               完整  ：YYYY-MM-DD HH:MM:SS  → 全量替换
  -o <偏移>    相对偏移，在每条提交【各自原始时间】基础上加减（与 -d 互斥）：
               格式：由 若干个 [+-]数字[dhm] 组成，可任意组合叠加
                 d = 天, h = 小时, m = 分钟
               例如：
                 +1d        向后推 1 天
                 -3h        向前提 3 小时
                 +2d-3h+15m 向后推 2 天，再提前 3 小时，再向后推 15 分钟
  -h           显示此帮助

${BOLD}示例：${RESET}
  $0                                      # 全交互模式
  $0 -c 3 -d "2024-01-15"                 # 仅改第3条的日期
  $0 -c 1,3,5 -d "2024-01-15 10:30:00"    # 改多条完整时间
  $0 -c 2-5 -d "2024-01-15"               # 改第2~5条的日期
  $0 -c 3 -o "+1d"                        # 第3条提交时间在原基础上 +1天
  $0 -c 1,3-5 -o "-2h30m"                 # 选中的提交各自在原基础上 -2小时30分钟
EOF
  exit 0
}

# ── 参数 ──────────────────────────────────────────────────
TARGET_SELECTION=""
NEW_DATE=""
OFFSET_STR=""

while getopts "c:d:o:h" opt; do
  case $opt in
    c) TARGET_SELECTION="$OPTARG" ;;
    d) NEW_DATE="$OPTARG" ;;
    o) OFFSET_STR="$OPTARG" ;;
    h) usage ;;
    *) usage ;;
  esac
done

if [[ -n "$NEW_DATE" && -n "$OFFSET_STR" ]]; then
  error "-d（绝对时间）与 -o（相对偏移）不能同时使用"
fi

declare -a  LOG_LINES=()
declare -A  SELECTED_IDX=()
DATE_ONLY_MODE=false
NEW_DATE_INPUT=""
OFFSET_MODE=false
OFFSET_SECONDS=0         # 偏移量换算成的总秒数（可正可负）
OFFSET_DISPLAY=""        # 供展示用的原始偏移字符串

# ── 环境检查 ──────────────────────────────────────────────
check_env() {
  command -v git &>/dev/null || error "未找到 git 命令"
  git rev-parse --is-inside-work-tree &>/dev/null \
    || error "当前目录不是 Git 仓库"

  if ! git diff --quiet || ! git diff --cached --quiet; then
    warn "工作区存在未提交的变更，建议先执行 git stash"
    read -rp "  是否继续？(y/N): " ans
    [[ "$ans" =~ ^[Yy]$ ]] || { info "已取消"; exit 0; }
  fi
}

# ── 加载提交列表 ──────────────────────────────────────────
load_log() {
  mapfile -t LOG_LINES < <(
    git log --format="%H|%h|%ad|%s" --date=format:"%Y-%m-%d %H:%M:%S" -25
  )
}

# ── 展示提交列表 ──────────────────────────────────────────
show_log() {
  echo -e "\n${BOLD}最近 20 条提交：${RESET}"
  echo "──────────────────────────────────────────────────────────"
  local i=1
  for line in "${LOG_LINES[@]}"; do
    local sh date msg
    sh=$(  echo "$line" | cut -d'|' -f2)
    date=$(echo "$line" | cut -d'|' -f3)
    msg=$( echo "$line" | cut -d'|' -f4-)
    printf "  ${CYAN}%2d${RESET}. ${YELLOW}%s${RESET}  ${GREEN}%s${RESET}  %s\n" \
           "$i" "$sh" "$date" "$msg"
    ((i++))
  done
  echo "──────────────────────────────────────────────────────────"
}

# ── 解析选择字符串 → SELECTED_IDX（0-based）─────────────
parse_selection() {
  local sel="$1" max="$2"
  SELECTED_IDX=()
  IFS=',' read -ra parts <<< "$sel"
  for part in "${parts[@]}"; do
    part=$(echo "$part" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    if [[ "$part" =~ ^([0-9]+)-([0-9]+)$ ]]; then
      local lo="${BASH_REMATCH[1]}" hi="${BASH_REMATCH[2]}"
      (( lo >= 1 && hi <= max && lo <= hi )) \
        || error "范围越界：$part（有效范围 1-$max）"
      for (( n=lo; n<=hi; n++ )); do SELECTED_IDX[$((n-1))]=1; done
    elif [[ "$part" =~ ^([0-9]+)$ ]]; then
      local n="${BASH_REMATCH[1]}"
      (( n >= 1 && n <= max )) \
        || error "序号越界：$n（有效范围 1-$max）"
      SELECTED_IDX[$((n-1))]=1
    else
      error "无法识别的格式：'$part'"
    fi
  done
  (( ${#SELECTED_IDX[@]} > 0 )) || error "未选择任何提交"
}

# ── 解析绝对时间输入 ──────────────────────────────────────
parse_date_input() {
  local raw
  raw=$(echo "$1" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

  if [[ "$raw" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    date -d "$raw" &>/dev/null || error "日期不合法：'$raw'"
    DATE_ONLY_MODE=true
    NEW_DATE_INPUT="$raw"
  elif [[ "$raw" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}[[:space:]][0-9]{2}:[0-9]{2}:[0-9]{2}$ ]]; then
    date -d "$raw" &>/dev/null || error "时间不合法：'$raw'"
    DATE_ONLY_MODE=false
    NEW_DATE_INPUT="$raw"
  else
    error "格式不正确：'$raw'
       仅日期  → YYYY-MM-DD
       完整时间 → YYYY-MM-DD HH:MM:SS"
  fi
}

# ── 解析相对偏移输入，如 "+1d-3h+15m" ─────────────────────
parse_offset() {
  local raw
  raw=$(echo "$1" | sed 's/[[:space:]]*//g')
  [[ -n "$raw" ]] || error "偏移量不能为空"

  local pattern='^([+-][0-9]+[dhm])+$'
  [[ "$raw" =~ $pattern ]] \
    || error "偏移格式不正确：'$raw'
       正确格式示例：+1d  -3h  +2d-3h+15m（数字[dhm]，d=天 h=小时 m=分钟，必须带符号）"

  local tokens
  mapfile -t tokens < <(grep -oE '[+-][0-9]+[dhm]' <<< "$raw")

  # 不直接把 "+N hours" 拼进 date -d 的字符串里解析——GNU date 在紧跟完整
  # 日期时间之后会把 "+N" 误判成时区偏移（如 +1000），导致算出来的时间完全错误。
  # 因此这里统一换算成总秒数，后续用 epoch 秒做加减，彻底避开这个解析歧义。
  OFFSET_SECONDS=0
  local token sign num unit_char sec
  for token in "${tokens[@]}"; do
    sign="${token:0:1}"
    unit_char="${token: -1}"
    num="${token:1:${#token}-2}"
    case "$unit_char" in
      d) sec=$(( num * 86400 )) ;;
      h) sec=$(( num * 3600 ))  ;;
      m) sec=$(( num * 60 ))    ;;
    esac
    if [[ "$sign" == "-" ]]; then
      OFFSET_SECONDS=$(( OFFSET_SECONDS - sec ))
    else
      OFFSET_SECONDS=$(( OFFSET_SECONDS + sec ))
    fi
  done

  OFFSET_MODE=true
  OFFSET_DISPLAY="$raw"
}

# ── 交互：输入时间（绝对 / 相对，二选一）─────────────────
pick_date() {
  echo ""
  echo -e "  ${BOLD}请选择修改方式：${RESET}"
  echo -e "    ${CYAN}1${RESET}) 绝对时间  —— 替换为指定的日期/时间"
  echo -e "    ${CYAN}2${RESET}) 相对偏移  —— 在各提交【原时间】基础上加减 天/小时/分钟"
  read -rp "请选择 [1/2，默认 1]: " mode_choice
  mode_choice="${mode_choice:-1}"

  if [[ "$mode_choice" == "2" ]]; then
    echo -e "  格式：由若干个 ${CYAN}[+-]数字[dhm]${RESET} 组成，可叠加，d=天 h=小时 m=分钟"
    echo -e "  例如：${CYAN}+1d${RESET}  ${CYAN}-3h${RESET}  ${CYAN}+2d-3h+15m${RESET}"
    read -rp "请输入偏移量: " offset_input
    parse_offset "$offset_input"
    info "模式：${YELLOW}相对偏移${RESET} → ${GREEN}${OFFSET_DISPLAY}${RESET}（基于各提交原时间分别计算）"
  else
    echo -e "  时间格式说明："
    echo -e "    ${CYAN}YYYY-MM-DD${RESET}           仅替换日期，时分秒保留原提交值"
    echo -e "    ${CYAN}YYYY-MM-DD HH:MM:SS${RESET}  全量替换"
    local default_date
    default_date=$(date "+%Y-%m-%d %H:%M:%S")
    read -rp "请输入新时间（直接回车使用当前时间）: " input_date
    parse_date_input "${input_date:-$default_date}"

    if $DATE_ONLY_MODE; then
      info "模式：${YELLOW}仅替换日期${RESET} → ${GREEN}${NEW_DATE_INPUT}${RESET}（时分秒保留原值）"
    else
      info "模式：${YELLOW}完整替换${RESET} → ${GREEN}${NEW_DATE_INPUT}${RESET}"
    fi
  fi
}

# ── 根据原始时间计算目标 ISO 时间（绝对模式）──────────────
build_iso_date() {
  local original_datetime="$1"   # "YYYY-MM-DD HH:MM:SS"
  local final_datetime
  if $DATE_ONLY_MODE; then
    local orig_time
    orig_time=$(echo "$original_datetime" | awk '{print $2}')
    final_datetime="${NEW_DATE_INPUT} ${orig_time}"
  else
    final_datetime="$NEW_DATE_INPUT"
  fi
  date -d "$final_datetime" "+%Y-%m-%dT%H:%M:%S%z"
}

# ── 根据原始时间 + 偏移量计算目标 ISO 时间（相对模式）────
build_iso_date_offset() {
  local original_datetime="$1"   # "YYYY-MM-DD HH:MM:SS"
  local base_epoch target_epoch
  base_epoch=$(date -d "$original_datetime" "+%s") \
    || error "无法解析原始提交时间：'$original_datetime'"
  target_epoch=$(( base_epoch + OFFSET_SECONDS ))
  date -d "@${target_epoch}" "+%Y-%m-%dT%H:%M:%S%z"
}

# ── 统一入口：按当前模式计算目标 ISO 时间 ─────────────────
compute_new_iso() {
  local original_datetime="$1"
  if $OFFSET_MODE; then
    build_iso_date_offset "$original_datetime"
  else
    build_iso_date "$original_datetime"
  fi
}

# ── 核心：一次 filter-branch 修改所有选中提交 ────────────
do_redate_all() {
  local sorted_idx
  sorted_idx=$(echo "${!SELECTED_IDX[@]}" | tr ' ' '\n' | sort -n)

  # ── 构建"hash → 目标ISO时间"的映射，同时打印确认摘要 ──
  declare -A HASH_TO_DATE=()

  echo ""
  echo -e "${BOLD}即将修改以下提交：${RESET}"
  echo "──────────────────────────────────────────────────────────"

  while IFS= read -r idx; do
    local line="${LOG_LINES[$idx]}"
    local full_hash sh old_date msg iso
    full_hash=$(echo "$line" | cut -d'|' -f1)
    sh=$(       echo "$line" | cut -d'|' -f2)
    old_date=$( echo "$line" | cut -d'|' -f3)
    msg=$(      echo "$line" | cut -d'|' -f4-)
    iso=$(compute_new_iso "$old_date")

    HASH_TO_DATE["$full_hash"]="$iso"

    printf "  ${YELLOW}%s${RESET}  ${GREEN}%s${RESET} → ${GREEN}%s${RESET}  %s\n" \
           "$sh" "$old_date" "$iso" "$msg"
  done <<< "$sorted_idx"

  echo "──────────────────────────────────────────────────────────"
  read -rp "确认修改？(y/N): " confirm
  [[ "$confirm" =~ ^[Yy]$ ]] || { info "已取消"; exit 0; }

  # ── 判断是否只改 HEAD ────────────────────────────────────
  local head_hash
  head_hash=$(git rev-parse HEAD)

  # 仅有一条且是 HEAD，直接 amend
  if [[ ${#HASH_TO_DATE[@]} -eq 1 ]]; then
    local only_hash="${!HASH_TO_DATE[*]}"
    if [[ "$only_hash" == "$head_hash" ]]; then
      local iso="${HASH_TO_DATE[$only_hash]}"
      info "目标是 HEAD，直接 amend..."
      GIT_COMMITTER_DATE="$iso" \
        git commit --amend --no-edit --date="$iso" \
        || error "amend 失败"
      success "修改完成！"
      return
    fi
  fi

  # ── 构建 case 语句，一次 filter-branch 搞定所有提交 ─────
  # 格式：
  #   case "$GIT_COMMIT" in
  #     <hash1>) export GIT_AUTHOR_DATE="..." ; export GIT_COMMITTER_DATE="..." ;;
  #     <hash2>) ...
  #   esac
  local case_body=""
  for full_hash in "${!HASH_TO_DATE[@]}"; do
    local iso="${HASH_TO_DATE[$full_hash]}"
    case_body+="    ${full_hash}) "
    case_body+="export GIT_AUTHOR_DATE=\"${iso}\"; "
    case_body+="export GIT_COMMITTER_DATE=\"${iso}\" ;;"$'\n'
  done

  local env_filter
  env_filter=$(cat <<FILTER
case "\$GIT_COMMIT" in
${case_body}esac
FILTER
)

  info "执行 filter-branch，共修改 ${#HASH_TO_DATE[@]} 条提交..."

  FILTER_BRANCH_SQUELCH_WARNING=1 \
  git filter-branch -f --env-filter "$env_filter" -- HEAD \
    || error "filter-branch 执行失败，请确保工作区干净（git stash）后重试"

  success "共修改 ${#HASH_TO_DATE[@]} 条提交完成！"
}

# ── 显示结果 ──────────────────────────────────────────────
show_result() {
  echo ""
  echo -e "${BOLD}修改后的提交记录（最近10条）：${RESET}"
  echo "──────────────────────────────────────────────────────────"
  git log \
    --format="${YELLOW}%h${RESET}  ${GREEN}%ad${RESET}  %s" \
    --date=format:"%Y-%m-%d %H:%M:%S" \
    -10
  echo "──────────────────────────────────────────────────────────"
  echo ""
  warn "如已推送到远程，需要强制推送："
  echo -e "  ${CYAN}git push --force-with-lease${RESET}"
}

# ── 主流程 ────────────────────────────────────────────────
main() {
  echo -e "${BOLD}╔══════════════════════════════════════╗${RESET}"
  echo -e "${BOLD}║    Git 提交时间修改工具               ║${RESET}"
  echo -e "${BOLD}╚══════════════════════════════════════╝${RESET}"
  echo ""

  check_env
  load_log

  if [[ -z "$TARGET_SELECTION" ]]; then
    show_log
    echo -e "  支持格式：单个 ${CYAN}3${RESET}、多个 ${CYAN}1,3,5${RESET}、范围 ${CYAN}2-5${RESET}、混合 ${CYAN}1,3-5${RESET}"
    read -rp "请输入序号: " TARGET_SELECTION
    [[ -n "$TARGET_SELECTION" ]] || error "未输入任何序号"
  fi

  parse_selection "$TARGET_SELECTION" "${#LOG_LINES[@]}"

  if [[ -n "$OFFSET_STR" ]]; then
    parse_offset "$OFFSET_STR"
    info "模式：${YELLOW}相对偏移${RESET} → ${GREEN}${OFFSET_DISPLAY}${RESET}（基于各提交原时间分别计算）"
  elif [[ -n "$NEW_DATE" ]]; then
    parse_date_input "$NEW_DATE"
    if $DATE_ONLY_MODE; then
      info "模式：${YELLOW}仅替换日期${RESET} → ${GREEN}${NEW_DATE_INPUT}${RESET}"
    else
      info "模式：${YELLOW}完整替换${RESET} → ${GREEN}${NEW_DATE_INPUT}${RESET}"
    fi
  else
    pick_date
  fi

  do_redate_all
  show_result
}

main "$@"
