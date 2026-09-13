# planetJoystick

**Configurable Linux joystick input.**

planetJoystick turns Linux joystick events into device-independent axes, requests and safety signals over PLNJ. Device reconnects and disconnected input are handled by the service.

Task repositories define the meaning of request IDs and supply their own button mappings. The built-in profile provides generic axes and safety signals with an empty request map.

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

`planetj` provides the service and CLI; `planetj-protocol` provides the shared wire codec. The `external/cadence` submodule supplies only `cadence-config` to this repository's bootstrap. Cadence runtime, robot SDKs and planner packages are not installed.

## Configuration

The default is `pkg://planetj/data/xbox.yaml`. Create a local overlay:

```yaml
extends: pkg://planetj/data/xbox.yaml
target:
  host: 127.0.0.1
  port: 50560
inputs:
  requests:
    - buttons: [4, 0]
      request_id: 6
      debug_name: CUSTOM_REQUEST
```

```bash
.venv/bin/planetj --config /path/to/operator.yaml --check
.venv/bin/planetj --config /path/to/operator.yaml
```

The requests list replaces the inherited list. Relative `extends` paths resolve beside the declaring YAML. Device paths such as `/dev/input/js0` are passed to Linux directly.

Rally bindings belong to [planet-rally](https://github.com/Renforce-Dynamics/planet-rally/tree/main/configs/operators), and `cadence-rally` interprets their IDs. See [configuration](docs/configuration.md) for ownership and validation details.

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
