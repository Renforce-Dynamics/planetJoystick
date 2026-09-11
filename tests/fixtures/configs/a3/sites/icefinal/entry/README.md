# IceFinal planner entries

Every planner has one End A entry and one End B entry. The two entries share
the same planner YAML and differ only in OptiTrack rigid-body/site calibration
and recording rate. Generic entries target the white robot by default.

- Default transport: white robot (`192.168.120.122`).
- Explicit final profiles for both robot colors live under `final/white/` and
  `final/blue/`; they differ only in communication transport.

| Planner | Entry suffix | Runtime strategy | Planner config |
| --- | --- | --- | --- |
| deterministic single plane (default, `sin1`) | none | `rule_single_plane` | `rally_rule_single_plane_icefinal.yaml` |
| network-free multi-plane | `_region_multiplane` | `region_multiplane` | `rally_region_multiplane_icefinal.yaml` |
| learned one-plane ablation | `_feasi_plane` | `feasi_multiplane` | `rally_feasi_plane_icefinal.yaml` |
| learned exact multi-plane | `_feasi_multiplane` | `feasi_multiplane` | `rally_feasi_multiplane_icefinal.yaml` |
| sampled-time feasibility batch | `_feasi_batch` | `feasi_batch` | `rally_feasi_batch_icefinal.yaml` |
| periodic actuator/FK diagnostic | `_fixed_hit` | `fixed_hit` | `rally_fixed_hit.yaml` |

Use the corresponding `end_a` or `end_b` filename. For example:

```bash
# Stable deterministic baseline on End B.
uv run --no-sync python scripts/run.py \
  --config configs/a3/sites/icefinal/entry/entry_optitrack_onboard_end_b.yaml

# Learned exact multi-plane planner on End B.
uv run --no-sync python scripts/run.py \
  --config configs/a3/sites/icefinal/entry/entry_optitrack_onboard_end_b_feasi_multiplane.yaml
```

Do not infer the runtime strategy from the filename alone. Recordings save the
exact entry and effective planner manifest in `meta.json`:

```bash
jq '{entry: .planner.system_config,
     strategy: .planner.rally_manifest.stream.strategy,
     config_hash: .planner.rally_config_hash}' SESSION/meta.json
```

Historical or recorder-only sessions may contain only
`{"schema":"planetr.session.v1"}` and therefore cannot identify a planner.

## Final FeasiBatch entries

```bash
# White robot, End A.
uv run --no-sync python scripts/run.py \
  --config configs/a3/sites/icefinal/entry/final/white/entry_optitrack_onboard_end_a.yaml

# Blue robot, End A.
uv run --no-sync python scripts/run.py \
  --config configs/a3/sites/icefinal/entry/final/blue/entry_optitrack_onboard_end_a.yaml
```

Replace `end_a` with `end_b` when the robot is at the other end. There are no
IceFinal A/B entry profiles; validated parameters are folded directly into the
single final planner configuration.

Two isolated final diagnostic variants are available in both robot-color
folders and at both ends:

- `_base_return`: Base lock 200 ms plus return-duration priority, without the
  low-contact table guard.
- `_base_table_guard`: Base lock 200 ms plus the low-contact table guard,
  without return-duration priority.

The filename without a variant suffix is the complete Final and enables both.
