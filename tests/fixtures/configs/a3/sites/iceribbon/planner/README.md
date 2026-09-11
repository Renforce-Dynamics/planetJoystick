# IceRibbon planner profiles

This directory is the authoritative planner configuration bundle for every
entry under `configs/a3/sites/iceribbon/entry`.

- Every IceRibbon entry points to a YAML file in this directory.
- Every `extends` reference in this directory stays inside this directory.
- Shared repository planner profiles remain available to other sites, but an
  IceRibbon deployment does not inherit planner YAML from those locations.
- Ball and racket parameter YAML files are copied into this directory as part
  of the self-contained configuration bundle.
- Model checkpoints and scene XML files remain normal repository assets.

When changing an IceRibbon planner, update the site-local profile here. Do not
silently rely on a similarly named file under `configs/a3/planner`.
