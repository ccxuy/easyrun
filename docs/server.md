# 分布式执行 (Server/Client)

EZ 支持分布式任务执行，通过 Server/Client 模式实现跨节点任务编排。

## 架构

```
                ┌─────────────────────────────────────┐
                │          EZ Server (Docker)         │
                │  ┌─────────┐  ┌─────────────────┐   │
                │  │ Web UI  │  │   REST API      │   │
                │  │ :8080   │  │   /api/v1/...   │   │
                │  └─────────┘  └─────────────────┘   │
                └─────────────────┬───────────────────┘
                                  │
       ┌──────────────────────────┼──────────────────────┐
       │                          │                      │
┌──────┴──────┐            ┌──────┴──────┐        ┌──────┴──────┐
│  EZ Client  │            │  EZ Client  │        │  EZ Client  │
│  (node-1)   │            │  (node-2)   │        │  (node-3)   │
└─────────────┘            └─────────────┘        └─────────────┘
```

## 启动 Server

```bash
# 直接启动 (需要 Python3 + Flask)
./ez server start 8080

# Docker 启动
./ez server docker up

# 停止 / 查看日志
./ez server docker down
./ez server docker logs
```

## 启动 Client

```bash
# 连接到服务器
./ez client start http://server:8080 my-node

# 环境变量方式
export EZ_SERVER_URL=http://server:8080
export EZ_NODE_NAME=builder-1
./ez client start
```

## Web Dashboard

访问 `http://server:8080`:

- **Overview**: 节点状态、活跃任务
- **Nodes**: 节点管理、状态监控
- **Tasks**: 任务列表、快速执行
- **Jobs**: 执行历史、实时日志

## REST API

```bash
# 节点
curl http://server:8080/api/v1/nodes

# 任务
curl http://server:8080/api/v1/tasks

# 提交执行
curl -X POST http://server:8080/api/v1/tasks/run \
  -H "Content-Type: application/json" \
  -d '{"task": "kernel-build", "node": "node-1", "vars": {"EZ_ARCH": "x86_64"}}'

# 执行记录
curl http://server:8080/api/v1/jobs
curl http://server:8080/api/v1/jobs/{job_id}
```

## Docker 部署

```bash
# 使用 docker-compose
docker-compose up -d

# 查看状态
./ez server status
```

参见项目根目录的 `docker-compose.yml` 和 `Dockerfile.server`。
