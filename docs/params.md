# ez-params 参数系统

EZ 通过 `ez-params` 扩展字段为 go-task 任务添加交互式参数。go-task 会安全忽略这些字段。

## 基本定义

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
        help: "目标环境"
```

## 参数类型

| 类型 | 说明 |
|------|------|
| `input` | 文本输入，支持 default |
| `select` | 从选项列表选择 |

## 交互流程

```
$ ./ez run deploy

Configure: deploy

app
  选择要部署的应用
    1) frontend (default)
    2) backend
  Choice [1-2]: 2

env
  目标环境
    1) dev (default)
    2) staging
    3) prod
  Choice [1-3]:

Running: ./dep/task deploy EZ_APP=backend EZ_ENV=dev
```

## 预设参数

跳过交互，直接传递变量:

```bash
ez deploy EZ_APP=frontend EZ_ENV=prod
ez deploy EZ_APP=frontend EZ_ENV=prod --dry-run
```

## 动态选项 (query.command)

使用命令输出作为选项列表:

```yaml
ez-params:
  - name: "branch"
    type: "select"
    query:
      command: "git branch --format='%(refname:short)'"
    help: "选择分支"
```

## 远程 URL 选项 (query.url)

从 URL 获取 JSON 数据:

```yaml
ez-params:
  - name: "version"
    type: "select"
    query:
      url: "https://api.example.com/versions"
      jq: ".versions[]"
    help: "选择版本号"
```

## Skill 中的参数

Skill 支持两种参数定义方式:

1. **skill.yml params** — 优先级最高
2. **Taskfile ez-params** — 回退方案

```yaml
# skills/deploy/skill.yml
params:
  - name: env
    type: select
    options: [dev, staging, prod]
    default: dev
    desc: "目标环境"
```

## 查看参数详情

```bash
$ ./ez show deploy

Task: deploy
Description: 部署应用

Parameters:
  app (select) → ${{.EZ_APP}}
    选择要部署的应用
    Default: frontend
    Options: frontend, backend

  env (select) → ${{.EZ_ENV}}
    目标环境
    Default: dev
    Options: dev, staging, prod
```
