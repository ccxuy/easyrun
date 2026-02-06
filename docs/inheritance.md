# 继承与组合

## ez-extends 任务继承

通过 `ez-extends` 继承基础任务的参数和命令，用 `ez-defaults` 覆盖默认参数值。

```yaml
tasks:
  _base-build:
    desc: "基础构建任务"
    cmds:
      - 'echo "Building for {{.EZ_ARCH}} in {{.EZ_MODE}} mode"'
    ez-params:
      - name: "arch"
        type: "select"
        options: ["x86_64", "arm64", "riscv"]
        default: "x86_64"
      - name: "mode"
        type: "select"
        options: ["debug", "release"]
        default: "release"

  kernel-build-debug:
    desc: "内核调试构建"
    ez-extends: "_base-build"
    ez-defaults:
      EZ_MODE: "debug"

  kernel-build-arm:
    desc: "ARM 内核构建"
    ez-extends: "_base-build"
    ez-defaults:
      EZ_ARCH: "arm64"
```

运行继承任务时使用基础任务的命令，但应用覆盖后的默认值:

```bash
./ez kernel-build-debug     # mode=debug
./ez kernel-build-arm       # arch=arm64
```

## ez-compose 任务组合

将多个任务组合为一个，按顺序执行:

```yaml
tasks:
  kernel-ci:
    desc: "完整内核 CI"
    ez-compose:
      - task: "kernel-config"
      - task: "kernel-build"
        defaults:
          EZ_JOBS: "8"
      - task: "kernel-test"
        defaults:
          EZ_SUITE: "smoke"
    ez-defaults:
      EZ_ARCH: "x86_64"    # 全局默认值，所有子任务共享
```

```bash
$ ./ez kernel-ci
========================================
Composed Task: kernel-ci (3 tasks)
========================================
[1/3] kernel-config
...
[2/3] kernel-build
...
[3/3] kernel-test
...
========================================
```

## 变量优先级

组合任务中的变量优先级（低到高）:
1. `ez-defaults` (任务级全局默认)
2. 步骤 `defaults` (每步独立默认)
3. 命令行预设 (用户指定)
