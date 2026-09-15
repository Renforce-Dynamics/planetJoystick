# planetJoystick

读取 Linux 手柄，发送 operator 请求、摇杆输入和连续上肢关节目标。

## 安装与启动

需要 Linux、Python 3.10+、`uv`。

```bash
git clone --recurse-submodules git@github.com:Renforce-Dynamics/planetJoystick.git
cd planetJoystick
./scripts/bootstrap.sh

./scripts/run.sh --config configs/entry/entry_operator.yaml
```

默认读取 `/dev/input/js0`，发送到 `127.0.0.1:50560`；持续运行，Ctrl+C 退出。
`operator.yaml` 包含 passive、damping、fixedpos、loco 请求。
只发送摇杆和安全信号时，选择 `configs/entry/entry_joystick.yaml`。

## 配置接收端和按键

新建 `configs/entry/entry_operator_site.yaml`：

```yaml
extends: entry_operator.yaml
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
./scripts/run.sh --config configs/entry/entry_operator_site.yaml
```

按实际部署修改地址。请求按名称逐项继承，`null` 禁用继承项；
状态 ID 和名称由接收端解释。接收端启动后，可用
`.venv/bin/planetj --config configs/entry/entry_operator_site.yaml --check-remote` 检查配对。

## 连续上肢目标

```bash
./scripts/upper-stream.sh --config configs/entry/entry_upper_stream.yaml
```

目标角度单位为 rad。配置决定关节顺序、轴映射、角度范围和发送频率。
默认采集实体手柄；断开后停止发送，目标保持与动作执行由接收端负责。

## 按键播放序列

同一个手柄进程可按键启动后台关节序列，状态请求、摇杆和急停持续正常发包：

```bash
./scripts/run.sh --config configs/entry/entry_sequences.yaml
```

这是两关节示例，接收端需配置对应的 `upper_stream` 状态。任务仓库在自己的
entry 中指定状态 ID、按键和实际 NPZ；详见[序列配置](docs/sequences.md)。
按一下启动，松键后继续；取消、切换状态或断开手柄会停止发送，接收端保持最新目标。

配置只保存在根目录 `configs/`；安装包只包含代码。每次启动都显式选择 entry，缺失路径直接报错。

## 文档与开发

- [配置和键位继承](docs/configuration.md)
- [上肢发送示例](examples/upper_stream/README.md)
- [按键启动后台序列](docs/sequences.md)

依赖 [planetConfig](https://github.com/Renforce-Dynamics/planetConfig) 的配置和协议包，
不依赖 Cadence 或 SDK。

开发：`./scripts/test.sh` 运行测试，`./scripts/build.sh` 构建安装包。
`./scripts/doctor.sh --config configs/entry/entry_operator.yaml` 检查选定配置，不启动 I/O。

工具支持 `--venv /path/to/env`。由 **Renforce Dynamics** 开发维护，采用 [MIT License](LICENSE)。
