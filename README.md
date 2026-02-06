# EZ - go-task 超集前端

EZ 是 [go-task](https://github.com/go-task/task) 的超集前端，专注于参数管理、任务编排和工作区隔离。go-task 是执行引擎，EZ 在其上提供智能层。

**当前版本: 2.0.0-beta** (beta 阶段，不保证向后兼容)

## 核心概念

| 概念 | 说明 |
|------|------|
| **Task** (任务) | go-task task 的超集，支持 `ez-*` 扩展字段 |
| **目录任务** | `tasks/<name>/` 下自包含的任务目录，含 `Taskfile.yml` + `task.yml` 元数据 |
| **Plan** (计划) | 多 Task 的编排，编译为标准 go-task Taskfile |
| **Workspace** (工作区) | 项目根 `workspace/` 下的隔离执行目录，方便 debug 和人工介入 |

详见 [DESIGN.md](DESIGN.md)。

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
ez list [filter]          列出任务（目录任务标记 [dir]）
ez show <name>            显示详情（含 task.yml 元数据）
ez run <name> [vars]      运行任务（交互式参数）
ez check [name]           验证 Taskfile 语法
ez version / help         版本信息 / 帮助
```

### 目录任务管理
```
ez new <name>             创建目录任务 (tasks/<name>/ + task.yml)
ez export <name>          导出为 .tar.gz
ez import <path>          导入目录任务
ez clean <name>           清理工作区 (workspace/<name>/)
ez clean --workspace      清理全部工作区
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

### Workspace + 迭代工作流
```
ez ws                     列出所有工作区
ez ws <name>              显示工作区详情（上次运行、参数、状态）
ez ws clean <name|--all>  清理工作区
ez rerun <workspace>      使用保存的参数重新执行
ez rerun <ws> KEY=val     覆盖部分参数重新执行
ez rerun                  重复最近一次执行
```

### Matrix 多变体并行
```
ez matrix <task> --vary KEY=v1,v2           单维度并行
ez matrix <task> --vary K1=a,b --vary K2=x,y  多维度组合
ez matrix <task> --vary KEY=v1,v2 FIXED=val  固定参数
ez matrix <task> --vary KEY=v1,v2 --dry-run  预览
```

## 典型工作流：内核测试

```bash
# 1. 首次运行完整流程
ez plan run kernel-ci -w ci-x86 EZ_ARCH=x86_64

# 2. 发现 bug，进入工作区修改代码
cd workspace/ci-x86/src
vim drivers/xxx/bug.c

# 3. 重新运行（使用保存的参数）
ez rerun ci-x86

# 4. 同时测试多个架构
ez matrix kernel-build --vary EZ_ARCH=x86_64,arm64,riscv64

# 5. 查看所有工作区状态
ez ws
```

## 项目结构

```
easyrun/
├── ez                    # 主入口脚本
├── lib/
│   ├── ez-core.sh        # 核心函数库
│   └── completion/       # Tab 补全脚本
├── dep/                  # 依赖二进制 (首次运行自动安装)
├── tasks/                # 目录任务
├── plans/                # Plan 定义
├── Taskfile.yml          # 根 Taskfile（行内任务）
├── workspace/            # 执行工作区（gitignore）
│   ├── <name>/           #   任务工作区
│   └── <task>--<variant>/#   matrix 变体工作区
├── .ez/                  # 内部状态（gitignore）
│   ├── plans/<name>/     #   编译输出 / 恢复状态
│   └── logs/             #   全局日志
├── test/selftest/        # 自测试套件 (19 组)
├── server/               # Server + Client（可选）
└── DESIGN.md             # 设计规格
```

## 测试

```bash
./ez run test             # 运行全部 19 组测试
./dep/task test:quick     # 快速测试
```

## 依赖

- [go-task](https://github.com/go-task/task) - 任务执行引擎
- [yq](https://github.com/mikefarah/yq) - YAML 处理器

## License

MIT
