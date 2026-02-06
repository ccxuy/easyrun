# 日志系统

任务执行日志自动记录到 `.ez/skills/<name>/logs/` 或 `.ez/plans/<name>/logs/`。

## 启用日志

```bash
# Plan 执行自动记录日志
ez plan run kernel-ci --log

# 输出:
# Plan: kernel-ci
# Run ID: 20260206-012610-362445
# [1/3] 配置
#   Log: .ez/plans/kernel-ci/logs/20260206-012610_kernel-config.log
```

## 日志命令

```bash
ez log list              # 列出最近日志
ez log show <pattern>    # 显示日志内容
ez log clean [days]      # 清理旧日志 (默认 7 天)
```

## 日志格式

```
================================================================================
EZ Task Execution Log
================================================================================
Task:      kernel-config
Plan:      kernel-ci
Step:      配置
Timestamp: 2026-02-06T01:26:10+08:00
Host:      build-server
User:      ci
================================================================================

Command: task -t ./Taskfile.yml kernel-config ...
[实际输出...]

================================================================================
Exit Code: 0
Duration:  3s
================================================================================
```

## 自定义日志路径 (ez-log)

每个任务可指定自己的日志目录和文件前缀:

```yaml
tasks:
  kernel-build:
    desc: "构建内核"
    cmds:
      - make -j$EZ_JOBS
    ez-log:
      dir: "logs/kernel-build"
      prefix: "build"
```

日志文件将保存到 `logs/kernel-build/YYYYMMDD-HHMMSS_build_<run_id>.log`
