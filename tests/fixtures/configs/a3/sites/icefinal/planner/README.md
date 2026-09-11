# IceFinal planner profiles

This directory is the authoritative planner configuration bundle for every
entry under `configs/a3/sites/icefinal/entry`.

- Every IceFinal entry points to a YAML file in this directory.
- Every `extends` reference in this directory stays inside this directory.
- Shared repository planner profiles remain available to other sites, but an
  IceFinal deployment does not inherit planner YAML from those locations.
- Ball and racket parameter YAML files are copied into this directory as part
  of the self-contained configuration bundle.
- Model checkpoints and scene XML files remain normal repository assets.

When changing an IceFinal planner, update the site-local profile here. Do not
silently rely on a similarly named file under `configs/a3/planner`.
The complete End A/End B entry matrix and launch commands are documented in
`../entry/README.md`.

## Inheritance

`rally_common.yaml` owns geometry, assets and broad robot command limits.
`rally.yaml` is the IceFinal deployment base and owns the calibrated ball
estimator, drag/table parameters, contact guard and strike conditioning.
Strategy files inherit that base and contain only strategy-specific choices:

- `rally_rule_single_plane_icefinal.yaml`: deterministic single-plane policy.
- `rally_region_multiplane_icefinal.yaml`: network-free exact multi-plane policy.
- `rally_feasi_batch_icefinal.yaml`: sampled-time feasibility batch policy.
- `rally_feasi_batch_icefinal_base.yaml`: shared 200 ms Base-lock foundation.
- `rally_feasi_batch_icefinal_base_return.yaml`: foundation + return priority.
- `rally_feasi_batch_icefinal_base_table_guard.yaml`: foundation + table guard.
- `rally_feasi_multiplane_icefinal.yaml`: learned exact-plane policy.
- `rally_feasi_plane_icefinal.yaml`: one-plane learned-policy specialization.
- `rally_fixed_hit.yaml`: periodic fixed-command diagnostic.

Keep strategy-specific return flight time, network threshold, candidate lattice,
contact guard, and lock timing in the leaf profile. Do not duplicate the site
ball calibration in leaf profiles.

IceFinal has one complete final parameter set per strategy. Historical A/B
overlays were removed. The two named FeasiBatch diagnostic variants isolate one
final mechanism each without reintroducing an A/B hierarchy.
