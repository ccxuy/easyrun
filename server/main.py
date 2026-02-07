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
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock, Thread

import yaml

from flask import Flask, render_template, jsonify, request, Response, redirect
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


# =============================================================================
# YAML 缓存基础设施
# =============================================================================

_tree_cache = {'result': None, 'mtimes': {}}
_tree_cache_lock = Lock()


def _load_yaml_file(filepath):
    """安全加载 YAML 文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def _get_file_mtimes():
    """收集影响任务树的所有文件 mtime"""
    mtimes = {}
    # Taskfile.yml
    taskfile = os.path.join(EZ_ROOT, 'Taskfile.yml')
    if os.path.isfile(taskfile):
        mtimes[taskfile] = os.path.getmtime(taskfile)
    # tasks/*/task.yml 和 tasks/*/Taskfile.yml
    tasks_dir = os.path.join(EZ_ROOT, 'tasks')
    if os.path.isdir(tasks_dir):
        for entry in os.listdir(tasks_dir):
            for fname in ('task.yml', 'Taskfile.yml'):
                fpath = os.path.join(tasks_dir, entry, fname)
                if os.path.isfile(fpath):
                    mtimes[fpath] = os.path.getmtime(fpath)
    # lib/tools/*.yml
    tools_dir = os.path.join(EZ_ROOT, 'lib', 'tools')
    if os.path.isdir(tools_dir):
        for f in os.listdir(tools_dir):
            if f.endswith('.yml'):
                fpath = os.path.join(tools_dir, f)
                mtimes[fpath] = os.path.getmtime(fpath)
    # includes (scan from Taskfile.yml)
    if os.path.isfile(taskfile):
        try:
            data = _load_yaml_file(taskfile)
            for ns, inc_val in (data.get('includes') or {}).items():
                inc_path = inc_val if isinstance(inc_val, str) else (inc_val or {}).get('taskfile', '')
                if inc_path:
                    inc_file = os.path.join(EZ_ROOT, inc_path)
                    if os.path.isfile(inc_file):
                        mtimes[inc_file] = os.path.getmtime(inc_file)
                        # sub-includes
                        try:
                            sub_data = _load_yaml_file(inc_file)
                            for sub_ns, sub_val in (sub_data.get('includes') or {}).items():
                                sub_path = sub_val if isinstance(sub_val, str) else (sub_val or {}).get('taskfile', '')
                                if sub_path:
                                    sub_file = os.path.join(os.path.dirname(inc_file), sub_path)
                                    if os.path.isfile(sub_file):
                                        mtimes[sub_file] = os.path.getmtime(sub_file)
                        except Exception:
                            pass
        except Exception:
            pass
    return mtimes


def _is_cache_valid():
    """检查缓存是否仍然有效"""
    if _tree_cache['result'] is None:
        return False
    return _get_file_mtimes() == _tree_cache['mtimes']


def _invalidate_cache():
    """清除缓存"""
    with _tree_cache_lock:
        _tree_cache['result'] = None
        _tree_cache['mtimes'] = {}


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
                trigger_type TEXT DEFAULT 'manual',
                duration REAL,
                total_steps INTEGER DEFAULT 0,
                completed_steps INTEGER DEFAULT 0,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS plan_run_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                step_name TEXT NOT NULL,
                task_name TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                exit_code INTEGER,
                logs TEXT,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                duration REAL
            )
        ''')
        # Migrate: add columns if missing
        try:
            conn.execute('SELECT trigger_type FROM plan_runs LIMIT 1')
        except sqlite3.OperationalError:
            conn.execute('ALTER TABLE plan_runs ADD COLUMN trigger_type TEXT DEFAULT "manual"')
        try:
            conn.execute('SELECT duration FROM plan_runs LIMIT 1')
        except sqlite3.OperationalError:
            conn.execute('ALTER TABLE plan_runs ADD COLUMN duration REAL')
        try:
            conn.execute('SELECT total_steps FROM plan_runs LIMIT 1')
        except sqlite3.OperationalError:
            conn.execute('ALTER TABLE plan_runs ADD COLUMN total_steps INTEGER DEFAULT 0')
        try:
            conn.execute('SELECT completed_steps FROM plan_runs LIMIT 1')
        except sqlite3.OperationalError:
            conn.execute('ALTER TABLE plan_runs ADD COLUMN completed_steps INTEGER DEFAULT 0')
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


def _get_task_bin():
    """获取 task 二进制路径"""
    task_bin = os.path.join(EZ_ROOT, 'dep', 'task')
    if not os.path.isfile(task_bin):
        import shutil
        task_bin = shutil.which('task') or 'task'
    return task_bin


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


@app.route('/tasks/<task_name>')
def task_detail_page(task_name):
    """任务详情页面"""
    return render_template('task_detail.html', task_name=task_name)


@app.route('/tasks/new')
def task_new_page():
    """新建任务页面"""
    return render_template('task_new.html')


@app.route('/plans')
def plans_page():
    """计划管理页面"""
    return render_template('plans.html')


@app.route('/plans/<plan_name>')
def plan_detail_page(plan_name):
    """计划详情页面"""
    return render_template('plan_detail.html', plan_name=plan_name)


@app.route('/executions')
def executions_page():
    """执行记录页面"""
    return render_template('executions.html')


@app.route('/executions/<exec_id>')
def execution_detail_page(exec_id):
    """执行详情页面"""
    return render_template('execution_detail.html', exec_id=exec_id)


@app.route('/settings')
def settings_page():
    """设置页面"""
    return render_template('settings.html')


# Redirects for old URLs
@app.route('/jobs')
def jobs_redirect():
    return redirect('/executions', code=301)


@app.route('/charts')
def charts_redirect():
    return redirect('/settings', code=301)


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

@app.route('/api/v1/tasks', methods=['GET', 'POST'])
def api_tasks():
    """GET: 列出可用任务; POST: 创建任务"""
    if request.method == 'POST':
        return _api_create_task()

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


def _api_create_task():
    """创建任务"""
    data = request.json or {}
    name = data.get('name', '').strip()
    task_type = data.get('type', 'dir')
    desc = data.get('desc', '')

    if not name:
        return jsonify({'error': 'name required'}), 400
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return jsonify({'error': 'name 只允许字母、数字、下划线和连字符'}), 400

    if task_type == 'dir':
        task_dir = os.path.join(EZ_ROOT, 'tasks', name)
        if os.path.isdir(task_dir):
            return jsonify({'error': f'目录任务 "{name}" 已存在'}), 409
        os.makedirs(task_dir, exist_ok=True)
        # 创建 task.yml
        meta = {'desc': desc, 'params': []}
        with open(os.path.join(task_dir, 'task.yml'), 'w', encoding='utf-8') as f:
            yaml.dump(meta, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        # 创建 Taskfile.yml 脚手架
        taskfile = {
            'version': '3',
            'tasks': {
                'default': {
                    'desc': desc,
                    'cmds': ['echo "Hello from ' + name + '"']
                }
            }
        }
        with open(os.path.join(task_dir, 'Taskfile.yml'), 'w', encoding='utf-8') as f:
            yaml.dump(taskfile, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    else:
        # inline: 追加到 Taskfile.yml
        taskfile_path = os.path.join(EZ_ROOT, 'Taskfile.yml')
        if not os.path.isfile(taskfile_path):
            return jsonify({'error': 'Taskfile.yml not found'}), 404
        tf_data = _load_yaml_file(taskfile_path)
        if 'tasks' not in tf_data:
            tf_data['tasks'] = {}
        if name in tf_data['tasks']:
            return jsonify({'error': f'行内任务 "{name}" 已存在'}), 409
        tf_data['tasks'][name] = {
            'desc': desc,
            'cmds': ['echo "Hello from ' + name + '"']
        }
        with open(taskfile_path, 'w', encoding='utf-8') as f:
            yaml.dump(tf_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    _invalidate_cache()
    return jsonify({'ok': True, 'name': name, 'type': task_type})


@app.route('/api/v1/tasks/<task_name>', methods=['GET', 'DELETE'])
def api_get_or_delete_task(task_name):
    """GET: 获取任务详情; DELETE: 删除任务"""
    if request.method == 'DELETE':
        return _api_delete_task(task_name)

    try:
        result = subprocess.run(
            [os.path.join(EZ_ROOT, 'ez'), 'show', task_name],
            capture_output=True, text=True, timeout=10
        )
        return jsonify({'name': task_name, 'details': strip_ansi(result.stdout)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _api_delete_task(task_name):
    """删除任务"""
    import shutil
    # 目录任务
    task_dir = os.path.join(EZ_ROOT, 'tasks', task_name)
    if os.path.isdir(task_dir):
        shutil.rmtree(task_dir)
        _invalidate_cache()
        return jsonify({'ok': True, 'deleted': task_name})

    # 行内任务
    taskfile_path = os.path.join(EZ_ROOT, 'Taskfile.yml')
    if os.path.isfile(taskfile_path):
        tf_data = _load_yaml_file(taskfile_path)
        tasks_map = tf_data.get('tasks') or {}
        if task_name in tasks_map:
            del tasks_map[task_name]
            tf_data['tasks'] = tasks_map
            with open(taskfile_path, 'w', encoding='utf-8') as f:
                yaml.dump(tf_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            _invalidate_cache()
            return jsonify({'ok': True, 'deleted': task_name})

    return jsonify({'error': f'Task "{task_name}" not found'}), 404


@app.route('/api/v1/tasks/<task_name>/history', methods=['GET'])
def api_task_history(task_name):
    """获取任务的执行历史"""
    limit = request.args.get('limit', 20, type=int)
    history = []

    # 从 jobs (内存)
    for jid, job in sorted(jobs.items(), key=lambda x: x[1].get('created_at', ''), reverse=True):
        if job.get('task') == task_name:
            history.append({
                'id': jid, 'type': 'task',
                'name': job.get('task'), 'status': job.get('status'),
                'started_at': job.get('started_at'), 'finished_at': job.get('finished_at'),
                'created_at': job.get('created_at')
            })
    # 从 jobs (DB)
    with db_lock:
        with get_db() as conn:
            rows = conn.execute(
                'SELECT id, task, status, started_at, finished_at, created_at FROM jobs WHERE task = ? ORDER BY created_at DESC LIMIT ?',
                (task_name, limit)
            ).fetchall()
            seen = {h['id'] for h in history}
            for r in rows:
                if r['id'] not in seen:
                    history.append({
                        'id': r['id'], 'type': 'task',
                        'name': r['task'], 'status': r['status'],
                        'started_at': r['started_at'], 'finished_at': r['finished_at'],
                        'created_at': r['created_at']
                    })

    history.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return jsonify({'history': history[:limit]})


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
        Thread(target=_execute_job_local, args=(job_id,), daemon=True).start()
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

    task_bin = _get_task_bin()
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
                INSERT OR REPLACE INTO jobs (id, task, node_id, vars, status, exit_code, logs, started_at, finished_at)
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
    if job_id in jobs:
        return jsonify(jobs[job_id])
    # 从 DB 查
    with db_lock:
        with get_db() as conn:
            row = conn.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
    if row:
        return jsonify(dict(row))
    return jsonify({'error': 'Job not found'}), 404


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
# API Routes - Executions (统一视图)
# =============================================================================

@app.route('/api/v1/executions', methods=['GET'])
def api_list_executions():
    """统一执行列表: 合并 jobs + plan_runs + cli executions"""
    exec_type = request.args.get('type', 'all')
    status_filter = request.args.get('status', '')
    search = request.args.get('search', '').lower()
    limit = request.args.get('limit', 50, type=int)

    results = []

    # Jobs (task runs)
    if exec_type in ('all', 'task'):
        # 从内存
        for jid, job in jobs.items():
            if status_filter and job.get('status') != status_filter:
                continue
            if search and search not in (job.get('task') or '').lower():
                continue
            results.append({
                'id': jid, 'type': 'task',
                'name': job.get('task', ''),
                'status': job.get('status', 'unknown'),
                'started_at': job.get('started_at'),
                'finished_at': job.get('finished_at'),
                'created_at': job.get('created_at'),
                'node_id': job.get('node_id'),
            })
        # 从 DB (补充已不在内存中的)
        seen_ids = {r['id'] for r in results}
        with db_lock:
            with get_db() as conn:
                rows = conn.execute(
                    'SELECT id, task, node_id, status, started_at, finished_at, created_at FROM jobs ORDER BY created_at DESC LIMIT ?',
                    (limit * 2,)
                ).fetchall()
                for r in rows:
                    if r['id'] not in seen_ids:
                        if status_filter and r['status'] != status_filter:
                            continue
                        if search and search not in (r['task'] or '').lower():
                            continue
                        results.append({
                            'id': r['id'], 'type': 'task',
                            'name': r['task'], 'status': r['status'],
                            'started_at': r['started_at'], 'finished_at': r['finished_at'],
                            'created_at': r['created_at'], 'node_id': r['node_id'],
                        })

    # Plan runs
    if exec_type in ('all', 'plan'):
        with db_lock:
            with get_db() as conn:
                rows = conn.execute(
                    'SELECT id, plan_name, status, duration, total_steps, completed_steps, started_at, finished_at, created_at FROM plan_runs ORDER BY created_at DESC LIMIT ?',
                    (limit * 2,)
                ).fetchall()
                for r in rows:
                    if status_filter and r['status'] != status_filter:
                        continue
                    if search and search not in (r['plan_name'] or '').lower():
                        continue
                    results.append({
                        'id': r['id'], 'type': 'plan',
                        'name': r['plan_name'], 'status': r['status'],
                        'duration': r['duration'],
                        'total_steps': r['total_steps'],
                        'completed_steps': r['completed_steps'],
                        'started_at': r['started_at'], 'finished_at': r['finished_at'],
                        'created_at': r['created_at'],
                    })

    # CLI executions
    if exec_type in ('all', 'cli'):
        with db_lock:
            with get_db() as conn:
                rows = conn.execute(
                    'SELECT id, task, exit_code, duration, host, timestamp, created_at FROM executions ORDER BY created_at DESC LIMIT ?',
                    (limit * 2,)
                ).fetchall()
                for r in rows:
                    cli_status = 'success' if r['exit_code'] == 0 else 'failed'
                    if status_filter and cli_status != status_filter:
                        continue
                    if search and search not in (r['task'] or '').lower():
                        continue
                    results.append({
                        'id': 'cli-' + str(r['id']), 'type': 'cli',
                        'name': r['task'], 'status': cli_status,
                        'duration': r['duration'],
                        'host': r['host'],
                        'created_at': r['timestamp'] or r['created_at'],
                    })

    # 按时间倒序
    results.sort(key=lambda x: x.get('created_at') or '', reverse=True)
    return jsonify({'executions': results[:limit]})


# =============================================================================
# API Routes - Dashboard
# =============================================================================

@app.route('/api/v1/dashboard', methods=['GET'])
def api_dashboard():
    """聚合 dashboard 数据"""
    now = datetime.now()
    cutoff_24h = (now - timedelta(hours=24)).isoformat()

    # 活跃运行
    active_runs = []
    for jid, job in jobs.items():
        if job.get('status') in ('running', 'pending'):
            active_runs.append({
                'id': jid, 'type': 'task',
                'name': job.get('task'), 'status': job.get('status'),
                'started_at': job.get('started_at')
            })

    with db_lock:
        with get_db() as conn:
            # 活跃 plan runs
            rows = conn.execute(
                "SELECT id, plan_name, status, total_steps, completed_steps, started_at FROM plan_runs WHERE status IN ('running', 'pending')"
            ).fetchall()
            for r in rows:
                active_runs.append({
                    'id': r['id'], 'type': 'plan',
                    'name': r['plan_name'], 'status': r['status'],
                    'total_steps': r['total_steps'], 'completed_steps': r['completed_steps'],
                    'started_at': r['started_at']
                })

            # 24h 失败
            failed_24h = []
            # jobs
            rows = conn.execute(
                "SELECT id, task, status, finished_at FROM jobs WHERE status IN ('failed', 'error') AND finished_at >= ?",
                (cutoff_24h,)
            ).fetchall()
            for r in rows:
                failed_24h.append({
                    'id': r['id'], 'type': 'task',
                    'name': r['task'], 'status': r['status'],
                    'finished_at': r['finished_at']
                })
            # from memory
            for jid, job in jobs.items():
                if job.get('status') in ('failed', 'error') and (job.get('finished_at') or '') >= cutoff_24h:
                    if not any(f['id'] == jid for f in failed_24h):
                        failed_24h.append({
                            'id': jid, 'type': 'task',
                            'name': job.get('task'), 'status': job.get('status'),
                            'finished_at': job.get('finished_at')
                        })
            # plan runs
            rows = conn.execute(
                "SELECT id, plan_name, status, finished_at FROM plan_runs WHERE status IN ('failed', 'error') AND finished_at >= ?",
                (cutoff_24h,)
            ).fetchall()
            for r in rows:
                failed_24h.append({
                    'id': r['id'], 'type': 'plan',
                    'name': r['plan_name'], 'status': r['status'],
                    'finished_at': r['finished_at']
                })

            # 24h stats
            total_24h = 0
            success_24h = 0
            # From memory jobs
            for job in jobs.values():
                if (job.get('created_at') or '') >= cutoff_24h:
                    total_24h += 1
                    if job.get('status') == 'success':
                        success_24h += 1
            # From DB jobs
            row = conn.execute(
                "SELECT COUNT(*) as c FROM jobs WHERE created_at >= ?", (cutoff_24h,)
            ).fetchone()
            db_total = row['c'] if row else 0
            row = conn.execute(
                "SELECT COUNT(*) as c FROM jobs WHERE status = 'success' AND created_at >= ?", (cutoff_24h,)
            ).fetchone()
            db_success = row['c'] if row else 0

            # CLI
            row = conn.execute(
                "SELECT COUNT(*) as c FROM executions WHERE created_at >= ?", (cutoff_24h,)
            ).fetchone()
            cli_total = row['c'] if row else 0
            row = conn.execute(
                "SELECT COUNT(*) as c FROM executions WHERE exit_code = 0 AND created_at >= ?", (cutoff_24h,)
            ).fetchone()
            cli_success = row['c'] if row else 0

            # Plan runs
            row = conn.execute(
                "SELECT COUNT(*) as c FROM plan_runs WHERE created_at >= ?", (cutoff_24h,)
            ).fetchone()
            plan_total = row['c'] if row else 0
            row = conn.execute(
                "SELECT COUNT(*) as c FROM plan_runs WHERE status = 'success' AND created_at >= ?", (cutoff_24h,)
            ).fetchone()
            plan_success = row['c'] if row else 0

    total = total_24h + db_total + cli_total + plan_total
    success = success_24h + db_success + cli_success + plan_success
    success_rate = round(success / total * 100, 1) if total > 0 else 0

    # 节点摘要
    online_nodes = sum(1 for n in nodes.values() if n.get('status') == 'online')
    total_nodes = len(nodes)

    return jsonify({
        'active_runs': active_runs,
        'failed_24h': failed_24h,
        'stats_24h': {
            'total': total,
            'success': success,
            'failed': len(failed_24h),
            'success_rate': success_rate
        },
        'nodes_summary': {
            'online': online_nodes,
            'total': total_nodes
        }
    })


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
def api_cli_executions():
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
    """返回树形任务结构 (PyYAML 解析, mtime 缓存)"""
    try:
        with _tree_cache_lock:
            if _is_cache_valid():
                return jsonify({'tree': _tree_cache['result']})

        tasks_flat = []

        # 1. 读 Taskfile.yml 获取行内任务
        taskfile = os.path.join(EZ_ROOT, 'Taskfile.yml')
        if os.path.isfile(taskfile):
            data = _load_yaml_file(taskfile)
            tasks_map = data.get('tasks') or {}

            for name, task_def in tasks_map.items():
                if not isinstance(task_def, dict):
                    task_def = {}
                desc = task_def.get('desc', '')
                ez_params = task_def.get('ez-params') or []
                has_params = len(ez_params) > 0
                tasks_flat.append({
                    'name': name, 'desc': desc, 'type': 'inline',
                    'has_params': has_params
                })

            # 处理 includes 命名空间
            includes = data.get('includes') or {}
            for ns, inc_val in includes.items():
                inc_path = inc_val if isinstance(inc_val, str) else (inc_val or {}).get('taskfile', '')
                inc_file = os.path.join(EZ_ROOT, inc_path) if inc_path else None
                children = []

                if inc_file and os.path.isfile(inc_file):
                    inc_data = _load_yaml_file(inc_file)
                    inc_tasks = inc_data.get('tasks') or {}
                    for child_name, child_def in inc_tasks.items():
                        if not isinstance(child_def, dict):
                            child_def = {}
                        children.append({
                            'name': f'{ns}:{child_name}',
                            'desc': child_def.get('desc', ''),
                            'type': 'inline', 'has_params': False
                        })

                    # 子 includes (2 层深度)
                    sub_includes = inc_data.get('includes') or {}
                    for sub_ns, sub_val in sub_includes.items():
                        sub_path = sub_val if isinstance(sub_val, str) else (sub_val or {}).get('taskfile', '')
                        sub_file = os.path.join(os.path.dirname(inc_file), sub_path) if sub_path else None
                        if sub_file and os.path.isfile(sub_file):
                            sub_data = _load_yaml_file(sub_file)
                            sub_tasks = sub_data.get('tasks') or {}
                            for sc_name, sc_def in sub_tasks.items():
                                if not isinstance(sc_def, dict):
                                    sc_def = {}
                                children.append({
                                    'name': f'{ns}:{sc_name}',
                                    'desc': sc_def.get('desc', ''),
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
                    meta = os.path.join(entry_path, 'task.yml')
                    if os.path.isfile(meta):
                        meta_data = _load_yaml_file(meta)
                        desc = meta_data.get('desc', '')
                        params = meta_data.get('params') or []
                        has_params = len(params) > 0

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
                    tool_data = _load_yaml_file(tool_path)
                    tool_name = tool_data.get('name', '')
                    tool_desc = tool_data.get('desc', '')
                    if tool_name:
                        tasks_flat.append({
                            'name': tool_name, 'desc': tool_desc, 'type': 'tool',
                            'has_params': False
                        })

        # 更新缓存
        with _tree_cache_lock:
            _tree_cache['result'] = tasks_flat
            _tree_cache['mtimes'] = _get_file_mtimes()

        return jsonify({'tree': tasks_flat})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/tasks/<task_name>/params', methods=['GET'])
def api_task_params(task_name):
    """获取任务参数定义 (结构化 JSON, PyYAML)"""
    try:
        params = []
        desc = ''

        # 目录任务: 读 task.yml
        task_meta = os.path.join(EZ_ROOT, 'tasks', task_name, 'task.yml')
        if os.path.isfile(task_meta):
            meta_data = _load_yaml_file(task_meta)
            desc = meta_data.get('desc', '')
            params = meta_data.get('params') or []

        # 行内任务: 读 Taskfile.yml 的 ez-params
        if not params:
            taskfile = os.path.join(EZ_ROOT, 'Taskfile.yml')
            actual_task = task_name
            actual_file = taskfile
            if ':' in task_name:
                ns, sub = task_name.split(':', 1)
                if os.path.isfile(taskfile):
                    tf_data = _load_yaml_file(taskfile)
                    inc_val = (tf_data.get('includes') or {}).get(ns, '')
                    inc_path = inc_val if isinstance(inc_val, str) else (inc_val or {}).get('taskfile', '')
                    if inc_path:
                        actual_file = os.path.join(EZ_ROOT, inc_path)
                actual_task = sub

            if os.path.isfile(actual_file):
                file_data = _load_yaml_file(actual_file)
                task_def = (file_data.get('tasks') or {}).get(actual_task) or {}
                if isinstance(task_def, dict):
                    desc = task_def.get('desc', '') or desc
                    params = task_def.get('ez-params') or []

        # 工具任务: 读 lib/tools/<name>.yml
        tool_file = os.path.join(EZ_ROOT, 'lib', 'tools', f'{task_name}.yml')
        if not params and os.path.isfile(tool_file):
            tool_data = _load_yaml_file(tool_file)
            desc = tool_data.get('desc', '') or desc

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

        # 行内任务: 用 PyYAML 提取对应 task 片段
        taskfile = os.path.join(EZ_ROOT, 'Taskfile.yml')
        actual_task = task_name
        actual_file = taskfile
        if ':' in task_name:
            ns, sub = task_name.split(':', 1)
            if os.path.isfile(taskfile):
                tf_data = _load_yaml_file(taskfile)
                inc_val = (tf_data.get('includes') or {}).get(ns, '')
                inc_path = inc_val if isinstance(inc_val, str) else (inc_val or {}).get('taskfile', '')
                if inc_path:
                    actual_file = os.path.join(EZ_ROOT, inc_path)
            actual_task = sub

        if os.path.isfile(actual_file):
            file_data = _load_yaml_file(actual_file)
            task_def = (file_data.get('tasks') or {}).get(actual_task)
            if task_def is not None:
                yaml_str = yaml.dump({actual_task: task_def}, default_flow_style=False, allow_unicode=True)
                rel_path = os.path.relpath(actual_file, EZ_ROOT)
                return jsonify({'yaml': yaml_str, 'file': rel_path, 'task_key': actual_task, 'type': 'inline'})

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

        _invalidate_cache()
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

        _invalidate_cache()
        return jsonify({'ok': True, 'file': os.path.relpath(plan_file, EZ_ROOT)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# =============================================================================
# API Routes - Plans
# =============================================================================

@app.route('/api/v1/plans', methods=['GET', 'POST'])
def api_plans():
    """GET: 列出所有计划; POST: 创建计划"""
    if request.method == 'POST':
        return _api_create_plan()
    return _api_list_plans()


def _api_list_plans():
    """列出所有计划 (PyYAML)"""
    plans = []
    plans_dir = os.path.join(EZ_ROOT, 'plans')
    if os.path.isdir(plans_dir):
        for f in os.listdir(plans_dir):
            if f.endswith('.yml') or f.endswith('.yaml'):
                name = os.path.splitext(f)[0]
                desc = ''
                step_count = 0
                try:
                    plan_data = _load_yaml_file(os.path.join(plans_dir, f))
                    desc = plan_data.get('name', '') or plan_data.get('desc', '')
                    step_count = len(plan_data.get('steps') or [])
                except Exception:
                    pass

                # 最近执行
                last_run = None
                with db_lock:
                    with get_db() as conn:
                        row = conn.execute(
                            'SELECT id, status, finished_at FROM plan_runs WHERE plan_name = ? ORDER BY created_at DESC LIMIT 1',
                            (name,)
                        ).fetchone()
                        if row:
                            last_run = {'id': row['id'], 'status': row['status'], 'finished_at': row['finished_at']}

                plans.append({
                    'name': name, 'file': f, 'desc': desc,
                    'step_count': step_count, 'last_run': last_run
                })

    return jsonify({'plans': plans})


def _api_create_plan():
    """创建计划"""
    data = request.json or {}
    name = data.get('name', '').strip()
    desc = data.get('desc', '')
    steps = data.get('steps', [])

    if not name:
        return jsonify({'error': 'name required'}), 400
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return jsonify({'error': 'name 只允许字母、数字、下划线和连字符'}), 400

    plans_dir = os.path.join(EZ_ROOT, 'plans')
    os.makedirs(plans_dir, exist_ok=True)
    plan_file = os.path.join(plans_dir, f'{name}.yml')

    if os.path.isfile(plan_file):
        return jsonify({'error': f'Plan "{name}" already exists'}), 409

    plan_data = {
        'name': name,
        'desc': desc,
        'steps': steps or [{'name': 'step1', 'task': 'default'}]
    }
    yaml_content = yaml.dump(plan_data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    with open(plan_file, 'w', encoding='utf-8') as f:
        f.write(yaml_content)

    return jsonify({'ok': True, 'name': name, 'file': f'plans/{name}.yml'})


@app.route('/api/v1/plans/<plan_name>', methods=['GET', 'DELETE'])
def api_get_or_delete_plan(plan_name):
    """GET: 获取计划详情; DELETE: 删除计划"""
    if request.method == 'DELETE':
        return _api_delete_plan(plan_name)
    return _api_get_plan(plan_name)


def _api_get_plan(plan_name):
    """获取计划详情 (PyYAML)"""
    try:
        plan_file = os.path.join(EZ_ROOT, 'plans', f'{plan_name}.yml')
        if not os.path.isfile(plan_file):
            plan_file = os.path.join(EZ_ROOT, 'plans', f'{plan_name}.yaml')
        if not os.path.isfile(plan_file):
            return jsonify({'error': f'Plan not found: {plan_name}'}), 404

        with open(plan_file, 'r', encoding='utf-8') as f:
            yaml_content = f.read()

        plan_data = yaml.safe_load(yaml_content) or {}

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


def _api_delete_plan(plan_name):
    """删除计划"""
    plan_file = os.path.join(EZ_ROOT, 'plans', f'{plan_name}.yml')
    if not os.path.isfile(plan_file):
        plan_file = os.path.join(EZ_ROOT, 'plans', f'{plan_name}.yaml')
    if not os.path.isfile(plan_file):
        return jsonify({'error': f'Plan "{plan_name}" not found'}), 404

    os.remove(plan_file)
    return jsonify({'ok': True, 'deleted': plan_name})


@app.route('/api/v1/plans/<plan_name>/run', methods=['POST'])
def api_run_plan(plan_name):
    """执行计划 — 逐步骤执行"""
    data = request.json or {}
    task_vars = data.get('vars', {})
    trigger_type = data.get('trigger_type', 'manual')

    # 加载 plan
    plan_file = os.path.join(EZ_ROOT, 'plans', f'{plan_name}.yml')
    if not os.path.isfile(plan_file):
        plan_file = os.path.join(EZ_ROOT, 'plans', f'{plan_name}.yaml')
    if not os.path.isfile(plan_file):
        return jsonify({'error': f'Plan not found: {plan_name}'}), 404

    plan_data = _load_yaml_file(plan_file)
    steps = plan_data.get('steps', [])
    if not steps:
        return jsonify({'error': 'Plan has no steps'}), 400

    run_id = str(uuid.uuid4())[:8]

    # 记录到数据库
    with db_lock:
        with get_db() as conn:
            conn.execute(
                '''INSERT INTO plan_runs (id, plan_name, status, params, trigger_type, total_steps, started_at)
                   VALUES (?, ?, 'running', ?, ?, ?, ?)''',
                (run_id, plan_name, json.dumps(task_vars), trigger_type, len(steps), datetime.now().isoformat())
            )
            # 插入每个步骤
            for step in steps:
                conn.execute(
                    '''INSERT INTO plan_run_steps (run_id, step_name, task_name, status)
                       VALUES (?, ?, ?, 'pending')''',
                    (run_id, step.get('name', ''), step.get('task', ''))
                )
            conn.commit()

    socketio.emit('plan_update', {'run_id': run_id, 'plan_name': plan_name, 'status': 'running'})

    # 在后台线程逐步骤执行
    Thread(target=_run_plan_steps, args=(run_id, plan_name, steps, task_vars), daemon=True).start()
    return jsonify({'run_id': run_id, 'status': 'running'})


def _run_plan_steps(run_id, plan_name, steps, global_vars):
    """逐步骤执行 plan (拓扑排序)"""
    task_bin = _get_task_bin()
    step_map = {s.get('name', ''): s for s in steps}

    # 拓扑排序
    completed = set()
    failed_steps = set()
    start_time = datetime.now()

    def can_run(step):
        needs = step.get('needs') or []
        for dep in needs:
            if dep in failed_steps:
                return 'skip'
            if dep not in completed:
                return 'wait'
        return 'ready'

    remaining = [s.get('name', '') for s in steps]
    completed_count = 0

    while remaining:
        progressed = False
        for step_name in list(remaining):
            step = step_map.get(step_name)
            if not step:
                remaining.remove(step_name)
                continue

            status = can_run(step)
            if status == 'skip':
                # 依赖失败, 跳过
                remaining.remove(step_name)
                _update_step(run_id, step_name, 'skipped')
                socketio.emit('plan_step_update', {
                    'run_id': run_id, 'step_name': step_name, 'status': 'skipped'
                })
                progressed = True
            elif status == 'ready':
                remaining.remove(step_name)
                progressed = True

                # 执行该步骤
                _update_step(run_id, step_name, 'running', started_at=datetime.now().isoformat())
                socketio.emit('plan_step_update', {
                    'run_id': run_id, 'step_name': step_name, 'status': 'running'
                })

                task_name = step.get('task', '')
                step_vars = dict(global_vars)
                step_vars.update(step.get('vars') or {})

                cmd = [task_bin, '-t', os.path.join(EZ_ROOT, 'Taskfile.yml'), task_name]
                env = os.environ.copy()
                for k, v in step_vars.items():
                    env[str(k)] = str(v)

                step_start = datetime.now()
                try:
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=3600,
                        env=env, cwd=EZ_ROOT
                    )
                    step_end = datetime.now()
                    duration = (step_end - step_start).total_seconds()
                    logs = result.stdout + result.stderr
                    exit_code = result.returncode
                    step_status = 'success' if exit_code == 0 else 'failed'
                except subprocess.TimeoutExpired:
                    step_end = datetime.now()
                    duration = (step_end - step_start).total_seconds()
                    logs = 'Step timed out'
                    exit_code = -1
                    step_status = 'failed'
                except Exception as e:
                    step_end = datetime.now()
                    duration = (step_end - step_start).total_seconds()
                    logs = str(e)
                    exit_code = -1
                    step_status = 'failed'

                _update_step(run_id, step_name, step_status,
                             exit_code=exit_code, logs=logs, duration=duration,
                             finished_at=step_end.isoformat())

                if step_status == 'success':
                    completed.add(step_name)
                else:
                    failed_steps.add(step_name)

                completed_count += 1
                # 更新 plan_runs completed_steps
                with db_lock:
                    with get_db() as conn:
                        conn.execute(
                            'UPDATE plan_runs SET completed_steps = ? WHERE id = ?',
                            (completed_count, run_id)
                        )
                        conn.commit()

                socketio.emit('plan_step_update', {
                    'run_id': run_id, 'step_name': step_name,
                    'status': step_status, 'exit_code': exit_code, 'duration': duration
                })

        if not progressed:
            # 死锁或所有剩余都在等待
            for step_name in remaining:
                _update_step(run_id, step_name, 'skipped')
            break

        time.sleep(0.1)

    # 完成 plan run
    end_time = datetime.now()
    total_duration = (end_time - start_time).total_seconds()
    final_status = 'success' if not failed_steps else 'failed'

    with db_lock:
        with get_db() as conn:
            conn.execute(
                '''UPDATE plan_runs SET status=?, finished_at=?, duration=?, completed_steps=?
                   WHERE id=?''',
                (final_status, end_time.isoformat(), total_duration, completed_count, run_id)
            )
            conn.commit()

    socketio.emit('plan_update', {'run_id': run_id, 'plan_name': plan_name, 'status': final_status})


def _update_step(run_id, step_name, status, **kwargs):
    """更新步骤状态"""
    with db_lock:
        with get_db() as conn:
            sets = ['status = ?']
            vals = [status]
            for k, v in kwargs.items():
                sets.append(f'{k} = ?')
                vals.append(v)
            vals.extend([run_id, step_name])
            conn.execute(
                f'UPDATE plan_run_steps SET {", ".join(sets)} WHERE run_id = ? AND step_name = ?',
                vals
            )
            conn.commit()


@app.route('/api/v1/plans/<plan_name>/hook', methods=['POST'])
def api_plan_webhook(plan_name):
    """Webhook 触发执行"""
    data = request.json or {}
    data['trigger_type'] = 'webhook'
    # 复用 run plan
    with app.test_request_context(
        f'/api/v1/plans/{plan_name}/run',
        method='POST',
        json=data,
        content_type='application/json'
    ):
        return api_run_plan(plan_name)


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
    Thread(target=_execute_job_local, args=(job_id,), daemon=True).start()
    return jsonify({'job_id': job_id, 'status': 'running'})


@app.route('/api/v1/plans/runs', methods=['GET'])
def api_list_plan_runs():
    """获取计划执行历史"""
    limit = request.args.get('limit', 20, type=int)
    plan_name = request.args.get('plan', '')
    with db_lock:
        with get_db() as conn:
            if plan_name:
                rows = conn.execute(
                    'SELECT * FROM plan_runs WHERE plan_name = ? ORDER BY created_at DESC LIMIT ?',
                    (plan_name, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    'SELECT * FROM plan_runs ORDER BY created_at DESC LIMIT ?', (limit,)
                ).fetchall()
    return jsonify({'runs': [dict(r) for r in rows]})


@app.route('/api/v1/plans/runs/<run_id>', methods=['GET'])
def api_get_plan_run(run_id):
    """获取单次计划执行状态 + 步骤详情"""
    with db_lock:
        with get_db() as conn:
            row = conn.execute('SELECT * FROM plan_runs WHERE id = ?', (run_id,)).fetchone()
            if not row:
                return jsonify({'error': 'not found'}), 404

            steps = conn.execute(
                'SELECT * FROM plan_run_steps WHERE run_id = ? ORDER BY id ASC',
                (run_id,)
            ).fetchall()

    result = dict(row)
    result['steps'] = [dict(s) for s in steps]
    return jsonify(result)


@app.route('/api/v1/plans/runs/<run_id>/steps/<step_name>/logs', methods=['GET'])
def api_step_logs(run_id, step_name):
    """获取单步日志"""
    with db_lock:
        with get_db() as conn:
            row = conn.execute(
                'SELECT logs, status FROM plan_run_steps WHERE run_id = ? AND step_name = ?',
                (run_id, step_name)
            ).fetchone()
    if not row:
        return jsonify({'error': 'Step not found'}), 404
    return jsonify({'logs': row['logs'] or '', 'status': row['status']})


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
# API Routes - Cache Management
# =============================================================================

@app.route('/api/v1/cache/clear', methods=['POST'])
def api_clear_cache():
    """手动清除缓存"""
    _invalidate_cache()
    return jsonify({'status': 'ok'})


# =============================================================================
# API Routes - File Browser (目录任务)
# =============================================================================

@app.route('/api/v1/tasks/<task_name>/files', methods=['GET'])
def api_task_files(task_name):
    """列出目录任务的文件列表"""
    try:
        task_dir = os.path.join(EZ_ROOT, 'tasks', task_name)
        if not os.path.isdir(task_dir):
            return jsonify({'error': 'Task directory not found'}), 404

        files = []
        for root, dirs, filenames in os.walk(task_dir):
            # 跳过隐藏目录和 workspace
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'workspace']
            for fname in sorted(filenames):
                if fname.startswith('.'):
                    continue
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, task_dir)
                try:
                    size = os.path.getsize(full_path)
                except OSError:
                    size = 0
                files.append({
                    'path': rel_path,
                    'name': fname,
                    'size': size
                })

        return jsonify({'task': task_name, 'files': files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/tasks/<task_name>/files/<path:file_path>', methods=['GET'])
def api_task_file_content(task_name, file_path):
    """读取目录任务中的单个文件内容"""
    try:
        task_dir = os.path.join(EZ_ROOT, 'tasks', task_name)
        if not os.path.isdir(task_dir):
            return jsonify({'error': 'Task directory not found'}), 404

        # 安全: 防目录穿越
        full_path = os.path.normpath(os.path.join(task_dir, file_path))
        if not full_path.startswith(os.path.normpath(task_dir) + os.sep) and full_path != os.path.normpath(task_dir):
            return jsonify({'error': 'Access denied'}), 403

        if not os.path.isfile(full_path):
            return jsonify({'error': 'File not found'}), 404

        # 限制文件大小 (1MB)
        size = os.path.getsize(full_path)
        if size > 1024 * 1024:
            return jsonify({'error': 'File too large (>1MB)'}), 413

        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        return jsonify({
            'path': file_path,
            'content': content,
            'size': size
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# API Routes - Task to Plan Conversion
# =============================================================================

@app.route('/api/v1/tasks/<task_name>/to-plan', methods=['POST'])
def api_task_to_plan(task_name):
    """将任务转换为单步 Plan"""
    try:
        data = request.json or {}
        plan_name = data.get('plan_name', '').strip()
        task_vars = data.get('vars', {})
        overwrite = data.get('overwrite', False)

        if not plan_name:
            return jsonify({'error': 'plan_name required'}), 400

        # 安全: 只允许合法文件名
        if not re.match(r'^[a-zA-Z0-9_-]+$', plan_name):
            return jsonify({'error': 'plan_name 只允许字母、数字、下划线和连字符'}), 400

        plans_dir = os.path.join(EZ_ROOT, 'plans')
        os.makedirs(plans_dir, exist_ok=True)
        plan_file = os.path.join(plans_dir, f'{plan_name}.yml')

        if os.path.isfile(plan_file) and not overwrite:
            return jsonify({'error': f'Plan "{plan_name}" already exists'}), 409

        # 构造 Plan YAML
        plan_data = {
            'name': plan_name,
            'desc': f'从任务 {task_name} 创建',
            'steps': [{
                'name': task_name.replace(':', '-'),
                'task': task_name,
            }]
        }

        if task_vars:
            plan_data['steps'][0]['vars'] = task_vars

        yaml_content = yaml.dump(plan_data, default_flow_style=False, allow_unicode=True, sort_keys=False)

        with open(plan_file, 'w', encoding='utf-8') as f:
            f.write(yaml_content)

        return jsonify({
            'ok': True,
            'plan_name': plan_name,
            'file': f'plans/{plan_name}.yml'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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
