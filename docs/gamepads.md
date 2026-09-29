# Linux 与 macOS 手柄

`planetj` 和 `planetj-upper` 共用设备后端。Linux 默认使用原 `js_event` 读取器；
macOS 默认使用 pygame-ce 的 SDL Controller 接口。pygame-ce 在 Mac 上随普通安装
自动安装；不需要为篮球、Rally 或机器人状态机增加 macOS 分支。

## 设备选择

| YAML `device` | 行为 |
| --- | --- |
| `auto`（默认） | Linux：`/dev/input/js0`；macOS：第一个 SDL 已映射手柄 |
| `sdl:auto` | 明确使用 SDL，自动选择第一个已映射手柄 |
| `sdl:0`、`sdl:1` | 选择 `--list-devices` 显示的 SDL 设备索引 |
| `/dev/input/js1` | 指定 Linux joystick 节点 |
| `/tmp/cadence_vjs0` | 按 Linux `js_event` 格式读取测试 FIFO，包括在 macOS 上显式使用 FIFO |

设备选择值不按 YAML 目录改写。显式设备路径优先，不会被平台自动选择覆盖。
旧现场配置若写着 `/dev/input/js0`，在 Mac 上改为 `auto` 或 `sdl:auto`。
设备索引可能随插拔变化；多个手柄时重新查看列表。`mapped=False` 表示 SDL
未提供标准 GameController 映射，该设备不会被自动选择。

```bash
./scripts/run.sh --config configs/entry/entry_operator.yaml --list-devices
./scripts/run.sh --config configs/entry/entry_operator.yaml --monitor
```

这两种模式只读取本地设备；不创建 UDP socket，也不启动后台轨迹播放器。
monitor 显示连接状态、按下的按钮编号、经过配置映射的摇杆、十字键、请求 ID 和信号位。
`--duration-s 5` 可限定检查时间。`--check` 只检查配置，连 SDL 都不会加载。

正常运行会打印实际后端、连接的设备名、断连及状态请求。断连或读到设备移除时，
立即清空设备按钮与轴；上肢流停止发送，序列按既有取消规则处理。
连接恢复后重新读取当前输入，至少保留一次断连状态，不把旧按键带给新设备。
已触发的急停仍遵循配置的 500 ms 信号保持规则。

## 固定 Xbox 逻辑布局

SDL 的原始编号不同，后端统一转换为原 Linux Xbox 布局，再交给现有 YAML 映射：

| 索引 | 按钮 |
| --- | --- |
| 0 / 1 / 2 / 3 | A / B / X / Y |
| 4 / 5 | LB / RB |
| 6 / 7 / 8 | Back / Menu（Start）/ Guide（Home）|
| 9 / 10 | 左 / 右摇杆按下 |

原始轴依次为 `LX, LY, LT, RX, RY, RT, D-pad X, D-pad Y`。
扳机释放为 −1、压满为 +1；十字键右为 X=+1、上为 Y=−1，之后继续应用
`xbox.yaml` 的 scale，所以最终 D-pad 上为 +1。不需要按 macOS 重新编号。
其他手柄使用 SDL 的 Xbox 位置语义；实际按钮标签可能不同。

接口依据：[pygame-ce SDL Controller](https://pyga.me/docs/ref/sdl2_controller.html)。
SDL 在主线程采样，允许后台手柄事件，不创建游戏窗口或初始化音频。
系统可能占用 Home 等快捷键；用 monitor 确认实际收到的输入。

## 安装和验证

macOS 按 README 普通 bootstrap 即可。Linux 默认没有 pygame 依赖；需要在 Linux
使用 SDL 或运行其原生回归测试时：

```bash
./scripts/bootstrap.sh --extra sdl
./scripts/test.sh
```

测试使用真正的 SDL 虚拟手柄 API，覆盖 Xbox 键位、摇杆和扳机方向、十字键、
插拔清零、重连、读到一半移除、真实 PLNJ UDP 发包、独立上肢流和本地监视不发包。
默认 Linux 读取器与原协议保留。当前开发环境是 Linux：SDL 测试不等于 macOS
USB/蓝牙驱动实测，Mac 实体手柄的连接和系统快捷键行为需现场确认。
