#!/bin/bash

# ==============================================================================
# verify_redis_cluster.sh - 通用 Redis 集群状态验证脚本 (最终版)
#
# 功能:
#   - 动态、安全地验证任何 Redis 集群的状态。
#   - 检查集群整体状态、节点信息和槽位分配。
#   - 执行安全的读写和清理测试。
#
# 解决了:
#   1. 硬编码问题：通过命令行参数接收主机、端口和密码。
#   2. 密码警告问题：使用 REDISCLI_AUTH 环境变量代替 `-a` 参数，避免警告信息干扰输出。
#
# 使用方法:
#   ./verify_redis_cluster.sh <host> <port> [password]
#
# 示例:
#   # 无密码集群
#   ./verify_redis_cluster.sh 192.168.1.10 7000
#
#   # 有密码集群
#   ./verify_redis_cluster.sh 192.168.1.10 7000 my_secret_password
#
# ==============================================================================

# --- 颜色定义，用于美化输出 ---
GREEN=$(tput setaf 2)
YELLOW=$(tput setaf 3)
RED=$(tput setaf 1)
NC=$(tput sgr0) # No Color

# --- 函数定义 ---

# 打印使用方法并退出
usage() {
    echo "使用方法: $0 <host> <port> [password]"
    echo "示例: $0 192.168.1.10 7000 my_secret_password"
    exit 1
}

# 打印格式化的标题
print_header() {
    echo -e "\n${YELLOW}========== $1 ==========${NC}"
}

# --- 1. 参数校验和环境设置 ---
if [[ $# -lt 2 || $# -gt 3 ]]; then
    usage
fi

CLUSTER_HOST="$1"
CLUSTER_PORT="$2"
PASSWORD="$3"

# **核心解决方案：使用环境变量处理密码**
# 如果提供了密码，将其导出为 REDISCLI_AUTH 环境变量。
# 这可以避免 `redis-cli -a` 命令产生的警告，确保脚本解析输出的稳定性。
if [[ -n "$PASSWORD" ]]; then
    export REDISCLI_AUTH="$PASSWORD"
fi

# 脚本退出时自动清理环境变量
trap 'unset REDISCLI_AUTH' EXIT

# --- 2. 开始验证 ---

print_header "开始验证 Redis 集群: ${CLUSTER_HOST}:${CLUSTER_PORT}"

# 初始连接测试
echo -n "0. 测试与入口节点 ${CLUSTER_HOST}:${CLUSTER_PORT} 的连接... "
PING_RESULT=$(redis-cli -h "$CLUSTER_HOST" -p "$CLUSTER_PORT" ping 2>&1)
if [[ "$PING_RESULT" != "PONG" ]]; then
    echo "${RED}失败!${NC}"
    echo "错误信息: $PING_RESULT"
    echo "请检查主机、端口或密码是否正确。"
    exit 1
else
    echo "${GREEN}成功 (PONG)!${NC}"
fi

# 集群基本信息
print_header "1. 集群基本信息 (cluster info)"
redis-cli -h "$CLUSTER_HOST" -p "$CLUSTER_PORT" cluster info | sed 's/^/  /'

# 集群节点列表
print_header "2. 集群节点列表 (cluster nodes)"
redis-cli -h "$CLUSTER_HOST" -p "$CLUSTER_PORT" cluster nodes | sed 's/^/  /'

# 检查槽位分配情况
print_header "3. 槽位分配检查 (cluster slots)"
SLOTS_OUTPUT=$(redis-cli -h "$CLUSTER_HOST" -p "$CLUSTER_PORT" cluster slots)
echo "$SLOTS_OUTPUT" | sed 's/^/  /'
# 检查是否存在未分配的槽位，这通常表示集群配置不完整
if echo "$SLOTS_OUTPUT" | grep -q '\[.*-.*\] ->'; then
    echo "${RED}警告: 发现可能未分配的槽位，请仔细检查上面的输出。${NC}"
fi

# 各节点详细信息
print_header "4. 各节点详细信息"
# **核心解决方案：动态获取节点列表**
# 从 `cluster nodes` 的输出中解析出所有节点的 IP 和端口
NODE_LIST=$(redis-cli -h "$CLUSTER_HOST" -p "$CLUSTER_PORT" cluster nodes | awk '{print $2}' | sed 's/@.*//')

if [ -z "$NODE_LIST" ]; then
    echo "${RED}错误：无法获取节点列表。请检查集群状态。${NC}"
    exit 1
fi

for node in $NODE_LIST; do
    ip=$(echo "$node" | cut -d: -f1)
    port=$(echo "$node" | cut -d: -f2)

    echo "节点 ${GREEN}${ip}:${port}${NC}:"
    # 检查每个节点是否可达
    PING_STATUS=$(redis-cli -h "$ip" -p "$port" ping 2>/dev/null)

    if [ "$PING_STATUS" != "PONG" ]; then
        echo "  - 连接状态: ${RED}无法连接或认证失败${NC}"
    else
        NODE_INFO=$(redis-cli -h "$ip" -p "$port" info replication)
        MYID=$(redis-cli -h "$ip" -p "$port" cluster myid)
        echo "  - 连接状态: ${GREEN}正常 (PONG)${NC}"
        echo "  - 节点 ID  : $MYID"
        echo "  - 角色信息 : $(echo "$NODE_INFO" | grep "role:")"
    fi
    echo ""
done

# 数据读写测试
print_header "5. 数据读写测试 (自动清理)"
# 使用带时间戳的前缀，避免与现有数据冲突
KEY_PREFIX="verify_script_$(date +%s)"
echo "  - 写入 10 个测试键 (前缀: ${KEY_PREFIX}_)..."
for i in {1..10}; do
    # 使用 -c 参数，redis-cli 会自动处理 MOVED 重定向
    redis-cli -c -h "$CLUSTER_HOST" -p "$CLUSTER_PORT" SET "${KEY_PREFIX}_${i}" "value_${i}" > /dev/null
done
echo "    ${GREEN}写入完成。${NC}"

echo "  - 随机读取 3 个键进行验证..."
SUCCESS_COUNT=0
for i in 3 7 9; do
    VALUE=$(redis-cli -c -h "$CLUSTER_HOST" -p "$CLUSTER_PORT" GET "${KEY_PREFIX}_${i}")
    echo -n "    - 读取 ${KEY_PREFIX}_${i}: "
    if [[ "$VALUE" == "value_${i}" ]]; then
        echo "${GREEN}成功 (值: $VALUE)${NC}"
        ((SUCCESS_COUNT++))
    else
        echo "${RED}失败 (实际值: '$VALUE', 期望值: 'value_${i}')${NC}"
    fi
done

echo "  - 清理测试数据..."
# 使用 --scan 和 xargs 高效、安全地删除所有测试键
TEST_KEYS=$(redis-cli -c -h "$CLUSTER_HOST" -p "$CLUSTER_PORT" --scan --pattern "${KEY_PREFIX}_*")
if [[ -n "$TEST_KEYS" ]]; then
    echo "$TEST_KEYS" | xargs redis-cli -c -h "$CLUSTER_HOST" -p "$CLUSTER_PORT" DEL > /dev/null
    echo "    ${GREEN}清理完成。${NC}"
else
    echo "    ${YELLOW}未找到测试键，无需清理。${NC}"
fi

# 故障转移测试建议
print_header "6. 故障转移测试建议"
echo "  脚本已验证集群基本功能。如需测试高可用性，可手动执行以下操作:"
echo "  1. 查找一个 ${YELLOW}Master${NC} 节点及其 IP。"
echo "  2. 在该节点服务器上执行: ${RED}systemctl stop redis-server.service${NC} (或等效命令)"
echo "  3. 等待约 30 秒，让哨兵协议完成故障转移。"
echo "  4. 再次运行此脚本，观察原 Master 的 Slave 是否已提升为新的 Master。"

print_header "验证完成"
