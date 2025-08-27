#!/bin/bash

# Redis 哨兵状态检查和调试脚本
# 修复版本 - 解决无法显示 slave 和 sentinel 节点的问题

HOST="127.0.0.1"
PORT="6379"
PASSWORD=""
SENTINEL_PORT=""

# 颜色定义
COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[1;33m'
COLOR_RED='\033[0;31m'
COLOR_BLUE='\033[0;34m'
COLOR_RESET='\033[0m'

usage() {
    echo "使用方法: $0 [-h <host>] [-p <port>] [-a <password>] [-s <sentinel_port>] [-d]"
    echo "  -h: Redis 服务器地址 (默认: 127.0.0.1)"
    echo "  -p: Redis 数据节点端口 (默认: 6379)"
    echo "  -a: Redis 密码"
    echo "  -s: 指定哨兵端口直接查询哨兵集群"
    echo "  -d: 调试模式，显示原始输出"
    exit 1
}

DEBUG_MODE=false

# 解析命令行参数
while getopts "h:p:a:s:d" opt; do
    case ${opt} in
        h) HOST=$OPTARG ;;
        p) PORT=$OPTARG ;;
        a) PASSWORD=$OPTARG ;;
        s) SENTINEL_PORT=$OPTARG ;;
        d) DEBUG_MODE=true ;;
        *) usage ;;
    esac
done

# 构建 redis-cli 命令
REDIS_CMD="redis-cli"
if [ -n "$HOST" ]; then
    REDIS_CMD="$REDIS_CMD -h $HOST"
fi
if [ -n "$PASSWORD" ]; then
    export REDISCLI_AUTH="$PASSWORD"
fi

check_connection() {
    local target_port=$1
    local output
    output=$($REDIS_CMD -p "$target_port" PING 2>&1)
    if [[ "$output" != "PONG" ]]; then
        echo -e "${COLOR_RED}无法连接到 Redis ($HOST:$target_port): $output${COLOR_RESET}"
        exit 1
    fi
    echo -e "${COLOR_GREEN}成功连接到 Redis ($HOST:$target_port)${COLOR_RESET}"
}

# 修复后的节点信息提取函数 - 处理简单列表格式
extract_node_info() {
    local raw_data="$1"
    local node_type="$2"
    
    if [ "$DEBUG_MODE" = true ]; then
        echo -e "\n${COLOR_BLUE}=== 调试: ${node_type} 原始数据 ===${COLOR_RESET}"
        echo "$raw_data"
        echo -e "${COLOR_BLUE}=== 调试结束 ===${COLOR_RESET}\n"
    fi
    
    # 新的解析逻辑：处理Redis哨兵的简单列表输出格式
    echo "$raw_data" | awk '
    BEGIN { 
        name = ""
        ip = ""
        port = ""
        node_count = 0
    }
    
    # 当遇到 "name" 时，下一行就是名称
    /^name$/ {
        getline
        name = $0
        next
    }
    
    # 当遇到 "ip" 时，下一行就是IP
    /^ip$/ {
        getline
        ip = $0
        next
    }
    
    # 当遇到 "port" 时，下一行就是端口，并且可以输出这个节点
    /^port$/ {
        getline
        port = $0
        # 输出节点信息
        if (ip != "" && port != "") {
            printf "  - %s:%s", ip, port
            if (name != "" && name != ip ":" port) {
                printf " (%s)", name
            }
            printf "\n"
            node_count++
        }
        # 重置变量准备下一个节点
        name = ""
        ip = ""
        port = ""
        next
    }
    
    END {
        if (node_count == 0) {
            print "  - 未发现节点"
        }
    }'
}

check_sentinel() {
    echo -e "\n${COLOR_BLUE}--- 正在检查哨兵 (Sentinel) 模式 ---${COLOR_RESET}"
    check_connection "$SENTINEL_PORT"
    
    echo -e "${COLOR_YELLOW}模式判断: 哨兵 (Sentinel) 模式${COLOR_RESET}"

    # 获取所有master名称
    local masters_raw=$($REDIS_CMD -p "$SENTINEL_PORT" SENTINEL masters 2>/dev/null)
    if [ -z "$masters_raw" ]; then
        echo -e "${COLOR_RED}错误: 在 $HOST:$SENTINEL_PORT 上未找到任何被监控的 Master.${COLOR_RESET}"
        exit 1
    fi

    # 提取master名称
    local master_names=$(echo "$masters_raw" | awk '
        /^[[:space:]]*[0-9]+\)[[:space:]]*"name"[[:space:]]*$/ {
            getline
            if ($0 ~ /^[[:space:]]*[0-9]+\)[[:space:]]*".*"[[:space:]]*$/) {
                name = $0
                gsub(/^[[:space:]]*[0-9]+\)[[:space:]]*"/, "", name)
                gsub(/"[[:space:]]*$/, "", name)
                print name
            }
        }')

    for master_name in $master_names; do
        echo -e "\n${COLOR_YELLOW}监控组: ${master_name}${COLOR_RESET}"
        echo "----------------------------------------"
        
        # 获取master地址
        master_info=$($REDIS_CMD -p "$SENTINEL_PORT" SENTINEL get-master-addr-by-name "$master_name")
        master_ip=$(echo "$master_info" | head -n 1)
        master_port=$(echo "$master_info" | tail -n 1)
        echo -e "${COLOR_GREEN}[Master 节点]${COLOR_RESET}"
        printf "  - %s:%s\n" "$master_ip" "$master_port"

        # 获取slave节点信息
        echo -e "${COLOR_GREEN}[Slave 节点]${COLOR_RESET}"
        local slaves_raw=$($REDIS_CMD -p "$SENTINEL_PORT" SENTINEL slaves "$master_name" 2>/dev/null)
        if [ -n "$slaves_raw" ]; then
            extract_node_info "$slaves_raw" "SLAVE"
        else
            echo "  - 未发现slave节点"
        fi

        # 获取sentinel节点信息
        echo -e "${COLOR_GREEN}[Sentinel 节点]${COLOR_RESET}"
        local sentinels_raw=$($REDIS_CMD -p "$SENTINEL_PORT" SENTINEL sentinels "$master_name" 2>/dev/null)
        if [ -n "$sentinels_raw" ]; then
            extract_node_info "$sentinels_raw" "SENTINEL"
        else
            echo "  - 未发现其他sentinel节点"
        fi
        
        # 显示当前sentinel节点自己
        echo "  - $HOST:$SENTINEL_PORT (当前连接的节点)"
    done
}

check_standalone_or_replication() {
    local target_port=$1
    echo -e "\n${COLOR_BLUE}--- 正在检查单机/主从模式 ---${COLOR_RESET}"
    local info=$($REDIS_CMD -p "$target_port" INFO)
    local role=$(echo "$info" | grep -w "role" | cut -d: -f2 | tr -d '\r')
    local connected_slaves=$(echo "$info" | grep -w "connected_slaves" | cut -d: -f2 | tr -d '\r')
    local redis_version=$(echo "$info" | grep -w "redis_version" | cut -d: -f2 | tr -d '\r')
    local uptime_in_days=$(echo "$info" | grep -w "uptime_in_days" | cut -d: -f2 | tr -d '\r')
    local connected_clients=$(echo "$info" | grep -w "connected_clients" | cut -d: -f2 | tr -d '\r')
    local used_memory_human=$(echo "$info" | grep -w "used_memory_human" | cut -d: -f2 | tr -d '\r')
    
    echo -e "${COLOR_YELLOW}模式判断: 主从复制模式 或 单机模式${COLOR_RESET}"
    echo "----------------------------------------"
    printf "%-20s : %s\n" "Redis 版本" "$redis_version"
    printf "%-20s : %s 天\n" "运行时间" "$uptime_in_days"
    printf "%-20s : %s\n" "已连接客户端" "$connected_clients"
    printf "%-20s : %s\n" "使用内存" "$used_memory_human"
    printf "%-20s : %s\n" "当前节点角色" "$(echo "$role" | tr 'a-z' 'A-Z')"
    echo "----------------------------------------"
    
    if [ "$role" == "master" ]; then
        echo -e "${COLOR_YELLOW}节点角色: MASTER${COLOR_RESET}"
        if [ "$connected_slaves" -gt 0 ]; then
            echo -e "发现 ${connected_slaves} 个从节点:"
            echo "$info" | grep "^slave" | sed 's/,/ /g' | awk '{ 
                for(i=1;i<=NF;i++){ 
                    if($i ~ "ip=") {
                        gsub("ip=", "", $i)
                        ip = $i
                    }
                    if($i ~ "port=") {
                        gsub("port=", "", $i)
                        port = $i
                        printf "  - %s:%s\n", ip, port
                    }
                } 
            }'
        else
            echo "这是一个 ${COLOR_GREEN}单机模式${COLOR_RESET} 的 Master 节点 (没有从节点)."
        fi
    elif [ "$role" == "slave" ]; then
        local master_host=$(echo "$info" | grep "master_host" | cut -d: -f2 | tr -d '\r')
        local master_port=$(echo "$info" | grep "master_port" | cut -d: -f2 | tr -d '\r')
        local master_link_status=$(echo "$info" | grep "master_link_status" | cut -d: -f2 | tr -d '\r')
        echo -e "${COLOR_YELLOW}节点角色: SLAVE${COLOR_RESET}"
        printf "  - 主节点地址: %s:%s\n" "$master_host" "$master_port"
        printf "  - 主从同步状态: "
        if [ "$master_link_status" == "up" ]; then
            echo -e "${COLOR_GREEN}UP (正常)${COLOR_RESET}"
        else
            echo -e "${COLOR_RED}DOWN (异常)${COLOR_RESET}"
        fi
    fi
}

check_cluster() {
    local target_port=$1
    echo -e "\n${COLOR_BLUE}--- 正在检查集群 (Cluster) 模式 ---${COLOR_RESET}"
    local cluster_nodes_output=$($REDIS_CMD -p "$target_port" -c CLUSTER NODES 2>/dev/null)
    if [ -z "$cluster_nodes_output" ]; then
        echo -e "${COLOR_RED}获取集群节点信息失败. 请检查连接和权限.${COLOR_RESET}"
        return
    fi
    echo -e "${COLOR_YELLOW}模式判断: 集群 (Cluster) 模式${COLOR_RESET}"
    echo "-----------------------------------------------------------------------------------------------------"
    printf "%-42s %-22s %-10s %-12s %s\n" "节点 ID" "地址" "角色" "状态" "哈希槽 (Slots)"
    echo "-----------------------------------------------------------------------------------------------------"
    echo "$cluster_nodes_output" | while read -r line; do
        address=$(echo "$line" | awk '{print $2}' | sed 's/@.*//')
        if ! [[ "$address" == *":"* ]]; then 
            address=$(echo "$line" | awk '{print $2}' | cut -d'@' -f1)
        fi
        id=$(echo "$line" | awk '{print $1}')
        flags=$(echo "$line" | awk '{print $3}')
        status=$(echo "$line" | awk '{print $8}')
        slots=$(echo "$line" | awk '{$1=$2=$3=$4=$5=$6=$7=$8=""; print $0}' | sed 's/^[ \t]*//')
        
        if [[ "$flags" == *"master"* ]]; then 
            role="MASTER"
        elif [[ "$flags" == *"slave"* ]]; then 
            role="SLAVE"
        else 
            role="UNKNOWN"
        fi
        
        local status_color
        if [ "$status" == "connected" ]; then 
            status_color=$COLOR_GREEN
        else 
            status_color=$COLOR_RED
        fi
        
        printf "%-42s %-22s %-10s ${status_color}%-12s${COLOR_RESET} %s\n" "$id" "$address" "$role" "$status" "$slots"
    done
    echo "-----------------------------------------------------------------------------------------------------"
}

# 修复后的哨兵检查函数
check_sentinel() {
    echo -e "\n${COLOR_BLUE}--- 正在检查哨兵 (Sentinel) 模式 ---${COLOR_RESET}"
    check_connection "$SENTINEL_PORT"
    
    echo -e "${COLOR_YELLOW}模式判断: 哨兵 (Sentinel) 模式${COLOR_RESET}"

    # 获取所有master
    local masters_raw=$($REDIS_CMD -p "$SENTINEL_PORT" SENTINEL masters 2>/dev/null)
    if [ -z "$masters_raw" ]; then
        echo -e "${COLOR_RED}错误: 在 $HOST:$SENTINEL_PORT 上未找到任何被监控的 Master.${COLOR_RESET}"
        exit 1
    fi

    # 提取master名称（修复版本 - 处理简单列表格式）
    local master_names=$(echo "$masters_raw" | awk '
        /^name$/ { 
            getline
            print $0
        }')

    if [ "$DEBUG_MODE" = true ]; then
        echo -e "${COLOR_BLUE}=== 调试: 发现的Master名称 ===${COLOR_RESET}"
        echo "Master names: [$master_names]"
        echo -e "${COLOR_BLUE}=== 调试结束 ===${COLOR_RESET}\n"
    fi

    for master_name in $master_names; do
        echo -e "\n${COLOR_YELLOW}监控组: ${master_name}${COLOR_RESET}"
        echo "----------------------------------------"
        
        # 获取master地址
        master_info=$($REDIS_CMD -p "$SENTINEL_PORT" SENTINEL get-master-addr-by-name "$master_name" 2>/dev/null)
        master_ip=$(echo "$master_info" | head -n 1)
        master_port=$(echo "$master_info" | tail -n 1)
        
        echo -e "${COLOR_GREEN}[Master 节点]${COLOR_RESET}"
        if [ -n "$master_ip" ] && [ -n "$master_port" ]; then
            printf "  - %s:%s\n" "$master_ip" "$master_port"
        else
            echo "  - 无法获取Master地址信息"
        fi

        # 获取slave节点
        echo -e "${COLOR_GREEN}[Slave 节点]${COLOR_RESET}"
        local slaves_raw=$($REDIS_CMD -p "$SENTINEL_PORT" SENTINEL slaves "$master_name" 2>/dev/null)
        if [ -n "$slaves_raw" ]; then
            if [ "$DEBUG_MODE" = true ]; then
                echo -e "${COLOR_BLUE}=== 调试: Slaves原始数据 ===${COLOR_RESET}"
                echo "$slaves_raw"
                echo -e "${COLOR_BLUE}=== 调试结束 ===${COLOR_RESET}"
            fi
            extract_node_info "$slaves_raw" "SLAVE"
        else
            echo "  - 未发现slave节点"
        fi

        # 获取其他sentinel节点
        echo -e "${COLOR_GREEN}[Sentinel 节点]${COLOR_RESET}"
        local sentinels_raw=$($REDIS_CMD -p "$SENTINEL_PORT" SENTINEL sentinels "$master_name" 2>/dev/null)
        if [ -n "$sentinels_raw" ]; then
            if [ "$DEBUG_MODE" = true ]; then
                echo -e "${COLOR_BLUE}=== 调试: Sentinels原始数据 ===${COLOR_RESET}"
                echo "$sentinels_raw"
                echo -e "${COLOR_BLUE}=== 调试结束 ===${COLOR_RESET}"
            fi
            extract_node_info "$sentinels_raw" "SENTINEL"
        else
            echo "  - 未发现其他sentinel节点"
        fi
        
        # 显示当前连接的sentinel节点
        echo "  - $HOST:$SENTINEL_PORT (当前连接的节点)"
    done
}

# 主逻辑
main() {
    if [ -n "$SENTINEL_PORT" ]; then
        check_sentinel
        exit 0
    fi
    
    check_connection "$PORT"
    
    local info=$($REDIS_CMD -p "$PORT" INFO)
    local cluster_enabled=$(echo "$info" | grep -w "cluster_enabled" | cut -d: -f2 | tr -d '\r')
    
    if [ "$cluster_enabled" == "1" ]; then
        check_cluster "$PORT"
    else
        check_standalone_or_replication "$PORT"
        echo -e "\n${COLOR_YELLOW}提示: 如果这是一个由 Sentinel 管理的集群, 请使用 -s <sentinel_port> 参数来获取详细的哨兵和主从信息.${COLOR_RESET}"
    fi
}

# 执行脚本
main
