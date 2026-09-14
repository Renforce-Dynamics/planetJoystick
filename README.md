# planetJoystick

读取 Linux 手柄，发送 operator 请求、摇杆输入和连续上肢关节目标。

## 安装与启动

需要 Linux、Python 3.10+、`uv`。

```bash
git clone --recurse-submodules git@github.com:Renforce-Dynamics/planetJoystick.git
cd planetJoystick
./scripts/bootstrap.sh

./scripts/run.sh -- --config pkg://planetj/data/operator.yaml
```

默认读取 `/dev/input/js0`，发送到 `127.0.0.1:50560`；持续运行，Ctrl+C 退出。
`operator.yaml` 包含 passive、damping、fixedpos、loco 请求。
只发送摇杆和安全信号时，选择 `pkg://planetj/data/xbox.yaml`。

## 配置接收端和按键

新建 `operator-site.yaml`：

```yaml
extends: pkg://planetj/data/operator.yaml
device: /dev/input/js0
target:
  host: 192.168.1.100
  port: 50560
inputs:
  requests:
    loco:
      buttons: [5, 2]
```

```bash
./scripts/run.sh -- --config ./operator-site.yaml
```

按实际部署修改地址。请求按名称逐项继承，`null` 禁用继承项；
状态 ID 和名称由接收端解释。接收端启动后，可用
`.venv/bin/planetj --config ./operator-site.yaml --check-remote` 检查配对。

## 连续上肢目标

```bash
./scripts/upper-stream.sh -- --config pkg://planetj/data/upper_stream.yaml
```

目标角度单位为 rad。配置决定关节顺序、轴映射、角度范围和发送频率。
默认采集实体手柄；断开后停止发送，目标保持与动作执行由接收端负责。

## 文档与开发

- [配置和键位继承](docs/configuration.md)
- [上肢发送示例](examples/upper_stream/README.md)

依赖 [planetConfig](https://github.com/Renforce-Dynamics/planetConfig) 的配置和协议包，
不依赖 Cadence 或 SDK。

开发：`./scripts/test.sh` 运行测试，`./scripts/build.sh` 构建安装包。

工具支持 `--venv /path/to/env`。由 **Renforce Dynamics** 开发维护，采用 [MIT License](LICENSE)。
