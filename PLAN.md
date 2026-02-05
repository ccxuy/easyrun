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
│   ├── go-task.md        # go-task 参考文档
│   └── yq.md             # yq 参考文档
├── install-deps.sh       # 依赖安装脚本
├── Taskfile.yml          # 示例/测试文件
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
| `check_deps` | 检查依赖是否存在 |
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

---

## 下一阶段: v0.8 - 增强功能

基于 DESIGN.md 4.2 参数验证和 6.2 插件上下文

### v0.8 - 参数验证与缓存

| 版本 | 功能 | 说明 | 优先级 |
|------|------|------|--------|
| 0.8.0 | validation.rule | 参数验证规则 (regex, semver) | P2 |
| 0.8.1 | validation.range | 数值范围验证 (min, max) | P2 |
| 0.8.2 | query.cache | 查询结果缓存 (TTL) | P3 |
| 0.8.3 | query.transform | 结果转换 (jq 表达式) | P3 |

### v0.9 - 多文件发现

| 版本 | 功能 | 说明 | 优先级 |
|------|------|------|--------|
| 0.9.0 | Makefile 发现 | 自动包装 make 目标 | P3 |
| 0.9.1 | *.sh 发现 | 包装 shell 脚本 | P3 |
| 0.9.2 | 子目录扫描 | 递归发现任务文件 | P3 |

### v1.0 - 团队协作

| 版本 | 功能 | 说明 | 优先级 |
|------|------|------|--------|
| 1.0.0 | plugin registry | 插件注册中心 | P3 |
| 1.0.1 | team:// 协议 | 团队插件共享 | P3 |
| 1.0.2 | Workspace | 多项目管理 | P3 |

---

## 测试覆盖 (当前)

| 测试文件 | 测试项 | 状态 |
|----------|--------|------|
| 01-deps.yml | yq, task 二进制 | ✅ |
| 02-core.yml | 核心函数库 | ✅ |
| 03-commands.yml | list, show, run | ✅ |
| 04-nesting.yml | 任务嵌套和依赖 | ✅ |
| 05-vars.yml | 变量传递 | ✅ |
| 06-query.yml | 动态选项查询 | ✅ |
| 07-hooks.yml | 钩子系统 | ✅ |
| 08-plan.yml | 计划编排 | ✅ |
| 09-template.yml | 模板系统 | ✅ |
| 10-plugin.yml | 插件系统 | ✅ |
| 11-remote.yml | 远程执行和归档 | ✅ |

**总测试数: 40 | 通过率: 100%**

---

### 当前状态

**DESIGN.md 核心需求完成度: 95%**

已实现:
- ✅ Task 任务系统 (ez-params, ez-hooks)
- ✅ Plan 计划编排 (steps, matrix, checkpoint, when, resume)
- ✅ Template 模板系统 (list, show, use)
- ✅ Plugin 插件系统 (param, hook, template)
- ✅ 远程执行 (remote-copy, remote-exec)
- ✅ 结果归档 (result-archive, result-stats)
- ✅ AI 插件 (ai-review, ai-suggest)

待实现 (P2/P3):
- validation 参数验证规则
- query 缓存机制
- Makefile/sh 自动发现
- 团队插件仓库

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
