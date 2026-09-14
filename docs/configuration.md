# planetJoystick: configuration and dependencies

## Defaults and task ownership

Each process selects a root entry explicitly:

| Entry | Local profile | Purpose |
| --- | --- | --- |
| `configs/entry/entry_joystick.yaml` | `configs/xbox.yaml` | Axes, D-pad and safety signals; no state requests |
| `configs/entry/entry_operator.yaml` | `configs/operator.yaml` | Adds passive (0), damping (1), fixedpos (2), loco (3) |
| `configs/entry/entry_upper_stream.yaml` | `configs/upper_stream.yaml` | Independent continuous joint-target producer |

The operator profile inherits the root device profile. Task repositories maintain their own bindings, such as `planet-rally/configs/operators/rally.yaml`. Wheels contain no configuration or data files. A wheel installation uses an explicitly supplied configuration tree.

Use `planetj --config FILE --check` for offline validation. `device` is a Linux device path, and `target` is a network address; neither is rewritten relative to YAML. Request IDs are interpreted by the consuming application.

`inputs.requests` accepts a mapping keyed by state name. Each value contains `buttons`, `request_id`, optional `blocked_by`, optional `state_key`, and optional `debug_name`. The key supplies `state_key` by default, and the default debug label is its uppercase spelling. Mappings merge recursively, so a task can change one chord without copying IDs or the other bindings. Set an entry to `null` to disable it. Duplicate request IDs remain invalid.

Legacy request lists are supported unchanged and replace the inherited list. Legacy entries may add `state_key` to enable remote validation. Signals remain a list and replace their inherited list.

`--check-remote` uses the configured `target.host`/`target.port` to describe the receiver's actual state catalog and validates each `(request_id, state_key)` pair. Advertised aliases are accepted. Missing services, missing state names, unknown states and mismatched IDs fail explicitly. The check exits without opening a joystick or requesting a transition. Neither `--check` nor normal input performs this handshake automatically.

## Source installation

`external/planetConfig` pins the repository whose root package is `planet-config` and whose `packages/planet-protocol` package is the pure-standard-library `planet-protocol`. Bootstrap installs these packages, the compatibility `planetj-protocol` and `planetj`. The recursive source graph contains only Planet components; the receiver runtime is an independent service.

## Upper-joint source

`planetj-upper` uses its own version-1 configuration and a separate joint-target port. It defaults to physical joystick input; `--source sine` and `--source scripted` explicitly select demonstrations. The configuration includes complete joint order, reference positions, limits, named axis mappings, frequency and connection timeout. Its producer has no state requests or PD ownership. See the [example and schema](../examples/upper_stream/README.md).

An upper target carries `activation`, `sequence` and `q_des` in radians. Activation changes reset the producer sequence; reconnects to the same activation preserve it. Disconnect or network failure pauses publication without emitting a fallback. The receiver retains its latest accepted target without a TTL. Joint-target receipts acknowledge reception only.

## Layering rules

All service configuration entry points use `planet-config`; each service validates its own schema after composition.

1. Apply `extends` entries in their listed order.
2. Apply `compose` layers in the fixed order `robot`, `backend`, `task`, `site`, `experiment`.
3. Merge the current file.
4. Apply explicit entry-point overrides, where supported.

Mappings merge recursively; lists and scalars replace. Missing parents, duplicate YAML keys and inheritance cycles fail. A service may reject fields that are valid for a different service. `compose` keys are loader directives, not fields added to the resulting service configuration.

All service profiles live in the root `configs/` tree; wheels contain code only. An explicit `--config` filesystem entry is required. Relative inheritance paths resolve beside the YAML declaring them, without searching another directory. Resource fields accessed through `ResolvedConfig.path()` resolve relative to their declaration; output directories and Linux device/abstract-socket endpoints follow the consuming service's rules below. The generic loader does not rewrite every string into a filesystem path.

Source ownership, Python dependencies and YAML inheritance are separate: Git submodules select code revisions; package metadata selects compatible installed distributions; `extends` selects configuration values. Changing a Git submodule does not select a task profile automatically.

See the [shared loader reference](https://github.com/Renforce-Dynamics/planetConfig/blob/main/docs/configuration.md).
