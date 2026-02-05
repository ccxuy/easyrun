#!/usr/bin/env bash
#
# EZ 依赖安装脚本
# 下载 go-task 和 yq 到本地 dep/ 目录
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEP_DIR="$SCRIPT_DIR/dep"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

info() { echo -e "${CYAN}[INFO]${NC} $*"; }
ok() { echo -e "${GREEN}[OK]${NC} $*"; }
err() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# 检测 OS: linux, darwin
detect_os() {
    local os
    os=$(uname -s | tr '[:upper:]' '[:lower:]')
    case "$os" in
        linux|darwin) echo "$os" ;;
        *) err "不支持的操作系统: $os" ;;
    esac
}

# 检测架构并标准化
detect_arch() {
    local arch
    arch=$(uname -m)
    case "$arch" in
        x86_64)  echo "amd64" ;;
        aarch64) echo "arm64" ;;
        arm64)   echo "arm64" ;;
        *) err "不支持的架构: $arch" ;;
    esac
}

# 下载 yq
install_yq() {
    local os="$1" arch="$2"
    local url="https://github.com/mikefarah/yq/releases/latest/download/yq_${os}_${arch}"

    info "下载 yq: $url"
    if curl -fsSL "$url" -o "$DEP_DIR/yq"; then
        chmod +x "$DEP_DIR/yq"
        ok "yq 安装完成"
    else
        err "yq 下载失败"
    fi
}

# 下载 go-task
install_task() {
    local os="$1" arch="$2"
    local url="https://github.com/go-task/task/releases/latest/download/task_${os}_${arch}.tar.gz"

    info "下载 task: $url"
    if curl -fsSL "$url" | tar -xz -C "$DEP_DIR" task; then
        chmod +x "$DEP_DIR/task"
        ok "task 安装完成"
    else
        err "task 下载失败"
    fi
}

# 下载 ytt (carvel)
install_ytt() {
    local os="$1" arch="$2"
    local url="https://github.com/carvel-dev/ytt/releases/latest/download/ytt-${os}-${arch}"

    info "下载 ytt: $url"
    if curl -fsSL "$url" -o "$DEP_DIR/ytt"; then
        chmod +x "$DEP_DIR/ytt"
        ok "ytt 安装完成"
    else
        # ytt 是可选的，不报错
        info "ytt 下载失败 (可选依赖)"
    fi
}

# 验证安装
verify() {
    echo ""
    info "验证安装..."

    if [[ -x "$DEP_DIR/yq" ]]; then
        ok "yq: $("$DEP_DIR/yq" --version 2>/dev/null | head -1)"
    else
        err "yq 不可执行"
    fi

    if [[ -x "$DEP_DIR/task" ]]; then
        ok "task: $("$DEP_DIR/task" --version 2>/dev/null | head -1)"
    else
        err "task 不可执行"
    fi

    if [[ -x "$DEP_DIR/ytt" ]]; then
        ok "ytt: $("$DEP_DIR/ytt" --version 2>/dev/null | head -1)"
    else
        info "ytt: 未安装 (可选)"
    fi
}

main() {
    local os arch

    os=$(detect_os)
    arch=$(detect_arch)

    info "检测到: OS=$os ARCH=$arch"

    mkdir -p "$DEP_DIR"

    install_yq "$os" "$arch"
    install_task "$os" "$arch"
    install_ytt "$os" "$arch"

    verify

    echo ""
    ok "所有依赖安装完成!"
}

main "$@"
