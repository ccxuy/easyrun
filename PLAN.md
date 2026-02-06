# EZ 实现计划

## 概述
基于 go-task 和 yq 实现 EZ 任务编排框架，纯 Shell 脚本实现，无需编译。

## 设计约束
- **执行引擎**: 100% 复用 go-task，EZ 仅作为智能前端
- **YAML 处理**: 使用 yq 解析和操作 YAML
- **可移植性**: 依赖安装到本地 `dep/` 目录，项目自包含
- **渐进增强**: 从基础功能开始，逐步添加高级特性
- **兼容性**: `ez-*` 扩展字段可被 go-task 安全忽略

## 项目结构
```
easyrun/
├── ez                    # 主入口脚本
├── lib/ez-core.sh        # 核心函数库
├── dep/
│   ├── task              # go-task 二进制
│   ├── yq                # yq 二进制
│   └── install-deps.sh   # 依赖安装脚本
├── tasks/                # 文件夹任务（EZ 自动发现）
├── plans/                # Plan 定义
├── Taskfile.yml          # 根 Taskfile（行内任务）
├── .ez/                  # 运行时数据（按粒度组织，gitignore）
│   ├── tasks/<name>/     # 按任务粒度（workspace/logs/artifacts）
│   └── plans/<name>/     # 按 Plan 粒度（build/logs/state）
├── test/selftest/        # 自测试套件
├── DESIGN.md             # 设计规格
└── PLAN.md               # 本文件
```

---

## 阶段 1: 依赖安装

### 功能规格
- 自动检测 OS (linux/darwin) 和架构 (amd64/arm64)
- 从 GitHub Releases 下载最新版本
- 安装到本地 `dep/` 目录
- 验证安装成功

### 下载地址
- yq: `https://github.com/mikefarah/yq/releases/latest/download/yq_${OS}_${ARCH}`
- task: `https://github.com/go-task/task/releases/latest/download/task_${OS}_${ARCH}.tar.gz`

### 测试用例
| 编号 | 测试项 | 命令 | 预期结果 |
|------|--------|------|----------|
| 1.1 | 执行安装 | `./install-deps.sh` | 下载完成，显示版本 |
| 1.2 | yq 可用 | `./dep/yq --version` | 显示 v4.x.x |
| 1.3 | task 可用 | `./dep/task --version` | 显示 v3.x.x |

**检查点**: 所有测试通过后进入阶段 2

---

## 阶段 2: 核心函数库

### 功能规格
- 定义 `$YQ` 和 `$TASK` 指向本地二进制
- 提供 YAML 查询函数 (get_tasks, get_task_prop, has_ez_params)
- 提供错误处理函数 (die, warn, info)
- 查找 Taskfile (支持多种文件名)

### 核心函数
| 函数 | 用途 |
|------|------|
| `ensure_deps` | 检查依赖是否存在，不存在则自动安装 |
| `find_taskfile` | 查找当前目录的 Taskfile |
| `get_tasks` | 获取所有任务名称列表 |
| `get_task_prop` | 获取任务的指定属性 |
| `has_ez_params` | 检查任务是否有 ez-params |
| `get_ez_params_json` | 获取 ez-params 为 JSON |

### 测试用例
| 编号 | 测试项 | 命令 | 预期结果 |
|------|--------|------|----------|
| 2.1 | 加载库 | `source lib/ez-core.sh` | 无错误 |
| 2.2 | 依赖检查 | `check_deps` | 返回成功 |
| 2.3 | 获取任务 | `get_tasks Taskfile.yml` | 返回任务列表 |
| 2.4 | 获取属性 | `get_task_prop Taskfile.yml hello desc` | 返回描述 |

**检查点**: 所有测试通过后进入阶段 3

---

## 阶段 3: 命令框架

### 功能规格
- 主入口脚本 `ez`
- 命令路由: list, show, run, version, help
- 统一错误处理
- 帮助信息

### 命令结构
```
ez <command> [options] [args]

命令:
  list              列出所有任务
  show <task>       显示任务详情
  run <task>        运行任务（交互式参数）
  version           显示版本
  help              显示帮助
```

### 测试用例
| 编号 | 测试项 | 命令 | 预期结果 |
|------|--------|------|----------|
| 3.1 | 帮助 | `./ez help` | 显示帮助文本 |
| 3.2 | 版本 | `./ez version` | 显示版本和依赖 |
| 3.3 | 未知命令 | `./ez unknown` | 错误提示 |

**检查点**: 所有测试通过后进入阶段 4

---

## 阶段 4: list 命令

### 功能规格
- 列出 Taskfile 中所有任务
- 显示任务描述
- 标记有 ez-params 的任务 `[params]`
- 无 Taskfile 时报错

### 输出格式
```
Tasks in Taskfile.yml:
  hello               Say hello [params]
  build               Build project [params]
  clean               Clean artifacts
```

### 测试用例
| 编号 | 测试项 | 命令 | 预期结果 |
|------|--------|------|----------|
| 4.1 | 列出任务 | `./ez list` | 显示任务列表 |
| 4.2 | 参数标记 | `./ez list \| grep params` | 有参数的任务显示标记 |
| 4.3 | 无文件 | `cd /tmp && ez list` | 报错 "No Taskfile" |

**检查点**: 所有测试通过后进入阶段 5

---

## 阶段 5: show 命令

### 功能规格
- 显示任务详细信息
- 显示命令列表
- 显示 ez-params 参数定义
- 对于 select 类型显示可选值

### 输出格式
```
Task: build

Description: Build project

Commands:
  - echo "Building for {{.EZ_ARCH}}"

Parameters:
  arch (select)
    Help: Target architecture
    Default: x86_64
    Options: x86_64, aarch64, riscv64
```

### 测试用例
| 编号 | 测试项 | 命令 | 预期结果 |
|------|--------|------|----------|
| 5.1 | 显示详情 | `./ez show hello` | 显示任务信息 |
| 5.2 | 显示选项 | `./ez show build` | 显示 options 列表 |
| 5.3 | 无参数任务 | `./ez show clean` | 不显示 Parameters |
| 5.4 | 不存在 | `./ez show xxx` | 报错 "not found" |

**检查点**: 所有测试通过后进入阶段 6

---

## 阶段 6: run 命令

### 功能规格
- 交互式参数选择（select 类型显示菜单）
- 支持默认值（直接回车使用）
- 参数转换为 `EZ_VARNAME` 格式传递给 task
- `--dry-run` 只显示命令不执行
- 支持直接传递变量 `EZ_NAME=value`

### 交互流程
```
Configure: build

arch
  Target architecture
    1) x86_64 (default)
    2) aarch64
    3) riscv64
  Choice [1-3]: 2

Running: ./dep/task -t Taskfile.yml build EZ_ARCH=aarch64
```

### 测试用例
| 编号 | 测试项 | 命令 | 预期结果 |
|------|--------|------|----------|
| 6.1 | 干跑默认值 | `echo "" \| ./ez run hello --dry-run` | 显示 EZ_NAME=World |
| 6.2 | 干跑选择 | `echo "2" \| ./ez run build --dry-run` | 显示 EZ_ARCH=aarch64 |
| 6.3 | 实际运行 | `echo "" \| ./ez run hello` | 输出 "Hello, World!" |
| 6.4 | 无参数任务 | `./ez run clean` | 直接运行 |
| 6.5 | 预设变量 | `./ez run hello EZ_NAME=Test --dry-run` | 显示 EZ_NAME=Test |

**检查点**: 所有测试通过，阶段 6 完成

---

## 迭代计划

基于 DESIGN.md 核心概念: Task → Plan → Template → Plugin

---

### v0.1 - 基础框架

| 版本 | 功能 | 变更文件 | 测试 |
|------|------|----------|------|
| 0.1.0 | 依赖安装 | `install-deps.sh` | 1.1-1.3 ✅ |
| 0.1.1 | 核心函数库 | `lib/ez-core.sh` | 2.1-2.4 ✅ |
| 0.1.2 | help/version | `ez` | 3.1-3.3 |
| 0.1.3 | list 基础 | `ez` | 4.1-4.3 |
| 0.1.4 | show 基础 | `ez` | 5.1-5.4 |
| 0.1.5 | run 无参数 | `ez` | 6.4 |

---

### v0.2 - ez-params 参数系统

对应 DESIGN.md 4.2 参数系统

| 版本 | 功能 | 说明 | 测试 |
|------|------|------|------|
| 0.2.0 | input 类型 | 文本输入，支持 default | 6.1 |
| 0.2.1 | select 类型 | 静态选项列表 | 6.2 |
| 0.2.2 | --dry-run | 只显示命令不执行 | 6.5 |
| 0.2.3 | 预设变量 | `EZ_NAME=value` 跳过交互 | 6.5 |
| 0.2.4 | validation | 参数验证规则 | 新增 |
| 0.2.5 | query:command | 命令动态获取选项 | 新增 |
| 0.2.6 | query:url | URL 动态获取选项 | 新增 |

---

### v0.3 - ez-hooks 钩子

对应 DESIGN.md 2.1 ez-hooks

| 版本 | 功能 | 说明 | 测试 |
|------|------|------|------|
| 0.3.0 | post_run | 任务完成后执行脚本 | 新增 |
| 0.3.1 | pre_run | 任务执行前检查 | 新增 |
| 0.3.2 | on_error | 失败时执行 | 新增 |

---

### v0.4 - Plan 计划编排

对应 DESIGN.md 2.2 Plan

| 版本 | 功能 | 说明 | 测试 |
|------|------|------|------|
| 0.4.0 | plan list | 列出 .ez-plan.yaml 中的计划 | 新增 |
| 0.4.1 | plan show | 显示计划步骤 | 新增 |
| 0.4.2 | plan run | 顺序执行步骤 | 新增 |
| 0.4.3 | checkpoint | 断点暂停，交互确认 | 新增 |
| 0.4.4 | when 条件 | 条件分支执行 | 新增 |
| 0.4.5 | matrix | 矩阵组合执行 | 新增 |
| 0.4.6 | resume | 恢复中断的计划 | 新增 |

---

### v0.5 - Template 模板

对应 DESIGN.md 2.3 Template

| 版本 | 功能 | 说明 | 测试 |
|------|------|------|------|
| 0.5.0 | template list | 列出可用模板 | 新增 |
| 0.5.1 | template show | 显示模板参数 | 新增 |
| 0.5.2 | template use | 生成 Taskfile | 新增 |

---

### v0.6 - Plugin 插件

对应 DESIGN.md 2.4 Plugin 和 6.1 插件注册

| 版本 | 功能 | 说明 | 测试 |
|------|------|------|------|
| 0.6.0 | plugin 目录结构 | ~/.ez/plugins/{param,hook,template} | 新增 |
| 0.6.1 | plugin list | 列出已安装插件 | 新增 |
| 0.6.2 | param 插件 | 动态参数选项提供者 | 新增 |
| 0.6.3 | hook 插件 | 可复用的钩子脚本 | 新增 |
| 0.6.4 | template 插件 | 可复用的模板 | 新增 |
| 0.6.5 | plugin install | 从 URL 安装插件 | 新增 |

---

### v0.7 - 远程执行与结果归档

| 版本 | 功能 | 说明 | 测试 |
|------|------|------|------|
| 0.7.0 | remote-copy | 文件传输到远程主机 | ✅ |
| 0.7.1 | remote-exec | 远程命令执行 | ✅ |
| 0.7.2 | result-archive | 归档测试结果 | ✅ |
| 0.7.3 | result-stats | 显示测试统计 | ✅ |
| 0.7.4 | AI 插件 | ai-review, ai-suggest | ✅ |

---

### v0.8 - 日志系统与 ytt 模板

| 版本 | 功能 | 说明 | 测试 |
|------|------|------|------|
| 0.8.0 | 日志记录 | 任务执行日志到 .ez-logs/ | ✅ |
| 0.8.1 | log list | 列出最近日志 | ✅ |
| 0.8.2 | log show | 显示日志内容 | ✅ |
| 0.8.3 | log clean | 清理旧日志 | ✅ |
| 0.8.4 | ytt 模板 | 支持 ytt 复杂模板生成 | ✅ |

---

### v0.9 - 任务继承与组合

| 版本 | 功能 | 说明 | 测试 |
|------|------|------|------|
| 0.9.0 | ez-extends | 任务继承基础任务 | ✅ |
| 0.9.1 | ez-defaults | 覆盖继承的默认参数 | ✅ |
| 0.9.2 | ez-compose | 组合多个任务顺序执行 | ✅ |
| 0.9.3 | ez-log | 自定义日志目录和前缀 | ✅ |

---

## 已完成版本汇总

| 版本 | 功能 | 状态 |
|------|------|------|
| v0.1.x | 基础框架 (deps, core, commands) | ✅ |
| v0.2.x | ez-params 参数系统 | ✅ |
| v0.3.0 | ez-hooks 钩子系统 | ✅ |
| v0.4.x | Plan 计划编排 (matrix, when, resume) | ✅ |
| v0.5.x | Template 模板系统 | ✅ |
| v0.6.x | Plugin 插件系统 | ✅ |
| v0.7.x | 远程执行、结果归档、AI 插件 | ✅ |
| v0.8.x | 日志系统、ytt 模板支持 | ✅ |
| v0.9.x | 任务继承、组合、自定义日志路径 | ✅ |
| v1.0.x | Web Server/Client 分布式架构 | ✅ |
| v1.1.0 | 命令重塑 + Task-as-Folder + Tab 补全 | ✅ |
| v1.2.0 | Plan 编译系统 | ✅ |
| v1.3.0 | Workspace 隔离 + .ez/ 统一目录 | ✅ |
| v1.4.0-beta | 文件夹任务体系 + .ez/ 按粒度重组 | ✅ |
| v1.5.0-beta | 命令精简 + 依赖自动安装 + 目录整洁 | ✅ |

---

## 下一阶段: v1.0 - Web Server/Client 分布式架构

基于 DESIGN.md 第九章分布式执行架构

### v1.0 - Server 基础

| 版本 | 功能 | 说明 | 优先级 |
|------|------|------|--------|
| 1.0.0 | ez server start | 启动 HTTP 服务器 | P1 |
| 1.0.1 | REST API 基础 | /api/v1/tasks, /api/v1/nodes | P1 |
| 1.0.2 | SQLite 存储 | 节点、任务、执行记录 | P1 |
| 1.0.3 | 静态 Web UI | 简单 Dashboard 页面 | P1 |
| 1.0.4 | Dockerfile | Server 容器化部署 | P1 |

### v1.1 - Client 代理

| 版本 | 功能 | 说明 | 优先级 |
|------|------|------|--------|
| 1.1.0 | ez client start | 启动客户端代理 | P1 |
| 1.1.1 | 节点注册 | 连接 Server 并注册 | P1 |
| 1.1.2 | 心跳机制 | 定时上报状态 | P1 |
| 1.1.3 | 任务执行 | 接收并执行任务 | P1 |
| 1.1.4 | 日志上报 | 实时推送执行日志 | P1 |

### v1.2 - 分布式执行

| 版本 | 功能 | 说明 | 优先级 |
|------|------|------|--------|
| 1.2.0 | 任务分发 | Server 分配任务到 Client | P1 |
| 1.2.1 | 矩阵执行 | 多节点并行矩阵任务 | P1 |
| 1.2.2 | 结果聚合 | 收集各节点执行结果 | P1 |
| 1.2.3 | 失败重试 | 任务失败自动重试 | P2 |

### v1.3 - Web Dashboard

| 版本 | 功能 | 说明 | 优先级 |
|------|------|------|--------|
| 1.3.0 | 节点总览 | 节点状态、资源监控 | P1 |
| 1.3.1 | 任务中心 | 任务列表、快速执行 | P1 |
| 1.3.2 | 执行监控 | 实时状态、日志流 | P1 |
| 1.3.3 | 计划编排 | 可视化计划管理 | P2 |

### v1.4 - 增强功能

| 版本 | 功能 | 说明 | 优先级 |
|------|------|------|--------|
| 1.4.0 | Token 认证 | API 安全认证 | P1 |
| 1.4.1 | 节点标签 | 按标签选择节点 | P2 |
| 1.4.2 | docker-compose | 完整部署方案 | P1 |
| 1.4.3 | WebSocket 日志 | 实时日志推送 | P2 |

---

### v1.1 - 命令重塑 + Task-as-Folder + Tab 补全

| 版本 | 功能 | 说明 | 测试 |
|------|------|------|------|
| v1.1.0 | implicit run | `ez <task>` 直接执行, `ez` = `ez list` | ✅ |
| 1.1.1 | Task-as-Folder | `tasks/` 目录自动发现, [folder] 标记 | ✅ |
| 1.1.2 | ez new | 创建 `tasks/<name>/Taskfile.yml + task.yml` | ✅ |
| 1.1.3 | ez check | 验证 Taskfile 语法和依赖 | ✅ |
| 1.1.4 | Tab 补全 | `ez completion bash/zsh` 输出补全脚本 | ✅ |

---

### v1.2 - Plan 编译系统

| 版本 | 功能 | 说明 | 测试 |
|------|------|------|------|
| 1.2.0 | plan new | 创建 `plans/<name>.yml` | ✅ |
| 1.2.1 | plan add | 向 Plan 添加步骤 (--needs 依赖) | ✅ |
| 1.2.2 | plan build | 编译为 `.ez/plans/<name>/build/Taskfile.yml` | ✅ |
| 1.2.3 | plan check | 依赖完备性验证 (拓扑排序, 产物匹配) | ✅ |
| 1.2.4 | plan run (v2) | build + check + execute 一体化 | ✅ |
| 1.2.5 | implicit plan run | `ez plan <name>` = `ez plan run <name>` | ✅ |

---

### v1.3 - Workspace 隔离 + .ez/ 统一目录

| 版本 | 功能 | 说明 | 测试 |
|------|------|------|------|
| 1.3.0 | .ez/ 统一目录 | build/workspace/artifacts/logs/state 收归 .ez/ | ✅ |
| 1.3.1 | --workspace=auto | 自动创建隔离工作区执行 | ✅ |
| 1.3.2 | --workspace=name | 指定工作区名称 | ✅ |

---

### v1.4 - 文件夹任务体系 + .ez/ 按粒度重组

| 版本 | 功能 | 说明 | 测试 |
|------|------|------|------|
| 1.4.0 | tasks/ 文件夹任务 | 文件夹任务体系，tasks/ 目录 | ✅ |
| 1.4.1 | task.yml | AI-readable 元数据，任务创建自动生成 | ✅ |
| 1.4.2 | .ez/ 按粒度 | .ez/tasks/<name>/ + .ez/plans/<name>/ | ✅ |
| 1.4.3 | 默认 workspace | 文件夹任务默认在 .ez/tasks/<name>/workspace/ 执行 | ✅ |
| 1.4.4 | --no-workspace | 在源码目录直接执行（opt-out） | ✅ |
| 1.4.5 | ez export/import | 导出/导入文件夹任务 | ✅ |
| 1.4.6 | ez clean | 按粒度清理运行时数据 | ✅ |

---

### v1.5 - 命令精简 + 依赖自动安装 + 目录整洁

| 版本 | 功能 | 说明 | 测试 |
|------|------|------|------|
| 1.5.0 | Help 菜单精简 | 4 区块聚焦核心，server/client 收为一行提示 | ✅ |
| 1.5.1 | 依赖自动安装 | ensure_deps() 首次运行自动安装，支持离线拷贝 | ✅ |
| 1.5.2 | 目录整洁 | client/ → server/client/，completion/ → lib/completion/ | ✅ |
| 1.5.3 | 设计原则 | 添加便携适配、精简核心原则到 CLAUDE.md/DESIGN.md | ✅ |

---

## v1.5+ - 长期规划

### v1.5 - Server 资产管理 + 自动部署

| 版本 | 功能 | 说明 | 优先级 |
|------|------|------|--------|
| 1.5.0 | assets 表 | Server 端 assets 数据库表 | P1 |
| 1.5.1 | ez server import | 批量导入 CSV 资产 | P1 |
| 1.5.2 | ez server deploy | SSH 自动部署 client 到资产 | P1 |
| 1.5.3 | Web UI 扩展 | 资产导入/部署操作界面 | P2 |

### 参数验证与缓存

| 版本 | 功能 | 说明 | 优先级 |
|------|------|------|--------|
| 1.5.0 | validation.rule | 参数验证规则 (regex, semver) | P2 |
| 1.5.1 | validation.range | 数值范围验证 (min, max) | P2 |
| 1.5.2 | query.cache | 查询结果缓存 (TTL) | P3 |
| 1.5.3 | query.transform | 结果转换 (jq 表达式) | P3 |

### 多文件发现

| 版本 | 功能 | 说明 | 优先级 |
|------|------|------|--------|
| 1.6.0 | Makefile 发现 | 自动包装 make 目标 | P3 |
| 1.6.1 | *.sh 发现 | 包装 shell 脚本 | P3 |
| 1.6.2 | 子目录扫描 | 递归发现任务文件 | P3 |

### 团队协作

| 版本 | 功能 | 说明 | 优先级 |
|------|------|------|--------|
| 1.7.0 | plugin registry | 插件注册中心 | P3 |
| 1.7.1 | team:// 协议 | 团队插件共享 | P3 |
| 1.7.2 | Workspace | 多项目管理 | P3 |

---

## 测试覆盖 (当前)

| 测试文件 | 测试项 | 状态 |
|----------|--------|------|
| 01-deps.yml | yq, task 二进制 | ✅ |
| 02-core.yml | 核心函数库 | ✅ |
| 03-commands.yml | list, show, run, export/import, clean | ✅ |
| 04-nesting.yml | 任务嵌套和依赖 | ✅ |
| 05-vars.yml | 变量传递 | ✅ |
| 06-query.yml | 动态选项查询 | ✅ |
| 07-hooks.yml | 钩子系统 | ✅ |
| 08-plan.yml | 计划编排 | ✅ |
| 09-template.yml | 模板系统 | ✅ |
| 10-plugin.yml | 插件系统 | ✅ |
| 11-remote.yml | 远程执行和归档 | ✅ |
| 12-log.yml | 日志系统 | ✅ |
| 13-inheritance.yml | 任务继承和组合 | ✅ |
| 14-server.yml | Server/Client 分布式 | ✅ |
| 16-plan-compile.yml | Plan 编译系统 | ✅ |
| 17-workspace.yml | Workspace + 文件夹任务默认 workspace | ✅ |

**总测试数: 59+ | 通过率: 100%**

---

### 当前状态

**当前版本: 1.5.0-beta**

已实现:
- ✅ Task 任务系统 (ez-params, ez-hooks)
- ✅ Plan 计划编排 (steps, matrix, checkpoint, when, resume)
- ✅ Template 模板系统 (list, show, use, ytt)
- ✅ Plugin 插件系统 (param, hook, template)
- ✅ 远程执行 (remote-copy, remote-exec)
- ✅ 结果归档 (result-archive, result-stats)
- ✅ AI 插件 (ai-review, ai-suggest)
- ✅ 日志系统 (list, show, clean, 任务上下文)
- ✅ 任务继承 (ez-extends, ez-defaults)
- ✅ 任务组合 (ez-compose)
- ✅ 自定义日志路径 (ez-log)
- ✅ **Web Server** (REST API, WebSocket, Dashboard)
- ✅ **Client Agent** (节点注册, 任务执行, 日志上报)
- ✅ **Docker 部署** (Dockerfile, docker-compose)
- ✅ **命令重塑** (implicit run, Task-as-Folder, Tab 补全)
- ✅ **Plan 编译** (plan new/add/build/check, 拓扑排序, 依赖验证)
- ✅ **Workspace 隔离** (.ez/ 统一目录, --workspace 隔离执行)
- ✅ **文件夹任务** (tasks/ 目录, task.yml 元数据, 默认 workspace)
- ✅ **按粒度 .ez/** (.ez/tasks/<name>/, .ez/plans/<name>/)
- ✅ **任务管理** (ez export/import, ez clean)
- ✅ **命令精简** (Help 4 区块聚焦核心, server/client 收纳)
- ✅ **依赖自动安装** (ensure_deps, 首次运行自动安装, 离线拷贝)
- ✅ **目录整洁** (client/ → server/client/, completion/ → lib/completion/)

待实现:
- v1.5+: Server 资产管理 + 自动部署
- P2/P3: validation 参数验证、query 缓存、Makefile 发现

---

## 测试 Taskfile 模板

```yaml
version: '3'

tasks:
  hello:
    desc: "Say hello"
    cmds:
      - echo "Hello, {{.EZ_NAME}}!"
    ez-params:
      - name: "name"
        type: "input"
        default: "World"
        help: "Your name"

  build:
    desc: "Build project"
    cmds:
      - echo "Building for {{.EZ_ARCH}}"
    ez-params:
      - name: "arch"
        type: "select"
        options: ["x86_64", "aarch64", "riscv64"]
        default: "x86_64"
        help: "Target architecture"

  clean:
    desc: "Clean artifacts"
    cmds:
      - echo "Cleaning..."
```
