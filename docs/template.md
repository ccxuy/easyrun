# 模板系统

使用模板快速生成任务定义。支持 Go template 和 ytt 两种模板引擎。

## 查看可用模板

```bash
ez template list
```

## 使用模板

```bash
ez template use kernel-build --name=linux --arch=arm64
```

## 自定义模板

创建 `templates/my-template.yml`:

```yaml
name: my-template
desc: "我的模板"
version: "1.0"

params:
  - name: "name"
    desc: "项目名称"
    default: "myproject"

template: |
  {{.name}}-task:
    desc: "任务 ({{.name}})"
    cmds:
      - echo "Hello from {{.name}}"
```

## ytt 复杂模板

支持 [ytt](https://carvel.dev/ytt/) 进行复杂模板生成:

```yaml
#@ load("@ytt:data", "data")

#@ for arch in data.values.arches.split(","):
(@= data.values.name @)-build-(@= arch @):
  desc: "构建内核 ((@= arch @))"
  cmds:
    - make ARCH=(@= arch @) -j$(nproc)
#@ end
```

```bash
ez template use kernel-matrix --name=linux --arches=x86_64,arm64,riscv
```
