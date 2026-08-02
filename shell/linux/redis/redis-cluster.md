# Redis 3主3从集群部署脚本 —— 使用文档

配套脚本：`redis-cluster.sh` [redis-cluster.sh](redis-cluster.sh)
```bash
#!/bin/bash
#=============================================================
# Redis 3主3从 集群 离线部署脚本
# 支持 1 台 / 2 台 / 3 台服务器灵活部署（总节点数固定 6 个：3主3从）
#
# 前置条件（离线环境）：
#   1. 两种方式二选一，在每台目标机器上准备好可执行的 redis-server、redis-cli：
#      方式A：提前编译/解压好整个 redis 目录，配置 REDIS_BIN_DIR 指向其 bin 目录；
#      方式B：只需准备好 redis 源码包(tar.gz/tar.bz2)，配置 REDIS_SRC_PACKAGE 指向
#             该源码包路径 —— 脚本会在 REDIS_BIN_DIR 下找不到 redis-server/redis-cli
#             时，自动解压并编译该源码包，将编译产物拷贝到 REDIS_BIN_DIR 下（全程
#             不需要 root 权限，只要 REDIS_BIN_DIR / REDIS_BUILD_DIR 对当前用户可写）。
#             注意：编译本身依赖机器上已装好 gcc、make 等基础构建工具，这些工具
#             脚本不会离线安装，需要运维提前装好。
#   2. 本脚本需拷贝到每一台参与集群的机器上，且【配置区内容必须完全一致】
#   3. 各机器之间的以下端口需要互通（TCP）：
#        数据端口: BASE_PORT ~ BASE_PORT+每机节点数-1
#        总线端口: 数据端口 + 10000
#
# 用法（在每台机器上执行）：
#   ./redis-cluster.sh build    # 检查/编译 redis-server、redis-cli 到 REDIS_BIN_DIR
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
NODE_IPS=("172.16.18.235" "172.16.18.233")

# redis 访问密码，留空 "" 表示不设置密码
REDIS_PASSWORD="Redis@123456"

# redis 二进制目录（需包含 redis-server / redis-cli）。
# 建议指向当前用户有写权限的目录（如 /data/redis/bin 或 $HOME 下），无需 root。
# 若该目录下找不到 redis-server/redis-cli，脚本会尝试用下面的 REDIS_SRC_PACKAGE 自动编译。
REDIS_BIN_DIR="/opt/redis/bin"

# 【可选】redis 源码包路径（tar.gz/tar.bz2）。当 REDIS_BIN_DIR 下缺少可执行文件时，
# 脚本会自动解压并编译该源码包，编译产物会拷贝到 REDIS_BIN_DIR 下。
# 如果本机已经有现成的 redis-server/redis-cli（方式A），可以留空 ""，不会触发编译。
REDIS_SRC_PACKAGE="/opt/software/redis-8.6.3.tar.gz"

# 源码编译时使用的解压/编译临时目录，需要当前用户可写
REDIS_BUILD_DIR="/opt/redis-cluster/build"

# 【可选】编译附加参数，例如系统上jemalloc编译有问题时可填 "MALLOC=libc"，一般留空即可
REDIS_MAKE_OPTS=""

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
    if [[ -x "${REDIS_BIN_DIR}/redis-server" && -x "${REDIS_BIN_DIR}/redis-cli" ]]; then
        return 0
    fi

    warn "${REDIS_BIN_DIR} 下未找到 redis-server/redis-cli，尝试通过源码包自动编译..."
    build_redis_from_source

    if [[ ! -x "${REDIS_BIN_DIR}/redis-server" || ! -x "${REDIS_BIN_DIR}/redis-cli" ]]; then
        err "编译后仍未在 ${REDIS_BIN_DIR} 下找到 redis-server/redis-cli，请检查编译日志"
        exit 1
    fi
    log "redis-server/redis-cli 已就绪：${REDIS_BIN_DIR}"
}

# 当 REDIS_BIN_DIR 下缺少 redis-server/redis-cli 时，从 REDIS_SRC_PACKAGE 源码包
# 自动解压+编译，并把编译产物拷贝到 REDIS_BIN_DIR。全程只需当前用户对
# REDIS_BUILD_DIR / REDIS_BIN_DIR 有写权限，不依赖 root，也不执行 make install。
build_redis_from_source() {
    if [[ -z "$REDIS_SRC_PACKAGE" ]]; then
        err "REDIS_BIN_DIR 下没有可用的redis二进制，且未配置 REDIS_SRC_PACKAGE，无法自动编译"
        exit 1
    fi
    if [[ ! -f "$REDIS_SRC_PACKAGE" ]]; then
        err "指定的源码包不存在：${REDIS_SRC_PACKAGE}"
        exit 1
    fi
    if ! command -v make >/dev/null 2>&1; then
        err "未检测到 make 命令，请提前安装好编译工具链(gcc/make等)后再重试"
        exit 1
    fi
    if ! command -v gcc >/dev/null 2>&1 && ! command -v cc >/dev/null 2>&1; then
        err "未检测到 gcc/cc 编译器，请提前安装好编译工具链后再重试"
        exit 1
    fi

    mkdir -p "$REDIS_BUILD_DIR"
    if [[ ! -w "$REDIS_BUILD_DIR" ]]; then
        err "当前用户对 REDIS_BUILD_DIR(${REDIS_BUILD_DIR}) 没有写权限"
        exit 1
    fi

    # 解析源码包解压后的顶层目录名（一般是 redis-x.y.z/）
    local top_dir
    top_dir=$(tar -tf "$REDIS_SRC_PACKAGE" 2>/dev/null | head -1 | cut -d/ -f1)
    if [[ -z "$top_dir" ]]; then
        err "无法识别源码包结构，请确认 ${REDIS_SRC_PACKAGE} 是合法的 tar.gz/tar.bz2 包"
        exit 1
    fi
    local src_dir="${REDIS_BUILD_DIR}/${top_dir}"

    if [[ -x "${src_dir}/src/redis-server" && -x "${src_dir}/src/redis-cli" ]]; then
        log "检测到已编译过的产物，跳过重新编译：${src_dir}/src"
    else
        log "解压源码包到 ${REDIS_BUILD_DIR} ..."
        tar -xf "$REDIS_SRC_PACKAGE" -C "$REDIS_BUILD_DIR"
        if [[ ! -d "$src_dir" ]]; then
            err "解压后未找到源码目录：${src_dir}"
            exit 1
        fi

        local jobs
        jobs=$(nproc 2>/dev/null || echo 1)
        log "开始编译 redis（make -j${jobs} ${REDIS_MAKE_OPTS}），日志见 ${src_dir}/build.log ..."
        if ! (cd "$src_dir" && make -j"${jobs}" ${REDIS_MAKE_OPTS}) > "${src_dir}/build.log" 2>&1; then
            err "编译失败，请查看日志：${src_dir}/build.log"
            exit 1
        fi
        log "编译完成"
    fi

    mkdir -p "$REDIS_BIN_DIR"
    if [[ ! -w "$REDIS_BIN_DIR" ]]; then
        err "当前用户对 REDIS_BIN_DIR(${REDIS_BIN_DIR}) 没有写权限"
        exit 1
    fi

    local bin_files=(redis-server redis-cli redis-benchmark redis-check-rdb redis-check-aof)
    for f in "${bin_files[@]}"; do
        if [[ -f "${src_dir}/src/${f}" ]]; then
            cp -f "${src_dir}/src/${f}" "${REDIS_BIN_DIR}/"
        fi
    done
    chmod +x "${REDIS_BIN_DIR}"/redis-* 2>/dev/null

    log "编译产物已拷贝到 ${REDIS_BIN_DIR}（无需root，普通用户即可）"
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
    build)  check_binary ;;
    init)   do_init ;;
    start)  do_start ;;
    stop)   do_stop ;;
    status) do_status ;;
    create) do_create ;;
    check)  do_check ;;
    clean)  do_clean ;;
    deploy) do_deploy ;;
    *)
        echo "用法: $0 {build|init|start|stop|status|create|check|clean|deploy}"
        echo "  build  - 检查/编译redis-server、redis-cli到REDIS_BIN_DIR(源码包缺失二进制时自动编译)"
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
```

本脚本用于在**离线环境**下，基于 1 台 / 2 台 / 3 台服务器，快速搭建一套 **3 主 3 从**（6 节点）的 Redis Cluster。同一份脚本、同一份配置需拷贝到每一台参与集群的机器上运行，脚本会自动识别当前机器负责哪些节点。

---

## 1. 整体原理

- 集群总节点数固定为 **6 个**（3 主 + 3 从）。
- 根据配置区 `NODE_IPS` 数组里填了几台机器的 IP，脚本自动计算"每台机器负责几个节点"：

| 机器数量 | 每台机器负责节点数 | 说明 |
|---|---|---|
| 1 台 | 6 | 6 个节点全部在同一台机器的不同端口上 |
| 2 台 | 3 | 每台 3 个节点，主从会自动分散到两台机器上 |
| 3 台 | 2 | 每台 2 个节点，主从会自动分散到三台机器上 |

- 每台机器只需要执行 `init` + `start` 来启动**自己负责的节点**；
- 最后只需要在**任意一台**机器上执行一次 `create`，脚本会把所有机器上的节点信息收集起来，调用 `redis-cli --cluster create` 自动组建成 3 主 3 从集群（redis 会尽量把主和从分布在不同机器上，以获得更好的高可用效果）。

---

## 2. 环境要求（离线前提）

**每一台**参与集群的机器上，都需要有可执行的 `redis-server` 和 `redis-cli`（版本建议 **5.0 及以上**，因为脚本使用了 `redis-cli --cluster create` 这个 5.0+ 才有的子命令；4.x 及更早版本请用 `redis-trib.rb` 替代，需要单独调整脚本，可以另外找我改）。获取二进制有两种方式，二选一：

- **方式 A（已有现成二进制）**：把提前编译好的 `redis-server`、`redis-cli` 放到 `REDIS_BIN_DIR` 目录下即可，脚本检测到已存在就不会触发编译。
- **方式 B（只有源码包，需要现场编译）**：把 `REDIS_SRC_PACKAGE` 指向离线准备好的 redis 源码包（如 `redis-7.4.0.tar.gz`）。脚本在发现 `REDIS_BIN_DIR` 下缺少 `redis-server`/`redis-cli` 时，会**自动**解压该源码包并执行 `make` 编译，再把编译产物拷贝到 `REDIS_BIN_DIR` 下——**全程不需要 root 权限**，只要当前用户对 `REDIS_BIN_DIR`、`REDIS_BUILD_DIR` 有写权限即可，也不会执行 `make install`。

> 方式 B 依赖机器上已经装好基础编译工具链（`gcc`/`cc`、`make`）。这些系统级依赖脚本不负责离线安装，需要运维提前在机器镜像里装好。官方 redis 源码包自带 `deps/`（jemalloc、hiredis、lua 等依赖源码），正常情况下编译过程本身**不需要联网**。

其余环境要求：

1. 系统为 Linux，脚本使用 `bash` 运行，不支持 `sh`。
2. 各机器之间网络互通，且以下端口需要在防火墙/安全组中放通（见第 7 节）。
3. 建议以普通用户或专用 `redis` 用户运行，注意 `CLUSTER_HOME`、`REDIS_BIN_DIR`、`REDIS_BUILD_DIR` 目录的读写/执行权限（推荐都放在当前用户可写的路径下，如 `/data/...` 或 `$HOME` 下，避免需要 root）。

---

## 3. 文件与目录结构

脚本运行后，会在配置的 `CLUSTER_HOME`（默认 `/data/redis-cluster`）下，为本机负责的每个端口生成一个独立目录：

```
/data/redis-cluster/
├── 7000/
│   ├── redis.conf         # 该节点的配置文件
│   ├── redis.pid          # 进程 pid 文件（daemonize后生成）
│   ├── nodes-7000.conf     # 集群自动生成的节点信息文件
│   ├── data/               # 该节点的数据目录（rdb / aof）
│   └── logs/
│       └── redis.log       # 该节点日志
├── 7001/
│   └── ...
└── 7002/
    └── ...
```

每个节点完全独立（独立配置、独立数据目录、独立日志），互不影响。

---

## 4. 配置项说明

打开 `redis-cluster.sh`，找到脚本顶部的"用户配置区"，逐项说明如下：

| 配置项 | 说明 | 示例 |
|---|---|---|
| `NODE_IPS` | 参与集群的机器 IP 列表，数组形式，1/2/3 个均可。**所有机器上这个数组必须完全一致（顺序也要一致）** | `("192.168.1.11" "192.168.1.12")` |
| `REDIS_PASSWORD` | 集群访问密码，留空 `""` 表示不设密码（不建议生产环境留空） | `"Redis@123456"` |
| `REDIS_BIN_DIR` | redis 二进制所在目录，需包含可执行的 `redis-server`、`redis-cli`。建议指向当前用户可写的路径，无需 root。缺少二进制时会尝试自动编译 | `/data/redis/bin` |
| `REDIS_SRC_PACKAGE` | 【可选】redis 源码包路径（tar.gz/tar.bz2）。`REDIS_BIN_DIR` 缺少二进制时会自动编译该包；已有现成二进制可留空 `""` | `/data/software/redis-7.4.0.tar.gz` |
| `REDIS_BUILD_DIR` | 源码解压/编译用的临时目录，需当前用户可写 | `/data/redis-cluster/build` |
| `REDIS_MAKE_OPTS` | 【可选】编译附加参数，一般留空；如 jemalloc 编译异常可填 `"MALLOC=libc"` | `""` |
| `CLUSTER_HOME` | 存放所有节点配置和数据的根目录，会自动创建 | `/data/redis-cluster` |
| `BASE_PORT` | 起始端口号，本机负责的节点会从这个端口往后连续占用 | `7000` |
| `TOTAL_NODES` | 集群总节点数，固定为 `6`（3主3从），不建议修改 | `6` |

> ⚠️ **重要**：`NODE_IPS`、`BASE_PORT`、`TOTAL_NODES` 这三项必须在所有参与集群的机器上**完全一致**，否则 `create` 阶段生成的节点列表会不匹配，导致建群失败。

---

## 5. 部署场景演示

### 5.1 单机部署（1 台机器，6 个节点跑在同一台机器不同端口）

适合本地测试或资源有限的场景。

```bash
# 1. 编辑配置区
NODE_IPS=("127.0.0.1")

# 2. 一条龙部署（init + start + create 自动完成）
chmod +x redis-cluster.sh
./redis-cluster.sh deploy
```

执行完成后会得到 6 个节点：`127.0.0.1:7000` ~ `127.0.0.1:7005`，自动组成 3 主 3 从。

### 5.2 两台机器部署（每台 3 个节点）

```bash
# 1. 把脚本和一致的配置分别拷贝到机器 A（192.168.1.11）和机器 B（192.168.1.12）
NODE_IPS=("192.168.1.11" "192.168.1.12")

# 2. 在机器 A 上执行：
./redis-cluster.sh init
./redis-cluster.sh start

# 3. 在机器 B 上执行：
./redis-cluster.sh init
./redis-cluster.sh start

# 4. 确认 A、B 都启动成功后（可用 status 分别检查），
#    只需在【任意一台】上执行一次：
./redis-cluster.sh create
```

结果：A 上 `7000~7002`，B 上 `7000~7002`，共 6 个节点，自动组成 3 主 3 从，且主从会尽量分散在 A、B 两台机器上。

### 5.3 三台机器部署（每台 2 个节点）

```bash
NODE_IPS=("192.168.1.11" "192.168.1.12" "192.168.1.13")

# 分别在 A、B、C 三台机器上执行：
./redis-cluster.sh init
./redis-cluster.sh start

# 三台都启动成功后，任选一台执行一次：
./redis-cluster.sh create
```

结果：每台机器 `7000~7001` 共 2 个节点，三台共 6 个节点，自动组成 3 主 3 从，每台机器上大致会分到 1 主 1 从（互为不同主从关系），可用性最好。

### 5.4 服务器上没有现成 redis，只有源码包

以两台机器为例，机器上完全没装过 redis，只在每台机器上放好了同一份源码包（如 `/data/software/redis-7.4.0.tar.gz`）。

```bash
# 1. 配置区里指定源码包路径（REDIS_BIN_DIR 留空目录即可，不需要提前准备二进制）
REDIS_SRC_PACKAGE="/data/software/redis-7.4.0.tar.gz"
REDIS_BIN_DIR="/data/redis/bin"
REDIS_BUILD_DIR="/data/redis-cluster/build"
NODE_IPS=("192.168.1.11" "192.168.1.12")

# 2. 在每台机器上先单独执行一次 build，确认编译能正常通过
#    （用普通用户执行即可，不需要 sudo/root，只要目录有写权限）
./redis-cluster.sh build

# 3. build 成功后，后续 init/start/create 用法和前面完全一样：
./redis-cluster.sh init
./redis-cluster.sh start
# 全部机器启动后，任选一台执行一次：
./redis-cluster.sh create
```

`build` 只是把编译这一步单独拎出来方便排查问题；实际上 `init`、`start`、`create` 内部也会自动检测并触发编译，直接跳过 `build` 步骤、从 `init` 开始也是可以的。

---

## 6. 命令详解

| 命令 | 作用范围 | 说明 |
|---|---|---|
| `build` | 本机 | 检查 `REDIS_BIN_DIR` 下是否已有 `redis-server`/`redis-cli`；没有则用 `REDIS_SRC_PACKAGE` 自动解压编译并拷贝过去（无需root） |
| `init` | 本机 | 生成本机负责的所有节点的配置文件、数据目录、日志目录（内部会先执行一次 `build` 检查） |
| `start` | 本机 | 启动本机负责的所有节点（已在运行的会自动跳过） |
| `stop` | 本机 | 优雅停止本机负责的所有节点（失败会尝试 kill pid） |
| `status` | 本机 | 用 `PING` 检测本机每个节点是否存活 |
| `create` | **全局，只需在 1 台机器上执行 1 次** | 汇总所有机器的节点信息，检测连通性后调用 `redis-cli --cluster create` 建群，`--cluster-replicas 1` 表示 1 主配 1 从 |
| `check` | 全局（查看用） | 调用 `redis-cli --cluster check` 查看集群健康状态、主从分布、槽位分布 |
| `clean` | 本机 | **危险操作**，会先停止再删除本机所有节点的数据目录，需二次确认 |
| `deploy` | 本机，**仅限单机场景** | `init` + `start` + `create` 一次性完成，多机场景会被脚本拒绝执行 |

### 常用查看命令示例

```bash
# 查看本机节点状态
./redis-cluster.sh status

# 查看整体集群状态（主从关系、槽位分配是否完整等）
./redis-cluster.sh check
```

`check` 的典型输出会包含每个节点的角色（master/slave）、负责的槽位区间、集群槲位是否覆盖完整（`[OK] All 16384 slots covered.` 表示正常）。

### 手动连接节点验证

```bash
# 连接任意一个节点，-c 表示以集群模式连接（自动重定向）
${REDIS_BIN_DIR}/redis-cli -c -h 192.168.1.11 -p 7000 -a Redis@123456 --no-auth-warning

127.0.0.1:7000> cluster nodes      # 查看所有节点及角色
127.0.0.1:7000> cluster info       # 查看集群整体信息
127.0.0.1:7000> set foo bar
127.0.0.1:7000> get foo
```

---

## 7. 端口与防火墙说明

每个 Redis Cluster 节点需要占用 **2 个端口**：

- **数据端口**：客户端连接用，即配置的 `BASE_PORT` 开始的端口（如 7000、7001、7002）
- **集群总线端口**：节点间通信用，固定为「数据端口 + 10000」（如 7000 对应 17000）

多机部署时，需要在所有机器之间放通这些端口（TCP），例如三台机器每台 2 个节点（7000、7001）：

```
7000, 7001, 17000, 17001
```

单机部署（`127.0.0.1`）不涉及跨机器网络，可以忽略此项。

---

## 8. 常见问题 FAQ

**Q1：执行 `init` 报错"本机IP不在 NODE_IPS 配置列表中"？**
说明本机的 IP 和配置区 `NODE_IPS` 里填的不一致。用 `hostname -I` 查看本机实际 IP，确认和配置一致（注意内外网 IP、多网卡的情况）。

**Q2：执行 `create` 报错某个节点连接失败？**
先在对应机器上执行 `./redis-cluster.sh status` 确认该节点已启动；再检查两台机器之间对应端口（数据端口 + 总线端口）是否已放通防火墙。

**Q3：密码认证失败 `NOAUTH Authentication required`？**
确认所有机器上的 `REDIS_PASSWORD` 配置完全一致；连接时记得带上 `-a 密码 --no-auth-warning`。

**Q4：想扩容/缩容集群怎么办？**
本脚本聚焦于"从 0 到 1"快速建群，不包含在线扩缩容逻辑。扩缩容需使用 `redis-cli --cluster add-node` / `reshard` / `del-node` 等命令手动操作，如需要可以单独再写一个扩缩容脚本。

**Q5：如何彻底重新部署？**
在每台机器上执行 `./redis-cluster.sh clean` 清空数据后，重新走一遍 `init` → `start` → `create` 流程。

**Q6：Redis 版本低于 5.0 怎么办？**
`redis-cli --cluster create` 是 5.0+ 才有的功能，4.x 及更早版本需要用 `redis-trib.rb create --replicas 1 <ip:port> ...` 替代，需要 Ruby 环境和 redis gem，建议直接升级到 5.0+ 版本使用本脚本。

**Q7：执行 `build`/`init` 报错"未检测到 make/gcc 命令"？**
说明机器上没有装基础编译工具链，脚本不会离线安装这些系统依赖，需要运维提前装好 `gcc`、`make`（通常随系统安装源或离线rpm/deb包安装，不在本脚本职责范围内）。

**Q8：编译失败怎么排查？**
脚本会提示日志路径，形如 `${REDIS_BUILD_DIR}/redis-x.y.z/build.log`，打开该日志查看具体报错（常见问题：缺编译工具链、磁盘空间不足、glibc版本过低等）。修复后重新执行 `build`/`init` 即可，脚本会跳过已解压的源码目录直接重新编译。

**Q9：一定要用 root 编译安装吗？**
不需要。脚本编译时只在源码目录内执行 `make`（不执行 `make install`），产物直接从源码目录 `cp` 到 `REDIS_BIN_DIR`，全程只要当前用户对 `REDIS_BUILD_DIR`、`REDIS_BIN_DIR` 有写权限即可，不依赖 sudo/root。

---

## 9. 运维建议

- 生产环境务必设置 `REDIS_PASSWORD`，且各节点间通信也已通过 `masterauth` 自动配置好。
- `appendonly yes` 已默认开启（AOF 持久化），如需同时开启 RDB 定时快照，可在各节点 `redis.conf` 中追加 `save` 规则。
- 建议对 `CLUSTER_HOME` 所在磁盘做好容量监控和定期备份。
- 系统层面建议按 Redis 官方推荐调整：`vm.overcommit_memory=1`、关闭 Transparent Huge Pages、适当调大 `ulimit -n`，脚本本身未包含这些系统级调优（需要 root 权限，请按需手动执行）。

---

## 10. 卸载

```bash
# 在每台机器上分别执行
./redis-cluster.sh clean
```

会先停止本机所有节点进程，再删除 `CLUSTER_HOME` 下本机负责的节点目录（配置、数据、日志一并删除），执行前会二次确认。
