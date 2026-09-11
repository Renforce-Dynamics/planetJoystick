# A3 sites

先按场地、再按消息源查找配置。入口文件必须以 `entry_` 开头；不要新增
`onboard.yaml`、`mix_sim.yaml` 这类无法从文件名看出消息源的入口。

标定脚本只允许更新同目录的 `site_<msgsource>.json`，不得重写 `site.yaml`。
实体姿态标定单独更新 `pose_<msgsource>.json`；不得写入 site JSON。
PlanetJ 放在 `<site>/planetj.yaml`，因为 operator 信号属于场地而不是消息源；
sim2sim 也使用 `sites/mujoco/planetj.yaml` 并继承 common 基础键位。网络中转配置
同样放在场地根目录，如 `sites/ad201/relay.yaml`。

真实 A3 机器人使用固定颜色身份，不再用球场端位暗示网络地址：

- `blue`：`192.168.120.121`，OptiTrack 刚体 `THU_P1`；
- `white`：`192.168.120.122`，OptiTrack 刚体 `THU_P2`。

`planetj.yaml` 与无颜色后缀的 `transport_onboard_blackbox.yaml` 默认选择
`blue`。需要明确机器人时使用 `planetj_blue/white.yaml` 和
`transport_onboard_blackbox_blue/white.yaml`。End A/B 仍只表示场地标定端位；当前
IceFinal/IceRibbon 的 End A bundle 配 blue，End B bundle 配 white。
完整约束与入口清单见 [`configs/README.md`](../../README.md)。

同一物理场地存在两个机器人端位时，entry 必须原子绑定桌面 profile、当前机器人刚体和
该刚体到标准语义原点的 pose shift。当前加载器不支持 entry 覆盖 generated JSON 的
`active_profile`，因此使用 `<msgsource>/end_a/`、`<msgsource>/end_b/` 独立 side
bundle；禁止让两个 entry 指向同一个可变 `active_profile` 文件。
