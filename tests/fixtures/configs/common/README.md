# Common configs

这里只放跨机器人、跨场地复用的稳定配置，例如 transport、planner 默认值、独立
进程配置以及硬件厂商发布的 MarkerSet 几何模板。现场实体 ID、IP、桌角、坐标变换和
平移标定不得放入 `common`；它们分别
属于 `configs/<robot>/sites/<site>/<msgsource>/site.yaml` 和
`site_<msgsource>.json`。

`nokov/calibration/` 保存的是离线物理模型拟合说明，不是某个 site 的几何标定。
`pose_templates/` 保存固定 marker 坐标与 MuJoCo 轴语义，不包含任何现场 rigid pose。
完整配置范式见 [`configs/README.md`](../README.md)。
