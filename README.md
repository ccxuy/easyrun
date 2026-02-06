# EZ - go-task 智能前端

EZ 是 [go-task](https://github.com/go-task/task) 的智能驾驶舱，专注于任务发现、参数管理和可视化编排。go-task 是执行引擎，EZ 是上层智能层。

**当前版本: 1.4.0-beta**

## 核心概念

| 概念 | 说明 |
|------|------|
| **Skill** (技能) | 自包含的可复用执行单元，位于 `skills/` 目录，含 `skill.yml` 元数据 |
| **Plan** (计划) | 多 Skill 的编排，编译为标准 go-task Taskfile |
| **Workspace** (工作区) | 隔离执行目录，Skill 默认在 workspace 中执行 |

详见 [DESIGN.md](DESIGN.md) 设计规格。

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
ez <name>                 直接执行任务或 Skill
ez <name> --dry-run       预览执行
ez list [filter]          列出任务（Skill 标记 [skill]）
ez show <name>            显示详情（含 skill.yml 元数据）
ez run <name> [vars]      运行任务（交互式参数）
ez check [name]           验证 Taskfile 语法
ez version / help         版本信息 / 帮助
```

### Skill 管理
```
ez new <name>             创建 Skill (skills/<name>/ + skill.yml)
ez skill list             列出所有 Skill
ez skill export <name>    导出为 .tar.gz
ez skill import <path>    导入 Skill
ez clean <name>           清理运行时数据 (.ez/skills/<name>/)
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
├── skills/               # Skill 目录（自包含技能）
├── plans/                # Plan 定义
├── Taskfile.yml          # 根 Taskfile（简单任务）
├── .ez/                  # 运行时数据（gitignore）
│   ├── skills/<name>/    #   workspace / logs / artifacts
│   └── plans/<name>/     #   build / logs / state
├── task/selftest/        # 自测试套件 (17 组)
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
