# EZ - go-task 智能前端

EZ 是 [go-task](https://github.com/go-task/task) 的智能前端，专注于改善用户体验和团队协作。

## 特性

- **交互式参数** - 通过菜单选择参数，无需记忆命令行选项
- **参数预设** - 支持 `EZ_VAR=value` 跳过交互
- **100% 兼容** - 所有 `ez-*` 扩展字段可被 go-task 安全忽略

## 快速开始

```bash
# 1. 安装依赖 (下载 yq 和 task 到 dep/)
./dep/install-deps.sh

# 2. 查看可用任务
./ez list

# 3. 查看任务详情
./ez show build

# 4. 运行任务 (交互式)
./ez run build

# 5. 运行任务 (预设参数)
./ez run build EZ_ARCH=aarch64
```

## 命令

| 命令 | 说明 |
|------|------|
| `ez list` | 列出所有任务 |
| `ez show <task>` | 显示任务详情和参数 |
| `ez run <task>` | 运行任务（交互式参数） |
| `ez run <task> --dry-run` | 只显示命令，不执行 |
| `ez plan list` | 列出所有计划 |
| `ez plan show <plan>` | 显示计划详情 |
| `ez plan run <plan>` | 执行计划 |
| `ez version` | 显示版本信息 |
| `ez help` | 显示帮助 |

## ez-params 参数定义

在 Taskfile.yml 中使用 `ez-params` 定义交互式参数：

```yaml
tasks:
  deploy:
    desc: "部署应用"
    cmds:
      - 'echo "Deploying {{.EZ_APP}} to {{.EZ_ENV}}"'

    ez-params:
      - name: "app"
        type: "select"
        options: ["frontend", "backend"]
        default: "frontend"
        help: |
          选择要部署的应用
          - frontend: React 前端
          - backend: Node.js 后端

      - name: "env"
        type: "select"
        options: ["dev", "staging", "prod"]
        default: "dev"
        help: "目标环境 ⚠️ prod 需要审批"
```

### 查看参数详情

```
$ ./ez show deploy

Task: deploy

Description: 部署应用

Parameters:
  app (select) → ${{.EZ_APP}}
    选择要部署的应用
    - frontend: React 前端
    - backend: Node.js 后端
    Default: frontend
    Options: frontend, backend

  env (select) → ${{.EZ_ENV}}
    目标环境 ⚠️ prod 需要审批
    Default: dev
    Options: dev, staging, prod

Usage:
  ./ez run deploy
  ./ez run deploy EZ_APP=frontend EZ_ENV=dev
```

### 参数类型

| 类型 | 说明 |
|------|------|
| `input` | 文本输入 |
| `select` | 从选项列表选择 |

### 动态选项 (query.command)

使用 `query.command` 从命令输出动态获取选项：

```yaml
tasks:
  git-checkout:
    desc: "切换分支"
    cmds:
      - git checkout {{.EZ_BRANCH}}

    ez-params:
      - name: "branch"
        type: "select"
        query:
          command: "git branch --format='%(refname:short)'"
        help: "选择分支"
```

运行时会执行命令获取可选值：
```
$ ./ez run git-checkout
Configure: git-checkout

  (query: git branch --format='%(refname:short)')
branch
  选择分支
    1) main
    2) develop
    3) feature/xxx
  Choice [1-3]:
```

### 远程 URL 选项 (query.url)

从 URL 获取 JSON 数据并提取选项：

```yaml
tasks:
  select-version:
    desc: "选择版本"
    cmds:
      - echo "Version {{.EZ_VERSION}}"

    ez-params:
      - name: "version"
        type: "select"
        query:
          url: "https://api.example.com/versions"
          jq: ".versions[]"
        help: "选择版本号"
```

## ez-hooks 钩子

在任务执行前后运行脚本：

```yaml
tasks:
  build:
    desc: "构建项目"
    cmds:
      - make build

    ez-hooks:
      pre_run:
        - name: "check-env"
          script: 'echo "Checking..."'
      post_run:
        - name: "notify"
          script: 'echo "Task $EZ_TASK_NAME completed!"'
      on_error:
        - name: "alert"
          script: 'echo "Failed with code $EZ_TASK_EXIT_CODE"'
```

### 钩子类型

| 类型 | 触发时机 |
|------|----------|
| `pre_run` | 任务执行前 |
| `post_run` | 任务成功后 |
| `on_error` | 任务失败后 |

### 钩子上下文变量

| 变量 | 说明 |
|------|------|
| `$EZ_TASK_NAME` | 任务名称 |
| `$EZ_TASK_EXIT_CODE` | 任务退出码 |
| `$EZ_TASK_OUTPUT` | 任务输出内容 |

## Plan 计划编排

将多个任务组织成执行计划，支持步骤编排、变量传递和矩阵构建。

### 计划定义 (.ez-plan.yml)

```yaml
plans:
  deploy:
    desc: "部署流程"
    steps:
      - name: "构建"
        task: "build"

      - name: "测试"
        task: "test"
        vars:
          EZ_ENV: "staging"

      - name: "确认"
        checkpoint: true
        prompt: "是否继续部署到生产环境？"

      - name: "部署"
        task: "deploy-prod"
```

### 矩阵构建

```yaml
plans:
  multi-arch:
    desc: "多架构构建"
    steps:
      - name: "构建"
        task: "build"
        matrix:
          arch: ["x86_64", "aarch64"]
          os: ["linux", "darwin"]
        vars:
          EZ_ARCH: "{{.arch}}"
          EZ_OS: "{{.os}}"
```

### Plan 命令

| 命令 | 说明 |
|------|------|
| `ez plan list` | 列出所有计划 |
| `ez plan show <plan>` | 显示计划详情 |
| `ez plan run <plan>` | 执行计划 |
| `ez plan run <plan> --dry-run` | 预览执行 |

## Template 模板

使用模板快速生成任务定义。

### 查看可用模板

```bash
$ ./ez template list
Templates in templates/:
  kernel-build         Linux 内核编译任务模板
  service-deploy       服务部署任务模板
```

### 使用模板

```bash
$ ./ez template use kernel-build --name=linux --arch=arm64
Generated tasks:
  linux-config:
    desc: "配置内核 (linux)"
    ...
```

### 自定义模板

创建 `templates/my-template.yml`:

```yaml
name: my-template
desc: "我的模板"
version: "1.0"

params:
  - name: "name"
    desc: "项目名称"
    default: "myproject"

template: |
  {{.name}}-task:
    desc: "任务 ({{.name}})"
    cmds:
      - echo "Hello from {{.name}}"
```

## Plugin 插件

扩展 EZ 功能的插件系统。

### 插件类型

| 类型 | 说明 |
|------|------|
| `param` | 动态参数选项提供者 |
| `hook` | 可复用的钩子脚本 |
| `template` | 可复用的模板 |

### 插件命令

```bash
ez plugin list              # 列出已安装插件
ez plugin show <name>       # 显示插件详情
ez plugin run <name>        # 运行插件脚本
ez plugin install <url>     # 从 URL 安装插件
```

### 示例插件

```yaml
# plugins/param/git-branch.yml
name: git-branch
type: param
desc: "动态获取 Git 分支列表"
version: "1.0"

script: |
  #!/usr/bin/env bash
  git branch --format='%(refname:short)'
```

## 远程执行

支持远程任务执行和多机器部署。

### 远程任务

```yaml
# Taskfile.yml
tasks:
  remote-copy:
    desc: "复制文件到远程主机"
    cmds:
      - scp $EZ_FILE $EZ_HOST:/tmp/
    ez-params:
      - name: "host"
        type: "input"
        help: "远程主机"
      - name: "file"
        type: "input"
        help: "要传输的文件"

  remote-exec:
    desc: "在远程主机执行命令"
    cmds:
      - ssh $EZ_HOST "$EZ_CMD"
    ez-params:
      - name: "host"
        type: "input"
        help: "远程主机"
      - name: "cmd"
        type: "input"
        help: "要执行的命令"
```

### 多机器部署计划

```yaml
# .ez-plan.yml
plans:
  multi-deploy:
    desc: "多机器并行部署"
    steps:
      - name: "分发到各节点"
        task: "remote-copy"
        matrix:
          host: ["node-1", "node-2", "node-3"]
        vars:
          EZ_HOST: "{{.host}}"
          EZ_FILE: "app.tar.gz"
```

## 结果归档与统计

自动记录和统计任务执行结果。

### 归档结果

```bash
./ez run result-archive EZ_RUN_ID=run-001 EZ_STATUS=pass
```

### 查看统计

```bash
./ez run result-stats
# 输出:
# === 测试结果统计 ===
# 总运行数: 10
# 通过: 8
# 失败: 2
```

## AI 插件

支持 AI 增强功能（需要 API Key）。

### AI 代码审查钩子

```yaml
# plugins/hook/ai-review.yml
name: ai-review
type: hook
desc: "使用 AI 进行代码审查"
script: |
  curl -s https://api.openai.com/v1/chat/completions \
    -H "Authorization: Bearer $OPENAI_API_KEY" \
    -d '{"model":"gpt-4","messages":[...]}'
```

## 测试

```bash
./dep/task test        # 运行所有测试
./dep/task test:quick  # 快速测试
```

## 项目结构

```
easyrun/
├── ez                    # 主入口脚本
├── lib/ez-core.sh        # 核心函数库
├── dep/
│   ├── install-deps.sh   # 依赖安装脚本
│   ├── task              # go-task 二进制
│   └── yq                # yq 二进制
├── templates/            # 模板目录
├── plugins/              # 插件目录
│   ├── param/            # 参数插件
│   └── hook/             # 钩子插件
├── task/selftest/        # 自测试套件
├── Taskfile.yml          # 示例任务
├── .ez-plan.yml          # 计划定义
├── DESIGN.md             # 设计规格
└── PLAN.md               # 实现计划
```

## 版本历史

- **v0.7.0** - 远程执行、结果归档、AI 插件
- **v0.6.0** - Plugin 插件系统 (param/hook/template)
- **v0.5.0** - Template 模板系统 (list/show/use)
- **v0.4.0** - Plan 计划编排 (list/show/run, matrix, when)
- **v0.3.0** - ez-hooks 钩子系统 (pre_run/post_run/on_error)
- **v0.2.7** - 增强 show 命令展示
- **v0.2.6** - query.url 远程选项获取
- **v0.2.5** - query.command 动态选项
- **v0.2.0** - 交互式参数支持 (input/select 类型)
- **v0.1.5** - run 命令基础执行
- **v0.1.4** - show 命令
- **v0.1.3** - list 命令
- **v0.1.0** - 依赖安装脚本

## 依赖

- [go-task](https://github.com/go-task/task) - 任务执行引擎
- [yq](https://github.com/mikefarah/yq) - YAML 处理器

## License

MIT
