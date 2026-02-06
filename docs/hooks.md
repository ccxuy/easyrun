# ez-hooks 钩子系统

在任务执行前后运行脚本。

## 定义

```yaml
tasks:
  build:
    desc: "构建项目"
    cmds:
      - make build

    ez-hooks:
      pre_run:
        - name: "check-env"
          script: 'echo "Checking..."'
      post_run:
        - name: "notify"
          script: 'echo "Task $EZ_TASK_NAME completed!"'
      on_error:
        - name: "alert"
          script: 'echo "Failed with code $EZ_TASK_EXIT_CODE"'
```

## 钩子类型

| 类型 | 触发时机 |
|------|----------|
| `pre_run` | 任务执行前 |
| `post_run` | 任务成功后 |
| `on_error` | 任务失败后 |

## 上下文变量

| 变量 | 说明 |
|------|------|
| `$EZ_TASK_NAME` | 任务名称 |
| `$EZ_TASK_EXIT_CODE` | 任务退出码 |
| `$EZ_TASK_OUTPUT` | 任务输出内容 |
