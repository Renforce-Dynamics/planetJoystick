# `configs/nokov/calibration/` — fitted physics overrides

**Tracked in git** (tiny YAML, traceable via embedded `sources:`).

Contains `physics.yaml` files produced by
`scripts/nokov/calibrate/calibrate_physics.py` from L1 trajectories in
`../../trajectories/nokov/` (real) or `../../trajectories/sim/`
(MuJoCo-synthetic, used to self-test the calibration pipeline).
Each file looks like:

```yaml
# generated_by: scripts/nokov/calibrate/calibrate_physics.py
sources: [<abs path to each input L1 file>]
gravity_z:    -9.78
drag_k:        0.00
restitution_v: 0.83
restitution_h: 0.72
stats:
  gravity_z:    {n: 14, median: -9.78, mad: 0.12, p25: -9.85, p75: -9.71}
  ...
```

Parameters with zero usable estimates are **omitted** rather than
written as NaN — the planner's hand-tuned default stays in place for
anything we couldn't fit.

## Wiring into the planner

After a successful calibration run:

1. Read this file.
2. Copy `gravity_z` / `drag_k` into the `planner:` block of
   `configs/common/planner/rally.yaml` or the robot-specific planner profile.
3. Copy `restitution_v` / `restitution_h` into the planner's `table:`
   block (the racket coefficient has no data source — leave it alone).
4. Smoke against `scripts/sim2sim/test/scripted_landing.py` before committing.
5. Commit both the updated active planner profile and the new
   `physics.yaml` (it carries `sources:` for audit).

Run `scripts/nokov/calibrate/calibrate_physics.py --help` for the supported
estimators and acceptance thresholds.
