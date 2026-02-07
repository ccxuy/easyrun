#!/usr/bin/env python3
"""
EZ Server - 分布式任务执行服务器
"""

import os
import re
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
YQ = os.path.join(EZ_ROOT, 'dep', 'yq')
if not os.path.isfile(YQ):
    # Docker 环境: yq 安装在系统路径
    YQ = 'yq'

def strip_ansi(text):
    """清除 ANSI 转义序列"""
    return re.sub(r'\033\[[0-9;]*m', '', text)

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
        conn.execute('''
            CREATE TABLE IF NOT EXISTS charts (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT DEFAULT 'bar',
                formula TEXT NOT NULL,
                config TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT NOT NULL,
                exit_code INTEGER,
                duration REAL,
                host TEXT,
                workspace TEXT,
                params TEXT,
                timestamp TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS plan_runs (
                id TEXT PRIMARY KEY,
                plan_name TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                steps_json TEXT,
                params TEXT,
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


@app.route('/plans')
def plans_page():
    """计划管理页面"""
    return render_template('plans.html')


@app.route('/jobs')
def jobs_page():
    """执行记录页面"""
    return render_template('jobs.html')


@app.route('/charts')
def charts_page():
    """数据可视化页面"""
    return render_template('charts.html')


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
    """列出可用任务 (复用 task tree 逻辑)"""
    try:
        tree_resp = api_task_tree()
        data = tree_resp.get_json()
        # 扁平化: 展开 namespace children
        tasks = []
        for item in data.get('tree', []):
            if item.get('type') == 'namespace' and item.get('children'):
                for child in item['children']:
                    tasks.append({'name': child['name'], 'desc': child.get('desc', '')})
            else:
                tasks.append({'name': item['name'], 'desc': item.get('desc', '')})
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
        return jsonify({'name': task_name, 'details': strip_ansi(result.stdout)})
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

    # 使用 task 直接执行 (避免 ez ensure_deps 在 Docker 中的问题)
    task_bin = os.path.join(EZ_ROOT, 'dep', 'task')
    if not os.path.isfile(task_bin):
        import shutil
        task_bin = shutil.which('task') or 'task'

    cmd = [task_bin, '-t', os.path.join(EZ_ROOT, 'Taskfile.yml'), job['task']]
    env = os.environ.copy()
    for k, v in job.get('vars', {}).items():
        env[k] = v

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, env=env, cwd=EZ_ROOT)
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
# API Routes - Stats & Charts
# =============================================================================

@app.route('/api/v1/stats', methods=['GET'])
def api_stats():
    """聚合统计数据"""
    job_list = list(jobs.values())

    # 按状态统计
    status_counts = {}
    task_stats = {}
    node_stats = {}
    timeline = {}
    durations = []

    for job in job_list:
        status = job.get('status', 'unknown')
        task_name = job.get('task', 'unknown')
        node = job.get('node_id') or 'local'

        # 状态分布
        status_counts[status] = status_counts.get(status, 0) + 1

        # 按任务
        if task_name not in task_stats:
            task_stats[task_name] = {'task': task_name, 'total': 0, 'success': 0, 'failed': 0}
        task_stats[task_name]['total'] += 1
        if status == 'success':
            task_stats[task_name]['success'] += 1
        elif status in ('failed', 'error'):
            task_stats[task_name]['failed'] += 1

        # 按节点
        if node not in node_stats:
            node_stats[node] = {'node': node, 'total': 0, 'success': 0, 'failed': 0}
        node_stats[node]['total'] += 1
        if status == 'success':
            node_stats[node]['success'] += 1
        elif status in ('failed', 'error'):
            node_stats[node]['failed'] += 1

        # 时间线（按日）
        created = job.get('created_at', '')
        if created:
            date = created[:10]
            if date not in timeline:
                timeline[date] = {'date': date, 'total': 0, 'success': 0, 'failed': 0}
            timeline[date]['total'] += 1
            if status == 'success':
                timeline[date]['success'] += 1
            elif status in ('failed', 'error'):
                timeline[date]['failed'] += 1

        # 耗时
        started = job.get('started_at')
        finished = job.get('finished_at')
        if started and finished:
            try:
                s = datetime.fromisoformat(started)
                f = datetime.fromisoformat(finished)
                durations.append((f - s).total_seconds())
            except (ValueError, TypeError):
                pass

    total = len(job_list)
    success = status_counts.get('success', 0)
    failed = status_counts.get('failed', 0) + status_counts.get('error', 0)

    # 耗时统计
    duration_stats = {'avg': 0, 'min': 0, 'max': 0, 'p50': 0, 'p90': 0}
    if durations:
        durations.sort()
        duration_stats = {
            'avg': round(sum(durations) / len(durations), 1),
            'min': round(durations[0], 1),
            'max': round(durations[-1], 1),
            'p50': round(durations[len(durations) // 2], 1),
            'p90': round(durations[int(len(durations) * 0.9)], 1),
        }

    # 时间线排序
    timeline_sorted = sorted(timeline.values(), key=lambda x: x['date'])

    # raw_jobs（最近 200 条，不含 logs 以减少数据量）
    raw = []
    for j in sorted(job_list, key=lambda x: x.get('created_at', ''), reverse=True)[:200]:
        raw.append({
            'id': j.get('id'),
            'task': j.get('task'),
            'node_id': j.get('node_id'),
            'status': j.get('status'),
            'exit_code': j.get('exit_code'),
            'started_at': j.get('started_at'),
            'finished_at': j.get('finished_at'),
            'created_at': j.get('created_at'),
        })

    return jsonify({
        'summary': {
            'total_jobs': total,
            'success': success,
            'failed': failed,
            'error': status_counts.get('error', 0),
            'success_rate': round(success / total * 100, 1) if total > 0 else 0,
        },
        'by_status': [{'status': k, 'count': v} for k, v in status_counts.items()],
        'by_task': list(task_stats.values()),
        'by_node': list(node_stats.values()),
        'timeline': timeline_sorted,
        'duration': duration_stats,
        'raw_jobs': raw,
    })


@app.route('/api/v1/stats/report', methods=['POST'])
def api_stats_report():
    """接收 CLI 上报的执行统计"""
    data = request.json or {}
    task = data.get('task', '')
    if not task:
        return jsonify({'error': 'task required'}), 400

    with db_lock:
        with get_db() as conn:
            conn.execute(
                '''INSERT INTO executions (task, exit_code, duration, host, workspace, params, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (task, data.get('exit_code', 0), data.get('duration', 0),
                 data.get('host', ''), data.get('workspace', ''),
                 data.get('params', ''), data.get('timestamp', datetime.now().isoformat()))
            )
            conn.commit()

    return jsonify({'status': 'ok'})


@app.route('/api/v1/stats/executions', methods=['GET'])
def api_executions():
    """获取 CLI 上报的执行历史"""
    limit = request.args.get('limit', 50, type=int)
    with db_lock:
        with get_db() as conn:
            rows = conn.execute(
                'SELECT * FROM executions ORDER BY created_at DESC LIMIT ?', (limit,)
            ).fetchall()
    return jsonify({'executions': [dict(r) for r in rows]})


# =============================================================================
# API Routes - Task Tree
# =============================================================================

@app.route('/api/v1/tasks/tree', methods=['GET'])
def api_task_tree():
    """返回树形任务结构 (直接解析 YAML，避免 ANSI 问题)"""
    try:
        tasks_flat = []

        # 1. 读 Taskfile.yml 获取行内任务
        taskfile = os.path.join(EZ_ROOT, 'Taskfile.yml')
        if os.path.isfile(taskfile):
            # 获取所有 task 名称
            result = subprocess.run(
                [YQ, 'eval', '.tasks | keys | .[]', taskfile],
                capture_output=True, text=True, timeout=10
            )
            for name in result.stdout.strip().split('\n'):
                name = name.strip()
                if not name:
                    continue
                # 获取 desc
                desc_result = subprocess.run(
                    [YQ, 'eval', f'.tasks."{name}".desc // ""', taskfile],
                    capture_output=True, text=True, timeout=5
                )
                desc = desc_result.stdout.strip().strip('"')
                # 检查是否有 ez-params
                params_result = subprocess.run(
                    [YQ, 'eval', f'.tasks."{name}".ez-params | length', taskfile],
                    capture_output=True, text=True, timeout=5
                )
                params_count = params_result.stdout.strip()
                has_params = params_count not in ('0', 'null', '')
                tasks_flat.append({
                    'name': name, 'desc': desc, 'type': 'inline',
                    'has_params': has_params
                })

            # 处理 includes 命名空间
            inc_result = subprocess.run(
                [YQ, 'eval', '.includes | keys | .[]', taskfile],
                capture_output=True, text=True, timeout=5
            )
            for ns in inc_result.stdout.strip().split('\n'):
                ns = ns.strip()
                if not ns:
                    continue
                # 获取 include 的 taskfile 路径
                inc_path_result = subprocess.run(
                    [YQ, 'eval', f'.includes."{ns}".taskfile // .includes."{ns}"', taskfile],
                    capture_output=True, text=True, timeout=5
                )
                inc_path = inc_path_result.stdout.strip().strip('"')
                inc_file = os.path.join(EZ_ROOT, inc_path) if inc_path else None
                children = []
                if inc_file and os.path.isfile(inc_file):
                    child_result = subprocess.run(
                        [YQ, 'eval', '.tasks | keys | .[]', inc_file],
                        capture_output=True, text=True, timeout=5
                    )
                    for child_name in child_result.stdout.strip().split('\n'):
                        child_name = child_name.strip()
                        if not child_name:
                            continue
                        child_desc_result = subprocess.run(
                            [YQ, 'eval', f'.tasks."{child_name}".desc // ""', inc_file],
                            capture_output=True, text=True, timeout=5
                        )
                        child_desc = child_desc_result.stdout.strip().strip('"')
                        children.append({
                            'name': f'{ns}:{child_name}', 'desc': child_desc,
                            'type': 'inline', 'has_params': False
                        })
                    # 也扫描 includes 内的子 includes
                    sub_inc_result = subprocess.run(
                        [YQ, 'eval', '.includes | keys | .[]', inc_file],
                        capture_output=True, text=True, timeout=5
                    )
                    for sub_ns in sub_inc_result.stdout.strip().split('\n'):
                        sub_ns = sub_ns.strip()
                        if not sub_ns:
                            continue
                        sub_path_result = subprocess.run(
                            [YQ, 'eval', f'.includes."{sub_ns}".taskfile // .includes."{sub_ns}"', inc_file],
                            capture_output=True, text=True, timeout=5
                        )
                        sub_path = sub_path_result.stdout.strip().strip('"')
                        # 相对于 inc_file 的目录
                        sub_file = os.path.join(os.path.dirname(inc_file), sub_path) if sub_path else None
                        if sub_file and os.path.isfile(sub_file):
                            sub_child_result = subprocess.run(
                                [YQ, 'eval', '.tasks | keys | .[]', sub_file],
                                capture_output=True, text=True, timeout=5
                            )
                            for sc_name in sub_child_result.stdout.strip().split('\n'):
                                sc_name = sc_name.strip()
                                if not sc_name:
                                    continue
                                sc_desc_result = subprocess.run(
                                    [YQ, 'eval', f'.tasks."{sc_name}".desc // ""', sub_file],
                                    capture_output=True, text=True, timeout=5
                                )
                                sc_desc = sc_desc_result.stdout.strip().strip('"')
                                children.append({
                                    'name': f'{ns}:{sc_name}', 'desc': sc_desc,
                                    'type': 'inline', 'has_params': False
                                })

                if children:
                    tasks_flat.append({
                        'name': ns, 'type': 'namespace',
                        'desc': f'{len(children)} 个子任务',
                        'children': children
                    })

        # 2. 扫描 tasks/ 获取目录任务
        tasks_dir = os.path.join(EZ_ROOT, 'tasks')
        if os.path.isdir(tasks_dir):
            for entry in sorted(os.listdir(tasks_dir)):
                entry_path = os.path.join(tasks_dir, entry)
                tf = os.path.join(entry_path, 'Taskfile.yml')
                if os.path.isdir(entry_path) and os.path.isfile(tf):
                    desc = ''
                    has_params = False
                    # 读 task.yml 元数据
                    meta = os.path.join(entry_path, 'task.yml')
                    if os.path.isfile(meta):
                        desc_result = subprocess.run(
                            [YQ, 'eval', '.desc // ""', meta],
                            capture_output=True, text=True, timeout=5
                        )
                        desc = desc_result.stdout.strip().strip('"')
                        params_result = subprocess.run(
                            [YQ, 'eval', '.params | length', meta],
                            capture_output=True, text=True, timeout=5
                        )
                        pc = params_result.stdout.strip()
                        has_params = pc not in ('0', 'null', '')
                    # 已在行内列表中则更新
                    found = False
                    for t in tasks_flat:
                        if t.get('name') == entry and t.get('type') != 'namespace':
                            t['type'] = 'dir'
                            t['path'] = f'tasks/{entry}/'
                            if desc:
                                t['desc'] = desc
                            if has_params:
                                t['has_params'] = True
                            found = True
                            break
                    if not found:
                        tasks_flat.append({
                            'name': entry, 'desc': desc, 'type': 'dir',
                            'has_params': has_params, 'path': f'tasks/{entry}/'
                        })

        # 3. 扫描 lib/tools/*.yml 获取工具任务
        tools_dir = os.path.join(EZ_ROOT, 'lib', 'tools')
        if os.path.isdir(tools_dir):
            for f in sorted(os.listdir(tools_dir)):
                if f.endswith('.yml'):
                    tool_path = os.path.join(tools_dir, f)
                    name_result = subprocess.run(
                        [YQ, 'eval', '.name // ""', tool_path],
                        capture_output=True, text=True, timeout=5
                    )
                    tool_name = name_result.stdout.strip().strip('"')
                    desc_result = subprocess.run(
                        [YQ, 'eval', '.desc // ""', tool_path],
                        capture_output=True, text=True, timeout=5
                    )
                    tool_desc = desc_result.stdout.strip().strip('"')
                    if tool_name:
                        tasks_flat.append({
                            'name': tool_name, 'desc': tool_desc, 'type': 'tool',
                            'has_params': False
                        })

        return jsonify({'tree': tasks_flat})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/tasks/<task_name>/params', methods=['GET'])
def api_task_params(task_name):
    """获取任务参数定义 (结构化 JSON)"""
    try:
        taskfile = os.path.join(EZ_ROOT, 'Taskfile.yml')
        params = []
        desc = ''

        # 目录任务: 读 task.yml
        task_meta = os.path.join(EZ_ROOT, 'tasks', task_name, 'task.yml')
        if os.path.isfile(task_meta):
            desc_result = subprocess.run(
                [YQ, 'eval', '.desc // ""', task_meta],
                capture_output=True, text=True, timeout=5
            )
            desc = desc_result.stdout.strip().strip('"')
            params_result = subprocess.run(
                [YQ, 'eval', '-o=json', '.params // []', task_meta],
                capture_output=True, text=True, timeout=5
            )
            if params_result.stdout.strip():
                try:
                    params = json.loads(params_result.stdout)
                except json.JSONDecodeError:
                    pass

        # 行内任务: 读 Taskfile.yml 的 ez-params
        if not params and os.path.isfile(taskfile):
            # 处理带命名空间的任务名 (如 selftest:xxx → 查对应 include 文件)
            actual_task = task_name
            actual_file = taskfile
            if ':' in task_name:
                ns, sub = task_name.split(':', 1)
                inc_path_result = subprocess.run(
                    [YQ, 'eval', f'.includes."{ns}".taskfile // .includes."{ns}" // ""', taskfile],
                    capture_output=True, text=True, timeout=5
                )
                inc_path = inc_path_result.stdout.strip().strip('"')
                if inc_path:
                    actual_file = os.path.join(EZ_ROOT, inc_path)
                actual_task = sub

            if os.path.isfile(actual_file):
                desc_result = subprocess.run(
                    [YQ, 'eval', f'.tasks."{actual_task}".desc // ""', actual_file],
                    capture_output=True, text=True, timeout=5
                )
                desc = desc_result.stdout.strip().strip('"')
                params_result = subprocess.run(
                    [YQ, 'eval', '-o=json', f'.tasks."{actual_task}".ez-params // []', actual_file],
                    capture_output=True, text=True, timeout=5
                )
                if params_result.stdout.strip():
                    try:
                        params = json.loads(params_result.stdout)
                    except json.JSONDecodeError:
                        pass

        # 工具任务: 读 lib/tools/<name>.yml
        tool_file = os.path.join(EZ_ROOT, 'lib', 'tools', f'{task_name}.yml')
        if not params and os.path.isfile(tool_file):
            desc_result = subprocess.run(
                [YQ, 'eval', '.desc // ""', tool_file],
                capture_output=True, text=True, timeout=5
            )
            desc = desc_result.stdout.strip().strip('"')

        return jsonify({
            'name': task_name,
            'desc': desc,
            'params': params
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/tasks/<task_name>/yaml', methods=['GET'])
def api_task_yaml(task_name):
    """获取任务 YAML 源文件"""
    try:
        # 目录任务
        dir_taskfile = os.path.join(EZ_ROOT, 'tasks', task_name, 'Taskfile.yml')
        if os.path.isfile(dir_taskfile):
            with open(dir_taskfile, 'r', encoding='utf-8') as f:
                return jsonify({'yaml': f.read(), 'file': f'tasks/{task_name}/Taskfile.yml', 'type': 'dir'})

        # 工具任务
        tool_file = os.path.join(EZ_ROOT, 'lib', 'tools', f'{task_name}.yml')
        if os.path.isfile(tool_file):
            with open(tool_file, 'r', encoding='utf-8') as f:
                return jsonify({'yaml': f.read(), 'file': f'lib/tools/{task_name}.yml', 'type': 'tool'})

        # 行内任务: 提取 Taskfile.yml 中对应 task 片段
        taskfile = os.path.join(EZ_ROOT, 'Taskfile.yml')
        actual_task = task_name
        actual_file = taskfile
        if ':' in task_name:
            ns, sub = task_name.split(':', 1)
            inc_result = subprocess.run(
                [YQ, 'eval', f'.includes."{ns}".taskfile // .includes."{ns}" // ""', taskfile],
                capture_output=True, text=True, timeout=5
            )
            inc_path = inc_result.stdout.strip().strip('"')
            if inc_path:
                actual_file = os.path.join(EZ_ROOT, inc_path)
            actual_task = sub

        if os.path.isfile(actual_file):
            result = subprocess.run(
                [YQ, 'eval', f'.tasks."{actual_task}"', actual_file],
                capture_output=True, text=True, timeout=5
            )
            rel_path = os.path.relpath(actual_file, EZ_ROOT)
            return jsonify({'yaml': result.stdout, 'file': rel_path, 'task_key': actual_task, 'type': 'inline'})

        return jsonify({'error': 'Task not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/tasks/<task_name>/yaml', methods=['PUT'])
def api_save_task_yaml(task_name):
    """保存任务 YAML"""
    try:
        data = request.json or {}
        yaml_content = data.get('yaml', '')
        file_type = data.get('type', '')

        if file_type == 'dir':
            target = os.path.join(EZ_ROOT, 'tasks', task_name, 'Taskfile.yml')
        elif file_type == 'tool':
            target = os.path.join(EZ_ROOT, 'lib', 'tools', f'{task_name}.yml')
        else:
            return jsonify({'error': '行内任务暂不支持直接保存，请手动编辑 Taskfile.yml'}), 400

        if not os.path.isfile(target):
            return jsonify({'error': f'File not found: {target}'}), 404

        with open(target, 'w', encoding='utf-8') as f:
            f.write(yaml_content)

        return jsonify({'ok': True, 'file': os.path.relpath(target, EZ_ROOT)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/plans/<plan_name>/yaml', methods=['GET'])
def api_plan_yaml(plan_name):
    """获取 Plan YAML 源文件"""
    try:
        plan_file = os.path.join(EZ_ROOT, 'plans', f'{plan_name}.yml')
        if not os.path.isfile(plan_file):
            plan_file = os.path.join(EZ_ROOT, 'plans', f'{plan_name}.yaml')
        if not os.path.isfile(plan_file):
            return jsonify({'error': 'Plan not found'}), 404

        with open(plan_file, 'r', encoding='utf-8') as f:
            return jsonify({'yaml': f.read(), 'file': os.path.relpath(plan_file, EZ_ROOT)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/plans/<plan_name>/yaml', methods=['PUT'])
def api_save_plan_yaml(plan_name):
    """保存 Plan YAML"""
    try:
        data = request.json or {}
        yaml_content = data.get('yaml', '')

        plan_file = os.path.join(EZ_ROOT, 'plans', f'{plan_name}.yml')
        if not os.path.isfile(plan_file):
            plan_file = os.path.join(EZ_ROOT, 'plans', f'{plan_name}.yaml')
        if not os.path.isfile(plan_file):
            return jsonify({'error': 'Plan not found'}), 404

        with open(plan_file, 'w', encoding='utf-8') as f:
            f.write(yaml_content)

        return jsonify({'ok': True, 'file': os.path.relpath(plan_file, EZ_ROOT)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# =============================================================================
# API Routes - Plans
# =============================================================================

@app.route('/api/v1/plans', methods=['GET'])
def api_list_plans():
    """列出所有计划"""
    plans = []
    plans_dir = os.path.join(EZ_ROOT, 'plans')
    if os.path.isdir(plans_dir):
        for f in os.listdir(plans_dir):
            if f.endswith('.yml') or f.endswith('.yaml'):
                name = os.path.splitext(f)[0]
                # 读取 plan 概要
                try:
                    result = subprocess.run(
                        [YQ, 'eval', '.name // .desc // ""',
                         os.path.join(plans_dir, f)],
                        capture_output=True, text=True, timeout=5
                    )
                    desc = result.stdout.strip()
                except Exception:
                    desc = ''
                plans.append({'name': name, 'file': f, 'desc': desc})

    return jsonify({'plans': plans})


@app.route('/api/v1/plans/<plan_name>', methods=['GET'])
def api_get_plan(plan_name):
    """获取计划详情 (结构化 JSON)"""
    try:
        plan_file = os.path.join(EZ_ROOT, 'plans', f'{plan_name}.yml')
        if not os.path.isfile(plan_file):
            plan_file = os.path.join(EZ_ROOT, 'plans', f'{plan_name}.yaml')
        if not os.path.isfile(plan_file):
            return jsonify({'error': f'Plan not found: {plan_name}'}), 404

        # 读取原始 YAML
        with open(plan_file, 'r', encoding='utf-8') as f:
            yaml_content = f.read()

        # 用 yq 解析结构化数据
        result = subprocess.run(
            [YQ, 'eval', '-o=json', '.', plan_file],
            capture_output=True, text=True, timeout=10
        )
        plan_data = json.loads(result.stdout) if result.stdout.strip() else {}

        # 提取步骤
        steps = []
        for s in plan_data.get('steps', []):
            steps.append({
                'name': s.get('name', ''),
                'task': s.get('task', ''),
                'needs': s.get('needs', []) or [],
                'vars': s.get('vars', {}) or {},
                'artifacts': s.get('artifacts', []) or [],
                'inputs': s.get('inputs', []) or []
            })

        return jsonify({
            'name': plan_data.get('name', plan_name),
            'desc': plan_data.get('desc', ''),
            'steps': steps,
            'yaml': yaml_content
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/plans/<plan_name>/run', methods=['POST'])
def api_run_plan(plan_name):
    """执行计划"""
    data = request.json or {}
    task_vars = data.get('vars', {})

    run_id = str(uuid.uuid4())[:8]

    # 记录到数据库
    with db_lock:
        with get_db() as conn:
            conn.execute(
                '''INSERT INTO plan_runs (id, plan_name, status, params, started_at)
                   VALUES (?, ?, 'running', ?, ?)''',
                (run_id, plan_name, json.dumps(task_vars), datetime.now().isoformat())
            )
            conn.commit()

    # 在后台线程执行
    import threading
    def _run():
        cmd = [os.path.join(EZ_ROOT, 'ez'), 'plan', 'run', plan_name]
        for k, v in task_vars.items():
            cmd.append(f'{k}={v}')

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            status = 'success' if result.returncode == 0 else 'failed'
            with db_lock:
                with get_db() as conn:
                    conn.execute(
                        '''UPDATE plan_runs SET status=?, finished_at=?, steps_json=?
                           WHERE id=?''',
                        (status, datetime.now().isoformat(),
                         json.dumps({'stdout': result.stdout[-2000:], 'stderr': result.stderr[-2000:]}),
                         run_id)
                    )
                    conn.commit()
            socketio.emit('plan_update', {'run_id': run_id, 'status': status})
        except Exception as e:
            with db_lock:
                with get_db() as conn:
                    conn.execute(
                        'UPDATE plan_runs SET status=?, finished_at=? WHERE id=?',
                        ('error', datetime.now().isoformat(), run_id)
                    )
                    conn.commit()

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({'run_id': run_id, 'status': 'running'})


@app.route('/api/v1/plans/run-task', methods=['POST'])
def api_run_single_task():
    """单任务执行 (包装为最简 Plan)"""
    data = request.json or {}
    task = data.get('task')
    if not task:
        return jsonify({'error': 'task required'}), 400

    task_vars = data.get('vars', {})
    node_id = data.get('node')

    # 如果指定了节点，使用原来的分布式执行
    if node_id:
        if node_id not in nodes:
            return jsonify({'error': f'Node {node_id} not found'}), 404
        job_id = str(uuid.uuid4())[:8]
        job = {
            'id': job_id, 'task': task, 'node_id': node_id,
            'vars': task_vars, 'status': 'pending', 'logs': '',
            'created_at': datetime.now().isoformat()
        }
        jobs[job_id] = job
        socketio.emit('job_assigned', job, room=node_id)
        return jsonify({'job_id': job_id, 'status': 'pending'})

    # 本地执行
    job_id = str(uuid.uuid4())[:8]
    job = {
        'id': job_id, 'task': task, 'node_id': None,
        'vars': task_vars, 'status': 'running', 'logs': '',
        'created_at': datetime.now().isoformat()
    }
    jobs[job_id] = job
    _execute_job_local(job_id)
    return jsonify({'job_id': job_id, 'status': job['status']})


@app.route('/api/v1/plans/runs', methods=['GET'])
def api_list_plan_runs():
    """获取计划执行历史"""
    limit = request.args.get('limit', 20, type=int)
    with db_lock:
        with get_db() as conn:
            rows = conn.execute(
                'SELECT * FROM plan_runs ORDER BY created_at DESC LIMIT ?', (limit,)
            ).fetchall()
    return jsonify({'runs': [dict(r) for r in rows]})


@app.route('/api/v1/plans/runs/<run_id>', methods=['GET'])
def api_get_plan_run(run_id):
    """获取单次计划执行状态"""
    with db_lock:
        with get_db() as conn:
            row = conn.execute('SELECT * FROM plan_runs WHERE id = ?', (run_id,)).fetchone()
    if not row:
        return jsonify({'error': 'not found'}), 404
    return jsonify(dict(row))


# =============================================================================
# API Routes - Templates
# =============================================================================

@app.route('/api/v1/templates', methods=['GET'])
def api_list_templates():
    """列出可用模板"""
    templates = []
    tpl_dir = os.path.join(EZ_ROOT, 'templates')
    if os.path.isdir(tpl_dir):
        for f in os.listdir(tpl_dir):
            if f.endswith('.yml') or f.endswith('.yaml') or f.endswith('.ytt.yml'):
                name = f.replace('.ytt.yml', '').replace('.yml', '').replace('.yaml', '')
                templates.append({'name': name, 'file': f})
    return jsonify({'templates': templates})


@app.route('/api/v1/charts', methods=['GET'])
def api_list_charts():
    """列出保存的自定义图表"""
    with db_lock:
        with get_db() as conn:
            rows = conn.execute(
                'SELECT id, name, type, formula, config, created_at FROM charts ORDER BY created_at DESC'
            ).fetchall()
    charts = [dict(r) for r in rows]
    return jsonify({'charts': charts})


@app.route('/api/v1/charts', methods=['POST'])
def api_save_chart():
    """保存自定义图表配置"""
    data = request.json
    name = data.get('name', '').strip()
    chart_type = data.get('type', 'bar')
    formula = data.get('formula', '').strip()

    if not name or not formula:
        return jsonify({'error': 'name and formula required'}), 400

    chart_id = str(uuid.uuid4())[:8]
    with db_lock:
        with get_db() as conn:
            conn.execute(
                'INSERT INTO charts (id, name, type, formula, config) VALUES (?, ?, ?, ?, ?)',
                (chart_id, name, chart_type, formula, json.dumps(data.get('config', {})))
            )
            conn.commit()

    return jsonify({'id': chart_id, 'status': 'saved'})


@app.route('/api/v1/charts/<chart_id>', methods=['DELETE'])
def api_delete_chart(chart_id):
    """删除自定义图表"""
    with db_lock:
        with get_db() as conn:
            conn.execute('DELETE FROM charts WHERE id = ?', (chart_id,))
            conn.commit()
    return jsonify({'status': 'deleted'})


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
