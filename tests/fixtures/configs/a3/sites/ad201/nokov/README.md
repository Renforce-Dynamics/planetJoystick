# AD201 Nokov End-A / End-B 配置

AD201 使用自身的 Nokov 原点和桌角采集，不复用 IceRibbon 的场地变换。运行时仍把
桌面中心统一映射到 Planet-PingPong world `[2.0, 0.0, 0.76]`，以保持 planner 与 A3 policy
的坐标契约一致。

固定配对如下：

| 物理侧 | 场地 profile | 刚体 | XING ID | 机器人网络 |
| --- | --- | --- | --- | --- |
| End A | `robot_end_a` | `THU_P1` | 0 | blue / `192.168.120.121` |
| End B | `robot_end_b` | `THU_P2` | 1 | white / `192.168.120.122` |

两侧必须通过相应 `entry_nokov_onboard_end_a*.yaml` 或
`entry_nokov_onboard_end_b*.yaml` 原子切换，禁止混用另一侧的 site、pose 或 transport。

场地几何来自 AD201 原始 Table 四角的 270 帧中位数：桌长 `2.7231802449 m`、桌宽
`1.5037835281 m`、最大平面误差 `1.0696 mm`。完整原始点、A/B 变换、ID 映射和
side pairing 位于各侧的 `site_nokov.json`。

`THU_P1` 和 `THU_P2` 的十点 MarkerSet 已分别用 `calibrate_base_pose.py` 拟合到
`imu_in_pelvis`。`pose_nokov.json` 同时保留机器可用四元数和便于现场核对的
`face_bias.rpy_xyz_deg` / `face_bias.yaw_deg`。XING 中重建任一刚体后，必须重新标定
对应侧，不能沿用旧 face bias。

现场 Probe：

```bash
uv run --no-sync python scripts/probe.py --source nokov \
  --config configs/a3/sites/ad201/nokov/end_a/site.yaml --duration-s 3

uv run --no-sync python scripts/probe.py --source nokov \
  --config configs/a3/sites/ad201/nokov/end_b/site.yaml --duration-s 3
```

Nokov SDK 已验证可在同一台控制机上由 End A/B 两个独立进程并发连接。

## 双机器人录制与调试

P1/P2 使用完全独立的本机 endpoint 和录制目录，避免两路 trace、metadata 与
DebugFrame 混流：

| 实例 | PlanetR | PlanetD | onboard UDP | 录制目录 |
| --- | --- | --- | --- | --- |
| P1 / End A | `@planetr_p1` | `@planetd_p1` | `50571` | `recordings/ad201/p1` |
| P2 / End B | `@planetr_p2` | `@planetd_p2` | `50572` | `recordings/ad201/p2` |

分别启动四个配套进程：

```bash
uv run --no-sync python scripts/run_planetr.py \
  --config configs/a3/sites/ad201/planetr_p1.yaml
uv run --no-sync python scripts/run_planetr.py \
  --config configs/a3/sites/ad201/planetr_p2.yaml

uv run --no-sync python scripts/run_planetd.py \
  --config configs/a3/sites/ad201/planetd_p1.yaml
uv run --no-sync python scripts/run_planetd.py \
  --config configs/a3/sites/ad201/planetd_p2.yaml
```

蓝机器人 A3DB/relay 的控制 PC 目标端口必须设为 `50571`，白机器人设为 `50572`；
仅拆 Unix endpoint 而仍让两个 PlanetR 监听同一 UDP 端口并不安全。
