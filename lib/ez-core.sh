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

# -----------------------------------------------------------------------------
# ez-hooks 钩子函数
# -----------------------------------------------------------------------------

# 检查任务是否有 ez-hooks
# 参数: $1 = Taskfile, $2 = 任务名, $3 = 钩子类型 (pre_run/post_run/on_error)
has_ez_hook() {
    local taskfile="$1"
    local task="$2"
    local hook_type="$3"
    local count
    count=$("$YQ" eval ".tasks.\"$task\".ez-hooks.$hook_type | length" "$taskfile" 2>/dev/null)
    [[ "$count" != "0" && "$count" != "null" && -n "$count" ]]
}

# 获取 ez-hooks 为 JSON
# 参数: $1 = Taskfile, $2 = 任务名, $3 = 钩子类型
get_ez_hooks_json() {
    local taskfile="$1"
    local task="$2"
    local hook_type="$3"
    "$YQ" eval -o=json ".tasks.\"$task\".ez-hooks.$hook_type // []" "$taskfile" 2>/dev/null
}

# 执行钩子
# 参数: $1 = Taskfile, $2 = 任务名, $3 = 钩子类型, $4 = 任务退出码, $5 = 任务输出(可选)
run_hooks() {
    local taskfile="$1"
    local task="$2"
    local hook_type="$3"
    local exit_code="${4:-0}"
    local task_output="${5:-}"

    if ! has_ez_hook "$taskfile" "$task" "$hook_type"; then
        return 0
    fi

    local hooks_json
    hooks_json=$(get_ez_hooks_json "$taskfile" "$task" "$hook_type")
    local count
    count=$(echo "$hooks_json" | "$YQ" eval 'length' -)

    echo -e "${BOLD}[ez-hooks:$hook_type]${NC}"
    for ((i=0; i<count; i++)); do
        local hook_name hook_script
        hook_name=$(echo "$hooks_json" | "$YQ" eval ".[$i].name // \"hook-$i\"" -)
        hook_script=$(echo "$hooks_json" | "$YQ" eval ".[$i].script // \"\"" -)

        if [[ -n "$hook_script" && "$hook_script" != "null" ]]; then
            echo -e "  ${CYAN}→ $hook_name${NC}"
            # 导出上下文供钩子使用
            export EZ_TASK_NAME="$task"
            export EZ_TASK_EXIT_CODE="$exit_code"
            export EZ_TASK_OUTPUT="$task_output"
            eval "$hook_script"
        fi
    done
}
