#!/usr/bin/env bash
#
# EZ 核心函数库
# 所有 ez 命令共享的基础函数
#

# 获取 EZ 根目录
EZ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EZ_VERSION="0.1.0"

# 本地二进制路径
YQ="$EZ_ROOT/dep/yq"
TASK="$EZ_ROOT/dep/task"

# -----------------------------------------------------------------------------
# 颜色定义
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# -----------------------------------------------------------------------------
# 错误处理
# -----------------------------------------------------------------------------
die() {
    echo -e "${RED}error:${NC} $*" >&2
    exit 1
}

warn() {
    echo -e "${YELLOW}warn:${NC} $*" >&2
}

info() {
    echo -e "${CYAN}info:${NC} $*"
}

# -----------------------------------------------------------------------------
# 依赖检查
# -----------------------------------------------------------------------------
check_deps() {
    [[ -x "$YQ" ]] || die "yq 未找到，请运行: ./dep/install-deps.sh"
    [[ -x "$TASK" ]] || die "task 未找到，请运行: ./dep/install-deps.sh"
}

# -----------------------------------------------------------------------------
# Taskfile 查找
# -----------------------------------------------------------------------------

# 在指定目录查找 Taskfile
# 返回: Taskfile 路径，未找到返回 1
find_taskfile() {
    local dir="${1:-.}"
    local file
    for file in "Taskfile.yml" "Taskfile.yaml" "taskfile.yml" "taskfile.yaml"; do
        if [[ -f "$dir/$file" ]]; then
            echo "$dir/$file"
            return 0
        fi
    done
    return 1
}

# -----------------------------------------------------------------------------
# YAML 查询函数 (基于 yq)
# -----------------------------------------------------------------------------

# 获取所有任务名称
# 参数: $1 = Taskfile 路径
get_tasks() {
    local taskfile="$1"
    "$YQ" eval '.tasks | keys | .[]' "$taskfile" 2>/dev/null || true
}

# 获取任务的指定属性
# 参数: $1 = Taskfile, $2 = 任务名, $3 = 属性名
get_task_prop() {
    local taskfile="$1"
    local task="$2"
    local prop="$3"
    "$YQ" eval ".tasks.\"$task\".$prop // \"\"" "$taskfile" 2>/dev/null
}

# 检查任务是否有 ez-params
# 参数: $1 = Taskfile, $2 = 任务名
# 返回: 0 = 有参数, 1 = 无参数
has_ez_params() {
    local taskfile="$1"
    local task="$2"
    local count
    count=$("$YQ" eval ".tasks.\"$task\".ez-params | length" "$taskfile" 2>/dev/null)
    [[ "$count" != "0" && "$count" != "null" && -n "$count" ]]
}

# 获取 ez-params 为 JSON 格式
# 参数: $1 = Taskfile, $2 = 任务名
get_ez_params_json() {
    local taskfile="$1"
    local task="$2"
    "$YQ" eval -o=json ".tasks.\"$task\".ez-params // []" "$taskfile" 2>/dev/null
}
