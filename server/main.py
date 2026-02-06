#!/usr/bin/env python3
"""
EZ Server - 分布式任务执行服务器
"""

import os
import json
import time
import uuid
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from threading import Lock

from flask import Flask, render_template, jsonify, request, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# 配置
EZ_ROOT = os.environ.get('EZ_ROOT', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.environ.get('EZ_DB_PATH', os.path.join(EZ_ROOT, '.ez-server', 'ez.db'))
SERVER_TOKEN = os.environ.get('EZ_SERVER_TOKEN', '')
HTTP_PORT = int(os.environ.get('EZ_HTTP_PORT', 8080))
API_PORT = int(os.environ.get('EZ_API_PORT', 9090))

# Flask 应用
app = Flask(__name__,
            template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
            static_folder=os.path.join(os.path.dirname(__file__), 'static'))
app.config['SECRET_KEY'] = os.environ.get('EZ_SECRET_KEY', 'ez-secret-key')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# 数据库锁
db_lock = Lock()

# 内存中的节点状态
nodes = {}  # node_id -> {name, status, last_seen, tags, ...}
jobs = {}   # job_id -> {task, node, status, logs, ...}


def init_db():
    """初始化数据库"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                tags TEXT,
                status TEXT DEFAULT 'offline',
                last_seen TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                task TEXT NOT NULL,
                node_id TEXT,
                vars TEXT,
                status TEXT DEFAULT 'pending',
                exit_code INTEGER,
                logs TEXT,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()


def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def verify_token():
    """验证 API Token"""
    if not SERVER_TOKEN:
        return True
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth[7:] == SERVER_TOKEN
    return False


# =============================================================================
# Web UI Routes
# =============================================================================

@app.route('/')
def index():
    """Dashboard 首页"""
    return render_template('index.html')


@app.route('/nodes')
def nodes_page():
    """节点管理页面"""
    return render_template('nodes.html')


@app.route('/tasks')
def tasks_page():
    """任务列表页面"""
    return render_template('tasks.html')


@app.route('/jobs')
def jobs_page():
    """执行记录页面"""
    return render_template('jobs.html')


# =============================================================================
# API Routes - Nodes
# =============================================================================

@app.route('/api/v1/nodes', methods=['GET'])
def api_list_nodes():
    """列出所有节点"""
    node_list = []
    for nid, node in nodes.items():
        node_list.append({
            'id': nid,
            'name': node.get('name', nid),
            'status': node.get('status', 'offline'),
            'tags': node.get('tags', []),
            'last_seen': node.get('last_seen'),
            'current_job': node.get('current_job')
        })
    return jsonify({'nodes': node_list})


@app.route('/api/v1/nodes/<node_id>', methods=['GET'])
def api_get_node(node_id):
    """获取节点详情"""
    if node_id not in nodes:
        return jsonify({'error': 'Node not found'}), 404
    return jsonify(nodes[node_id])


@app.route('/api/v1/nodes/register', methods=['POST'])
def api_register_node():
    """注册节点"""
    data = request.json
    node_id = data.get('id') or str(uuid.uuid4())[:8]
    name = data.get('name', node_id)
    tags = data.get('tags', [])

    nodes[node_id] = {
        'id': node_id,
        'name': name,
        'status': 'online',
        'tags': tags,
        'last_seen': datetime.now().isoformat(),
        'current_job': None
    }

    # 持久化到数据库
    with db_lock:
        with get_db() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO nodes (id, name, tags, status, last_seen)
                VALUES (?, ?, ?, ?, ?)
            ''', (node_id, name, json.dumps(tags), 'online', datetime.now()))
            conn.commit()

    socketio.emit('node_update', nodes[node_id])
    return jsonify({'id': node_id, 'status': 'registered'})


@app.route('/api/v1/nodes/<node_id>/ping', methods=['POST'])
def api_ping_node(node_id):
    """节点心跳"""
    if node_id not in nodes:
        return jsonify({'error': 'Node not found'}), 404

    nodes[node_id]['last_seen'] = datetime.now().isoformat()
    nodes[node_id]['status'] = 'online'

    # 返回待执行的任务
    pending_job = None
    for job_id, job in jobs.items():
        if job.get('node_id') == node_id and job.get('status') == 'pending':
            pending_job = job
            break

    return jsonify({'status': 'ok', 'pending_job': pending_job})


@app.route('/api/v1/nodes/<node_id>', methods=['DELETE'])
def api_remove_node(node_id):
    """移除节点"""
    if node_id in nodes:
        del nodes[node_id]
    return jsonify({'status': 'removed'})


# =============================================================================
# API Routes - Tasks
# =============================================================================

@app.route('/api/v1/tasks', methods=['GET'])
def api_list_tasks():
    """列出可用任务"""
    try:
        result = subprocess.run(
            [os.path.join(EZ_ROOT, 'ez'), 'list'],
            capture_output=True, text=True, timeout=10
        )
        # 解析输出
        tasks = []
        for line in result.stdout.split('\n'):
            line = line.strip()
            if line and not line.startswith('Tasks in'):
                parts = line.split(maxsplit=1)
                if parts:
                    name = parts[0]
                    desc = parts[1] if len(parts) > 1 else ''
                    tasks.append({'name': name, 'desc': desc})
        return jsonify({'tasks': tasks})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/tasks/<task_name>', methods=['GET'])
def api_get_task(task_name):
    """获取任务详情"""
    try:
        result = subprocess.run(
            [os.path.join(EZ_ROOT, 'ez'), 'show', task_name],
            capture_output=True, text=True, timeout=10
        )
        return jsonify({'name': task_name, 'details': result.stdout})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/tasks/run', methods=['POST'])
def api_run_task():
    """提交任务执行"""
    if not verify_token():
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    task = data.get('task')
    node_id = data.get('node')
    task_vars = data.get('vars', {})

    if not task:
        return jsonify({'error': 'Task name required'}), 400

    # 如果指定了节点，检查节点是否存在
    if node_id and node_id not in nodes:
        return jsonify({'error': f'Node {node_id} not found'}), 404

    # 创建 Job
    job_id = str(uuid.uuid4())[:8]
    job = {
        'id': job_id,
        'task': task,
        'node_id': node_id,
        'vars': task_vars,
        'status': 'pending' if node_id else 'running',
        'logs': '',
        'created_at': datetime.now().isoformat()
    }
    jobs[job_id] = job

    # 如果没有指定节点，在本地执行
    if not node_id:
        _execute_job_local(job_id)
    else:
        socketio.emit('job_assigned', job, room=node_id)

    return jsonify({'job_id': job_id, 'status': job['status']})


def _execute_job_local(job_id):
    """在本地执行任务"""
    job = jobs.get(job_id)
    if not job:
        return

    job['status'] = 'running'
    job['started_at'] = datetime.now().isoformat()
    socketio.emit('job_update', job)

    # 构建命令
    cmd = [os.path.join(EZ_ROOT, 'ez'), 'run', job['task']]
    for k, v in job.get('vars', {}).items():
        cmd.append(f'{k}={v}')

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        job['logs'] = result.stdout + result.stderr
        job['exit_code'] = result.returncode
        job['status'] = 'success' if result.returncode == 0 else 'failed'
    except subprocess.TimeoutExpired:
        job['status'] = 'timeout'
        job['logs'] = 'Task execution timed out'
    except Exception as e:
        job['status'] = 'error'
        job['logs'] = str(e)

    job['finished_at'] = datetime.now().isoformat()
    socketio.emit('job_update', job)

    # 持久化
    with db_lock:
        with get_db() as conn:
            conn.execute('''
                INSERT INTO jobs (id, task, node_id, vars, status, exit_code, logs, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (job_id, job['task'], job.get('node_id'), json.dumps(job.get('vars', {})),
                  job['status'], job.get('exit_code'), job.get('logs'),
                  job.get('started_at'), job.get('finished_at')))
            conn.commit()


# =============================================================================
# API Routes - Jobs
# =============================================================================

@app.route('/api/v1/jobs', methods=['GET'])
def api_list_jobs():
    """列出执行记录"""
    job_list = list(jobs.values())
    # 按创建时间倒序
    job_list.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return jsonify({'jobs': job_list[:50]})


@app.route('/api/v1/jobs/<job_id>', methods=['GET'])
def api_get_job(job_id):
    """获取执行详情"""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(jobs[job_id])


@app.route('/api/v1/jobs/<job_id>/logs', methods=['GET'])
def api_get_job_logs(job_id):
    """获取执行日志 (SSE)"""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404

    def generate():
        last_len = 0
        while True:
            job = jobs.get(job_id)
            if not job:
                break
            logs = job.get('logs', '')
            if len(logs) > last_len:
                yield f"data: {json.dumps({'logs': logs[last_len:]})}\n\n"
                last_len = len(logs)
            if job.get('status') in ('success', 'failed', 'error', 'timeout'):
                yield f"data: {json.dumps({'status': job['status'], 'done': True})}\n\n"
                break
            time.sleep(0.5)

    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/v1/jobs/<job_id>/cancel', methods=['POST'])
def api_cancel_job(job_id):
    """取消执行"""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404

    job = jobs[job_id]
    if job['status'] in ('pending', 'running'):
        job['status'] = 'cancelled'
        socketio.emit('job_update', job)

    return jsonify({'status': 'cancelled'})


@app.route('/api/v1/jobs/<job_id>/result', methods=['POST'])
def api_report_job_result(job_id):
    """Client 上报执行结果"""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404

    data = request.json
    job = jobs[job_id]
    job['status'] = data.get('status', 'unknown')
    job['exit_code'] = data.get('exit_code')
    job['logs'] = data.get('logs', '')
    job['finished_at'] = datetime.now().isoformat()

    # 更新节点状态
    node_id = job.get('node_id')
    if node_id and node_id in nodes:
        nodes[node_id]['current_job'] = None

    socketio.emit('job_update', job)
    return jsonify({'status': 'ok'})


# =============================================================================
# WebSocket Events
# =============================================================================

@socketio.on('connect')
def handle_connect():
    """客户端连接"""
    print(f'Client connected: {request.sid}')


@socketio.on('disconnect')
def handle_disconnect():
    """客户端断开"""
    print(f'Client disconnected: {request.sid}')


@socketio.on('node_register')
def handle_node_register(data):
    """节点注册 (WebSocket)"""
    node_id = data.get('id') or str(uuid.uuid4())[:8]
    nodes[node_id] = {
        'id': node_id,
        'name': data.get('name', node_id),
        'status': 'online',
        'tags': data.get('tags', []),
        'last_seen': datetime.now().isoformat(),
        'current_job': None,
        'sid': request.sid
    }
    emit('registered', {'id': node_id})
    socketio.emit('node_update', nodes[node_id])


@socketio.on('node_ping')
def handle_node_ping(data):
    """节点心跳 (WebSocket)"""
    node_id = data.get('id')
    if node_id in nodes:
        nodes[node_id]['last_seen'] = datetime.now().isoformat()
        nodes[node_id]['status'] = 'online'


@socketio.on('job_log')
def handle_job_log(data):
    """接收任务日志"""
    job_id = data.get('job_id')
    log_line = data.get('log', '')
    if job_id in jobs:
        jobs[job_id]['logs'] += log_line + '\n'
        socketio.emit('job_log_update', {'job_id': job_id, 'log': log_line})


# =============================================================================
# Main
# =============================================================================

def main():
    """启动服务器"""
    init_db()
    print(f'EZ Server starting on http://0.0.0.0:{HTTP_PORT}')
    print(f'EZ Root: {EZ_ROOT}')
    print(f'Database: {DB_PATH}')
    socketio.run(app, host='0.0.0.0', port=HTTP_PORT, debug=False)


if __name__ == '__main__':
    main()
