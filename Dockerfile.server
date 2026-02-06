FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 yq 和 task
RUN curl -sL https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -o /usr/local/bin/yq \
    && chmod +x /usr/local/bin/yq \
    && curl -sL https://taskfile.dev/install.sh | sh -s -- -d -b /usr/local/bin

# 复制依赖文件
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用
COPY ez /app/ez
COPY lib /app/lib
COPY server /app/server
COPY Taskfile.yml /app/

# 设置环境变量
ENV EZ_ROOT=/app
ENV EZ_DB_PATH=/data/ez.db
ENV EZ_HTTP_PORT=8080

# 数据卷
VOLUME ["/data", "/tasks"]

# 暴露端口
EXPOSE 8080

# 启动命令
CMD ["python", "-m", "server.main"]
