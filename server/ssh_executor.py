"""SSH 远程执行模块"""

import paramiko


def test_ssh_connection(host, port, user, auth_type, password=None, key_path=None):
    """测试 SSH 连接, 返回 (ok: bool, msg: str)"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        kwargs = {'hostname': host, 'port': int(port), 'username': user, 'timeout': 10}
        if auth_type == 'key':
            kwargs['key_filename'] = key_path
        else:
            kwargs['password'] = password
        client.connect(**kwargs)
        client.close()
        return True, 'OK'
    except Exception as e:
        return False, str(e)
    finally:
        client.close()


def execute_via_ssh(host, port, user, auth_type, task_cmd,
                    password=None, key_path=None, timeout=3600):
    """SSH 远程执行命令, 返回 (exit_code, logs)"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        kwargs = {'hostname': host, 'port': int(port), 'username': user, 'timeout': 10}
        if auth_type == 'key':
            kwargs['key_filename'] = key_path
        else:
            kwargs['password'] = password
        client.connect(**kwargs)

        stdin, stdout, stderr = client.exec_command(task_cmd, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        logs = stdout.read().decode('utf-8', errors='replace') + stderr.read().decode('utf-8', errors='replace')
        return exit_code, logs
    except Exception as e:
        return -1, str(e)
    finally:
        client.close()
