# 文件夹任务

文件夹任务是 `tasks/<name>/` 下自包含的任务目录。每个文件夹任务包含 `Taskfile.yml`（go-task 执行定义）和可选的 `task.yml`（EZ 元数据）。

## 目录结构

```
tasks/
├── kernel-build/
│   ├── Taskfile.yml      # go-task 执行定义
│   ├── task.yml          # EZ 元数据（可选）
│   ├── scripts/          # 辅助脚本
│   └── config/           # 配置文件
└── deploy/
    ├── Taskfile.yml
    └── task.yml
```

文件夹任务在 `ez list` 中以 `[folder]` 标记显示，与根 Taskfile 中的行内任务区分。

## 创建文件夹任务

```bash
ez new my-task
```

自动生成:
- `tasks/my-task/Taskfile.yml` — go-task 执行定义
- `tasks/my-task/task.yml` — 元数据模板

## task.yml 元数据

```yaml
name: kernel-build
version: "1.0"
desc: "构建 Linux 内核"

# 人类 + AI 共用的使用说明
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

**解析优先级**: `task.yml params` > `Taskfile ez-params` > 无参数

## 执行

```bash
# 默认在 workspace 中执行（隔离）
ez my-task

# 在源码目录直接执行
ez my-task --no-workspace

# 预设参数
ez my-task EZ_ARCH=arm64

# 预览
ez my-task --dry-run
```

文件夹任务默认在 `.ez/tasks/<name>/workspace/` 中执行，防止污染源码。使用 `--no-workspace` 在 `tasks/<name>/` 目录直接执行。

## 查看详情

```bash
ez show my-task
```

显示 Taskfile 命令、参数定义，以及 task.yml 中的 desc、usage、tags。

## 导出与导入

```bash
# 导出为 tar.gz
ez export my-task
# → my-task.tar.gz (含 Taskfile.yml + task.yml + scripts/)

# 导入
ez import my-task.tar.gz
# → tasks/my-task/
```

AI agent（Claude、OpenCode 等）可以:
1. 读取 `task.yml` 理解任务的能力和参数
2. 调用 `ez import` 安装到项目
3. 通过 `ez <task-name>` 执行

## 运行时数据

每个文件夹任务的运行时数据按粒度组织在 `.ez/tasks/<name>/`:

```
.ez/tasks/kernel-build/
├── workspace/        # 默认执行目录
├── logs/             # 执行日志
└── artifacts/        # 输出产物
```

清理:

```bash
ez clean kernel-build     # 清理单个任务
ez clean --all            # 清理全部
ez clean --logs           # 仅清理日志
ez clean --workspace      # 仅清理工作区
```
