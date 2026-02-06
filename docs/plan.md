# Plan 计划编排

Plan 是多 Task 的编排单元，定义执行顺序、依赖和产物传递。Plan 编译为标准 go-task Taskfile 后由 go-task 引擎执行。

## Plan 文件格式

Plans 存放在 `plans/` 目录:

```yaml
# plans/kernel-ci.yml
name: kernel-ci
desc: "内核 CI 流水线"
steps:
  - name: config
    task: kernel-config

  - name: build
    task: kernel-build
    needs: [config]
    artifacts:
      - name: vmlinux
        path: build/vmlinux

  - name: test
    task: kernel-test
    needs: [build]
    inputs:
      - from: build
        artifact: vmlinux
        to: ./vmlinux

  - name: package
    task: kernel-package
    needs: [build, test]
```

## 工作流

```bash
# 创建 Plan
ez plan new kernel-ci --desc "内核 CI"

# 添加步骤
ez plan add kernel-ci kernel-config --name config
ez plan add kernel-ci kernel-build --name build --needs config
ez plan add kernel-ci kernel-test --name test --needs build

# 编译为 Taskfile
ez plan build kernel-ci
# → .ez/plans/kernel-ci/build/Taskfile.yml

# 验证依赖完备性
ez plan check kernel-ci

# 编译 + 验证 + 执行
ez plan run kernel-ci
# 或简写
ez plan kernel-ci
```

## 编译流程

`ez plan build <name>` 执行以下步骤:
1. 解析 steps + matrix 展开
2. 拓扑排序（检查 needs 依赖，检测循环）
3. 生成 `Taskfile.yml` 到 `.ez/plans/<name>/build/`

编译输出是标准 go-task Taskfile，可直接用 `task -d .ez/plans/<name>/build/` 执行。

## 依赖验证

`ez plan check <name>` 验证:
- 所有 `step.task` 在 Taskfile 或 tasks/ 中存在
- `needs` 引用的 step 存在且无循环依赖
- `inputs` 引用的 artifact 在上游 step 有定义
- DAG 拓扑排序可行

## 旧格式 (.ez-plan.yml)

v1.2 之前的 Plan 使用 `.ez-plan.yml` 格式，支持 matrix、checkpoint、when 等:

```yaml
plans:
  deploy:
    desc: "部署流程"
    steps:
      - name: "构建"
        task: "build"

      - name: "确认"
        checkpoint: true
        prompt: "是否继续部署到生产环境？"

      - name: "部署"
        task: "deploy-prod"
        when: "$CONFIRMED == 'yes'"
```

支持的 Plan 特性:
- **matrix**: 矩阵组合执行
- **checkpoint**: 断点暂停，交互确认
- **when**: 条件分支
- **resume**: 恢复中断的计划

## 命令参考

| 命令 | 说明 |
|------|------|
| `ez plan list` | 列出所有计划 |
| `ez plan new <name>` | 创建 Plan |
| `ez plan add <name> <task>` | 添加步骤 (--name, --needs) |
| `ez plan show <name>` | 查看 Plan 结构 |
| `ez plan build <name>` | 编译为 Taskfile |
| `ez plan check <name>` | 验证依赖完备性 |
| `ez plan run <name>` | 编译 + 执行 |
| `ez plan <name>` | 等价于 `ez plan run <name>` |
