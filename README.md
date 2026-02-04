# EZ - go-task 智能前端

EZ 是 [go-task](https://github.com/go-task/task) 的智能前端，专注于改善用户体验和团队协作。

## 特性

- **交互式参数** - 通过菜单选择参数，无需记忆命令行选项
- **参数预设** - 支持 `EZ_VAR=value` 跳过交互
- **100% 兼容** - 所有 `ez-*` 扩展字段可被 go-task 安全忽略

## 快速开始

```bash
# 1. 安装依赖 (下载 yq 和 task 到 dep/)
./dep/install-deps.sh

# 2. 查看可用任务
./ez list

# 3. 查看任务详情
./ez show build

# 4. 运行任务 (交互式)
./ez run build

# 5. 运行任务 (预设参数)
./ez run build EZ_ARCH=aarch64
```

## 命令

| 命令 | 说明 |
|------|------|
| `ez list` | 列出所有任务 |
| `ez show <task>` | 显示任务详情和参数 |
| `ez run <task>` | 运行任务（交互式参数） |
| `ez run <task> --dry-run` | 只显示命令，不执行 |
| `ez version` | 显示版本信息 |
| `ez help` | 显示帮助 |

## ez-params 参数定义

在 Taskfile.yml 中使用 `ez-params` 定义交互式参数：

```yaml
tasks:
  build:
    desc: "构建项目"
    cmds:
      - echo "Building for {{.EZ_ARCH}}"

    ez-params:
      - name: "arch"
        type: "select"
        options: ["x86_64", "aarch64", "riscv64"]
        default: "x86_64"
        help: "目标架构"
```

### 参数类型

| 类型 | 说明 |
|------|------|
| `input` | 文本输入 |
| `select` | 从选项列表选择 |

## 测试

```bash
./dep/task test        # 运行所有测试
./dep/task test:quick  # 快速测试
```

## 项目结构

```
easyrun/
├── ez                    # 主入口脚本
├── lib/ez-core.sh        # 核心函数库
├── dep/
│   ├── install-deps.sh   # 依赖安装脚本
│   ├── task              # go-task 二进制
│   └── yq                # yq 二进制
├── task/selftest/        # 自测试套件
├── Taskfile.yml          # 示例任务
├── DESIGN.md             # 设计规格
└── PLAN.md               # 实现计划
```

## 版本历史

- **v0.2.0** - 交互式参数支持 (input/select 类型)
- **v0.1.5** - run 命令基础执行
- **v0.1.4** - show 命令
- **v0.1.3** - list 命令
- **v0.1.0** - 依赖安装脚本

## 依赖

- [go-task](https://github.com/go-task/task) - 任务执行引擎
- [yq](https://github.com/mikefarah/yq) - YAML 处理器

## License

MIT
