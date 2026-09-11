# IceFinal calibration and timing notes

## 2026-08-21: SDK estimator time without Base/queue coupling

Symptom: live operation previously showed an apparently frozen Base and a
backlogged perception queue.  The failure was not caused by Base pose coming
from the SDK clock: Base pose has always been a mocap rigid body.  It came from
three timing/handoff issues that could combine:

- `435fe76` fixed latest-mode processing so stale snapshots are discarded
  before record/source taps process the backlog.
- `c7cd63c` stopped directly treating the optional NatNet timestamp suffix as
  a safe online clock. Some NatNet versions/builds can decode a corrupt but
  still positive value.
- `3d8afbd` kept live timing in the receive-monotonic domain and prevented a
  stale Base slot from being replayed after a perception failure.

The current invariant is:

- Base pose, freshness/deadline checks, queue handoff, and published
  perception timestamps always use local monotonic receive time.
- `perception.ball.estimator_timebase` controls only the ball filter,
  finite-difference velocity, and ball estimator sample spacing.
- In `sdk` mode, SDK timestamps are mapped into the monotonic domain. Missing,
  reversed, discontinuous, or drifting SDK values automatically fall back to
  receive-monotonic time and re-anchor; they cannot block the Base pipeline.

IceFinal entries select `sdk`. Other sites retain the backward-compatible
`monotonic` default unless explicitly configured.

## 2026-08-21: end-to-end ball physics fit

The IceFinal OptiTrack replay was jointly optimized for final plane-crossing
quality instead of a single instantaneous state. The site override in
`planner/rally.yaml` is:

- `drag_k: 0.16`
- `restitution_h: 0.92`
- `restitution_v: 0.96`

All nine leave-one-session-out folds selected the same parameter tuple.

## 2026-08-22: clean-data estimator profile

IceFinal no longer inherits the short-history choices used to tolerate the
lower-quality IceRibbon stream. An endpoint replay over 798 incoming episodes
selected the following profile while retaining the configured 320 Hz grid:

- `trajectory_prediction.fit_window: 51`
- `perception.ball.estimator_min_samples: 12`
- `trajectory_prediction.contact_guard.confirm_samples: 1`
- physics-constrained fit, 12 mm Huber threshold, and three robust iterations
  remain unchanged.

`fit_window` is a steady-state history cap, not a startup wait. The estimator
publishes after `min_samples`. Around a bounce the contact guard first prevents
one fit from crossing the velocity discontinuity, then the estimator collects
12 clean post-contact samples. Reducing confirmation from three rising-slope
observations to one avoids spending latency twice.

At 320 Hz the candidate replay produced 8.84 cm session-weighted equivalent
miss versus 9.93 cm for the previous 31/6/3 profile. P50/P90 miss changed from
7.36/21.93 cm to 6.17/19.46 cm. Coverage decreased by about three percent,
concentrated in very short post-bounce interception windows; the planner keeps
the last valid pre-contact plan during this short estimator gap.

The native C++ fit measured 89.5 us/update at 31 samples and 100.1 us/update at
51 samples on the deployment host. At 320 Hz the increase is about 3.4 ms of
CPU time per second (0.34 percentage points of one core).

The validated estimator and lifecycle parameters are now part of the final
IceFinal planner configuration. Historical A/B entry profiles were removed.
