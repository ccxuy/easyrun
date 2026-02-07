# EZ Server

EZ Server 是 EZ (EasyRun) 的可选 Web 管理界面和分布式执行服务。

## 架构

```
Flask + SocketIO + SQLite
├── Web UI (6 页面: Dashboard / Tasks / Plans / Jobs / Nodes / Charts)
├── REST API (/api/v1/*)
├── WebSocket (实时日志、节点心跳、任务状态推送)
└── SQLite (节点注册、执行记录、计划运行、图表配置)
```

**核心依赖**: Flask, Flask-SocketIO, PyYAML, eventlet

**性能**: 任务树使用 PyYAML + mtime 缓存，首次加载解析 YAML 文件，后续请求自动校验文件修改时间。

## 快速启动

### 本地运行

```bash
cd server
pip install -r requirements.txt
python -m server.main
# 访问 http://localhost:8080
```

### Docker

```bash
cd server
docker compose up -d --build
# 访问 http://localhost:8080
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `EZ_ROOT` | 项目根目录 | EZ 项目根路径 |
| `EZ_DB_PATH` | `.ez-server/ez.db` | SQLite 数据库路径 |
| `EZ_SERVER_TOKEN` | (空) | API 认证 Token，空则不验证 |
| `EZ_HTTP_PORT` | `8080` | HTTP 监听端口 |
| `EZ_SECRET_KEY` | `ez-secret-key` | Flask Session 密钥 |

## Web 页面

| 路径 | 说明 |
|------|------|
| `/` | Dashboard — 统计概览、快速执行 |
| `/tasks` | 任务浏览器 — 搜索、参数配置、执行、YAML 编辑、文件浏览、创建计划 |
| `/plans` | 计划管理 — DAG 可视化、步骤详情、执行、YAML 编辑 |
| `/jobs` | 执行记录 — 状态、日志、取消 |
| `/nodes` | 节点管理 — 注册、心跳、删除 |
| `/charts` | 数据可视化 — 自定义图表、公式 |

## API 参考

所有 API 前缀: `/api/v1`

### 任务 (Tasks)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/tasks` | 列出所有任务 (扁平化) |
| GET | `/tasks/tree` | 树形任务结构 (含命名空间) |
| GET | `/tasks/<name>` | 任务详情 (ez show) |
| GET | `/tasks/<name>/params` | 参数定义 (JSON) |
| GET | `/tasks/<name>/yaml` | YAML 源文件 |
| PUT | `/tasks/<name>/yaml` | 保存 YAML |
| POST | `/tasks/run` | 提交执行 `{task, node?, vars?}` |
| GET | `/tasks/<name>/files` | 目录任务文件列表 |
| GET | `/tasks/<name>/files/<path>` | 读取文件内容 (文本, <1MB) |
| POST | `/tasks/<name>/to-plan` | 转换为计划 `{plan_name, vars?, overwrite?}` |

### 计划 (Plans)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/plans` | 列出所有计划 |
| GET | `/plans/<name>` | 计划详情 (步骤、DAG 结构) |
| GET | `/plans/<name>/yaml` | Plan YAML 源文件 |
| PUT | `/plans/<name>/yaml` | 保存 Plan YAML |
| POST | `/plans/<name>/run` | 执行计划 `{vars?}` |
| POST | `/plans/run-task` | 单任务执行 `{task, vars?, node?}` |
| GET | `/plans/runs` | 计划执行历史 |
| GET | `/plans/runs/<id>` | 单次执行状态 |

### 执行记录 (Jobs)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/jobs` | 列出执行记录 (最近 50 条) |
| GET | `/jobs/<id>` | 执行详情 |
| GET | `/jobs/<id>/logs` | 实时日志 (SSE) |
| POST | `/jobs/<id>/cancel` | 取消执行 |
| POST | `/jobs/<id>/result` | Client 上报结果 |

### 节点 (Nodes)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/nodes` | 列出所有节点 |
| GET | `/nodes/<id>` | 节点详情 |
| POST | `/nodes/register` | 注册节点 `{name, id?, tags?}` |
| POST | `/nodes/<id>/ping` | 心跳 |
| DELETE | `/nodes/<id>` | 移除节点 |

### 统计 & 图表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/stats` | 聚合统计 (状态分布、任务/节点统计、时间线) |
| POST | `/stats/report` | CLI 上报执行统计 |
| GET | `/stats/executions` | CLI 上报历史 |
| GET | `/charts` | 列出自定义图表 |
| POST | `/charts` | 保存图表 `{name, type, formula}` |
| DELETE | `/charts/<id>` | 删除图表 |

### 其他

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/templates` | 列出模板 |
| POST | `/cache/clear` | 清除任务树缓存 |

## WebSocket 事件

| 事件 | 方向 | 说明 |
|------|------|------|
| `connect` / `disconnect` | Client → Server | 连接生命周期 |
| `node_register` | Client → Server | 节点注册 `{id, name, tags}` |
| `node_ping` | Client → Server | 节点心跳 `{id}` |
| `job_log` | Client → Server | 日志上报 `{job_id, log}` |
| `registered` | Server → Client | 注册确认 `{id}` |
| `node_update` | Server → All | 节点状态变更 |
| `job_update` | Server → All | 任务执行状态变更 |
| `job_assigned` | Server → Node | 任务分配 |
| `job_log_update` | Server → All | 日志更新 |
| `plan_update` | Server → All | 计划执行状态变更 |

## 目录结构

```
server/
├── main.py              # Flask 应用入口
├── requirements.txt     # Python 依赖
├── Dockerfile           # Docker 构建
├── docker-compose.yml   # Docker Compose 编排
├── client/
│   └── agent.py         # Client Agent (连接 Server 执行任务)
├── templates/           # Jinja2 HTML 模板
│   ├── index.html       # Dashboard
│   ├── tasks.html       # 任务浏览器
│   ├── plans.html       # 计划管理
│   ├── jobs.html        # 执行记录
│   ├── nodes.html       # 节点管理
│   └── charts.html      # 数据可视化
├── static/
│   └── css/style.css    # 全局样式
└── data/                # SQLite 数据 (Docker volume)
```
