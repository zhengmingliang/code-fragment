#!/bin/bash
#=============================================================
# Redis 3主3从 集群 离线部署脚本
# 支持 1 台 / 2 台 / 3 台服务器灵活部署（总节点数固定 6 个：3主3从）
#
# 前置条件（离线环境）：
#   1. 提前在每台目标机器上准备好已编译/解压好的 redis-server、redis-cli
#      （可在同架构同系统的机器上提前编译好整个 redis 目录，再离线拷贝过去）
#   2. 本脚本需拷贝到每一台参与集群的机器上，且【配置区内容必须完全一致】
#   3. 各机器之间的以下端口需要互通（TCP）：
#        数据端口: BASE_PORT ~ BASE_PORT+每机节点数-1
#        总线端口: 数据端口 + 10000
#
# 用法（在每台机器上执行）：
#   ./redis-cluster.sh init     # 生成本机负责的节点配置
#   ./redis-cluster.sh start    # 启动本机负责的节点
#   ./redis-cluster.sh status   # 查看本机节点状态
#   ./redis-cluster.sh create   # 仅需在其中1台机器上执行1次：创建整个集群
#   ./redis-cluster.sh check    # 查看集群状态
#   ./redis-cluster.sh stop     # 停止本机节点
#   ./redis-cluster.sh clean    # 清空本机节点数据（危险操作）
#   ./redis-cluster.sh deploy   # 仅单机场景可用：init+start+create 一条龙
#=============================================================

############### 1. 用户配置区（务必先修改这里，且每台机器保持一致）###############

# 集群所有机器的 IP，1台/2台/3台均可，只填真实会用到的机器
# 单机示例:  NODE_IPS=("127.0.0.1")
# 两台示例:  NODE_IPS=("192.168.1.11" "192.168.1.12")
# 三台示例:  NODE_IPS=("192.168.1.11" "192.168.1.12" "192.168.1.13")
NODE_IPS=("127.0.0.1")

# redis 访问密码，留空 "" 表示不设置密码
REDIS_PASSWORD="Redis@123456"

# 离线环境下已准备好的 redis 二进制目录（需包含 redis-server / redis-cli）
REDIS_BIN_DIR="/usr/local/bin"

# 集群数据/配置存放的根目录
CLUSTER_HOME="/opt/redis/data/redis-cluster"

# 起始端口，每台机器会按本机负责的节点数往后顺延占用
BASE_PORT=7000

# 集群总节点数固定为 6（3主+3从），不建议修改
TOTAL_NODES=6

################################################################

ACTION="$1"
NUM_MACHINES=${#NODE_IPS[@]}

if (( TOTAL_NODES % NUM_MACHINES != 0 )); then
    echo "[错误] NODE_IPS 机器数量(${NUM_MACHINES}) 不能整除 6，只支持配置 1 / 2 / 3 / 6 台机器"
    exit 1
fi
NODES_PER_MACHINE=$(( TOTAL_NODES / NUM_MACHINES ))
BUS_OFFSET=10000

RED='\033[31m'; GREEN='\033[32m'; YELLOW='\033[33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; }

# 判断本机在 NODE_IPS 中对应哪一个下标
get_local_index() {
    local_ips=$(hostname -I 2>/dev/null)
    for i in "${!NODE_IPS[@]}"; do
        ip="${NODE_IPS[$i]}"
        if [[ "$ip" == "127.0.0.1" ]]; then
            echo "$i"; return 0
        fi
        if echo "$local_ips" | grep -qw "$ip"; then
            echo "$i"; return 0
        fi
    done
    echo "-1"
}

check_binary() {
    if [[ ! -x "${REDIS_BIN_DIR}/redis-server" || ! -x "${REDIS_BIN_DIR}/redis-cli" ]]; then
        err "未找到 ${REDIS_BIN_DIR}/redis-server 或 redis-cli，请先离线准备好redis二进制文件"
        exit 1
    fi
}

# 本机需要负责的端口列表
local_ports() {
    local ports=()
    for ((p=0; p<NODES_PER_MACHINE; p++)); do
        ports+=($((BASE_PORT+p)))
    done
    echo "${ports[@]}"
}

# 生成单个节点的配置文件
gen_conf() {
    local ip=$1
    local port=$2
    local dir="${CLUSTER_HOME}/${port}"
    mkdir -p "${dir}/data" "${dir}/logs"

    local pass_conf=""
    if [[ -n "$REDIS_PASSWORD" ]]; then
        pass_conf="requirepass ${REDIS_PASSWORD}
masterauth ${REDIS_PASSWORD}"
    fi

    local announce_conf=""
    if [[ "$ip" != "127.0.0.1" ]]; then
        announce_conf="cluster-announce-ip ${ip}
cluster-announce-port ${port}
cluster-announce-bus-port $((port+BUS_OFFSET))"
    fi

    cat > "${dir}/redis.conf" <<EOF
bind 0.0.0.0
protected-mode no
port ${port}
daemonize yes
pidfile ${dir}/redis.pid
logfile ${dir}/logs/redis.log
dir ${dir}/data
dbfilename dump.rdb

cluster-enabled yes
cluster-config-file nodes-${port}.conf
cluster-node-timeout 15000
cluster-require-full-coverage no

appendonly yes
appendfsync everysec

${pass_conf}
${announce_conf}
EOF
}

do_init() {
    check_binary
    idx=$(get_local_index)
    if [[ "$idx" == "-1" ]]; then
        err "本机IP不在 NODE_IPS 配置列表中，请检查配置区是否与本机一致"
        exit 1
    fi
    local_ip=${NODE_IPS[$idx]}
    log "本机对应 NODE_IPS[$idx] = ${local_ip}，将初始化 ${NODES_PER_MACHINE} 个节点"
    for port in $(local_ports); do
        gen_conf "$local_ip" "$port"
        log "已生成配置: ${CLUSTER_HOME}/${port}/redis.conf"
    done
    log "初始化完成"
}

do_start() {
    check_binary
    for port in $(local_ports); do
        local dir="${CLUSTER_HOME}/${port}"
        if [[ ! -f "${dir}/redis.conf" ]]; then
            err "端口 ${port} 未初始化，请先执行 init"
            continue
        fi
        if [[ -f "${dir}/redis.pid" ]] && kill -0 "$(cat "${dir}/redis.pid")" 2>/dev/null; then
            warn "端口 ${port} 已在运行，跳过"
            continue
        fi
        "${REDIS_BIN_DIR}/redis-server" "${dir}/redis.conf"
        sleep 0.3
        if [[ -f "${dir}/redis.pid" ]] && kill -0 "$(cat "${dir}/redis.pid")" 2>/dev/null; then
            log "端口 ${port} 启动成功 (pid=$(cat "${dir}/redis.pid"))"
        else
            err "端口 ${port} 启动失败，请查看 ${dir}/logs/redis.log"
        fi
    done
}

do_stop() {
    for port in $(local_ports); do
        local dir="${CLUSTER_HOME}/${port}"
        local auth=()
        [[ -n "$REDIS_PASSWORD" ]] && auth=(-a "$REDIS_PASSWORD" --no-auth-warning)
        if "${REDIS_BIN_DIR}/redis-cli" -p "$port" "${auth[@]}" shutdown nosave 2>/dev/null; then
            log "端口 ${port} 已停止"
        else
            if [[ -f "${dir}/redis.pid" ]]; then
                kill "$(cat "${dir}/redis.pid")" 2>/dev/null && log "端口 ${port} 已通过kill停止" || warn "端口 ${port} 停止失败或未运行"
            else
                warn "端口 ${port} 未运行"
            fi
        fi
    done
}

do_status() {
    for port in $(local_ports); do
        local auth=()
        [[ -n "$REDIS_PASSWORD" ]] && auth=(-a "$REDIS_PASSWORD" --no-auth-warning)
        if "${REDIS_BIN_DIR}/redis-cli" -p "$port" "${auth[@]}" ping 2>/dev/null | grep -q PONG; then
            log "端口 ${port} 运行正常"
        else
            err "端口 ${port} 未响应"
        fi
    done
}

do_create() {
    check_binary
    local endpoints=""
    for ip in "${NODE_IPS[@]}"; do
        for port in $(local_ports); do
            endpoints="${endpoints} ${ip}:${port}"
        done
    done
    log "即将创建集群，节点列表:${endpoints}"
    log "请确保以上所有节点已经在对应机器上执行过 init + start"

    local auth=()
    [[ -n "$REDIS_PASSWORD" ]] && auth=(-a "$REDIS_PASSWORD" --no-auth-warning)

    log "正在检测各节点连通性..."
    for ip in "${NODE_IPS[@]}"; do
        for port in $(local_ports); do
            if ! "${REDIS_BIN_DIR}/redis-cli" -h "$ip" -p "$port" "${auth[@]}" ping 2>/dev/null | grep -q PONG; then
                err "节点 ${ip}:${port} 连接失败，请检查该机器是否已启动/端口是否放通"
                exit 1
            fi
        done
    done
    log "所有节点连通性正常，开始创建集群 (3主3从)"

    "${REDIS_BIN_DIR}/redis-cli" --cluster create ${endpoints} \
        --cluster-replicas 1 "${auth[@]}" --cluster-yes

    log "集群创建完成！"
}

do_check() {
    local auth=()
    [[ -n "$REDIS_PASSWORD" ]] && auth=(-a "$REDIS_PASSWORD" --no-auth-warning)
    local first_ip=${NODE_IPS[0]}
    "${REDIS_BIN_DIR}/redis-cli" --cluster check "${first_ip}:${BASE_PORT}" "${auth[@]}"
}

do_clean() {
    read -p "确认要清空本机所有集群数据吗？(y/n) " yn
    [[ "$yn" != "y" ]] && exit 0
    do_stop
    for port in $(local_ports); do
        rm -rf "${CLUSTER_HOME}/${port}"
        log "已删除 ${CLUSTER_HOME}/${port}"
    done
}

do_deploy() {
    if (( NUM_MACHINES != 1 )); then
        err "deploy 一键部署仅适用于单机场景(NODE_IPS只有1个IP)；多台机器请先在每台机器上分别执行 init 和 start，全部启动后再在其中一台上执行 create"
        exit 1
    fi
    do_init
    do_start
    sleep 2
    do_create
}

case "$ACTION" in
    init)   do_init ;;
    start)  do_start ;;
    stop)   do_stop ;;
    status) do_status ;;
    create) do_create ;;
    check)  do_check ;;
    clean)  do_clean ;;
    deploy) do_deploy ;;
    *)
        echo "用法: $0 {init|start|stop|status|create|check|clean|deploy}"
        echo "  init   - 在本机生成集群节点配置"
        echo "  start  - 启动本机所有集群节点"
        echo "  stop   - 停止本机所有集群节点"
        echo "  status - 查看本机所有节点状态"
        echo "  create - 用所有机器的节点创建3主3从集群(仅需在1台机器上执行1次)"
        echo "  check  - 检查集群状态"
        echo "  clean  - 清空本机集群数据(危险操作)"
        echo "  deploy - 单机场景一键部署(init+start+create)"
        exit 1
        ;;
esac
