# planetJoystick: configuration and dependencies

## Defaults and task ownership

`src/planetj/data/xbox.yaml` is the packaged device default (`pkg://planetj/data/xbox.yaml`). `configs/xbox.yaml` is the source example. Generic defaults contain axes, D-pad and safety signals; `inputs.requests` is empty.

Task repositories own request mappings. Rally inherits these generic defaults in `planet-rally/src/planet_pingpong/data/configs/operators/rally.yaml`. The task's `configs/operators/rally.yaml` is an entry forwarding to that packaged profile. The old profiles under tests are compatibility fixtures.

Use `planetj --config FILE --check` before starting a service. `device` is a Linux device path, and `target` is a network address; neither is rewritten relative to YAML. Requests and signals are lists, so overriding them replaces each whole list. Request IDs are interpreted by the consuming application.

## Source installation

`external/cadence` pins the source containing `cadence-config`. Bootstrap installs that package, the local `planetj-protocol` and `planetj`. It does not install Cadence runtime or the optional SDK submodule inside Cadence.

## Layering rules

All service configuration entry points use `cadence-config`; each service validates its own schema after composition.

1. Apply `extends` entries in their listed order.
2. Apply `compose` layers in the fixed order `robot`, `backend`, `task`, `site`, `experiment`.
3. Merge the current file.
4. Apply explicit entry-point overrides, where supported.

Mappings merge recursively; lists and scalars replace. Missing parents, duplicate YAML keys and inheritance cycles fail. A service may reject fields that are valid for a different service. `compose` keys are loader directives, not fields added to the resulting service configuration.

Relative inheritance paths resolve beside the YAML declaring them. `pkg://package/path` resolves installed package resources. Resource fields accessed through `ResolvedConfig.path()` resolve relative to their declaration; output directories and Linux device/abstract-socket endpoints follow the consuming service's rules below. The generic loader does not rewrite every string into a filesystem path.

Source ownership, Python dependencies and YAML inheritance are separate: Git submodules select code revisions; package metadata selects compatible installed distributions; `extends` selects configuration values. Changing a Git submodule does not select a task profile automatically.

See the [shared loader reference](https://github.com/Renforce-Dynamics/cadence/blob/main/docs/configuration.md).
