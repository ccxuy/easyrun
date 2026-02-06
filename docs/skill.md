# Skill 技能系统

Skill 是 EZ 的核心概念 — 自包含、可复用、AI 可理解的执行单元。

## 目录结构

```
skills/
├── kernel-build/
│   ├── Taskfile.yml      # go-task 执行定义
│   ├── skill.yml         # EZ 元数据（可选）
│   ├── scripts/          # 辅助脚本
│   └── config/           # 配置文件
└── deploy/
    ├── Taskfile.yml
    └── skill.yml
```

Skill 在 `ez list` 中以 `[skill]` 标记显示，与根 Taskfile 中的普通 task 区分。

## 创建 Skill

```bash
ez new my-skill
```

自动生成:
- `skills/my-skill/Taskfile.yml` — go-task 执行定义
- `skills/my-skill/skill.yml` — 元数据模板

## skill.yml 元数据

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

**解析优先级**: `skill.yml params` > `Taskfile ez-params` > 无参数

## 执行

```bash
# 默认在 workspace 中执行（隔离）
ez my-skill

# 在源码目录直接执行
ez my-skill --no-workspace

# 预设参数
ez my-skill EZ_ARCH=arm64

# 预览
ez my-skill --dry-run
```

Skill 默认在 `.ez/skills/<name>/workspace/` 中执行，防止污染源码。使用 `--no-workspace` 在 `skills/<name>/` 目录直接执行。

## 查看详情

```bash
ez show my-skill
```

显示 Taskfile 命令、参数定义，以及 skill.yml 中的 desc、usage、tags。

## 导出与导入

```bash
# 导出为 tar.gz
ez skill export my-skill
# → my-skill.tar.gz (含 Taskfile.yml + skill.yml + scripts/)

# 导入
ez skill import my-skill.tar.gz
# → skills/my-skill/
```

AI agent（Claude、OpenCode 等）可以:
1. 读取 `skill.yml` 理解 Skill 的能力和参数
2. 调用 `ez skill import` 安装到项目
3. 通过 `ez <skill-name>` 执行

## 运行时数据

每个 Skill 的运行时数据按粒度组织在 `.ez/skills/<name>/`:

```
.ez/skills/kernel-build/
├── workspace/        # 默认执行目录
├── logs/             # 执行日志
└── artifacts/        # 输出产物
```

清理:

```bash
ez clean kernel-build     # 清理单个 Skill
ez clean --all            # 清理全部
ez clean --logs           # 仅清理日志
ez clean --workspace      # 仅清理工作区
```
