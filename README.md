# EZ - go-task 超集前端

EZ 是 [go-task](https://github.com/go-task/task) 的超集前端，专注于参数管理、任务编排和工作区隔离。go-task 是执行引擎，EZ 在其上提供智能层。

**当前版本: 1.4.0-beta** (beta 阶段，不保证向后兼容)

## 核心概念

| 概念 | 说明 |
|------|------|
| **Task** (任务) | go-task task 的超集，支持 `ez-*` 扩展字段 |
| **文件夹任务** | `tasks/<name>/` 下自包含的任务目录，含 `Taskfile.yml` + `task.yml` 元数据 |
| **Plan** (计划) | 多 Task 的编排，编译为标准 go-task Taskfile |
| **Workspace** (工作区) | 隔离执行目录，文件夹任务默认在 workspace 中执行 |

详见 [DESIGN.md](DESIGN.md) 和 [docs/](docs/)。

## 快速开始

```bash
# 安装依赖
./dep/install-deps.sh

# 查看可用任务
./ez                      # 等价于 ez list

# 执行任务 (implicit run)
./ez hello                # 等价于 ez run hello
./ez hello EZ_NAME=Test   # 预设参数

# 查看任务详情
./ez show hello

# Tab 补全
eval "$(./ez completion bash)"
```

## 命令一览

### 基础操作
```
ez                        列出所有任务 (= ez list)
ez <name>                 直接执行任务
ez <name> --dry-run       预览执行
ez list [filter]          列出任务（文件夹任务标记 [folder]）
ez show <name>            显示详情（含 task.yml 元数据）
ez run <name> [vars]      运行任务（交互式参数）
ez check [name]           验证 Taskfile 语法
ez version / help         版本信息 / 帮助
```

### 文件夹任务管理
```
ez new <name>             创建文件夹任务 (tasks/<name>/ + task.yml)
ez export <name>          导出为 .tar.gz
ez import <path>          导入文件夹任务
ez clean <name>           清理运行时数据 (.ez/tasks/<name>/)
ez clean --all            清理全部运行时
```

### Plan 编排
```
ez plan list              列出所有计划
ez plan new <name>        创建 Plan
ez plan add <name> <task> 添加步骤 (--needs 依赖)
ez plan build <name>      编译为 Taskfile
ez plan check <name>      验证依赖完备性
ez plan run <name>        编译 + 执行
ez plan <name>            等价于 ez plan run <name>
```

## 项目结构

```
easyrun/
├── ez                    # 主入口脚本
├── lib/ez-core.sh        # 核心函数库
├── dep/                  # 依赖二进制 (go-task, yq)
├── tasks/                # 文件夹任务
├── plans/                # Plan 定义
├── Taskfile.yml          # 根 Taskfile（行内任务）
├── .ez/                  # 运行时数据（gitignore）
│   ├── tasks/<name>/     #   workspace / logs / artifacts
│   └── plans/<name>/     #   build / logs / state
├── test/selftest/        # 自测试套件 (17 组)
└── DESIGN.md             # 设计规格
```

## 测试

```bash
./ez run test             # 运行全部 17 组测试
./dep/task test:quick     # 快速测试
```

## 依赖

- [go-task](https://github.com/go-task/task) - 任务执行引擎
- [yq](https://github.com/mikefarah/yq) - YAML 处理器

## License

MIT
