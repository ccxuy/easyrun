# EZ (EasyRun) — Claude 开发指南

## 项目概要

EZ 是 go-task 的超集前端，纯 Bash 实现。go-task 是执行引擎，EZ 在其上提供参数管理、任务编排、工作区隔离等能力。

核心文件:
- `ez` — 主入口脚本（~2800 行 Bash）
- `lib/ez-core.sh` — 核心函数库（~1100 行）
- `Taskfile.yml` — 根任务定义 + 测试入口
- `DESIGN.md` — 设计规格（概念、格式、约束）

## 架构原则

1. **Task 是核心** — EZ Task = go-task task + ez-* 扩展。不发明新执行概念，只扩展 go-task。
2. **超集不替代** — 所有 ez-* 字段可被 go-task 安全忽略，EZ 生成的 Taskfile 是合法 go-task 文件。
3. **Workspace 默认隔离** — 文件夹任务默认在 `.ez/tasks/<name>/workspace/` 执行，`--no-workspace` 可关闭。
4. **按粒度组织运行时** — `.ez/tasks/<name>/` 和 `.ez/plans/<name>/ ` 按任务/计划粒度存放日志、产物、状态。
5. **根目录整洁** — 项目根只放核心文件，运行时数据统一收归 `.ez/`。

## 目录结构

```
easyrun/
├── ez                    # 主入口（唯一可执行文件）
├── lib/ez-core.sh        # 核心库
├── dep/                  # 依赖二进制 (go-task, yq)
├── tasks/                # 文件夹任务（EZ 自动发现）
├── plans/                # Plan 定义
├── Taskfile.yml          # 根任务
├── .ez/                  # 运行时数据（已 gitignore）
│   ├── tasks/<name>/     #   workspace / logs / artifacts
│   └── plans/<name>/     #   build / logs / state
├── test/selftest/        # 自测试套件
├── server/               # Server 组件
├── client/               # Client Agent
├── docs/                 # 详细文档
├── DESIGN.md             # 设计规格
├── PLAN.md               # 开发计划
└── README.md             # 基础用法
```

## 开发模式

### 版本策略
- 当前全部为 beta 版本，格式 `X.Y.Z-beta`
- 未声明稳定版之前，不考虑向后兼容
- 大版本标志性功能对应（v1.4 = Task 体系重整）

### 提交规范
- **小功能点即提交**，不积攒大量变更
- 提交信息格式: `<scope>: <简述>`
  - 功能: `v1.4-beta: Skill 体系 + .ez/ 按粒度重组`
  - 文档: `docs: v1.4 设计规格 + README 精简`
  - 修复: `fix: plan build 输出路径`
  - 测试: `test: 添加 workspace 隔离测试`
- 每次提交确保测试通过

### 测试组织
- 所有测试集中在 `test/selftest/` 目录
- 测试 fixtures 放在 `test/selftest/fixtures/`
- 每个功能模块一个测试文件: `01-deps.yml`, `02-core.yml`, ...
- 运行全部测试: `./ez run test` 或 `./dep/task test`
- 新功能必须有对应测试

### 文档分层
- `README.md` — 基础用法和功能概览（简洁）
- `DESIGN.md` — 设计哲学、概念规格、格式定义（权威）
- `PLAN.md` — 迭代计划、进度追踪、测试覆盖
- `docs/` — 各功能的详细使用文档

## 代码规范

### Bash 风格
- 函数命名: `snake_case`，公共函数无前缀，内部函数 `_` 前缀
- 变量命名: 全局 `EZ_UPPER_CASE`，局部 `local lower_case`
- 错误处理: `die "message"` 退出，`warn "message"` 警告
- 输出: `info "message"` 正常信息，颜色输出通过 `$GREEN`/`$RED` 等

### 核心函数（lib/ez-core.sh）
- `is_folder_task(name)` — 检查是否为文件夹任务
- `get_folder_tasks()` — 列出所有文件夹任务
- `get_task_runtime_dir(name)` — `.ez/tasks/<name>/`
- `get_plan_dir(name)` — `.ez/plans/<name>/`
- `create_workspace(name)` — 创建隔离工作区
- `get_log_path(task, run_id)` — 日志路径

### 命令路由（ez）
- `cmd_<command>()` 函数处理对应命令
- `main()` 中 case 语句路由
- implicit run: 未知命令先查任务，找到则执行

## 当前状态

版本: `1.4.0-beta`
测试: 17 组，100% 通过
下一步: v1.5 Server 资产管理
