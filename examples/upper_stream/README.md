# Upper-joint streaming

This producer publishes joint targets using the shared Planet protocol. The optional
integration below combines an independent Cadence process with planetJoystick. Cadence
owns the robot state machine, lower policy, joint limits and PD commands.
planetJoystick supplies operator requests and a separate stream of joint positions
in radians. No rally package is required.

## Prepare two repositories

Clone and bootstrap `cadence` and `planetJoystick` independently with their pinned
submodules. Install Cadence's simulation and inference extras using its setup
instructions. Each process uses its own virtual environment.

In the Cadence repository, start the operator-enabled mock runtime:

```bash
./scripts/run.sh --config configs/entry/a3/mock/entry_a3_operator_stream.yaml
```

In the planetJoystick repository, verify the live catalog, then start operator
input in a second terminal:

```bash
.venv/bin/planetj --config configs/entry/entry_operator.yaml --check-remote
.venv/bin/planetj --config configs/entry/entry_operator.yaml
```

Use RB+A for `fixedpos` (ID 2), then RB+X for `loco` (ID 3). The other base bindings
are RB+B for `damping` (ID 1) and RB+left-stick-click for `passive` (ID 0).
The default profile also preserves the emergency and reset signals from `xbox.yaml`.

Start the independent upper-joint producer in a third terminal:

```bash
./scripts/upper-stream.sh --config examples/upper_stream/config.yaml --check
./scripts/upper-stream.sh --config examples/upper_stream/config.yaml
```

The default source opens `/dev/input/js0`. Its two sticks offset shoulder pitch
and elbow positions around the configured initial posture. Each target contains
all 14 A3 arm joints in the declared order; unmapped joints retain their configured
position. Connected sticks at neutral request the configured posture. Position
limits bound the generated targets.

For an explicit demonstration without a physical joystick:

```bash
./scripts/upper-stream.sh --config configs/entry/entry_upper_stream.yaml --source sine --duration-s 10
./scripts/upper-stream.sh --config configs/entry/entry_upper_stream.yaml --source scripted --duration-s 3
```

The motion state must already be active. The producer never selects a robot state.
The scripted source plays one configured frame per tick, then repeats its final
frame. The sine source moves only the configured axis-driven joints.

## Configuration and lifecycle

`config.yaml` extends the local `configs/entry/entry_upper_stream.yaml`, whose root profile is `configs/upper_stream.yaml`. Change `device`, `target`,
`publisher`, `joints`, `axes`, or `demo` in an overlay. `joints.names` defines the
complete output order; `initial_position`, `position_min`, and `position_max`
must have the same length. Another robot may use any nonzero joint count. The
receiver reports its dimension; the producer rejects a different count. Joint
names are local labels, so verify their order against the receiver configuration.

`axes` maps a joint name to a Linux axis index, angular scale (`scale_rad`) and
deadzone. A `null` mapping disables one inherited axis. `publisher.hz` controls
target frequency; `status_hz` controls activation discovery. Both endpoints use
the loopback interface in this example.

On state entry Cadence first applies its configured default command. The producer
obtains the current activation and starts sequence numbers at zero. A new
activation starts a fresh sequence; delayed frames from an old activation are
rejected. Reconnecting to the same activation continues increasing the sequence,
including when a receipt was lost.

Unplugging the physical joystick stops upper-target publication immediately at
the next input poll. A connection error pauses publication until the receiver is
available. Neither condition publishes zero or a default pose: Cadence keeps its
latest accepted target without a TTL. This physical connection check is separate
from PLNJ's emergency-signal latch and its logical `CONNECTED` flag. The operator
process retains its own heartbeat and safety behavior.

A target receipt confirms mailbox reception, not hardware execution. This example
sends joint positions only; it does not solve inverse kinematics, set gains or
take ownership of the lower policy.
