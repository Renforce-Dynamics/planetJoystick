# planetJoystick

**Configurable Linux joystick input.**

planetJoystick turns Linux joystick events into device-independent axes, requests and safety signals over PLNJ. Device reconnects and disconnected input are handled by the service.

The `xbox.yaml` device profile provides generic axes and safety signals. The optional `cadence.yaml` profile adds the reusable passive, damping, fixed-position and locomotion bindings. Task repositories extend these named bindings with their own states.

## Quick start

Requires Linux, Python 3.10+ and `uv`.

```bash
git clone --recurse-submodules git@github.com:Renforce-Dynamics/planetJoystick.git
cd planetJoystick
./scripts/bootstrap.sh
./scripts/doctor.sh
./scripts/run.sh -- --duration-s 2
./scripts/test.sh
```

## Packages and dependencies

`planetj` provides operator input and an independent upper-joint producer. `cadence-protocol` supplies the PLNJ codec and small UDP clients; `planetj-protocol` preserves existing imports. The `external/cadence` submodule supplies only `cadence-config` and `cadence-protocol` to this repository's bootstrap. These packages require no control runtime, NumPy, robot SDK or planner.

## Configuration

The default is `pkg://planetj/data/xbox.yaml`, which has no state requests. For Cadence, start from the base motion bindings and override only the fields you need:

```yaml
extends: pkg://planetj/data/cadence.yaml
target:
  host: 127.0.0.1
  port: 50560
inputs:
  requests:
    loco:
      buttons: [5, 2]
    passive: null
```

```bash
.venv/bin/planetj --config /path/to/operator.yaml --check
.venv/bin/planetj --config /path/to/operator.yaml --check-remote
.venv/bin/planetj --config /path/to/operator.yaml
```

Named request mappings merge by state key; `null` disables an inherited binding. Legacy request lists still replace the whole list. `--check` is offline. `--check-remote` describes the configured operator endpoint, checks state names and IDs (including aliases), and exits without publishing commands. Normal input does not require the receiver to start first. Relative `extends` paths resolve beside the declaring YAML; device paths are passed to Linux directly.

Rally bindings belong to [planet-rally](https://github.com/Renforce-Dynamics/planet-rally/tree/main/configs/operators). Cadence resolves their IDs through the catalog extended by `cadence-rally`. See [configuration](docs/configuration.md) and the [system architecture](https://github.com/Renforce-Dynamics/cadence/blob/main/docs/architecture.md) for ownership and matching rules.

## Continuous upper-joint input

`planetj-upper` supplies joint positions in radians to a Cadence streamed-upper state. The packaged example configures the 14 A3 arm joints; joint count, order, axis mappings, angular scales, limits and rate are configurable.

```bash
./scripts/upper-stream.sh -- --check
./scripts/upper-stream.sh
./scripts/upper-stream.sh -- --source sine --duration-s 10
```

The default source is a physical Linux joystick. Disconnecting it stops target publication and leaves Cadence holding its latest accepted target. The sender discovers state activations but does not switch robot states, set PD gains or send a timeout fallback. Its input connection is independent of PLNJ's emergency latch. See the [standalone Cadence example](examples/cadence_upper_stream/README.md) for separate runtime/operator/upper-stream processes and explicit hardware-free demonstration sources.

## Development

```bash
./scripts/submodules.sh init    # initialize or restore pinned dependencies
./scripts/submodules.sh check
./scripts/test.sh
./scripts/build.sh
```

Submodules pin source commits; Python requirements describe package compatibility. Bootstrap installs only the explicit packages in `source-workspace.json`. `scripts/setup.sh --wheelhouse /path/to/wheels` is available for package-based installation. Upgrade dependencies by committing reviewed submodule revisions with the parent repository.

## Authorship and license

Developed and maintained by [Renforce Dynamics](https://github.com/Renforce-Dynamics). See [AUTHORS.md](AUTHORS.md). Project code is available under the [MIT License](LICENSE).
