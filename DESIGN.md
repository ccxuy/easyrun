EZ 任务编排框架设计规格

〇、设计哲学

0.1 架构分层

```
┌─────────────────────────────────────────────┐
│           EZ Layer (智能编排)                │
│                                             │
│  Skill (技能)     Plan (计划)               │
│  - 自包含          - 编排技能               │
│  - 可导入/导出     - 拓扑依赖               │
│  - AI 可理解       - 产物传递               │
│  - skills/xxx/    - plans/xxx.yml           │
│                                             │
├─────────────────────────────────────────────┤
│           go-task Layer (执行引擎)          │
│                                             │
│  task (任务) = Taskfile.yml 条目            │
│  go-task 原生概念，EZ 不改变其语义          │
│                                             │
└─────────────────────────────────────────────┘
```

0.2 六条设计原则

1. **引擎/驾驶舱分离** — go-task 是执行引擎，EZ 是智能驾驶舱。EZ 绝不重新实现 go-task 已有的功能，也不将 go-task 术语（如"task"）暴露为 EZ 自身的顶层概念。
2. **Skill 是分发单元** — 自包含、可描述、可导入/导出。每个 Skill 同时面向人类和 AI agent 设计。`skills/` 目录是 EZ 自有概念，与 go-task 的 task 明确区分。
3. **Plan 是编排单元** — 编排多个 Skill 的执行顺序、依赖和产物传递。Plan 编译为标准 go-task Taskfile，实现「定义归 EZ、执行归 go-task」的分工。
4. **Workspace 是执行沙箱** — Skill 默认在隔离 workspace 中执行，防止污染源码目录。
5. **按粒度组织运行时数据** — `.ez/` 按 Skill/Plan 名称组织子目录，`rm -rf .ez/skills/X` 即可清理单个 Skill 的所有运行时数据。
6. **AI-Native** — Skill 的 `skill.yml` 元数据兼顾人类可读和 AI agent 可解析，可直接作为 Claude/OpenCode 的 skill 导入。

0.3 术语边界

| 层级 | 术语 | 属于 | 说明 |
|------|------|------|------|
| EZ | Skill (技能) | EZ 自有 | 自包含、可复用的执行单元，位于 `skills/` |
| EZ | Plan (计划) | EZ 自有 | 多 Skill 的编排，位于 `plans/` |
| EZ | Step (步骤) | EZ 自有 | Plan 内的单个环节 |
| EZ | Artifact (产物) | EZ 自有 | Skill 的输出文件，可被下游引用 |
| EZ | Workspace (工作区) | EZ 自有 | 隔离的执行目录 |
| go-task | task (任务) | go-task 原生 | Taskfile.yml 中的条目，EZ 仅透传 |
| go-task | Taskfile.yml | go-task 原生 | 执行定义文件 |

**生命周期**: `pending → running → success / failed`

---

一、设计哲学（兼容层）

EZ 是 go-task 的智能前端，不是替代品。

· 执行层：100% 复用 go-task
· 编排层：专注于任务发现、参数管理和可视化编排
· 设计目标：简单易用、快速上手、渐进增强

二、核心概念

2.1 Task（任务）- 可执行的工作单元

本质：完全兼容 go-task 语法，增加 ez- 扩展字段
约束：所有 ez- 扩展字段必须能被 go-task 安全忽略
don't generate any go file, but use the following tool instead:
https://github.com/go-task/task
https://mikefarah/yq
download the reference as your manual

```yaml
# 任务定义（Taskfile.yml格式）
tasks:
  build-kernel:
    desc: "构建Linux内核"
    cmds:
      - make defconfig ARCH={{.EZ_ARCH}}
      - make -j$(nproc) ARCH={{.EZ_ARCH}}
    
    # EZ扩展字段（go-task会忽略）
    ez-params:
      - name: "arch"
        type: "select"
        options: ["x86_64", "aarch64", "riscv64"]
        default: "x86_64"
        help: "目标架构"
      
      - name: "optimization"
        type: "select"
        options: ["O0", "O1", "O2", "O3", "Os"]
        default: "O2"
        help: "优化级别"
    
    ez-hooks:
      post_run:
        - name: "size-analysis"
          script: "du -h vmlinux bzImage | sort -hr"
```

2.2 Plan（计划）- 任务的编排流程

本质：定义多个 Task 的执行顺序、条件和依赖
产出：最终生成标准的 go-task Taskfile
特性：支持断点、并行执行、条件分支

```yaml
# 计划定义（.ez-plan.yaml格式）
plan:
  kernel-ci:
    steps:
      - name: "代码检查"
        task: "lint"
        parallel: true
      
      - name: "矩阵构建"
        matrix:
          arch: ["x86_64", "aarch64"]
          compiler: ["gcc", "clang"]
        task: "build"
        params:
          arch: "{{.arch}}"
          compiler: "{{.compiler}}"
      
      - name: "质量门禁"
        checkpoint: true
        prompt: "构建完成，是否继续测试？"
        
      - name: "测试验证"
        task: "test"
        when: "$CONFIRMED == 'yes'"
```

2.3 Template（模板）- 作为特殊插件

本质：一种生成 Task/Plan 的插件类型
作用：提供参数化、可复用的任务骨架
实现：Go template 语法 + YAML 变量声明

```yaml
# 模板定义
template:
  kernel-build:
    params:
      version:
        type: "select"
        query: "https://kernel.org/releases.json"
        extract: ".releases[].version"
      arch:
        type: "select"
        options: ["x86_64", "aarch64", "riscv64"]
    
    generate: |
      version: '3'
      vars:
        KERNEL_VERSION: "{{.version}}"
        ARCH: "{{.arch}}"
      
      tasks:
        build:
          desc: "构建内核 {{.version}} for {{.arch}}"
          cmds:
            - wget https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-{{.version}}.tar.xz
            - tar xf linux-{{.version}}.tar.xz
            - cd linux-{{.version}} && make defconfig ARCH={{.arch}}
            - make -j$(nproc) ARCH={{.arch}}
```

2.4 Plugin（插件）- 统一扩展机制

类型：

1. 参数插件：提供动态参数选项
2. 钩子插件：任务生命周期扩展
3. 模板插件：生成 Task/Plan 的特殊类型

```yaml
# 插件定义（YAML格式，无需编译）
plugin:
  name: "kernel-version-fetcher"
  type: "param"
  
  execute:
    script: |
      curl -s https://kernel.org/releases.json | \
      jq -r '.releases[] | select(.stable) | .version'
  
  cache:
    ttl: "1h"
```

三、设计约束

3.1 兼容性约束

1. 格式兼容：所有 ez- 扩展字段必须能被 go-task 安全忽略
2. 执行兼容：EZ 生成的最终 Taskfile 必须是 100% 有效的 go-task 语法
3. 路径兼容：任务中使用的相对路径应在执行上下文中正确解析

3.2 用户体验约束

1. 参数发现性：任务参数应有明确的帮助信息和默认值
2. Fail Fast：参数验证在任务执行前完成，避免无效执行
3. 渐进披露：复杂功能只在需要时出现，保持基础简单

3.3 扩展性约束

1. 插件无状态：插件不应依赖持久化状态
2. 模板幂等：相同参数模板应生成相同任务
3. 配置透明：所有生成的任务应有完整的来源信息

四、交互设计

4.1 任务发现与执行

```bash
# 1. 查看所有可用任务
ez list
# → 自动扫描当前目录及子目录的 Taskfile.yml、Makefile、*.sh

# 2. 查看任务详情和参数
ez show build-kernel
# → 显示任务描述、参数说明、使用示例

# 3. 交互式执行任务
ez run build-kernel
# → 弹出参数菜单，提供智能默认值和帮助
```

4.2 参数系统

```yaml
# 参数定义支持多种查询方式
ez-params:
  - name: "kernel_version"
    type: "select"
    
    # 查询源（支持多种）
    options:
      # 静态列表
      - ["6.6", "6.1", "5.15"]
      
      # 远程API查询
      query: 
        url: "https://kernel.org/releases.json"
        transform: "jq -r '.releases[].version'"
      
      # 命令查询
      command: "git ls-remote --tags https://git.kernel.org"
      transform: "grep -o 'v[0-9.]*' | sort -V"
    
    # 帮助信息（Markdown格式）
    help: |
      选择内核版本，推荐使用最新稳定版。
      
      查看所有版本:
      ```bash
      curl -s https://kernel.org/releases.json | jq '.releases'
      ```
    
    # 验证规则
    validation:
      - rule: "semver"
      - rule: "min_version"
        value: "5.4"
```

4.3 断点机制

```bash
# 执行计划，遇到断点暂停
ez plan run deployment

# 断点交互界面
⏸️  断点：构建完成，请确认部署
当前状态:
  ✓ 构建耗时: 45m 30s
  ✓ 产物大小: 48MB
  ✓ 测试通过率: 100%

选项:
[1] 继续部署到 staging
[2] 直接部署到 production  
[3] 修改部署参数
[4] 保存状态后退出

# 稍后恢复执行
ez resume deployment-20240115-1030
```

五、与 go-task 的协作模式

5.1 执行流程

```
原始Taskfile（带ez-扩展）
    ↓ EZ解析（参数收集、模板展开）
生成的纯go-task Taskfile
    ↓ 委托执行（dry-run验证）
go-task执行引擎
    ↓ 结果收集
执行ez-hooks插件
```

5.2 Dry-run 验证

```bash
# 1. 只生成Taskfile不执行（验证阶段）
ez run build-kernel --dry-run --output=generated-taskfile.yml

# 2. 验证生成的Taskfile
task -t generated-taskfile.yml --list  # 验证语法

# 3. 确认无误后执行
ez run build-kernel  # 或直接执行生成的Taskfile
```

5.3 与 yq 的集成

```bash
# EZ内部使用yq进行YAML处理
# 1. 提取扩展字段
yq eval '.tasks.build.ez-params' Taskfile.yml

# 2. 合并多个YAML文件
yq eval-all 'select(fileIndex==0) * select(fileIndex==1)' \
  base.yml override.yml

# 3. 变量替换
yq eval '.tasks.build.cmds[] | sub("{{.ARCH}}", "x86_64")' Taskfile.yml
```

六、扩展机制设计

6.1 插件注册与发现

```
插件目录结构:
~/.ez/plugins/
├── param/           # 参数插件
│   ├── kernel-versions.yaml
│   └── git-tags.yaml
├── hook/            # 钩子插件
│   ├── result-analyzer.yaml
│   └── slack-notify.yaml
└── template/        # 模板插件
    ├── kernel-build.yaml
    └── docker-build.yaml
```

6.2 插件执行上下文

```yaml
# 插件定义
plugin:
  name: "result-analyzer"
  type: "hook"
  
  # 可用上下文变量
  context:
    - name: "task_name"
      type: "string"
    - name: "task_output"
      type: "string"
    - name: "task_duration"
      type: "duration"
  
  # 执行脚本（支持多种语言）
  execute:
    script: |
      #!/usr/bin/env python3
      import json
      import sys
      
      context = json.loads(sys.stdin.read())
      print(f"分析任务: {context['task_name']}")
      print(f"执行耗时: {context['task_duration']}")
    
    # 或直接命令
    # command: "python3 analyze.py --input {{.task_output}}"
  
  # 输出格式（可选）
  output:
    format: "json"  # json, yaml, text
```

七、使用场景验证

7.1 场景：新成员快速上手

```bash
# 第一天：克隆项目
git clone project-url
cd project

# 查看可用任务
ez list
# → 显示所有发现的任务，包括自动包装的脚本

# 运行引导任务
ez run setup-env
# → 交互式引导设置开发环境
```

7.2 场景：复杂参数任务

```bash
# 传统方式（需要查文档）
make kernel-build ARCH=x86_64 VERSION=6.6 OPTIMIZE=O2

# EZ方式（引导式）
ez run kernel-build
# ? 内核版本: [从kernel.org查询的列表]
# ? 目标架构: x86_64 | aarch64 | riscv64
# ? 优化级别: O0 | O1 | O2 | O3
# → 自动组合参数执行
```

7.3 场景：团队协作

```bash
# 安装团队模板
ez plugin install team://templates/kernel-build

# 使用模板生成标准化任务
ez template use kernel-build --version=6.6 --arch=aarch64

# 生成的Taskfile符合团队规范
cat .ez-tasks/kernel-build-6.6-aarch64.yaml
```

八、总结：差异化设计

8.1 EZ vs 原生 go-task

特性 go-task EZ
任务发现 手动指定文件 自动扫描、统一入口
参数管理 环境变量、命令行 交互式菜单、动态查询
复杂编排 简单依赖 计划编排、断点控制
团队复用 手动复制 模板插件、共享仓库

8.2 核心价值

1. 统一入口：ez list 看到所有项目所有任务
2. 智能引导：复杂参数通过菜单系统简化
3. 复用共享：模板插件化，团队最佳实践可复用
4. 渐进增强：从简单执行到复杂编排平滑过渡

8.3 设计边界

· 不替代 go-task：只增强，不替换
· 不破坏兼容性：现有 Taskfile.yml 无需修改
· 不引入编译依赖：扩展通过 YAML 和脚本实现
· 不强制复杂概念：Workspace 等复杂概念按需使用

最终定位：EZ 是 go-task 的智能伴侣，专注于改善用户体验和团队协作，让任务管理从混乱变得有序，让复杂的参数变得简单。

九、交互式任务导航

9.1 渐进式展开

EZ 支持交互式浏览任务树，逐层展开子任务并选择操作。

```
$ ez browse

EZ Task Browser
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
kernel-*                              [12 tasks] ▶
  ├─ kernel-config                    配置内核选项
  │    └─ [subtasks]                  ▶
  ├─ kernel-build                     编译内核
  │    ├─ kernel-build-debug          调试构建 [extends]
  │    └─ kernel-build-arm            ARM 构建 [extends]
  ├─ kernel-ci                        CI 流程 [compose]
  │    ├─ 1. kernel-config
  │    ├─ 2. kernel-build
  │    └─ 3. kernel-test
  └─ ...

remote-*                              [3 tasks] ▶
deploy-*                              [2 tasks] ▶

[↑↓] Navigate  [Enter] Expand  [r] Run  [s] Show  [q] Quit
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Selected: kernel-build
Actions: [r]Run  [d]Dry-run  [s]Show  [e]Edit  [l]View logs
```

9.2 任务关系类型

```yaml
# 1. 依赖关系 (deps) - 执行前先执行依赖
kernel-build:
  deps: [kernel-config]  # 先执行 config
  cmds:
    - make -j8

# 2. 子任务调用 (task:) - 命令中调用其他任务
kernel-ci:
  cmds:
    - task: kernel-config
    - task: kernel-build
    - task: kernel-test

# 3. 继承关系 (ez-extends) - 复用基础任务
kernel-build-debug:
  ez-extends: kernel-build
  ez-defaults:
    EZ_MODE: debug

# 4. 组合关系 (ez-compose) - 编排多个任务
kernel-full-ci:
  ez-compose:
    - task: kernel-config
    - task: kernel-build
    - task: kernel-test
```

十、分布式执行模型

10.1 核心概念

**Artifact (产物)** - 任务输出的文件或数据，可在节点间传递
**Node (节点)** - 执行任务的机器
**Sync (同步)** - 在节点间传输文件

10.2 远程执行模式

**模式 A: 本地编排，远程执行**

任务定义保持本地，通过 `ez-remote` 指定在哪个节点执行：

```yaml
tasks:
  kernel-build:
    desc: "编译内核"
    cmds:
      - make ARCH={{.EZ_ARCH}} -j{{.EZ_JOBS}}
    ez-params:
      - name: arch
        type: select
        options: [x86_64, arm64]

    # 远程执行配置
    ez-remote:
      # 可在这些节点执行
      nodes: ["builder-1", "builder-2"]
      # 执行前同步到远程
      sync_in:
        - "./Makefile"
        - "./src/"
        - "./include/"
      # 执行后同步回本地
      sync_out:
        - "./build/vmlinux"
        - "./build/bzImage"
      # 远程工作目录
      workdir: "/tmp/kernel-build-{{.EZ_RUN_ID}}"
```

**模式 B: 产物传递**

定义任务的输入输出产物，自动处理节点间传递：

```yaml
tasks:
  kernel-build:
    desc: "编译内核"
    cmds:
      - make -j8
    # 产物定义
    ez-artifacts:
      vmlinux:
        path: "build/vmlinux"
        desc: "内核二进制"
      bzImage:
        path: "build/bzImage"
        desc: "压缩内核镜像"

  kernel-test:
    desc: "测试内核"
    # 依赖的产物
    ez-inputs:
      - artifact: vmlinux
        from: kernel-build     # 从哪个任务获取
        to: "./vmlinux"        # 放到本地哪里
    cmds:
      - ./run-test.sh ./vmlinux
```

**模式 C: 计划级编排**

在 Plan 中统一编排多节点执行：

```yaml
# .ez-plan.yml
plans:
  distributed-kernel-ci:
    desc: "分布式内核 CI"

    # 定义产物存储
    artifacts_store: ".ez-artifacts/{{.RUN_ID}}"

    steps:
      - name: "并行构建"
        task: kernel-build
        # 矩阵 + 节点分配
        matrix:
          arch: [x86_64, arm64]
        node_selector:
          tags: ["role:builder"]
        # 输出产物
        outputs:
          - name: "vmlinux-{{.arch}}"
            path: "build/vmlinux"

      - name: "测试"
        task: kernel-test
        node: "tester-1"
        # 输入产物 (自动从上一步获取)
        inputs:
          - from: "并行构建"
            artifact: "vmlinux-x86_64"
            to: "./vmlinux"
        depends: ["并行构建"]

      - name: "部署"
        task: kernel-deploy
        node: "prod-1"
        inputs:
          - from: "并行构建"
            artifact: "vmlinux-x86_64"
        when: "{{.DEPLOY_PROD}}"
```

10.3 执行流程

```
┌─────────────────────────────────────────────────────────────────┐
│                        EZ Server                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Plan Executor                          │   │
│  │  1. 解析 Plan 和依赖关系                                  │   │
│  │  2. 调度任务到合适节点                                    │   │
│  │  3. 管理产物存储和传输                                    │   │
│  │  4. 聚合结果和日志                                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                    ┌─────────┴─────────┐                       │
│                    │  Artifact Store   │                       │
│                    │  (本地/S3/NFS)    │                       │
│                    └─────────┬─────────┘                       │
└──────────────────────────────┼──────────────────────────────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         │                     │                     │
    ┌────┴────┐           ┌────┴────┐           ┌────┴────┐
    │ Node 1  │           │ Node 2  │           │ Node 3  │
    │ builder │           │ builder │           │ tester  │
    ├─────────┤           ├─────────┤           ├─────────┤
    │ 1.接收  │           │ 1.接收  │           │ 1.等待  │
    │   任务  │           │   任务  │           │   依赖  │
    │ 2.同步  │           │ 2.同步  │           │ 2.拉取  │
    │   输入  │           │   输入  │           │   产物  │
    │ 3.执行  │           │ 3.执行  │           │ 3.执行  │
    │ 4.上传  │           │ 4.上传  │           │ 4.上报  │
    │   产物  │           │   产物  │           │   结果  │
    └─────────┘           └─────────┘           └─────────┘
```

10.4 命令行使用

```bash
# 本地执行 (默认)
ez run kernel-build

# 指定远程节点执行
ez run kernel-build --node=builder-1

# 自动选择节点 (按标签)
ez run kernel-build --node-selector="role:builder"

# 执行分布式计划
ez plan run distributed-kernel-ci

# 查看产物
ez artifacts list
ez artifacts get vmlinux-x86_64 --output=./

# 查看节点
ez nodes list
ez nodes show builder-1
```

10.5 产物同步机制

```yaml
# 全局配置 (.ez-config.yml)
artifacts:
  # 存储后端
  store:
    type: "local"          # local | s3 | nfs
    path: ".ez-artifacts"
    # S3 配置
    # type: "s3"
    # bucket: "ez-artifacts"
    # region: "us-east-1"

  # 同步方式
  sync:
    method: "rsync"        # rsync | scp | s3
    compress: true
    bandwidth_limit: "100m"

  # 清理策略
  retention:
    max_age: "7d"
    max_size: "10G"
```

10.6 使用场景

**场景1: 跨架构编译**
```yaml
plans:
  multi-arch-build:
    steps:
      - name: "x86 构建"
        task: kernel-build
        node_selector: {arch: x86_64}
        vars: {EZ_ARCH: x86_64}
        outputs: [{name: vmlinux-x86, path: build/vmlinux}]

      - name: "ARM 构建"
        task: kernel-build
        node_selector: {arch: arm64}
        vars: {EZ_ARCH: arm64}
        outputs: [{name: vmlinux-arm, path: build/vmlinux}]
        parallel: true  # 与上一步并行

      - name: "打包发布"
        task: package-release
        inputs:
          - {from: "x86 构建", artifact: vmlinux-x86}
          - {from: "ARM 构建", artifact: vmlinux-arm}
```

**场景2: 编译-测试-部署流水线**
```yaml
plans:
  ci-cd-pipeline:
    steps:
      - name: build
        task: build
        node: builder-1
        outputs: [{name: app, path: dist/app.tar.gz}]

      - name: test
        task: test
        node: tester-1
        inputs: [{from: build, artifact: app}]
        depends: [build]

      - name: deploy-staging
        task: deploy
        node: staging-1
        inputs: [{from: build, artifact: app}]
        depends: [test]

      - name: deploy-prod
        task: deploy
        node: prod-1
        inputs: [{from: build, artifact: app}]
        depends: [deploy-staging]
        checkpoint: true
        prompt: "Staging 测试通过，是否部署到生产？"
```

9.1 架构概述

EZ 支持分布式任务执行，通过 Server/Client 模式实现跨节点任务编排。

```
                    ┌─────────────────────────────────────┐
                    │          EZ Server (Docker)         │
                    │  ┌─────────┐  ┌─────────────────┐   │
                    │  │ Web UI  │  │   REST API      │   │
                    │  │ :8080   │  │   /api/v1/...   │   │
                    │  └────┬────┘  └────────┬────────┘   │
                    │       │                │            │
                    │  ┌────┴────────────────┴────┐      │
                    │  │    Task Scheduler        │      │
                    │  │  - Queue Management      │      │
                    │  │  - Node Selection        │      │
                    │  │  - Result Aggregation    │      │
                    │  └──────────────────────────┘      │
                    └─────────────┬───────────────────────┘
                                  │ WebSocket/HTTP
           ┌──────────────────────┼──────────────────────┐
           │                      │                      │
    ┌──────┴──────┐        ┌──────┴──────┐        ┌──────┴──────┐
    │  EZ Client  │        │  EZ Client  │        │  EZ Client  │
    │  (node-1)   │        │  (node-2)   │        │  (node-3)   │
    │  - Agent    │        │  - Agent    │        │  - Agent    │
    │  - go-task  │        │  - go-task  │        │  - go-task  │
    │  - yq       │        │  - yq       │        │  - yq       │
    └─────────────┘        └─────────────┘        └─────────────┘
```

9.2 EZ Server

服务器端组件，提供 Web UI 和 API。

**核心功能**:
- 节点管理：注册、心跳、健康检查
- 任务调度：分配任务到指定节点
- 结果聚合：收集执行结果和日志
- Web Dashboard：可视化监控界面

**部署方式**:
```bash
# Docker 启动
docker run -d -p 8080:8080 -p 9090:9090 \
  -v /path/to/taskfiles:/tasks \
  -v /path/to/data:/data \
  ez-server:latest

# 或使用 docker-compose
docker-compose up -d
```

**配置文件** (ez-server.yml):
```yaml
server:
  http_port: 8080      # Web UI 端口
  api_port: 9090       # API 端口

  auth:
    enabled: true
    token: "${EZ_SERVER_TOKEN}"

  storage:
    type: "sqlite"     # sqlite | postgres | mysql
    path: "/data/ez.db"

  log:
    level: "info"
    dir: "/data/logs"
```

9.3 EZ Client

客户端代理，运行在工作节点上。

**核心功能**:
- 服务发现：连接到 Server
- 任务执行：本地调用 go-task
- 状态上报：实时汇报执行状态
- 日志流：实时推送执行日志

**启动方式**:
```bash
# 启动 client 连接到 server
ez client start --server=http://server:9090 --name=node-1

# 或通过配置文件
ez client start --config=ez-client.yml
```

**配置文件** (ez-client.yml):
```yaml
client:
  name: "node-1"
  tags:
    - "arch:x86_64"
    - "os:linux"
    - "role:builder"

  server:
    url: "http://server:9090"
    token: "${EZ_CLIENT_TOKEN}"
    reconnect_interval: "5s"

  executor:
    work_dir: "/workspace"
    max_parallel: 4
    timeout: "2h"
```

9.4 REST API

**节点管理**:
```
GET    /api/v1/nodes                # 列出所有节点
GET    /api/v1/nodes/:id            # 获取节点详情
POST   /api/v1/nodes/:id/ping       # 心跳
DELETE /api/v1/nodes/:id            # 移除节点
```

**任务管理**:
```
GET    /api/v1/tasks                # 列出任务定义
POST   /api/v1/tasks/run            # 提交任务执行
GET    /api/v1/jobs                 # 列出执行记录
GET    /api/v1/jobs/:id             # 获取执行详情
GET    /api/v1/jobs/:id/logs        # 获取执行日志 (SSE)
POST   /api/v1/jobs/:id/cancel      # 取消执行
```

**计划管理**:
```
GET    /api/v1/plans                # 列出计划
POST   /api/v1/plans/:name/run      # 执行计划
GET    /api/v1/plans/:name/status   # 计划执行状态
```

**请求示例**:
```bash
# 在指定节点执行任务
curl -X POST http://server:9090/api/v1/tasks/run \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "task": "kernel-build",
    "node": "node-1",
    "vars": {
      "EZ_ARCH": "x86_64",
      "EZ_JOBS": "8"
    }
  }'

# 执行矩阵计划
curl -X POST http://server:9090/api/v1/plans/kernel-ci/run \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "matrix": {
      "arch": ["x86_64", "arm64"],
      "node": ["node-1", "node-2"]
    }
  }'
```

9.5 Web Dashboard

**功能页面**:

1. **节点总览** (/nodes)
   - 节点列表和状态（在线/离线/繁忙）
   - 节点资源使用（CPU/内存/磁盘）
   - 节点标签和能力

2. **任务中心** (/tasks)
   - 任务列表和参数定义
   - 快速执行入口
   - 执行历史

3. **执行监控** (/jobs)
   - 实时执行状态
   - 日志流查看
   - 执行统计（成功率/耗时）

4. **计划编排** (/plans)
   - 计划可视化编辑
   - 执行进度追踪
   - 矩阵执行状态

5. **系统设置** (/settings)
   - 用户管理
   - Token 管理
   - 系统配置

**界面示意**:
```
┌─────────────────────────────────────────────────────────────────┐
│  EZ Dashboard                              [node-1] ● [admin]  │
├─────────────────────────────────────────────────────────────────┤
│  Nodes    Tasks    Jobs    Plans    Settings                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Active Jobs                                    View All  │ │
│  │  ┌─────────────────────────────────────────────────────┐  │ │
│  │  │  ● kernel-build (node-1)     [======>   ] 65%      │  │ │
│  │  │    arch=x86_64, jobs=8       Running 5m 30s        │  │ │
│  │  ├─────────────────────────────────────────────────────┤  │ │
│  │  │  ○ kernel-test (node-2)      [===       ] 30%      │  │ │
│  │  │    suite=smoke               Running 2m 15s        │  │ │
│  │  └─────────────────────────────────────────────────────┘  │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌─────────────────────┐  ┌─────────────────────────────────┐  │
│  │  Node Status        │  │  Recent Jobs                    │  │
│  │  ┌───────┬───────┐  │  │  ┌────────────┬────────┬─────┐  │  │
│  │  │node-1 │ ● 🟢  │  │  │  │ kernel-ci  │ ✓ PASS │ 45m │  │  │
│  │  │node-2 │ ● 🟡  │  │  │  │ lint       │ ✓ PASS │ 2m  │  │  │
│  │  │node-3 │ ○ 🔴  │  │  │  │ build      │ ✗ FAIL │ 12m │  │  │
│  │  └───────┴───────┘  │  │  └────────────┴────────┴─────┘  │  │
│  └─────────────────────┘  └─────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

9.6 Docker 部署

**docker-compose.yml**:
```yaml
version: '3.8'

services:
  ez-server:
    image: ez-server:latest
    build:
      context: .
      dockerfile: Dockerfile.server
    ports:
      - "8080:8080"  # Web UI
      - "9090:9090"  # API
    volumes:
      - ./taskfiles:/tasks:ro
      - ez-data:/data
    environment:
      - EZ_SERVER_TOKEN=${EZ_SERVER_TOKEN}
      - EZ_DB_PATH=/data/ez.db
    restart: unless-stopped

volumes:
  ez-data:
```

**Dockerfile.server**:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用
COPY server/ ./server/
COPY static/ ./static/
COPY templates/ ./templates/

# 安装 yq 和 task
RUN apt-get update && apt-get install -y curl && \
    curl -sL https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -o /usr/local/bin/yq && \
    chmod +x /usr/local/bin/yq && \
    curl -sL https://taskfile.dev/install.sh | sh -s -- -d -b /usr/local/bin

EXPOSE 8080 9090

CMD ["python", "-m", "server.main"]
```

9.7 使用场景

**场景1：多机器内核构建**
```bash
# 在 Server Web UI 或命令行
ez server run kernel-build \
  --matrix="node:[node-1,node-2,node-3];arch:[x86_64,arm64]" \
  --vars="EZ_JOBS=8"

# 查看执行状态
ez server jobs --follow
```

**场景2：CI 流水线**
```yaml
# .ez-plan.yml
plans:
  kernel-ci-distributed:
    desc: "分布式内核 CI"
    steps:
      - name: "并行构建"
        task: "kernel-build"
        matrix:
          node: ["builder-1", "builder-2"]
          arch: ["x86_64", "arm64"]
        parallel: true

      - name: "测试验证"
        task: "kernel-test"
        node: "tester-1"
        depends:
          - "并行构建"

      - name: "结果归档"
        task: "result-archive"
        node: "storage-1"
```

**场景3：动态节点选择**
```yaml
# 按标签选择节点
steps:
  - name: "构建"
    task: "build"
    node_selector:
      tags:
        - "arch:x86_64"
        - "role:builder"
      prefer: "least_busy"  # 选择最空闲的节点
```

十一、核心术语体系 (v1.1+ → v1.4 重定义见第〇章)

11.1 统一术语表

| 术语 | 中文 | 含义 |
|------|------|------|
| Skill | 技能 | 自包含的可复用执行单元（`skills/` 子文件夹）|
| Plan | 计划 | 多 Skill 的编排，可编译为 Taskfile |
| Step | 步骤 | Plan 内的单个环节 |
| Artifact | 产物 | Skill 的输出文件，可被下游 Skill 引用 |
| Workspace | 工作区 | 隔离的执行目录，防止污染源码 |

**生命周期**: `pending → running → success / failed`

11.2 命令体系 (v1.4)

原则：**Skill 是默认主体**，最常用操作最短路径。

```
# Skill / go-task task（默认主体，无需 run 子命令）
ez                          # 等价于 ez list
ez <name>                   # 直接执行（skill 或 go-task task）
ez <name> --dry-run         # 预览
ez list [filter]            # 列出（Skill 标记 [skill]）
ez show <name>              # 详情（含 skill.yml 元数据）
ez new <name>               # 创建 Skill 文件夹 + skill.yml
ez check [name]             # 验证语法和依赖
ez clean <name>             # 清理运行时数据

# Skill 管理
ez skill list               # 列出所有 Skill
ez skill show <name>        # 显示 skill.yml 元数据
ez skill export <name>      # 导出为 .tar.gz
ez skill import <path>      # 导入 Skill

# Plan（二级命令）
ez plan                     # 等价于 ez plan list
ez plan new <name>          # 创建 Plan
ez plan add <name> <task>   # 向 Plan 添加步骤
ez plan show <name>         # 查看 Plan 结构
ez plan build <name>        # 编译为可执行 Taskfile
ez plan check <name>        # 验证依赖完备性
ez plan run <name>          # build + 执行
ez plan <name>              # 等价于 ez plan run <name>
```

**Tab 补全**: `eval "$(ez completion bash)"` 或 `eval "$(ez completion zsh)"`

十二、Skill-as-Folder（文件夹即技能）(v1.4)

12.1 目录约定

```
project/
├── Taskfile.yml          # 根 Taskfile（简单任务，go-task 兼容层）
├── skills/               # EZ Skills（自包含技能，自动发现）
│   ├── kernel-build/
│   │   ├── Taskfile.yml  # go-task 执行定义
│   │   ├── skill.yml     # EZ 元数据（AI 可读，可选）
│   │   ├── scripts/      # 辅助脚本
│   │   └── config/       # 配置文件
│   └── deploy/
│       ├── Taskfile.yml
│       ├── skill.yml
│       └── templates/
├── plans/                # Plan 定义
│   └── kernel-ci.yml
├── .ez/                  # 运行时数据（按粒度组织，gitignore）
│   ├── skills/           # 按 Skill 粒度
│   │   ├── kernel-build/
│   │   │   ├── workspace/    # 默认 workspace
│   │   │   ├── logs/         # 执行日志
│   │   │   └── artifacts/    # 输出产物
│   │   └── deploy/
│   │       └── ...
│   ├── plans/            # 按 Plan 粒度
│   │   └── kernel-ci/
│   │       ├── build/        # 编译输出 (Taskfile.yml)
│   │       ├── logs/         # Plan 执行日志
│   │       └── state/        # 恢复状态
│   └── workspace/        # 显式命名的 ad-hoc workspace
│       └── debug-session/
└── completion/           # Tab 补全脚本
    └── ez.bash
```

Skill 目录 `skills/` 是唯一的 Skill 来源，不提供回退。

12.2 skill.yml 元数据

```yaml
# skills/kernel-build/skill.yml
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

**解析优先级**: skill.yml params > Taskfile ez-params > 无参数

12.3 发现逻辑

EZ 自动合并两种来源:
1. **根 Taskfile 任务**: Taskfile.yml 中的 tasks 条目（go-task 原生）
2. **Skill**: skills/ 目录下包含 Taskfile.yml 的子文件夹（EZ 自有概念）

Skill 在 `ez list` 中以 `[skill]` 标记显示。

12.4 创建和执行

```bash
ez new my-skill             # 创建 skills/my-skill/ + Taskfile.yml + skill.yml
ez my-skill                 # 直接执行（默认在 .ez/skills/my-skill/workspace/ 中）
ez my-skill --no-workspace  # 在源码目录直接执行（opt-out）
ez show my-skill            # 查看详情（含 skill.yml 元数据）
ez check my-skill           # 验证 Taskfile 语法
ez skill export my-skill    # 导出为 .tar.gz（含 Taskfile + skill.yml + scripts）
ez skill import my-skill.tar.gz  # 导入 Skill
ez clean my-skill           # 清理 .ez/skills/my-skill/ 运行时数据
```

Skill 通过 `task -d skills/<name> default` 执行（委托 go-task 引擎）。

十三、Plan 编译系统 (v1.2 → v1.4)

13.1 Plan 文件格式

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

13.2 编译流程

`ez plan build <name>` 将 Plan 编译为标准 go-task Taskfile:
1. 解析 steps + matrix 展开
2. 拓扑排序（检查 needs 依赖）
3. 生成 Taskfile.yml 到 `.ez/plans/<name>/build/` (v1.4: 按 Plan 粒度组织)

13.3 依赖验证

`ez plan check <name>` 验证:
- 所有 step.task 在 Taskfile 中存在（支持 Skill 名称）
- needs 引用的 step 存在且无循环依赖
- inputs 引用的 artifact 在上游 step 有定义
- DAG 拓扑排序可行（无环）

13.4 Shuffle

标记 `shuffle: true` 的步骤在相同依赖层级内可随机排序。适用于压力测试和验证执行顺序无关性。
