#!/bin/bash

# 修改文件或目录时间戳的脚本
# 使用方法: ./modify_timestamps.sh [选项] <路径> [时间]

# 显示帮助信息
show_help() {
    echo "用法: $0 [选项] <路径> [时间]"
    echo ""
    echo "选项:"
    echo "  -h, --help          显示此帮助信息"
    echo "  -r, --recursive     递归处理目录下的所有文件和子目录"
    echo "  -a, --access        只修改访问时间"
    echo "  -m, --modify        只修改修改时间"
    echo "  -c, --create        修改创建时间(需要debugfs支持)"
    echo "  -f, --force         强制执行，不询问确认"
    echo ""
    echo "时间格式:"
    echo "  YYYY-MM-DD HH:MM:SS  例如: 2024-01-01 12:00:00"
    echo "  如果不指定时间，将使用当前时间"
    echo ""
    echo "示例:"
    echo "  $0 /path/to/file                           # 修改文件为当前时间"
    echo "  $0 /path/to/file '2024-01-01 12:00:00'     # 修改文件为指定时间"
    echo "  $0 -r /path/to/directory                   # 递归修改目录"
    echo "  $0 -m /path/to/file '2024-01-01 12:00:00'  # 只修改修改时间"
    echo "  $0 -c /path/to/file '2024-01-01 12:00:00'  # 修改创建时间"
}

# 默认参数
RECURSIVE=false
ACCESS_ONLY=false
MODIFY_ONLY=false
CREATE_TIME=false
FORCE=false
TARGET_PATH=""
TIMESTAMP=""

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -r|--recursive)
            RECURSIVE=true
            shift
            ;;
        -a|--access)
            ACCESS_ONLY=true
            shift
            ;;
        -m|--modify)
            MODIFY_ONLY=true
            shift
            ;;
        -c|--create)
            CREATE_TIME=true
            shift
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        -*)
            echo "错误: 未知选项 $1"
            echo "使用 -h 或 --help 查看帮助"
            exit 1
            ;;
        *)
            if [[ -z "$TARGET_PATH" ]]; then
                TARGET_PATH="$1"
            elif [[ -z "$TIMESTAMP" ]]; then
                TIMESTAMP="$1"
            else
                echo "错误: 参数过多"
                exit 1
            fi
            shift
            ;;
    esac
done

# 检查必需参数
if [[ -z "$TARGET_PATH" ]]; then
    echo "错误: 请指定目标路径"
    show_help
    exit 1
fi

# 检查路径是否存在
if [[ ! -e "$TARGET_PATH" ]]; then
    echo "错误: 路径 '$TARGET_PATH' 不存在"
    exit 1
fi

# 如果没有指定时间，使用当前时间
if [[ -z "$TIMESTAMP" ]]; then
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    echo "使用当前时间: $TIMESTAMP"
fi

# 验证时间格式
if ! date -d "$TIMESTAMP" >/dev/null 2>&1; then
    echo "错误: 时间格式无效: $TIMESTAMP"
    echo "请使用格式: YYYY-MM-DD HH:MM:SS"
    exit 1
fi

# 修改创建时间的函数（需要root权限和debugfs）
modify_create_time() {
    local file="$1"
    local timestamp="$2"
    
    # 检查是否有debugfs
    if ! command -v debugfs >/dev/null 2>&1; then
        echo "警告: debugfs 未安装，无法修改创建时间"
        return 1
    fi
    
    # 检查是否有root权限
    if [[ $EUID -ne 0 ]]; then
        echo "警告: 修改创建时间需要root权限"
        return 1
    fi
    
    # 获取文件系统设备
    local device=$(df "$file" | tail -1 | awk '{print $1}')
    local inode=$(stat -c %i "$file")
    
    # 转换时间格式为debugfs需要的格式
    local debug_time=$(date -d "$timestamp" '+%Y%m%d%H%M%S')
    
    echo "正在修改 $file 的创建时间..."
    echo "set_inode_field <$inode> crtime $debug_time" | debugfs -w "$device"
}

# 修改文件时间戳的函数
modify_timestamps() {
    local file="$1"
    local timestamp="$2"
    
    echo "正在处理: $file"
    
    # 构建touch命令参数
    local touch_args=""
    
    if [[ "$ACCESS_ONLY" == true ]]; then
        touch_args="-a"
    elif [[ "$MODIFY_ONLY" == true ]]; then
        touch_args="-m"
    fi
    
    # 修改访问时间和修改时间
    if [[ "$CREATE_TIME" == false ]]; then
        touch $touch_args -d "$timestamp" "$file"
        if [[ $? -eq 0 ]]; then
            echo "✓ 已更新时间戳: $file"
        else
            echo "✗ 更新失败: $file"
        fi
    fi
    
    # 修改创建时间
    if [[ "$CREATE_TIME" == true ]]; then
        modify_create_time "$file" "$timestamp"
    fi
}

# 递归处理目录的函数
process_directory() {
    local dir="$1"
    local timestamp="$2"
    
    # 首先处理目录本身
    modify_timestamps "$dir" "$timestamp"
    
    # 然后处理目录中的内容
    find "$dir" -mindepth 1 -print0 | while IFS= read -r -d '' item; do
        modify_timestamps "$item" "$timestamp"
    done
}

# 确认操作
if [[ "$FORCE" == false ]]; then
    echo "即将修改以下路径的时间戳:"
    echo "路径: $TARGET_PATH"
    echo "时间: $TIMESTAMP"
    echo "递归: $RECURSIVE"
    echo "只修改访问时间: $ACCESS_ONLY"
    echo "只修改修改时间: $MODIFY_ONLY"
    echo "修改创建时间: $CREATE_TIME"
    echo ""
    read -p "确认继续? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "操作已取消"
        exit 0
    fi
fi

# 执行操作
echo "开始修改时间戳..."
echo "=================="

if [[ -d "$TARGET_PATH" ]] && [[ "$RECURSIVE" == true ]]; then
    # 递归处理目录
    process_directory "$TARGET_PATH" "$TIMESTAMP"
elif [[ -d "$TARGET_PATH" ]]; then
    # 只处理目录本身
    modify_timestamps "$TARGET_PATH" "$TIMESTAMP"
else
    # 处理单个文件
    modify_timestamps "$TARGET_PATH" "$TIMESTAMP"
fi

echo "=================="
echo "操作完成!"

# 显示结果
echo ""
echo "当前时间戳信息:"
if [[ -d "$TARGET_PATH" ]]; then
    ls -la "$TARGET_PATH"
else
    ls -la "$TARGET_PATH"
fi
