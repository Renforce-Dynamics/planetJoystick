# planet-rally 配置范式

配置按“机器人 → 场地 → 消息源”组织。A3 的标准路径是：

```text
configs/a3/
├── sites/
│   └── <site>/
│       ├── planetj.yaml
│       ├── relay.yaml       # 仅需要网络中转的真实场地
│       ├── transport_<用途>.yaml
│       ├── entry/
│       │   └── entry_<msgsource>_<用途或扩展名>.yaml
│       └── <msgsource>/
│           ├── site.yaml
│           ├── site_<msgsource>.json
│           └── pose_<msgsource>.json
└── planner/
```

## 文件职责

- `site.yaml`：人工维护、稳定且可审查的配置。包含场地名、
  `message_source.kind`、连接参数、JSON 路径、实体/role、单位与固定坐标轴约定。
- `site_<msgsource>.json`：探测或标定脚本直接保存的数据，例如桌角采样、拟合
  transform 和生成时间。不同消息源不得共用一个 JSON。
- `pose_<msgsource>.json`：实体局部 pose 标定，例如 Base rigid-body 到
  A3 `robot_imu`、手部 rigid-body 到 MuJoCo racket site 的固定 shift。Base 标定可
  引用 `configs/common/pose_templates/` 下的固定 MarkerSet 模板；文件只保存现场生成的
  shift、FK 基准与质量统计，实时感知不重复拟合。未标定或 `enabled: false` 时默认
  identity shift。
- `<site>/entry/entry_<msgsource>_<ext names>.yaml`：唯一运行入口，组合 site、transport、
  perception 和 planner。`depth_window` 等 planner 变体写在入口扩展名中。
- `<site>/planetj.yaml`：场地级 operator 配置，使用 `extends` 继承 common 基础
  键位，只覆盖目标地址或该场地不同的 request/signal。
- `<site>/planetj_blue.yaml` / `planetj_white.yaml`：真实机器人 operator 目标；blue
  固定为 `192.168.120.121`，white 固定为 `192.168.120.122`。无颜色后缀默认 blue。
- `<site>/relay.yaml`：部署在中转机上的 UDP route；不属于某个消息源。
- `<site>/transport_<用途>.yaml`：场地网络的 planet-rally 发布目标；入口按用途引用。
  真实机器人使用 `_blue` / `_white` 后缀；无颜色后缀默认 blue。
- `configs/common/*.yaml`：跨机器人、跨场地的固定配置；不得放现场标定值。
- `configs/common/pose_templates/*.json`：硬件 MarkerSet 的固定几何和 MuJoCo 轴语义；
  可以被多个 site pose JSON 引用，现场标定脚本不得改写。

PlanetJ `extends` 对 mapping 做递归合并，对 list 做整体替换。因此场地若覆盖
`inputs.requests` 或 `inputs.signals`，必须提供该场地的完整列表。

规则：JSON 是生成数据，YAML 是配置。现场位置、桌角和标定平移等可能变化的值只写
JSON；运行时由 site loader 将 JSON 中的 `transform` / `calibration` 覆盖到稳定 YAML。

## 当前 A3 入口

```text
sites/ad201/entry/entry_nokov_onboard_end_a.yaml
sites/ad201/entry/entry_nokov_onboard_end_b.yaml
sites/ad201/entry/entry_nokov_onboard_end_{a,b}_depth_window.yaml
sites/ad201/entry/entry_nokov_onboard_end_{a,b}_feasi_batch.yaml
sites/iceribbon/entry/entry_optitrack_onboard.yaml
sites/iceribbon/entry/entry_optitrack_onboard_depth_window.yaml
sites/mujoco/entry/entry_nokov_sim2sim.yaml
sites/mujoco/entry/entry_nokov_sim2sim_depth_window.yaml
sites/mujoco/entry/entry_nokov_sim2sim_feasi_batch.yaml
sites/mujoco/entry/entry_optitrack_sim2sim.yaml
sites/mujoco/entry/entry_optitrack_sim2sim_depth_window.yaml
sites/mujoco/entry/entry_optitrack_sim2sim_feasi_batch.yaml
sites/mujoco/entry/entry_null_sim2sim.yaml
```

以上路径均相对于 `configs/a3/`。MuJoCo 被视为正常 site；入口中的 source 字段表示
sim2sim 接入的 live message source。Nokov 与 OptiTrack 的 `site.yaml` 使用同一外层字段：

```yaml
version: 1
site: {name: example}
message_source:
  kind: nokov               # nokov | optitrack | null | sim
  calibration_data: site_nokov.json
  pose_data: pose_nokov.json
  connection: {}
mocap:
  entities: {}
  transform: {}             # 只放固定单位/轴约定
  ball_observer: {}
```

旧的 G1 flat site YAML 暂时保持兼容；新建或迁移的 A3 配置必须使用本范式。
