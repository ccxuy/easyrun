EZ 任务编排框架设计规格

一、设计哲学

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
