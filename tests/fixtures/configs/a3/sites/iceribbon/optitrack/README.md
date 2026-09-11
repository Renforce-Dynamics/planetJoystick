# Iceribbon OptiTrack 标定与真机 Root 验证

通用的新场地采集、A/B 换侧和真机验收流程见
[OptiTrack 球桌 A/B 侧快速标定 SOP](../../../../../docs/guides/optitrack-calibration-zh.md)。
新 side bundle 固定配对为 A 侧 `robot_end_a + THU_P1`、B 侧
`robot_end_b + THU_P2`。根目录下旧 `site.yaml` 仍保留 P2 兼容入口，不作为新 A/B
配置的参数来源。

本文档描述两层独立变换：

```text
NatNet 原始动捕坐标
  -- site_optitrack.json: p_world = R @ p_mocap + t --> MuJoCo / Planet-PingPong world
  -- 当前刚体 role_pose ----------------------------> robot_imu / imu_in_pelvis
  -- PlannerFrame :50550 ----------------------------> agi3dep
```

桌面标定只负责第一层。机器人刚体不参与桌面标定；刚体原点或局部轴偏差必须在
桌面标定完成后按每侧单独拟合和验证。

## A/B 侧标定入口

当前主线保留原有 B 侧兼容配置，并新增两套显式 side bundle。操作时只选择对应
entry，不要手动混搭 profile、刚体和 pose：

```text
entry/entry_optitrack_onboard_end_a.yaml
  -> optitrack/end_a/：robot_end_a + THU_P1

entry/entry_optitrack_onboard_end_a_feasi_batch.yaml
  -> 同一 end_a source + CUDA feasibility batch planner

entry/entry_optitrack_onboard_end_a_feasi_plane.yaml
  -> 同一 end_a source + 单平面 feasibility A/B 基线

entry/entry_optitrack_onboard_end_a_feasi_multiplane.yaml
  -> 同一 end_a source + 多平面/base/双手解析反解 feasibility planner

entry/entry_optitrack_onboard_end_a_region_multiplane.yaml
  -> 同一 end_a source + 无网络 Region 多平面/连续 Base planner

entry/entry_optitrack_onboard_end_a_fixed_hit.yaml
  -> 同一 end_a source + periodic fixed-command test

entry/entry_optitrack_onboard_end_b.yaml
  -> optitrack/end_b/：robot_end_b + THU_P2

entry/entry_optitrack_onboard_end_b_feasi_batch.yaml
  -> 同一 end_b source + CUDA feasibility batch planner

entry/entry_optitrack_onboard_end_b_feasi_plane.yaml
  -> 同一 end_b source + 单平面 feasibility A/B 基线

entry/entry_optitrack_onboard_end_b_feasi_multiplane.yaml
  -> 同一 end_b source + 多平面/base/双手解析反解 feasibility planner

entry/entry_optitrack_onboard_end_b_region_multiplane.yaml
  -> 同一 end_b source + 无网络 Region 多平面/连续 Base planner

entry/entry_optitrack_onboard_end_b_fixed_hit.yaml
  -> 同一 end_b source + periodic fixed-command test
```

以上 entry 的 planner 配置统一位于相邻的 `../planner/` 目录。该目录是 IceRibbon
现场参数的唯一来源，包含完整的 planner 继承链以及球、球拍参数 YAML；不要再让
IceRibbon entry 指向 `configs/a3/planner/` 或 `configs/common/planner/`。

两套 bundle 的网络和场地变换均已固化在当前仓库，不依赖仓库外文件。2026-08-18
现场 Probe 已确认 Motive 3.1 / NatNet 4.1、A 侧 `THU_P1` ID 6 和十点 MarkerSet；
同日 End B Probe 已确认 `THU_P2` ID 3 和十点 MarkerSet。两侧 rigid→IMU shift
均已用当前仓库工具链独立拟合并启用。在线球状态使用 Motive `Ball` 刚体（ID 5）的 tracking-valid 位和位置；
不会静默回退到会冻结的同名 MarkerSet。

## Base 与球拍位置来源

机器人 Base 的位置和朝向始终来自 OptiTrack 的 `THU_P1` / `THU_P2` 刚体；
`robot_imu` / `imu_in_pelvis` 只表示标定后的机器人标准原点，不表示使用 IMU 信号估计
Base。球拍不依赖 OptiTrack 球拍刚体：PlanetR 根据同一动捕 Base 世界位姿和 onboard
29 维关节角运行仓库内的 A3 FK，并把结果写入 `onboard.jsonl` 的 `racket_fk`；PlanetD
同步显示 `world/robot/racket_fk`。FK 常量和实现位于 `src/planet_pingpong/kinematics/a3.py`。

先用对应 side site Probe，确认当前 Motive 名称、ID 和十点 MarkerSet 名称。然后让
机器人静止、基本直立，先写临时结果：

```bash
# A 侧复标；B 侧复标时把 end_a/THU_P1 替换为 end_b/THU_P2。
uv run --no-sync python scripts/calibrate_base_pose.py \
  --site configs/a3/sites/iceribbon/optitrack/end_a/site.yaml \
  --entity THU_P1 \
  --duration-s 3 \
  --min-frames 30 \
  --output /tmp/pose_optitrack.end_a.fitted.json
```

确认 marker RMSE、位置和 yaw 后，再将拟合结果写入对应 side 的正式
`pose_optitrack.json`。Motive 中重建 rigid body 后必须重新拟合，不能沿用旧 shift。

## 旧 P2 兼容入口参数

以下内容仅描述根目录旧 `site.yaml` / `entry_optitrack_onboard.yaml`，便于已有部署回退；
新部署使用上面的 A/B side bundle。

- Motive/NatNet：`192.168.5.10`
- 本机动捕接口：`192.168.5.120`
- `table`：rigid body ID `1`
- `Ball`：marker set（使用可见 marker 的 centroid）
- `P2`：rigid body ID `0`，role 为 `robot_imu`
- MuJoCo 桌面中心：`[2.0, 0.0, 0.76]`
- MuJoCo 桌面范围：X `[0.63, 3.37]`，Y `[-0.7625, 0.7625]`

ID 不是永久协议。每次 Motive 工程变化后，以 Probe 输出的
`model_definitions` 为准，并同步检查 `site.yaml`。

## 重要：只用 NatNet 原始点标定

正式 `site.yaml` 会加载 `site_optitrack.json`。使用它运行 Probe 时，输出的
rigid body 和 marker 已经执行过 `p_world = R @ p_mocap + t`，属于 world 数据。
严禁把正式 Probe 输出重新写入 `table_corners_m`，否则会重复应用 transform。

采集原始 NatNet 点时，使用不加载 calibration JSON 的临时 site：

```bash
cd /home/idlab/ipingpong/Planet-PingPong
cp configs/a3/sites/iceribbon/optitrack/site.yaml /tmp/planet_pingpong-optitrack-raw.yaml
sed -i '/calibration_data: site_optitrack.json/d' /tmp/planet_pingpong-optitrack-raw.yaml

uv run --no-sync python scripts/probe.py \
  --source optitrack \
  --config /tmp/planet_pingpong-optitrack-raw.yaml \
  --duration-s 3 \
  --print-markers
```

此时输出等于未经场地变换的 NatNet 原始坐标。确认：

- `frames > 0`，现场约为 360 Hz；
- `rigid table valid=True`；
- `markers table valid=True visible=4/4`；
- 四点稳定且尺寸约为 `2.72 m × 1.50 m`。

从多帧 `markers table` 取每个 marker 的逐轴中位数，写入
`site_optitrack.json` 的 `captures.table_corners.table_corners_m`。

## 生成 mocap 到仿真 world 的变换

```bash
uv run --no-sync python scripts/calibrate_optitrack_table.py \
  --table-corners configs/a3/sites/iceribbon/optitrack/site_optitrack.json \
  --output configs/a3/sites/iceribbon/optitrack/site_optitrack.json \
  --table-center-in-robot-m 2.0 0.0 0.76
```

合理结果应满足：

- `table_length_m` 约 `2.72`；
- `table_width_m` 约 `1.50`；
- `max_plane_error_mm` 为几毫米；
- 正式 Probe 中 table center 约为 `[2.0, 0.0, 0.76]`。

桌子关于中心有 180° 对称歧义。`robot_end_a` 和 `robot_end_b` 均能把几何桌面
重合，但 X/Y 方向相反。若真实 X 与仿真 X 相反，在 JSON 中切换
`calibration.active_profile`；这是绕 world Z 轴旋转 180°，必须同时反转 X/Y，
不能只反 X（只反一轴会产生镜像坐标系）。当前现场使用 `robot_end_b`。

## 用桌心 Ball 验证

把 Ball 放在真实桌面中心，然后使用正式 site：

```bash
uv run --no-sync python scripts/probe.py \
  --source optitrack \
  --config configs/a3/sites/iceribbon/optitrack/site.yaml \
  --duration-s 3
```

通过标准：

- `rigid table valid=True` 且位置约 `[2.0, 0.0, 0.76]`；
- `rigid Ball valid=True`；
- Ball 的 XY 接近 `[2.0, 0.0]`；
- Ball Z 是否为 `0.76 + 0.02` 取决于 Motive Ball 刚体原点；若刚体原点不是球心，
  需要单独标定 Ball 的 role pose，不能平移场地 transform。

## 验证真机 P2 的 x/y/yaw

正式真机入口直接使用 OptiTrack 的 `robot_imu`：

```text
P2 raw pose
  -> site transform（mocap 到 world）
  -> 可选 role_pose（P2 rigid body 到 imu_in_pelvis）
  -> Planet-PingPong PlannerFrame.policy_root_position_w_m / orientation_wxyz
  -> UDP :50550
  -> agi3dep onboard policy_root
```

因此 agi3dep 真机已经使用 planner 发送的 x/y/yaw，无需增加新协议。位置和 yaw
可先由正式 Probe 检查。quaternion `[w,x,y,z]` 的 yaw 为：

```text
yaw = atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))
```

验证步骤：

1. 机器人静止在已知 world 点，核对 P2 的 X/Y；
2. 机器人正朝仿真 +X，期望 yaw 接近 `0`；
3. 原地转过已知角度，检查 yaw 的符号和增量；
4. 若 X/Y 正确但 yaw 存在固定偏差，标定 P2 `role_pose`，不要修改桌面 transform；
5. 若刚体原点不在 IMU，重新标定并写入 source-specific pose JSON；A3 entry 不叠加
   `policy_root_offset_*`。

当前 P2 已在 `pose_optitrack.json` 中配置绕 Z 轴 180° 的固定 shift：
`quaternion_wxyz: [0.0, 0.0, 0.0, 1.0]`。`site.yaml` 只引用该 JSON，不内嵌
临时 pose。每次重建 Motive 刚体后仍需重新验证朝向和原点。

## 安全验证 PlannerFrame 链路

控制机启动纯 OptiTrack Planet-PingPong（不是 mixed sim2sim 入口）：

```bash
cd /home/idlab/ipingpong/Planet-PingPong
uv run --no-sync python scripts/run.py \
  --config configs/a3/sites/iceribbon/entry/entry_optitrack_onboard.yaml
```

在 A3 上使用 agi3dep dry-run，可接收 PlannerFrame 但不发布关节命令：

```bash
cd /agibot/agi3dep
bash scripts/onboard/run_python_onboard.sh \
  --config configs/entry/entry_onboard_a3_real_readonly.yaml
```

dry-run 输出中的 planner root 应与 Planet-PingPong 正式 Probe 的 P2 world pose 一致。
确认 x/y/yaw 后，再进入 command-capable 真机流程。

## Sim2sim 与真机的区别

- 真机 `entry_optitrack_onboard.yaml`：P2 动捕 pose 进入 PlannerFrame，agi3dep 使用
  planner root。
- Sim2sim `entry_optitrack_sim2sim.yaml`：mixed source 使用 A3SM/MuJoCo root 覆盖
  P2，确保仿真闭环一致；它不能用于验证真实 P2 root。

每次修改 `site_optitrack.json` 后必须重启 Planet-PingPong，运行中不会自动重载标定。
