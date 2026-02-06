FROM ubuntu:22.04

# 构建参数: 代理、证书、目标架构
ARG HTTP_PROXY=
ARG HTTPS_PROXY=
ARG NO_PROXY=
ARG TARGETARCH=amd64

WORKDIR /app

# 构建期代理设置
ENV http_proxy=${HTTP_PROXY} \
    https_proxy=${HTTPS_PROXY} \
    no_proxy=${NO_PROXY}

# 防止交互式提示
ENV DEBIAN_FRONTEND=noninteractive

# 自定义 CA 证书（将 .crt 文件放入 server/certs/ 即可）
COPY server/certs/ /tmp/certs/
RUN if ls /tmp/certs/*.crt 1>/dev/null 2>&1; then \
        cp /tmp/certs/*.crt /usr/local/share/ca-certificates/ && \
        update-ca-certificates; \
    fi && rm -rf /tmp/certs

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 安装 yq 和 task (架构自适应)
RUN YQ_ARCH=$(case ${TARGETARCH} in arm64) echo "arm64";; *) echo "amd64";; esac) && \
    curl -sL "https://github.com/mikefarah/yq/releases/latest/download/yq_linux_${YQ_ARCH}" \
        -o /usr/local/bin/yq && chmod +x /usr/local/bin/yq \
    && curl -sL https://taskfile.dev/install.sh | sh -s -- -d -b /usr/local/bin

# Python 依赖
COPY server/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# 前端 JS 库（离线可用）
RUN mkdir -p /app/server/static/js && \
    curl -sL https://cdn.socket.io/4.6.0/socket.io.min.js \
        -o /app/server/static/js/socket.io.min.js && \
    curl -sL https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js \
        -o /app/server/static/js/chart.min.js

# 应用文件
COPY ez /app/ez
COPY lib /app/lib
COPY server /app/server
COPY Taskfile.yml /app/
COPY tasks /app/tasks
COPY plans /app/plans
COPY plugins /app/plugins
COPY templates /app/templates

# 清除构建期代理（运行时不需要）
ENV http_proxy= \
    https_proxy= \
    no_proxy= \
    DEBIAN_FRONTEND=

ENV EZ_ROOT=/app \
    EZ_DB_PATH=/data/ez.db \
    EZ_HTTP_PORT=8080

VOLUME ["/data", "/tasks"]
EXPOSE 8080

CMD ["python3", "-m", "server.main"]
