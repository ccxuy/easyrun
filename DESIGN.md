# EZ 设计规格

EZ 是 go-task 的超集前端。go-task 是执行引擎，EZ 在其上提供参数管理、任务编排、工作区隔离、分布式执行等能力。

## 设计原则

1. **超集不替代** — EZ 扩展 go-task，不替换。所有 `ez-*` 字段可被 go-task 安全忽略，EZ 生成的 Taskfile 是合法 go-task 文件。
2. **Task 是核心** — EZ 的 task 是 go-task task 的超集：行内任务定义在根 Taskfile.yml，文件夹任务是 `tasks/` 下的自包含目录。
3. **Workspace 默认隔离** — 文件夹任务默认在隔离工作区中执行，防止污染源码。`--no-workspace` 关闭隔离。
4. **按粒度组织运行时** — `.ez/` 按任务/计划名称组织子目录，`rm -rf .ez/tasks/X` 即可清理单个任务的全部运行时数据。
5. **根目录整洁** — 项目根只放核心文件（`ez`、`Taskfile.yml`），运行时和生成物统一收归 `.ez/`。
6. **渐进增强** — 从简单的 `ez <task>` 直接执行开始，按需使用参数、计划、远程执行等高级功能。

---

## 核心概念

### 术语表

| 术语 | 含义 |
|------|------|
| Task (任务) | 可执行的工作单元。go-task task 的超集，支持 `ez-*` 扩展字段 |
| 行内任务 | 定义在根 `Taskfile.yml` 中的 task 条目 |
| 文件夹任务 | `tasks/<name>/` 下自包含的任务目录，含 `Taskfile.yml` + `task.yml` 元数据 |
| Plan (计划) | 多 Task 的编排，定义执行顺序和依赖，编译为标准 go-task Taskfile |
| Step (步骤) | Plan 内的单个环节 |
| Artifact (产物) | Task 的输出文件，可被下游引用 |
| Workspace (工作区) | 隔离的执行目录，防止污染任务源码 |

**任务生命周期**: `pending → running → success / failed`

### 目录结构

```
project/
├── ez                        # 主入口（唯一可执行文件）
├── lib/ez-core.sh            # 核心函数库
├── dep/                      # 依赖二进制 (go-task, yq)
├── Taskfile.yml              # 根 Taskfile（行内任务）
├── tasks/                    # 文件夹任务（EZ 自动发现）
│   └── kernel-build/
│       ├── Taskfile.yml      # go-task 执行定义
│       ├── task.yml          # EZ 元数据（可选）
│       └── scripts/          # 辅助脚本
├── plans/                    # Plan 定义
│   └── kernel-ci.yml
├── .ez/                      # 运行时数据（gitignore）
│   ├── tasks/<name>/         # 按任务粒度
│   │   ├── workspace/        #   隔离工作区
│   │   ├── logs/             #   执行日志
│   │   └── artifacts/        #   输出产物
│   ├── plans/<name>/         # 按计划粒度
│   │   ├── build/            #   编译输出
│   │   ├── logs/             #   执行日志
│   │   └── state/            #   恢复状态
│   └── workspace/            # ad-hoc 工作区（--workspace=name）
├── test/selftest/            # 自测试套件
├── server/                   # Server 组件
├── client/                   # Client Agent
├── docs/                     # 详细文档
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

### 文件夹任务

`tasks/<name>/` 目录下的自包含任务。每个文件夹任务包含：

- `Taskfile.yml` — go-task 执行定义（必需）
- `task.yml` — EZ 元数据（可选）
- `scripts/`、`config/` 等辅助文件

文件夹任务在 `ez list` 中以 `[folder]` 标记显示。

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
2. **文件夹任务** — `tasks/` 下包含 `Taskfile.yml` 的子文件夹

文件夹任务通过 `task -d tasks/<name> default` 委托 go-task 执行。

### Workspace 隔离

文件夹任务默认在 `.ez/tasks/<name>/workspace/` 中执行，源码目录通过符号链接挂载。

```bash
ez my-task                  # 默认在 workspace 中执行
ez my-task --no-workspace   # 在源码目录直接执行（opt-out）
ez hello --workspace=auto   # 行内任务也可启用 workspace
ez hello --workspace=debug  # 指定 workspace 名称
```

Workspace 目录结构：
```
.ez/tasks/my-task/workspace/
├── src -> ../../tasks/my-task/  # 符号链接到源码
├── Taskfile.yml                 # 复制
└── (执行产物)
```

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

原则：最常用操作最短路径。`ez <name>` 直接执行，无需子命令。

```
# 任务操作（默认主体）
ez                            # 等价于 ez list
ez <name>                     # 直接执行（行内或文件夹任务）
ez <name> --dry-run           # 预览不执行
ez list [filter]              # 列出任务（文件夹任务标记 [folder]）
ez show <name>                # 显示详情（含 task.yml 元数据）
ez run <name> [vars]          # 运行任务（交互式参数）
ez new <name>                 # 创建文件夹任务 tasks/<name>/
ez check [name]               # 验证 Taskfile 语法
ez clean <name>               # 清理 .ez/tasks/<name>/ 运行时数据
ez clean --all                # 清理全部 .ez/

# 导入导出
ez export <name>              # 导出文件夹任务为 .tar.gz
ez import <path>              # 导入文件夹任务

# Plan 编排
ez plan list                  # 列出所有计划
ez plan new <name>            # 创建 Plan
ez plan add <name> <task>     # 添加步骤 (--needs 依赖)
ez plan show <name>           # 查看结构
ez plan build <name>          # 编译为 Taskfile
ez plan check <name>          # 验证依赖完备性
ez plan run <name>            # 编译 + 执行
ez plan <name>                # 等价于 ez plan run <name>

# Server/Client 分布式
ez server start               # 启动 HTTP 服务器
ez server status              # 查看 Server + 节点状态
ez server docker              # Docker 方式启动
ez client start               # 启动 Client Agent

# 辅助
ez browse                     # 交互式任务导航
ez version                    # 版本信息
ez help                       # 帮助
ez completion bash|zsh        # Tab 补全脚本
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
