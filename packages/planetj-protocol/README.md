# planetj-protocol

Compatibility imports for the canonical PLNJ codec in `cadence-protocol`.

Existing `from planetj_protocol import ...` callers keep the same types, packet
bytes and legacy decoding. New integrations may import `cadence_protocol.operator`
directly. This package contains no separate codec and does not install Cadence's
control runtime.

Developed and maintained by Renforce Dynamics as part of
[planetJoystick](https://github.com/Renforce-Dynamics/planetJoystick).

See the repository README for installation, public interfaces and development. Licensed under MIT.
