#!/usr/bin/env bash
#
# EZ 核心函数库
# 所有 ez 命令共享的基础函数
#

# 获取 EZ 根目录
EZ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EZ_VERSION="1.4.0-beta"

# 本地二进制路径
YQ="$EZ_ROOT/dep/yq"
TASK="$EZ_ROOT/dep/task"
YTT="$EZ_ROOT/dep/ytt"

# -----------------------------------------------------------------------------
# 核心术语 (详见 DESIGN.md)
# -----------------------------------------------------------------------------
# Task      任务    EZ 的核心单元，go-task task 的超集
#   - 行内任务: 定义在根 Taskfile.yml 中
#   - 文件夹任务: tasks/<name>/ 自包含目录，含 Taskfile.yml + task.yml
# Plan      计划    多 Task 的编排，可编译为 Taskfile
# Step      步骤    Plan 内的单个环节
# Artifact  产物    Task 的输出文件，可被下游 Task 引用
# Workspace 工作区  隔离的执行目录，防止污染源码
#
# 生命周期: pending → running → success / failed

# -----------------------------------------------------------------------------
# 目录常量
# -----------------------------------------------------------------------------
# .ez/ 统一运行时目录（v1.4: 按粒度组织）
EZ_DIR="$EZ_ROOT/.ez"
EZ_WORKSPACE_DIR="$EZ_DIR/workspace"
EZ_STATE_DIR="$EZ_DIR/state"
EZ_LOG_DIR="$EZ_DIR/logs"
EZ_ARTIFACTS_DIR="$EZ_DIR/artifacts"

# tasks/ 文件夹任务目录
EZ_TASKS_DIR="$EZ_ROOT/tasks"

# plans/ 计划目录
EZ_PLANS_DIR="$EZ_ROOT/plans"

# -----------------------------------------------------------------------------
# 颜色定义
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
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
# 格式: .ez/tasks/<name>/logs/YYYYMMDD-HHMMSS_<task>_<run_id>.log (文件夹任务模式)
#    或: .ez/logs/YYYYMMDD-HHMMSS_<task>_<run_id>.log (全局模式)
get_log_path() {
    local task_name="$1"
    local run_id="${2:-$(date +%s)}"
    local folder_name="${3:-}"  # 可选: 关联的文件夹任务名称
    local timestamp=$(date +%Y%m%d-%H%M%S)
    local safe_name=$(echo "$task_name" | tr '/:' '_')

    local log_dir
    if [[ -n "$folder_name" ]]; then
        log_dir=$(get_task_log_dir "$folder_name")
    else
        log_dir="$EZ_LOG_DIR"
        mkdir -p "$log_dir"
    fi
    echo "$log_dir/${timestamp}_${safe_name}_${run_id}.log"
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

# 检查任务是否存在（根 Taskfile 或 tasks/ 文件夹）
# 参数: $1 = Taskfile 路径, $2 = 任务名
# 返回: 0 = 存在, 1 = 不存在
task_exists() {
    local taskfile="$1"
    local task="$2"

    # 1. 检查根 Taskfile 中的任务
    local exists
    exists=$("$YQ" eval ".tasks.\"$task\" // \"\"" "$taskfile" 2>/dev/null)
    if [[ -n "$exists" && "$exists" != "null" ]]; then
        return 0
    fi

    # 2. 检查 tasks/ 文件夹任务
    if is_folder_task "$task"; then
        return 0
    fi

    return 1
}

# 检查是否是文件夹任务 (tasks/ 目录下的子文件夹)
# 参数: $1 = 名称
# 返回: 0 = 是文件夹任务, 1 = 不是
is_folder_task() {
    local name="$1"
    [[ -d "$EZ_TASKS_DIR/$name" && -f "$EZ_TASKS_DIR/$name/Taskfile.yml" ]]
}

# 发现所有任务：根 Taskfile + tasks/ 子文件夹
# 参数: $1 = 根目录 (可选, 默认 ".")
# 输出: 每行一个任务名，文件夹任务后缀 \t[folder]
discover_tasks() {
    local root="${1:-.}"

    # 1. 根 Taskfile 中的任务
    local taskfile
    if taskfile=$(find_taskfile "$root"); then
        while IFS= read -r name; do
            [[ -n "$name" ]] && echo "$name"
        done < <(get_tasks "$taskfile")
    fi

    # 2. tasks/ 目录中的文件夹任务
    if [[ -d "$EZ_TASKS_DIR" ]]; then
        for dir in "$EZ_TASKS_DIR"/*/; do
            [[ ! -d "$dir" ]] && continue
            if [[ -f "$dir/Taskfile.yml" || -f "$dir/Taskfile.yaml" ]]; then
                local name
                name=$(basename "$dir")
                echo "${name}\t[folder]"
            fi
        done
    fi
}

# 获取文件夹任务列表（仅返回名称）
get_folder_tasks() {
    if [[ -d "$EZ_TASKS_DIR" ]]; then
        for dir in "$EZ_TASKS_DIR"/*/; do
            [[ ! -d "$dir" ]] && continue
            if [[ -f "$dir/Taskfile.yml" || -f "$dir/Taskfile.yaml" ]]; then
                basename "$dir"
            fi
        done
    fi
}

# -----------------------------------------------------------------------------
# 按粒度组织的目录 (v1.4)
# -----------------------------------------------------------------------------

# 获取文件夹任务的运行时目录
# 参数: $1 = 任务名称
# 返回: .ez/tasks/<name>/
get_task_runtime_dir() {
    local name="$1"
    echo "$EZ_DIR/tasks/$name"
}

# 获取文件夹任务的日志目录
get_task_log_dir() {
    local name="$1"
    local dir="$EZ_DIR/tasks/$name/logs"
    mkdir -p "$dir"
    echo "$dir"
}

# 获取文件夹任务的 workspace 目录
get_task_workspace_dir() {
    local name="$1"
    echo "$EZ_DIR/tasks/$name/workspace"
}

# 获取文件夹任务的产物目录
get_task_artifacts_dir() {
    local name="$1"
    local dir="$EZ_DIR/tasks/$name/artifacts"
    mkdir -p "$dir"
    echo "$dir"
}

# 获取 Plan 的运行时目录
# 参数: $1 = plan 名称
# 返回: .ez/plans/<name>/
get_plan_dir() {
    local name="$1"
    echo "$EZ_DIR/plans/$name"
}

# 获取 Plan 的编译输出目录
get_plan_build_dir() {
    local name="$1"
    local dir="$EZ_DIR/plans/$name/build"
    mkdir -p "$dir"
    echo "$dir"
}

# 获取 Plan 的日志目录
get_plan_log_dir() {
    local name="$1"
    local dir="$EZ_DIR/plans/$name/logs"
    mkdir -p "$dir"
    echo "$dir"
}

# 清理 Task 或 Plan 的运行时数据
# 参数: $1 = 名称, $2 = 类型 (task|plan|all)
ez_clean() {
    local name="$1"
    local type="${2:-task}"

    case "$type" in
        task)
            rm -rf "$EZ_DIR/tasks/$name"
            ;;
        plan)
            rm -rf "$EZ_DIR/plans/$name"
            ;;
        all)
            rm -rf "$EZ_DIR"
            ;;
    esac
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
# ez-extends 任务继承
# -----------------------------------------------------------------------------

# 检查任务是否有继承
has_ez_extends() {
    local taskfile="$1"
    local task="$2"
    local extends
    extends=$("$YQ" eval ".tasks.\"$task\".ez-extends // \"\"" "$taskfile" 2>/dev/null)
    [[ -n "$extends" && "$extends" != "null" ]]
}

# 获取继承的基础任务名
get_ez_extends() {
    local taskfile="$1"
    local task="$2"
    "$YQ" eval ".tasks.\"$task\".ez-extends // \"\"" "$taskfile" 2>/dev/null
}

# 获取任务的默认参数值 (ez-defaults)
get_ez_defaults_json() {
    local taskfile="$1"
    local task="$2"
    "$YQ" eval -o=json ".tasks.\"$task\".ez-defaults // {}" "$taskfile" 2>/dev/null
}

# 解析继承链，获取合并后的参数
# 返回合并后的 ez-params JSON (子任务覆盖父任务)
resolve_inherited_params() {
    local taskfile="$1"
    local task="$2"

    if has_ez_extends "$taskfile" "$task"; then
        local base_task
        base_task=$(get_ez_extends "$taskfile" "$task")

        # 获取基础任务参数
        local base_params
        base_params=$(get_ez_params_json "$taskfile" "$base_task")

        # 获取当前任务的 ez-defaults 来覆盖默认值
        local defaults
        defaults=$(get_ez_defaults_json "$taskfile" "$task")

        # 合并默认值到参数
        if [[ "$defaults" != "{}" && "$defaults" != "null" ]]; then
            # 遍历默认值，更新参数的 default 字段
            while IFS= read -r key; do
                [[ -z "$key" ]] && continue
                local val
                val=$(echo "$defaults" | "$YQ" eval ".$key" -)
                # 更新参数列表中对应参数的 default
                local param_name="${key#EZ_}"
                param_name=$(echo "$param_name" | tr '[:upper:]' '[:lower:]')
                base_params=$(echo "$base_params" | "$YQ" eval "(.[] | select(.name == \"$param_name\") | .default) = \"$val\"" -)
            done < <(echo "$defaults" | "$YQ" eval 'keys | .[]' -)
        fi

        echo "$base_params"
    else
        get_ez_params_json "$taskfile" "$task"
    fi
}

# 获取继承后的命令
resolve_inherited_cmds() {
    local taskfile="$1"
    local task="$2"

    if has_ez_extends "$taskfile" "$task"; then
        local base_task
        base_task=$(get_ez_extends "$taskfile" "$task")
        # 使用基础任务的命令
        "$YQ" eval -o=json ".tasks.\"$base_task\".cmds // []" "$taskfile" 2>/dev/null
    else
        "$YQ" eval -o=json ".tasks.\"$task\".cmds // []" "$taskfile" 2>/dev/null
    fi
}

# -----------------------------------------------------------------------------
# ez-compose 任务组合
# -----------------------------------------------------------------------------

# 检查任务是否是组合任务
has_ez_compose() {
    local taskfile="$1"
    local task="$2"
    local count
    count=$("$YQ" eval ".tasks.\"$task\".ez-compose | length" "$taskfile" 2>/dev/null)
    [[ "$count" != "0" && "$count" != "null" && -n "$count" ]]
}

# 获取组合任务列表
get_ez_compose_json() {
    local taskfile="$1"
    local task="$2"
    "$YQ" eval -o=json ".tasks.\"$task\".ez-compose // []" "$taskfile" 2>/dev/null
}

# -----------------------------------------------------------------------------
# ez-log 自定义日志路径
# -----------------------------------------------------------------------------

# 检查任务是否有自定义日志配置
has_ez_log() {
    local taskfile="$1"
    local task="$2"
    local log_dir
    log_dir=$("$YQ" eval ".tasks.\"$task\".ez-log.dir // \"\"" "$taskfile" 2>/dev/null)
    [[ -n "$log_dir" && "$log_dir" != "null" ]]
}

# 获取任务的日志目录
get_ez_log_dir() {
    local taskfile="$1"
    local task="$2"
    local log_dir
    log_dir=$("$YQ" eval ".tasks.\"$task\".ez-log.dir // \"\"" "$taskfile" 2>/dev/null)
    if [[ -n "$log_dir" && "$log_dir" != "null" ]]; then
        echo "$EZ_ROOT/$log_dir"
    else
        echo "$EZ_LOG_DIR"
    fi
}

# 获取任务的日志前缀
get_ez_log_prefix() {
    local taskfile="$1"
    local task="$2"
    local prefix
    prefix=$("$YQ" eval ".tasks.\"$task\".ez-log.prefix // \"\"" "$taskfile" 2>/dev/null)
    if [[ -n "$prefix" && "$prefix" != "null" ]]; then
        echo "$prefix"
    else
        echo "$task"
    fi
}

# 获取任务的日志路径 (考虑自定义配置)
get_task_log_path() {
    local taskfile="$1"
    local task="$2"
    local run_id="${3:-$(date +%s)}"

    local log_dir log_prefix timestamp
    log_dir=$(get_ez_log_dir "$taskfile" "$task")
    log_prefix=$(get_ez_log_prefix "$taskfile" "$task")
    timestamp=$(date +%Y%m%d-%H%M%S)

    mkdir -p "$log_dir"
    echo "$log_dir/${timestamp}_${log_prefix}_${run_id}.log"
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

# -----------------------------------------------------------------------------
# ez-remote 远程执行
# -----------------------------------------------------------------------------

# 检查任务是否有远程配置
has_ez_remote() {
    local taskfile="$1"
    local task="$2"
    local remote
    remote=$("$YQ" eval ".tasks.\"$task\".ez-remote // \"\"" "$taskfile" 2>/dev/null)
    [[ -n "$remote" && "$remote" != "null" ]]
}

# 获取远程配置
get_ez_remote_json() {
    local taskfile="$1"
    local task="$2"
    "$YQ" eval -o=json ".tasks.\"$task\".ez-remote // {}" "$taskfile" 2>/dev/null
}

# 获取远程节点列表
get_ez_remote_nodes() {
    local taskfile="$1"
    local task="$2"
    "$YQ" eval ".tasks.\"$task\".ez-remote.nodes[]" "$taskfile" 2>/dev/null
}

# -----------------------------------------------------------------------------
# ez-artifacts 产物管理
# -----------------------------------------------------------------------------

# 检查任务是否有产物定义
has_ez_artifacts() {
    local taskfile="$1"
    local task="$2"
    local count
    count=$("$YQ" eval ".tasks.\"$task\".ez-artifacts | length" "$taskfile" 2>/dev/null)
    [[ "$count" != "0" && "$count" != "null" && -n "$count" ]]
}

# 获取产物定义
get_ez_artifacts_json() {
    local taskfile="$1"
    local task="$2"
    "$YQ" eval -o=json ".tasks.\"$task\".ez-artifacts // {}" "$taskfile" 2>/dev/null
}

# 检查任务是否有输入依赖
has_ez_inputs() {
    local taskfile="$1"
    local task="$2"
    local count
    count=$("$YQ" eval ".tasks.\"$task\".ez-inputs | length" "$taskfile" 2>/dev/null)
    [[ "$count" != "0" && "$count" != "null" && -n "$count" ]]
}

# 获取输入依赖
get_ez_inputs_json() {
    local taskfile="$1"
    local task="$2"
    "$YQ" eval -o=json ".tasks.\"$task\".ez-inputs // []" "$taskfile" 2>/dev/null
}

# 初始化产物目录
init_artifacts_dir() {
    local run_id="${1:-$(date +%Y%m%d-%H%M%S)}"
    local folder_name="${2:-}"  # 可选: 关联的文件夹任务名称

    local artifact_dir
    if [[ -n "$folder_name" ]]; then
        artifact_dir=$(get_task_artifacts_dir "$folder_name")
        artifact_dir="$artifact_dir/$run_id"
    else
        artifact_dir="$EZ_ARTIFACTS_DIR/$run_id"
    fi
    mkdir -p "$artifact_dir"
    echo "$artifact_dir"
}

# 保存产物
save_artifact() {
    local artifact_dir="$1"
    local name="$2"
    local source_path="$3"

    if [[ ! -e "$source_path" ]]; then
        warn "产物不存在: $source_path"
        return 1
    fi

    local target="$artifact_dir/$name"
    if [[ -d "$source_path" ]]; then
        cp -r "$source_path" "$target"
    else
        cp "$source_path" "$target"
    fi
    echo "$target"
}

# 获取产物
get_artifact() {
    local artifact_dir="$1"
    local name="$2"
    local target_path="$3"

    local source="$artifact_dir/$name"
    if [[ ! -e "$source" ]]; then
        warn "产物不存在: $name"
        return 1
    fi

    if [[ -d "$source" ]]; then
        cp -r "$source" "$target_path"
    else
        cp "$source" "$target_path"
    fi
}

# 列出产物
list_artifacts() {
    local artifact_dir="$1"
    if [[ -d "$artifact_dir" ]]; then
        ls -la "$artifact_dir"
    fi
}

# -----------------------------------------------------------------------------
# 任务关系分析
# -----------------------------------------------------------------------------

# 获取任务的依赖列表
get_task_deps() {
    local taskfile="$1"
    local task="$2"
    "$YQ" eval ".tasks.\"$task\".deps[]" "$taskfile" 2>/dev/null || true
}

# 获取任务的子任务调用 (从 cmds 中解析 task: xxx)
get_task_subtasks() {
    local taskfile="$1"
    local task="$2"
    "$YQ" eval ".tasks.\"$task\".cmds[] | select(has(\"task\")) | .task" "$taskfile" 2>/dev/null || true
}

# 获取任务的所有相关任务 (deps + subtasks + extends)
get_task_relations() {
    local taskfile="$1"
    local task="$2"

    # 依赖
    local deps
    deps=$(get_task_deps "$taskfile" "$task")

    # 子任务调用
    local subtasks
    subtasks=$(get_task_subtasks "$taskfile" "$task")

    # 继承
    local extends=""
    if has_ez_extends "$taskfile" "$task"; then
        extends=$(get_ez_extends "$taskfile" "$task")
    fi

    # 组合
    local compose=""
    if has_ez_compose "$taskfile" "$task"; then
        compose=$(get_ez_compose_json "$taskfile" "$task" | "$YQ" eval '.[].task' -)
    fi

    # 合并输出
    {
        [[ -n "$deps" ]] && echo "$deps"
        [[ -n "$subtasks" ]] && echo "$subtasks"
        [[ -n "$extends" ]] && echo "$extends"
        [[ -n "$compose" ]] && echo "$compose"
    } | sort -u
}

# -----------------------------------------------------------------------------
# Workspace 工作区管理 (v1.3 → v1.4)
# -----------------------------------------------------------------------------

# 创建工作区
# 参数: $1 = 工作区名称 (或 "auto" 自动生成)
#        $2 = 关联文件夹任务名称 (可选; 如提供，创建到 .ez/tasks/<name>/workspace/)
# 输出: 工作区路径
# 返回: 0 = 成功, 1 = 失败
create_workspace() {
    local name="$1"
    local folder_name="${2:-}"

    # auto 模式: 生成唯一名称
    if [[ "$name" == "auto" ]]; then
        name="$(date +%Y%m%d-%H%M%S)-$$"
    fi

    local ws_dir
    if [[ -n "$folder_name" ]]; then
        # 文件夹任务默认 workspace: .ez/tasks/<name>/workspace/
        ws_dir="$(get_task_workspace_dir "$folder_name")"
    else
        # Ad-hoc workspace: .ez/workspace/<name>/
        ws_dir="$EZ_WORKSPACE_DIR/$name"
    fi

    if [[ -d "$ws_dir" ]]; then
        echo "$ws_dir"
        return 0
    fi

    mkdir -p "$ws_dir"

    # 创建源码符号链接
    ln -sf "$EZ_ROOT" "$ws_dir/src"

    # 复制根 Taskfile (可在工作区内修改)
    local taskfile
    if taskfile=$(find_taskfile "$EZ_ROOT"); then
        cp "$taskfile" "$ws_dir/Taskfile.yml"
    fi

    echo "$ws_dir"
}

# 列出所有工作区
list_workspaces() {
    if [[ ! -d "$EZ_WORKSPACE_DIR" ]]; then
        return
    fi
    for dir in "$EZ_WORKSPACE_DIR"/*/; do
        [[ ! -d "$dir" ]] && continue
        local name
        name=$(basename "$dir")
        local created
        created=$(stat -c %y "$dir" 2>/dev/null | cut -d. -f1)
        echo "$name $created"
    done
}

# 清理工作区
# 参数: $1 = 工作区名称 (或 "all" 清理全部)
cleanup_workspace() {
    local name="$1"
    if [[ "$name" == "all" ]]; then
        rm -rf "$EZ_WORKSPACE_DIR"
        return
    fi
    rm -rf "$EZ_WORKSPACE_DIR/$name"
}

# -----------------------------------------------------------------------------
# Plan 编译系统 (v1.2 → v1.4: 按 Plan 粒度组织输出)
# -----------------------------------------------------------------------------

# 查找 Plan 文件
# 支持 plans/<name>.yml 和旧格式 .ez-plan.yml
find_plan_file() {
    local name="$1"

    # 1. plans/ 目录
    if [[ -f "$EZ_PLANS_DIR/$name.yml" ]]; then
        echo "$EZ_PLANS_DIR/$name.yml"
        return 0
    fi
    if [[ -f "$EZ_PLANS_DIR/$name.yaml" ]]; then
        echo "$EZ_PLANS_DIR/$name.yaml"
        return 0
    fi

    return 1
}

# 列出所有 Plan 文件
list_plan_files() {
    # 1. plans/ 目录
    if [[ -d "$EZ_PLANS_DIR" ]]; then
        for f in "$EZ_PLANS_DIR"/*.yml "$EZ_PLANS_DIR"/*.yaml; do
            [[ -f "$f" ]] && echo "$f"
        done
    fi
}

# 获取 Plan 名称列表
get_plan_names() {
    # 从 plans/ 目录
    if [[ -d "$EZ_PLANS_DIR" ]]; then
        for f in "$EZ_PLANS_DIR"/*.yml "$EZ_PLANS_DIR"/*.yaml; do
            [[ -f "$f" ]] && basename "$f" | sed 's/\.\(yml\|yaml\)$//'
        done
    fi

    # 从旧格式 .ez-plan.yml
    local old_planfile=""
    [[ -f "$EZ_ROOT/.ez-plan.yml" ]] && old_planfile="$EZ_ROOT/.ez-plan.yml"
    [[ -f "$EZ_ROOT/.ez-plan.yaml" ]] && old_planfile="$EZ_ROOT/.ez-plan.yaml"
    if [[ -n "$old_planfile" ]]; then
        "$YQ" eval '.plans | keys | .[]' "$old_planfile" 2>/dev/null || true
    fi
}

# 拓扑排序
# 参数: 步骤 JSON 数组
# 输出: 排序后的步骤名称列表（每行一个）
topo_sort() {
    local steps_json="$1"
    local count
    count=$(echo "$steps_json" | "$YQ" eval 'length' -)

    # 构建邻接表和入度
    declare -A in_degree
    declare -A edges  # step -> space-separated deps
    local -a all_names=()

    for ((i=0; i<count; i++)); do
        local name needs
        name=$(echo "$steps_json" | "$YQ" eval ".[$i].name" -)
        needs=$(echo "$steps_json" | "$YQ" eval ".[$i].needs // [] | .[]" - 2>/dev/null)
        all_names+=("$name")
        in_degree["$name"]=0
        edges["$name"]=""
    done

    # 计算入度
    for ((i=0; i<count; i++)); do
        local name
        name=$(echo "$steps_json" | "$YQ" eval ".[$i].name" -)
        local needs
        needs=$(echo "$steps_json" | "$YQ" eval ".[$i].needs // [] | .[]" - 2>/dev/null)
        while IFS= read -r dep; do
            [[ -z "$dep" ]] && continue
            in_degree["$name"]=$(( ${in_degree["$name"]} + 1 ))
            edges["$dep"]+=" $name"
        done <<< "$needs"
    done

    # BFS
    local -a queue=()
    local -a result=()

    for name in "${all_names[@]}"; do
        [[ ${in_degree["$name"]} -eq 0 ]] && queue+=("$name")
    done

    while [[ ${#queue[@]} -gt 0 ]]; do
        local current="${queue[0]}"
        queue=("${queue[@]:1}")
        result+=("$current")

        for neighbor in ${edges["$current"]}; do
            in_degree["$neighbor"]=$(( ${in_degree["$neighbor"]} - 1 ))
            [[ ${in_degree["$neighbor"]} -eq 0 ]] && queue+=("$neighbor")
        done
    done

    # 检测循环
    if [[ ${#result[@]} -ne $count ]]; then
        echo "ERROR:CYCLE" >&2
        return 1
    fi

    printf '%s\n' "${result[@]}"
}

# 编译 Plan 为 go-task Taskfile
# 参数: $1 = plan 文件路径, $2 = 输出目录
compile_plan() {
    local plan_file="$1"
    local output_dir="$2"

    local plan_name plan_desc
    plan_name=$("$YQ" eval '.name // ""' "$plan_file")
    plan_desc=$("$YQ" eval '.desc // ""' "$plan_file")

    local steps_json
    steps_json=$("$YQ" eval -o=json '.steps // []' "$plan_file")
    local step_count
    step_count=$(echo "$steps_json" | "$YQ" eval 'length' -)

    if [[ $step_count -eq 0 ]]; then
        echo "error: Plan has no steps" >&2
        return 1
    fi

    # 拓扑排序
    local sorted_names
    sorted_names=$(topo_sort "$steps_json") || {
        echo "error: Dependency cycle detected" >&2
        return 1
    }

    # 检查 shuffle 并随机化同层步骤
    # (简化: 对标记 shuffle 的步骤在无依赖约束时随机排序)

    mkdir -p "$output_dir"

    # 生成 Taskfile
    local output_file="$output_dir/Taskfile.yml"
    {
        echo "# Auto-generated by: ez plan build $plan_name"
        echo "# Source: $plan_file"
        echo "# Generated: $(date -Iseconds)"
        echo "version: '3'"
        echo ""
        echo "tasks:"

        # default task: 按拓扑序执行所有步骤
        echo "  default:"
        echo "    desc: \"$plan_name: $plan_desc\""
        echo "    cmds:"
        while IFS= read -r sname; do
            [[ -z "$sname" ]] && continue
            local safe_name
            safe_name=$(echo "$sname" | tr ' ' '-')
            echo "      - task: step-$safe_name"
        done <<< "$sorted_names"
        echo ""

        # 每个步骤作为独立 task
        local step_num=0
        while IFS= read -r sname; do
            [[ -z "$sname" ]] && continue
            ((step_num++))
            local safe_name
            safe_name=$(echo "$sname" | tr ' ' '-')

            # 查找步骤 JSON
            local step_idx=-1
            for ((i=0; i<step_count; i++)); do
                local n
                n=$(echo "$steps_json" | "$YQ" eval ".[$i].name" -)
                if [[ "$n" == "$sname" ]]; then
                    step_idx=$i
                    break
                fi
            done

            local stask needs_str svars
            stask=$(echo "$steps_json" | "$YQ" eval ".[$step_idx].task // \"\"" -)
            needs_str=$(echo "$steps_json" | "$YQ" eval ".[$step_idx].needs // [] | .[]" - 2>/dev/null)
            svars=$(echo "$steps_json" | "$YQ" eval -o=json ".[$step_idx].vars // {}" -)

            echo "  step-$safe_name:"
            echo "    desc: \"[$step_num/$step_count] $sname\""

            # 依赖
            local has_deps=false
            if [[ -n "$needs_str" ]]; then
                local deps_line=""
                while IFS= read -r dep; do
                    [[ -z "$dep" ]] && continue
                    local safe_dep
                    safe_dep=$(echo "$dep" | tr ' ' '-')
                    [[ -n "$deps_line" ]] && deps_line+=", "
                    deps_line+="step-$safe_dep"
                    has_deps=true
                done <<< "$needs_str"
                if $has_deps; then
                    echo "    deps: [$deps_line]"
                fi
            fi

            # 命令: 调用原始任务
            echo "    cmds:"
            if [[ -n "$stask" && "$stask" != "null" ]]; then
                # 构建变量参数
                local var_args=""
                if [[ "$svars" != "{}" && "$svars" != "null" ]]; then
                    while IFS= read -r key; do
                        [[ -z "$key" ]] && continue
                        local val
                        val=$(echo "$svars" | "$YQ" eval ".$key" -)
                        var_args+=" $key=$val"
                    done < <(echo "$svars" | "$YQ" eval 'keys | .[]' -)
                fi
                echo "      - cmd: \"$TASK -t $EZ_ROOT/Taskfile.yml $stask$var_args\""
            else
                echo "      - cmd: \"echo 'Step: $sname'\""
            fi

            echo ""
        done <<< "$sorted_names"
    } > "$output_file"

    echo "$output_file"
}

# 验证 Plan 完整性
# 参数: $1 = plan 文件路径
# 输出: 验证结果（逐行打印）
# 返回: 0 = 通过, 1 = 有错误
validate_plan() {
    local plan_file="$1"
    local errors=0

    local plan_name
    plan_name=$("$YQ" eval '.name // ""' "$plan_file")

    local steps_json
    steps_json=$("$YQ" eval -o=json '.steps // []' "$plan_file")
    local step_count
    step_count=$(echo "$steps_json" | "$YQ" eval 'length' -)

    local taskfile
    taskfile=$(find_taskfile "$EZ_ROOT") || true

    echo "Checking plan: $plan_name"

    for ((i=0; i<step_count; i++)); do
        local sname stask
        sname=$(echo "$steps_json" | "$YQ" eval ".[$i].name // \"step-$i\"" -)
        stask=$(echo "$steps_json" | "$YQ" eval ".[$i].task // \"\"" -)

        # 检查 task 是否存在
        if [[ -n "$stask" && "$stask" != "null" && -n "$taskfile" ]]; then
            if task_exists "$taskfile" "$stask"; then
                echo "  ✓ Step $sname → task $stask exists"
            else
                echo "  ✗ Step $sname → task $stask NOT FOUND"
                ((errors++))
            fi
        fi

        # 检查 needs 引用是否存在
        local needs
        needs=$(echo "$steps_json" | "$YQ" eval ".[$i].needs // [] | .[]" - 2>/dev/null)
        while IFS= read -r dep; do
            [[ -z "$dep" ]] && continue
            local found=false
            for ((j=0; j<step_count; j++)); do
                local jname
                jname=$(echo "$steps_json" | "$YQ" eval ".[$j].name" -)
                [[ "$jname" == "$dep" ]] && found=true && break
            done
            if $found; then
                echo "  ✓ Step $sname needs $dep (found)"
            else
                echo "  ✗ Step $sname needs $dep (NOT FOUND)"
                ((errors++))
            fi
        done <<< "$needs"

        # 检查 inputs 引用的 artifact
        local inputs
        inputs=$(echo "$steps_json" | "$YQ" eval -o=json ".[$i].inputs // []" -)
        local input_count
        input_count=$(echo "$inputs" | "$YQ" eval 'length' -)
        for ((k=0; k<input_count; k++)); do
            local from_step art_name
            from_step=$(echo "$inputs" | "$YQ" eval ".[$k].from" -)
            art_name=$(echo "$inputs" | "$YQ" eval ".[$k].artifact" -)

            # 查找 from_step 的 artifacts
            local art_found=false
            for ((j=0; j<step_count; j++)); do
                local jname
                jname=$(echo "$steps_json" | "$YQ" eval ".[$j].name" -)
                if [[ "$jname" == "$from_step" ]]; then
                    local jarts
                    jarts=$(echo "$steps_json" | "$YQ" eval ".[$j].artifacts // [] | .[].name" - 2>/dev/null)
                    while IFS= read -r aname; do
                        [[ "$aname" == "$art_name" ]] && art_found=true && break
                    done <<< "$jarts"
                    break
                fi
            done

            if $art_found; then
                echo "  ✓ Step $sname.inputs.$art_name ← $from_step.artifacts.$art_name (matched)"
            else
                echo "  ✗ Step $sname.inputs.$art_name ← $from_step.artifacts.$art_name (NOT FOUND)"
                ((errors++))
            fi
        done
    done

    # 拓扑排序检查（循环检测）
    if topo_sort "$steps_json" >/dev/null 2>&1; then
        echo "  ✓ Dependency graph: no cycles"
    else
        echo "  ✗ Dependency graph: CYCLE DETECTED"
        ((errors++))
    fi

    echo "  ✓ All $step_count steps checked"

    return $errors
}
