# EZ 设计规格

EZ 是轻量任务编排平台。go-task 是底层执行引擎，EZ 在其上提供参数管理、任务编排、工作区隔离、可视化管理等能力。

## 设计原则

1. **便携适配** — 拷贝即用，适配各种 Linux 执行环境。核心只依赖 Bash + 两个二进制 (go-task, yq)，无需系统级安装。首次运行自动安装依赖，离线环境支持直接拷贝 `dep/` 目录。
2. **精简核心** — EZ 是任务编排工具。AI 交互、分布式执行（server/client）等是可选扩展接口，不膨胀核心。
3. **超集不替代** — EZ 扩展 go-task，不替换。所有 `ez-*` 字段可被 go-task 安全忽略，EZ 生成的 Taskfile 是合法 go-task 文件。
4. **Task 是核心** — EZ 的 task 是 go-task task 的超集：行内任务定义在根 Taskfile.yml，目录任务是 `tasks/` 下的自包含目录。
5. **Workspace 触手可及** — 任务执行过程人工介入和 debug 是常态。workspace 在项目根目录，`.ez/` 仅存内部状态。
6. **迭代工作流** — 支持重复性高、参数有变化、经常中断修改的场景。`rerun` 一键重复，`matrix` 多变体并行。
7. **渐进增强** — 从简单的 `ez <task>` 直接执行开始，按需使用参数、计划、远程执行等高级功能。

---

## 核心概念

### 术语表

| 术语 | 含义 |
|------|------|
| Task (任务) | 可执行的工作单元。go-task task 的超集，支持 `ez-*` 扩展字段 |
| 行内任务 | 定义在根 `Taskfile.yml` 中的 task 条目 |
| 目录任务 | `tasks/<name>/` 下自包含的任务目录，含 `Taskfile.yml` + `task.yml` 元数据 |
| 工具任务 | `lib/tools/<name>.yml`，EZ 自身的内置工具（server、doctor、prune 等）|
| Plan (计划) | 多 Task 的编排，定义执行顺序和依赖，编译为标准 go-task Taskfile |
| Step (步骤) | Plan 内的单个环节 |
| Workspace (工作区) | 项目根 `workspace/` 下的隔离执行目录，防止污染源码 |
| Plugin (插件) | `plugins/` 或 `~/.ez/plugins/` 下的扩展，支持 hook 类型 |

**任务生命周期**: `pending → running → success / failed`

### 目录结构

```
project/
├── ez                        # 主入口（唯一可执行文件）
├── lib/
│   ├── ez-core.sh            # 核心函数库
│   ├── tools/                # 工具任务 (server, doctor, prune)
│   └── completion/           # Tab 补全脚本
├── dep/                      # 依赖二进制 (go-task, yq)
├── Taskfile.yml              # 根 Taskfile（行内任务）
├── tasks/                    # 目录任务（EZ 自动发现）
│   └── kernel-build/
│       ├── Taskfile.yml      # go-task 执行定义
│       ├── task.yml          # EZ 元数据（可选）
│       └── scripts/          # 辅助脚本
├── plans/                    # Plan 定义
│   └── kernel-ci.yml
├── plugins/                  # 项目级插件
│   └── stats-reporter.yml    # 统计上报插件
├── templates/                # 任务模板
├── workspace/                # 执行工作区（gitignore，项目根目录）
│   ├── kernel-build/         #   任务默认工作区
│   │   ├── src -> ../..      #   符号链接到项目根
│   │   ├── Taskfile.yml      #   任务定义副本
│   │   ├── .ez-run.yml       #   运行上下文（用于 rerun）
│   │   └── logs/             #   工作区本地日志
│   └── kernel-build--arm64/  #   变体工作区（matrix）
├── .ez/                      # 内部状态（gitignore）
│   ├── plans/<name>/         #   按计划粒度
│   │   ├── build/            #     编译输出
│   │   └── state/            #     恢复状态
│   └── logs/                 #   全局日志（非工作区运行）
├── test/selftest/            # 自测试套件
├── server/                   # Web 管理平台（Flask + SocketIO）
│   ├── main.py               #   Server 主程序
│   ├── templates/            #   HTML 模板
│   ├── static/               #   CSS/JS 静态资源
│   ├── Dockerfile            #   Docker 构建
│   └── docker-compose.yml    #   Docker 编排
├── DESIGN.md                 # 本文件
├── PLAN.md                   # 开发计划
└── README.md                 # 基础用法
```

---

## Task 任务系统

### 行内任务

定义在根 `Taskfile.yml` 中，完全兼容 go-task 语法，可选添加 `ez-*` 扩展字段：

```yaml
# Taskfile.yml
version: '3'
tasks:
  build-kernel:
    desc: "构建 Linux 内核"
    cmds:
      - make defconfig ARCH={{.EZ_ARCH}}
      - make -j$(nproc) ARCH={{.EZ_ARCH}}

    # EZ 扩展字段（go-task 安全忽略）
    ez-params:
      - name: "arch"
        type: "select"
        options: ["x86_64", "aarch64", "riscv64"]
        default: "x86_64"
        help: "目标架构"

    ez-hooks:
      post_run:
        - name: "size-analysis"
          script: "du -h vmlinux bzImage | sort -hr"
```

约束：所有 `ez-*` 字段必须能被 go-task 安全忽略。

### 目录任务

`tasks/<name>/` 目录下的自包含任务。每个目录任务包含：

- `Taskfile.yml` — go-task 执行定义（必需）
- `task.yml` — EZ 元数据（可选）
- `scripts/`、`config/` 等辅助文件

目录任务在 `ez list` 中以 `[dir]` 标记显示。

### 工具任务

`lib/tools/<name>.yml` 下的 EZ 内置工具。与行内/目录任务不同，工具任务随 EZ 发布，用于 EZ 自身功能（启动 Server、环境检查、清理等）。

工具任务特点：
- 存放在 `lib/tools/`，随 EZ 分发
- `ez list` 默认不显示，`ez list --tools` 或 `ez tools` 显示
- `ez <tool-name>` 可直接执行（如 `ez server`、`ez doctor`）
- 在任务列表中标记为 `[tool]`

预置工具任务：

| 工具 | 说明 |
|------|------|
| `server` | 启动 EZ Web 管理平台 |
| `doctor` | 检查 EZ 运行环境（依赖、项目结构）|
| `prune` | 清理过程文件（workspace、logs、state）|

工具任务 YAML 格式：

```yaml
# lib/tools/server.yml
name: server
desc: "启动 EZ Server Web 管理平台"
tool: true
tasks:
  default:
    desc: "启动 Server"
    cmd: "python3 -m server.main"
  docker:
    desc: "Docker 管理"
    cmd: "docker compose -f server/docker-compose.yml up -d"
```

### task.yml 元数据

```yaml
# tasks/kernel-build/task.yml
name: kernel-build
version: "1.0"
desc: "构建 Linux 内核"

usage: |
  构建指定架构的 Linux 内核。
  支持 x86_64、arm64、riscv64 架构。

# 参数定义（优先于 Taskfile 中的 ez-params）
params:
  - name: arch
    type: select
    options: [x86_64, arm64, riscv64]
    default: x86_64
    desc: "目标架构"

# 产物声明
artifacts:
  - name: vmlinux
    path: build/vmlinux
    desc: "内核二进制"

# AI agent 索引
tags: [build, compile, kernel, linux]
examples:
  - "构建 x86_64 架构的内核"
  - "使用 arm64 + defconfig 编译"
```

**元数据解析优先级**: `task.yml` params > Taskfile `ez-params` > 无参数

### 任务发现

EZ 自动合并两种来源：

1. **根 Taskfile 任务** — `Taskfile.yml` 中的 tasks 条目（go-task 原生）
2. **目录任务** — `tasks/` 下包含 `Taskfile.yml` 的子目录

目录任务通过 `task -d tasks/<name> default` 委托 go-task 执行。

### Workspace 隔离

目录任务默认在 `workspace/<name>/` 中执行，源码目录通过符号链接挂载。Workspace 在项目根目录，方便 debug 和人工介入。

```bash
ez my-task                  # 默认在 workspace 中执行
ez my-task --no-workspace   # 在源码目录直接执行（opt-out）
ez hello --workspace=auto   # 行内任务也可启用 workspace
ez hello --workspace=debug  # 指定 workspace 名称
```

Workspace 目录结构：
```
workspace/my-task/
├── src -> ../..                # 符号链接到项目根
├── Taskfile.yml                # 复制
├── .ez-run.yml                 # 运行上下文（rerun 用）
├── logs/                       # 工作区本地日志
└── (执行产物)
```

### Rerun 迭代工作流

每次工作区执行后自动保存运行上下文（`.ez-run.yml`），支持一键重复：

```bash
# 首次运行
ez plan run kernel-ci -w ci-x86 EZ_ARCH=x86_64

# 修改代码后重新运行
ez rerun ci-x86

# 覆盖部分参数
ez rerun ci-x86 EZ_ARCH=arm64

# 重复最近一次执行
ez rerun
```

### Matrix 多变体并行

```bash
# 单维度: 3 个架构并行
ez matrix kernel-build --vary EZ_ARCH=x86_64,arm64,riscv64

# 二维度: 架构 x 配置
ez matrix kernel-build --vary EZ_ARCH=x86_64,arm64 --vary EZ_CONFIG=defconfig,allmodconfig

# 固定参数 + 变化参数
ez matrix kernel-build --vary EZ_ARCH=x86_64,arm64 EZ_JOBS=8
```

每个变体创建独立工作区 `workspace/<task>--<variant>/`，并行执行后汇总结果。

---

## 扩展机制

### ez-params 参数系统

为 go-task 任务添加交互式参数管理：

```yaml
ez-params:
  - name: "arch"
    type: "select"                # select | input
    options: ["x86_64", "arm64"]  # select 的候选值
    default: "x86_64"
    help: "目标架构"

  - name: "version"
    type: "input"
    default: "6.6"
    help: "内核版本号"
```

参数类型：
- `select` — 从选项列表中选择
- `input` — 自由文本输入

参数传递：`ez-params` 中的 `name` 自动映射为 `EZ_<NAME>` 环境变量传递给 go-task。

```bash
ez run build                       # 交互式选择参数
ez run build EZ_ARCH=arm64         # 直接指定参数
ez run build --dry-run             # 预览不执行
```

### ez-hooks 钩子系统

在任务生命周期中插入自定义逻辑：

```yaml
ez-hooks:
  pre_run:
    - name: "check-env"
      script: "test -f .config"
  post_run:
    - name: "size-report"
      script: "du -sh build/"
  on_error:
    - name: "cleanup"
      script: "make clean"
```

### ez-extends 任务继承

基于已有任务派生新任务：

```yaml
tasks:
  kernel-build:
    desc: "构建内核"
    cmds:
      - make ARCH={{.EZ_ARCH}} -j$(nproc)
    ez-params:
      - name: arch
        type: select
        options: [x86_64, arm64]
        default: x86_64

  kernel-build-debug:
    ez-extends: kernel-build
    ez-defaults:
      EZ_ARCH: arm64
```

### ez-compose 任务组合

将多个任务串联为一个流程：

```yaml
tasks:
  kernel-ci:
    ez-compose:
      - task: kernel-config
      - task: kernel-build
      - task: kernel-test
```

---

## Plan 编排系统

### Plan 文件格式

```yaml
# plans/kernel-ci.yml
name: kernel-ci
desc: "内核 CI 流水线"
steps:
  - name: config
    task: kernel-config
    vars:
      EZ_ARCH: "{{.arch}}"

  - name: build
    task: kernel-build
    needs: [config]
    artifacts:
      - name: vmlinux
        path: build/vmlinux

  - name: test
    task: kernel-test
    needs: [build]
    inputs:
      - from: build
        artifact: vmlinux
        to: ./vmlinux

  - name: package
    task: kernel-package
    needs: [build, test]
    shuffle: true
```

### 编译流程

`ez plan build <name>` 将 Plan 编译为标准 go-task Taskfile：

1. 解析 steps + matrix 展开
2. 拓扑排序（检查 needs 依赖，检测循环）
3. 生成 Taskfile.yml 到 `.ez/plans/<name>/build/`

### 依赖验证

`ez plan check <name>` 验证：

- 所有 `step.task` 在 Taskfile 中存在（支持文件夹任务名称）
- `needs` 引用的 step 存在且无循环依赖
- `inputs` 引用的 artifact 在上游 step 有定义

### Shuffle

标记 `shuffle: true` 的步骤在相同依赖层级内随机排序，用于验证执行顺序无关性。

---

## 命令体系

原则：最常用操作最短路径。`ez <name>` 直接执行，无需子命令。一级菜单聚焦核心功能，扩展功能通过子命令 help 查看。

```
# 任务执行
ez                            # 项目概况摘要
ez <name>                     # 直接执行（行内、目录或工具任务）
ez <name> --dry-run           # 预览不执行

# 任务管理
ez new <name>                 # 创建文件夹任务 tasks/<name>/
ez show <name>                # 显示详情（含 task.yml 元数据）
ez export / import            # 导出/导入文件夹任务
ez check [name]               # 验证 Taskfile 语法
ez clean <name|--all>         # 清理运行时数据

# Plan 编排
ez plan <name>                # 等价于 ez plan run <name>
ez plan list / new / show / build / check
                              # 计划管理子命令

# 工具
ez tools                      # 列出工具任务
ez doctor                     # 环境检查
ez server                     # 启动 Web 管理平台
ez browse                     # 交互式任务导航
ez log list / show            # 执行日志
ez completion bash|zsh        # Tab 补全脚本

# 选项
--dry-run                     # 预览不执行
--log                         # 记录日志
--workspace=<name>            # 隔离执行 (auto = 自动命名)
--no-workspace                # 源目录执行

# 分布式（可选）
ez server help                # Server 子命令帮助
ez client help                # Client 子命令帮助
```

---

## 分布式执行

### 架构

```
┌─────────────────────────────────────┐
│          EZ Server (Docker)         │
│  ┌─────────┐  ┌─────────────────┐  │
│  │ Web UI  │  │   REST API      │  │
│  │ :8080   │  │   /api/v1/...   │  │
│  └────┬────┘  └────────┬────────┘  │
│       └────────┬───────┘           │
│       Task Scheduler               │
└────────────────┬────────────────────┘
                 │ HTTP/WebSocket
    ┌────────────┼────────────┐
    │            │            │
┌───┴───┐   ┌───┴───┐   ┌───┴───┐
│Client │   │Client │   │Client │
│node-1 │   │node-2 │   │node-3 │
│go-task│   │go-task│   │go-task│
└───────┘   └───────┘   └───────┘
```

### Server

Python (Flask) 实现，提供：

- **Web Dashboard** — 节点总览、任务中心、执行监控
- **REST API** — 节点管理、任务调度、结果聚合
- **SQLite 存储** — 节点、任务、执行记录持久化
- **Docker 部署** — `server/Dockerfile` + `server/docker-compose.yml`

### Client

Python Agent，运行在工作节点：

- 连接 Server 并注册
- 定时心跳上报状态
- 接收并执行任务（委托本地 go-task）
- 实时推送执行日志

### 远程执行

任务可通过 `ez-remote` 指定在远程节点执行：

```yaml
tasks:
  kernel-build:
    cmds:
      - make ARCH={{.EZ_ARCH}} -j8
    ez-remote:
      nodes: ["builder-1", "builder-2"]
      sync_in:
        - "./Makefile"
        - "./src/"
      sync_out:
        - "./build/vmlinux"
```

### REST API

```
# 节点管理
GET    /api/v1/nodes             # 列出节点
POST   /api/v1/nodes/:id/ping    # 心跳
DELETE /api/v1/nodes/:id          # 移除

# 任务执行
POST   /api/v1/tasks/run          # 提交任务
GET    /api/v1/jobs                # 列出执行记录
GET    /api/v1/jobs/:id            # 执行详情
GET    /api/v1/jobs/:id/logs       # 执行日志 (SSE)
POST   /api/v1/jobs/:id/cancel     # 取消执行

# 计划管理
GET    /api/v1/plans               # 列出计划
POST   /api/v1/plans/:name/run     # 执行计划
```

---

## 设计约束

### 兼容性

1. 所有 `ez-*` 扩展字段能被 go-task 安全忽略
2. EZ 生成的 Taskfile 是 100% 有效的 go-task 语法
3. 任务中使用的相对路径在执行上下文中正确解析

### 用户体验

1. 参数有明确的帮助信息和默认值
2. 参数验证在执行前完成（Fail Fast）
3. 复杂功能按需使用，基础操作保持简单

### 扩展性

1. 插件无状态
2. 模板幂等（相同参数生成相同结果）
3. 生成的任务有完整的来源信息

---

## 工具依赖

- [go-task](https://github.com/go-task/task) — 任务执行引擎
- [yq](https://github.com/mikefarah/yq) — YAML 处理器

EZ 不生成 Go 代码，纯 Bash 实现。go-task 和 yq 作为二进制依赖安装到 `dep/` 目录。

---

## 插件系统

### Hook 插件

Hook 插件在任务执行的特定阶段自动触发。插件文件为 YAML 格式，存放在：

- `plugins/` — 项目级插件
- `~/.ez/plugins/hook/` — 用户级插件

```yaml
# plugins/stats-reporter.yml
name: stats-reporter
type: hook
trigger: post_run    # pre_run | post_run | on_error
script: |
  #!/usr/bin/env bash
  curl -sf -X POST "$EZ_SERVER_URL/api/v1/stats/report" \
    -H "Content-Type: application/json" \
    -d '{"task": "'$EZ_TASK_NAME'", "exit_code": '$EZ_TASK_EXIT_CODE'}' \
    2>/dev/null || true
```

Hook 可用环境变量：`EZ_TASK_NAME`、`EZ_TASK_EXIT_CODE`、`EZ_TASK_OUTPUT`、`EZ_TASK_DURATION`、`EZ_WORKSPACE_NAME`。

---

## Web 管理平台

### 架构

EZ Server 是作业管理平台，核心理念：**一切执行都是 Plan，单任务是最简 Plan**。

```
┌─────────────────────────────────────┐
│        EZ Server (Flask)            │
│  ┌──────────┐ ┌──────────────────┐  │
│  │  Web UI  │ │    REST API      │  │
│  │  :8080   │ │    /api/v1/...   │  │
│  └────┬─────┘ └───────┬──────────┘  │
│       └───────┬───────┘             │
│        SQLite + SocketIO            │
└───────────────┬─────────────────────┘
                │ HTTP/WebSocket
   ┌────────────┼────────────┐
   │            │            │
┌──┴───┐   ┌───┴───┐   ┌───┴──┐
│CLI上报│   │Client │   │Client│
│Plugin │   │node-1 │   │node-2│
└──────┘   └───────┘   └──────┘
```

### 页面结构

| 页面 | 路由 | 功能 |
|------|------|------|
| 总览 | `/` | 状态摘要、最近执行、快速操作 |
| 任务 | `/tasks` | 任务树浏览器（命名空间展开、参数表单）|
| 计划 | `/plans` | Plan 管理 + DAG 执行视图 |
| 执行记录 | `/jobs` | Server 作业 + CLI 上报记录 |
| 节点 | `/nodes` | 节点管理 |
| 统计 | `/charts` | 执行趋势、任务分布、耗时分析图表 |

### API 体系

```
# 任务管理
GET  /api/v1/tasks/tree          任务树（含命名空间分组）
GET  /api/v1/tasks/<name>/params 任务参数定义

# Plan 编排
GET  /api/v1/plans               计划列表
GET  /api/v1/plans/<name>        计划详情
POST /api/v1/plans/<name>/run    执行计划
POST /api/v1/plans/run-task      单任务执行
GET  /api/v1/plans/runs          执行历史
GET  /api/v1/plans/runs/<id>     执行状态

# 统计上报
POST /api/v1/stats/report        CLI 统计上报
GET  /api/v1/stats/executions    CLI 执行历史

# 模板
GET  /api/v1/templates           模板列表

# 节点 + 作业（原有）
GET  /api/v1/nodes               节点列表
POST /api/v1/tasks/run           提交作业
GET  /api/v1/jobs                作业列表
```

### DAG 可视化

Plan 执行视图将每个步骤显示为 DAG 节点，通过 `needs` 依赖关系绘制连线：

- 灰色 = 待执行（pending）
- 蓝色 = 运行中（running）
- 绿色 = 成功（success）
- 红色 = 失败（failed）

节点可点击展开，查看任务描述、进度输出和完整日志。通过 WebSocket 实时推送状态更新。
