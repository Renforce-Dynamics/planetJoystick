# PlanetJ

通用 Linux joystick 输入服务：设备采集 → 可配置的轴、按键组合与信号 → PLNJ。默认只有通用轴、急停和 reset 信号，request 映射为空。

```bash
./scripts/setup.sh --wheelhouse /path/to/wheels
./scripts/doctor.sh
./scripts/run.sh -- --config configs/xbox.yaml
./scripts/test.sh
./scripts/build.sh
```

可直接执行 `planetj --check`、`planetj --duration-s 2`。默认配置使用包内资源，从任意目录可运行。无手柄时发布 disconnected 与零输入；设备重新出现后重连。按键 ID 的业务含义由消费端定义。

仓库内包含独立发布的 `planetj-protocol`，发送端和消费端共享编解码。既不依赖 planet-rally，也不依赖 Cadence 执行内核、SDK、模型或 NumPy。A3 按键 profile 在 `cadence-rally` 的应用 bundle 中，测试目录里的旧 profile 仅用作兼容性 fixture。

编辑本仓库 YAML 设置设备和地址；使用 `extends` 复用配置，普通路径相对于声明文件。构建输出包含主包和协议包。
