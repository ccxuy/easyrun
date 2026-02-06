# EZ - 轻量任务编排平台

EZ 是自包含的轻量任务编排平台，将 [go-task](https://github.com/go-task/task) 作为底层执行引擎，在其上构建参数管理、Plan 编排、工作区隔离、可视化管理等能力。

**当前版本: 2.1.0**

## 核心概念

| 概念 | 说明 |
|------|------|
| **行内任务** | 定义在根 `Taskfile.yml` 中的 task |
| **目录任务** | `tasks/<name>/` 下自包含的任务目录 |
| **工具任务** | `lib/tools/<name>.yml`，EZ 内置工具（server、doctor 等） |
| **Plan** (计划) | 多 Task 的 DAG 编排，编译为标准 go-task Taskfile |
| **Workspace** (工作区) | `workspace/` 下的隔离执行目录 |

详见 [DESIGN.md](DESIGN.md)。

## 快速开始

```bash
# 查看项目概况
./ez

# 执行任务
./ez hello                    # implicit run
./ez hello EZ_NAME=Test       # 带参数执行

# 查看任务详情
./ez show hello

# 工具任务
./ez doctor                   # 环境检查
./ez tools                    # 列出工具任务

# Tab 补全
eval "$(./ez completion bash)"
```

## 命令一览

### 基础操作
```
ez                        项目概况摘要
ez <name>                 直接执行任务
ez <name> --dry-run       预览执行
ez list [filter]          列出任务（-t 含工具任务）
ez show <name>            显示任务详情
ez run <name> [vars]      运行任务（交互式参数）
ez check [name]           验证 Taskfile 语法
ez version / help         版本信息 / 帮助
```

### 工具任务
```
ez tools                  列出工具任务
ez doctor                 检查运行环境
ez server                 启动 Web 管理平台
```

### 目录任务管理
```
ez new <name>             创建目录任务
ez export <name>          导出为 .tar.gz
ez import <path>          导入目录任务
ez clean <name|--all>     清理运行时数据
```

### Plan 编排
```
ez plan list              列出计划
ez plan new <name>        创建 Plan
ez plan add <name> <task> 添加步骤 (--needs 依赖)
ez plan build <name>      编译为 Taskfile
ez plan check <name>      验证依赖完备性
ez plan run <name>        编译 + 执行
```

### Workspace + 迭代工作流
```
ez ws                     列出所有工作区
ez ws <name>              工作区详情
ez rerun <workspace>      使用保存参数重新执行
ez rerun <ws> KEY=val     覆盖部分参数重执行
ez matrix <task> --vary KEY=v1,v2  多变体并行
```

## Web 管理平台

EZ Server 提供可视化的作业管理平台：

- **任务浏览** — 树形任务列表，支持命名空间展开
- **Plan DAG 视图** — 实时查看任务执行进度，节点可展开详情
- **执行记录** — 合并 Server 作业和 CLI 上报的执行数据
- **统计图表** — 执行趋势、任务分布、耗时分析

```bash
# 直接启动
./ez server

# Docker 部署
docker compose -f server/docker-compose.yml up -d
```

## 典型工作流

```bash
# 1. 首次运行完整流程
ez plan run kernel-ci -w ci-x86 EZ_ARCH=x86_64

# 2. 进入工作区修改代码
cd workspace/ci-x86/src && vim drivers/xxx/bug.c

# 3. 重新运行
ez rerun ci-x86

# 4. 多架构并行测试
ez matrix kernel-build --vary EZ_ARCH=x86_64,arm64,riscv64

# 5. 查看工作区状态
ez ws
```

## 项目结构

```
easyrun/
├── ez                    # 主入口脚本
├── lib/
│   ├── ez-core.sh        # 核心函数库
│   ├── tools/            # 工具任务 (server, doctor, prune)
│   └── completion/       # Tab 补全脚本
├── dep/                  # 依赖二进制 (首次运行自动安装)
├── tasks/                # 目录任务
├── plans/                # Plan 定义
├── plugins/              # 项目级插件 (stats-reporter 等)
├── templates/            # 任务模板
├── Taskfile.yml          # 根 Taskfile（行内任务）
├── workspace/            # 执行工作区（gitignore）
├── server/               # Web 管理平台（Flask + SocketIO）
├── test/selftest/        # 自测试套件
└── DESIGN.md             # 设计规格
```

## 统计上报

CLI 执行的任务会通过 `stats-reporter` 插件自动上报到 Server（如果可达），在 Web UI 的统计页面可查看汇总数据。

## 测试

```bash
./ez run test             # 运行全部测试
./dep/task test:quick     # 快速测试
```

## 依赖

- [go-task](https://github.com/go-task/task) - 任务执行引擎
- [yq](https://github.com/mikefarah/yq) - YAML 处理器

## License

MIT
