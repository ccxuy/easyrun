#!/usr/bin/env python3
"""
EZ Client - 分布式任务执行客户端代理
"""

import os
import sys
import json
import time
import signal
import subprocess
import argparse
from datetime import datetime
from threading import Thread

try:
    import socketio
    import requests
except ImportError:
    print("Missing dependencies. Please install: pip install python-socketio requests")
    sys.exit(1)

# 配置
EZ_ROOT = os.environ.get('EZ_ROOT', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_SERVER = os.environ.get('EZ_SERVER_URL', 'http://localhost:8080')
CLIENT_TOKEN = os.environ.get('EZ_CLIENT_TOKEN', '')

# SocketIO 客户端
sio = socketio.Client()

# 全局状态
running = True
current_job = None
node_id = None
server_url = None


def signal_handler(sig, frame):
    """处理中断信号"""
    global running
    print("\nShutting down...")
    running = False
    sio.disconnect()
    sys.exit(0)


@sio.event
def connect():
    """连接成功"""
    global node_id
    print(f"Connected to server")
    # 注册节点
    sio.emit('node_register', {
        'id': node_id,
        'name': node_id,
        'tags': get_node_tags()
    })


@sio.event
def disconnect():
    """连接断开"""
    print("Disconnected from server")


@sio.on('registered')
def on_registered(data):
    """注册成功"""
    global node_id
    node_id = data.get('id', node_id)
    print(f"Registered as node: {node_id}")


@sio.on('job_assigned')
def on_job_assigned(job):
    """收到任务分配"""
    global current_job
    print(f"Received job: {job['id']} - {job['task']}")
    current_job = job
    Thread(target=execute_job, args=(job,)).start()


def get_node_tags():
    """获取节点标签"""
    tags = []

    # 架构
    import platform
    machine = platform.machine()
    if machine:
        tags.append(f"arch:{machine}")

    # 操作系统
    system = platform.system().lower()
    if system:
        tags.append(f"os:{system}")

    # 从环境变量获取自定义标签
    custom_tags = os.environ.get('EZ_NODE_TAGS', '')
    if custom_tags:
        tags.extend(custom_tags.split(','))

    return tags


def execute_job(job):
    """执行任务"""
    global current_job

    job_id = job['id']
    task = job['task']
    task_vars = job.get('vars', {})

    print(f"Executing job {job_id}: {task}")

    # 构建命令
    ez_cmd = os.path.join(EZ_ROOT, 'ez')
    cmd = [ez_cmd, 'run', task]
    for k, v in task_vars.items():
        cmd.append(f'{k}={v}')

    # 执行并实时推送日志
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        logs = []
        for line in process.stdout:
            line = line.rstrip()
            logs.append(line)
            print(f"  [{job_id}] {line}")
            # 推送日志
            sio.emit('job_log', {'job_id': job_id, 'log': line})

        process.wait()
        exit_code = process.returncode

        # 上报结果
        result = {
            'status': 'success' if exit_code == 0 else 'failed',
            'exit_code': exit_code,
            'logs': '\n'.join(logs)
        }

    except Exception as e:
        result = {
            'status': 'error',
            'exit_code': -1,
            'logs': str(e)
        }

    # 发送结果到服务器
    try:
        requests.post(
            f"{server_url}/api/v1/jobs/{job_id}/result",
            json=result,
            headers={'Authorization': f'Bearer {CLIENT_TOKEN}'} if CLIENT_TOKEN else {},
            timeout=10
        )
    except Exception as e:
        print(f"Failed to report result: {e}")

    print(f"Job {job_id} completed: {result['status']}")
    current_job = None


def heartbeat_loop():
    """心跳循环"""
    while running:
        try:
            if sio.connected:
                sio.emit('node_ping', {'id': node_id})
        except:
            pass
        time.sleep(5)


def main():
    global node_id, server_url

    parser = argparse.ArgumentParser(description='EZ Client Agent')
    parser.add_argument('--server', '-s', default=DEFAULT_SERVER,
                        help='Server URL (default: http://localhost:8080)')
    parser.add_argument('--name', '-n', default=os.environ.get('EZ_NODE_NAME', f'node-{os.getpid()}'),
                        help='Node name')
    parser.add_argument('--token', '-t', default=CLIENT_TOKEN,
                        help='Authentication token')

    args = parser.parse_args()

    node_id = args.name
    server_url = args.server.rstrip('/')

    print(f"EZ Client Agent")
    print(f"  Server: {server_url}")
    print(f"  Node:   {node_id}")
    print(f"  EZ Root: {EZ_ROOT}")
    print()

    # 信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 启动心跳线程
    heartbeat_thread = Thread(target=heartbeat_loop, daemon=True)
    heartbeat_thread.start()

    # 连接服务器
    while running:
        try:
            print(f"Connecting to {server_url}...")
            sio.connect(server_url)
            sio.wait()
        except Exception as e:
            print(f"Connection failed: {e}")
            if running:
                print("Reconnecting in 5 seconds...")
                time.sleep(5)


if __name__ == '__main__':
    main()
