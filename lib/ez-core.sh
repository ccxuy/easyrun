#!/usr/bin/env bash
#
# EZ 核心函数库
# 所有 ez 命令共享的基础函数
#

# 获取 EZ 根目录
EZ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EZ_VERSION="0.8.0"

# 本地二进制路径
YQ="$EZ_ROOT/dep/yq"
TASK="$EZ_ROOT/dep/task"
YTT="$EZ_ROOT/dep/ytt"

# 日志目录
EZ_LOG_DIR="$EZ_ROOT/.ez-logs"

# -----------------------------------------------------------------------------
# 颜色定义
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# -----------------------------------------------------------------------------
# 日志系统
# -----------------------------------------------------------------------------

# 初始化日志目录
init_log_dir() {
    mkdir -p "$EZ_LOG_DIR"
}

# 生成日志文件路径
# 格式: .ez-logs/YYYYMMDD-HHMMSS_<task>_<run_id>.log
get_log_path() {
    local task_name="$1"
    local run_id="${2:-$(date +%s)}"
    local timestamp=$(date +%Y%m%d-%H%M%S)
    local safe_name=$(echo "$task_name" | tr '/:' '_')
    echo "$EZ_LOG_DIR/${timestamp}_${safe_name}_${run_id}.log"
}

# 写入日志头部
write_log_header() {
    local log_file="$1"
    local task_name="$2"
    local plan_name="${3:-}"
    local step_name="${4:-}"

    cat >> "$log_file" << EOF
================================================================================
EZ Task Execution Log
================================================================================
Task:      $task_name
Plan:      ${plan_name:--}
Step:      ${step_name:--}
Timestamp: $(date -Iseconds)
Host:      $(hostname)
User:      $(whoami)
PWD:       $(pwd)
================================================================================

EOF
}

# 写入日志尾部
write_log_footer() {
    local log_file="$1"
    local exit_code="$2"
    local duration="$3"

    cat >> "$log_file" << EOF

================================================================================
Exit Code: $exit_code
Duration:  ${duration}s
End Time:  $(date -Iseconds)
================================================================================
EOF
}

# 执行任务并记录日志
run_task_with_log() {
    local taskfile="$1"
    local task_name="$2"
    shift 2
    local task_vars=("$@")

    local plan_name="${EZ_CURRENT_PLAN:-}"
    local step_name="${EZ_CURRENT_STEP:-}"
    local run_id="${EZ_RUN_ID:-$(date +%s)}"

    init_log_dir
    local log_file
    log_file=$(get_log_path "$task_name" "$run_id")

    write_log_header "$log_file" "$task_name" "$plan_name" "$step_name"

    echo -e "  ${DIM}Log: $log_file${NC}"

    local start_time=$(date +%s)
    local exit_code=0

    # 执行任务并记录输出
    {
        echo "Command: $TASK -t $taskfile $task_name ${task_vars[*]}"
        echo ""
        "$TASK" -t "$taskfile" "$task_name" "${task_vars[@]}" 2>&1
    } | tee -a "$log_file"
    exit_code=${PIPESTATUS[0]}

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    write_log_footer "$log_file" "$exit_code" "$duration"

    # 创建符号链接便于查找最新日志
    ln -sf "$(basename "$log_file")" "$EZ_LOG_DIR/latest_${task_name//[:\/]/_}.log"

    return $exit_code
}

# 列出最近的日志
list_recent_logs() {
    local count="${1:-10}"
    init_log_dir

    echo -e "${BOLD}Recent logs in $EZ_LOG_DIR:${NC}"
    echo ""

    ls -1t "$EZ_LOG_DIR"/*.log 2>/dev/null | head -n "$count" | while read -r f; do
        local fname=$(basename "$f")
        local task=$(echo "$fname" | sed 's/^[0-9-]*_\([^_]*\)_.*/\1/')
        local size=$(du -h "$f" | cut -f1)
        printf "  ${GREEN}%-50s${NC} ${DIM}%s${NC}\n" "$fname" "$size"
    done
}

# 查看日志
show_log() {
    local pattern="$1"
    init_log_dir

    local log_file
    if [[ -f "$EZ_LOG_DIR/$pattern" ]]; then
        log_file="$EZ_LOG_DIR/$pattern"
    else
        log_file=$(ls -1t "$EZ_LOG_DIR"/*"$pattern"*.log 2>/dev/null | head -1)
    fi

    [[ -z "$log_file" || ! -f "$log_file" ]] && die "日志未找到: $pattern"

    cat "$log_file"
}

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
