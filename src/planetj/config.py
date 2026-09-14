"""Strict YAML configuration for the standalone PlanetJ process."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from .protocol import AXIS_NAMES


class PlanetJConfigError(ValueError):
  pass


def _merge_config(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
  """Recursively merge mappings; sequences and scalar values replace the base."""
  merged = dict(base)
  for key, value in override.items():
    if key == "extends":
      continue
    previous = merged.get(key)
    if isinstance(previous, Mapping) and isinstance(value, Mapping):
      merged[key] = _merge_config(previous, value)
    else:
      merged[key] = value
  return merged


def _resolve_extends(source_path: Path, value: Any) -> Path:
  if not isinstance(value, str) or not value.strip():
    raise PlanetJConfigError("extends must be a non-empty path string")
  candidate = Path(value).expanduser()
  if candidate.is_absolute():
    return candidate.resolve()
  # Repository-root paths are the canonical config spelling. Relative paths
  # remain useful for temporary configs and installed deployments.
  from_cwd = candidate.resolve()
  if from_cwd.is_file():
    return from_cwd
  return (source_path.parent / candidate).resolve()


def _load_yaml_tree(source_path: Path, stack=()):
  from planet_config import load_config, ConfigError
  try:
    result = load_config(source_path)
    _only_keys(result.data, {"version", "device", "target", "publisher", "inputs"}, "config")
    return result.data
  except ConfigError as error:
    raise PlanetJConfigError(str(error)) from error


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
  if not isinstance(value, Mapping):
    raise PlanetJConfigError(f"{path} must be a mapping")
  return value


def _sequence(value: Any, path: str) -> Sequence[Any]:
  if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
    raise PlanetJConfigError(f"{path} must be a sequence")
  return value


def _only_keys(value: Mapping[str, Any], allowed: set[str], path: str) -> None:
  unknown = set(value) - allowed
  if unknown:
    names = ", ".join(sorted(str(key) for key in unknown))
    raise PlanetJConfigError(f"{path} contains unknown keys: {names}")


def _integer(value: Any, path: str) -> int:
  if isinstance(value, bool) or not isinstance(value, int):
    raise PlanetJConfigError(f"{path} must be an integer")
  return value


def _button_tuple(value: Any, path: str) -> tuple[int, ...]:
  buttons = tuple(_integer(item, path) for item in _sequence(value, path))
  if not buttons:
    raise PlanetJConfigError(f"{path} must not be empty")
  if any(button < 0 for button in buttons):
    raise PlanetJConfigError(f"{path} entries must be non-negative")
  if len(buttons) != len(set(buttons)):
    raise PlanetJConfigError(f"{path} contains duplicate buttons")
  return buttons


@dataclass(frozen=True, slots=True)
class AxisMapping:
  index: int
  scale: float = 1.0
  deadzone: float = 0.0

  def __post_init__(self) -> None:
    if isinstance(self.index, bool) or self.index < 0:
      raise PlanetJConfigError("axis index must be non-negative")
    if not math.isfinite(self.scale) or self.scale == 0.0:
      raise PlanetJConfigError("axis scale must be finite and non-zero")
    if not math.isfinite(self.deadzone) or not 0.0 <= self.deadzone < 1.0:
      raise PlanetJConfigError("axis deadzone must be in [0, 1)")


@dataclass(frozen=True, slots=True)
class DpadAxisMapping:
  index: int
  scale: float = 1.0
  threshold: float = 0.5

  def __post_init__(self) -> None:
    if isinstance(self.index, bool) or self.index < 0:
      raise PlanetJConfigError("D-pad axis index must be non-negative")
    if not math.isfinite(self.scale) or self.scale == 0.0:
      raise PlanetJConfigError("D-pad scale must be finite and non-zero")
    if not math.isfinite(self.threshold) or not 0.0 < self.threshold <= 1.0:
      raise PlanetJConfigError("D-pad threshold must be in (0, 1]")


@dataclass(frozen=True, slots=True)
class RequestMapping:
  buttons: tuple[int, ...]
  request_id: int
  debug_name: str
  blocked_by: tuple[int, ...] = ()
  state_key: str | None = None

  def __post_init__(self) -> None:
    _validate_chord(self.buttons, self.blocked_by, self.debug_name)
    if isinstance(self.request_id, bool) or not 0 <= self.request_id <= 0xFFFF:
      raise PlanetJConfigError("request_id must be in [0, 65535]")
    if self.state_key is not None and (not isinstance(self.state_key, str) or not self.state_key.strip()):
      raise PlanetJConfigError("state_key must be a non-empty string")


@dataclass(frozen=True, slots=True)
class SignalMapping:
  buttons: tuple[int, ...]
  signal_id: int
  debug_name: str
  blocked_by: tuple[int, ...] = ()
  hold_after_release_ms: int = 0

  def __post_init__(self) -> None:
    _validate_chord(self.buttons, self.blocked_by, self.debug_name)
    if isinstance(self.signal_id, bool) or not 0 <= self.signal_id < 32:
      raise PlanetJConfigError("signal_id must be in [0, 31]")
    if isinstance(self.hold_after_release_ms, bool) or self.hold_after_release_ms < 0:
      raise PlanetJConfigError("hold_after_release_ms must be non-negative")


def _validate_chord(
  buttons: tuple[int, ...], blocked_by: tuple[int, ...], debug_name: str,
) -> None:
  if not buttons or any(isinstance(value, bool) or value < 0 for value in buttons):
    raise PlanetJConfigError("chord buttons must be non-empty non-negative integers")
  if len(buttons) != len(set(buttons)):
    raise PlanetJConfigError("chord buttons must be unique")
  if any(isinstance(value, bool) or value < 0 for value in blocked_by):
    raise PlanetJConfigError("blocked_by must contain non-negative integers")
  if len(blocked_by) != len(set(blocked_by)):
    raise PlanetJConfigError("blocked_by buttons must be unique")
  if set(buttons) & set(blocked_by):
    raise PlanetJConfigError("buttons and blocked_by must not overlap")
  if not isinstance(debug_name, str) or not debug_name.strip():
    raise PlanetJConfigError("debug_name must be a non-empty string")


@dataclass(frozen=True, slots=True)
class InputMapping:
  axes: tuple[tuple[str, AxisMapping], ...]
  dpad_x: DpadAxisMapping
  dpad_y: DpadAxisMapping
  requests: tuple[RequestMapping, ...]
  signals: tuple[SignalMapping, ...]

  def __post_init__(self) -> None:
    names = tuple(name for name, _ in self.axes)
    if names != AXIS_NAMES:
      raise PlanetJConfigError(f"inputs.axes must define exactly {', '.join(AXIS_NAMES)}")
    indices = tuple(mapping.index for _, mapping in self.axes)
    if len(indices) != len(set(indices)):
      raise PlanetJConfigError("inputs.axes indices must be unique")
    if self.dpad_x.index == self.dpad_y.index:
      raise PlanetJConfigError("D-pad x/y indices must differ")
    if {self.dpad_x.index, self.dpad_y.index} & set(indices):
      raise PlanetJConfigError("D-pad and analog axes must use distinct indices")
    request_chords = tuple((item.buttons, item.blocked_by) for item in self.requests)
    signal_chords = tuple((item.buttons, item.blocked_by) for item in self.signals)
    if len(request_chords) != len(set(request_chords)):
      raise PlanetJConfigError("request chords must be unique")
    if len(signal_chords) != len(set(signal_chords)):
      raise PlanetJConfigError("signal chords must be unique")
    request_ids = tuple(item.request_id for item in self.requests)
    signal_ids = tuple(item.signal_id for item in self.signals)
    if len(request_ids) != len(set(request_ids)):
      raise PlanetJConfigError("request IDs must be unique")
    if len(signal_ids) != len(set(signal_ids)):
      raise PlanetJConfigError("signal IDs must be unique")


@dataclass(frozen=True, slots=True)
class TargetConfig:
  host: str
  port: int

  def __post_init__(self) -> None:
    if not self.host:
      raise PlanetJConfigError("target.host cannot be empty")
    if not 1 <= self.port <= 65535:
      raise PlanetJConfigError("target.port must be in [1, 65535]")


@dataclass(frozen=True, slots=True)
class PublisherConfig:
  hz: float
  ttl_ms: int

  def __post_init__(self) -> None:
    if not math.isfinite(self.hz) or self.hz <= 0.0:
      raise PlanetJConfigError("publisher.hz must be positive")
    if not 1 <= self.ttl_ms <= 65535:
      raise PlanetJConfigError("publisher.ttl_ms must be in [1, 65535]")


@dataclass(frozen=True, slots=True)
class PlanetJConfig:
  version: int
  device: str
  target: TargetConfig
  publisher: PublisherConfig
  inputs: InputMapping
  source_path: Path

  def __post_init__(self) -> None:
    if self.version != 4:
      raise PlanetJConfigError(f"unsupported PlanetJ config version {self.version}; expected 4")
    if not self.device:
      raise PlanetJConfigError("device cannot be empty")


def _axis_mapping(value: Any, path: str) -> AxisMapping:
  raw = _mapping(value, path)
  _only_keys(raw, {"index", "scale", "deadzone"}, path)
  return AxisMapping(
    index=_integer(raw["index"], f"{path}.index"),
    scale=float(raw.get("scale", 1.0)),
    deadzone=float(raw.get("deadzone", 0.0)),
  )


def _dpad_mapping(value: Any, path: str) -> DpadAxisMapping:
  raw = _mapping(value, path)
  _only_keys(raw, {"index", "scale", "threshold"}, path)
  return DpadAxisMapping(
    index=_integer(raw["index"], f"{path}.index"),
    scale=float(raw.get("scale", 1.0)),
    threshold=float(raw.get("threshold", 0.5)),
  )


def _request_mapping(value: Any, path: str, state_key: str | None = None) -> RequestMapping:
  raw = _mapping(value, path)
  _only_keys(raw, {"buttons", "blocked_by", "request_id", "debug_name", "state_key"}, path)
  state_key = raw.get("state_key", state_key)
  debug_name = raw.get("debug_name", state_key.upper() if isinstance(state_key, str) else None)
  return RequestMapping(
    buttons=_button_tuple(raw["buttons"], f"{path}.buttons"),
    blocked_by=tuple(_integer(item, f"{path}.blocked_by") for item in _sequence(raw.get("blocked_by", ()), f"{path}.blocked_by")),
    request_id=_integer(raw["request_id"], f"{path}.request_id"),
    debug_name=debug_name,
    state_key=state_key,
  )


def _request_mappings(value: Any) -> tuple[RequestMapping, ...]:
  if value is None:
    return ()
  if isinstance(value, Mapping):
    result = []
    for name, item in value.items():
      if not isinstance(name, str) or not name.strip():
        raise PlanetJConfigError("inputs.requests keys must be non-empty state names")
      if item is not None:
        result.append(_request_mapping(item, f"inputs.requests.{name}", name))
    return tuple(result)
  return tuple(
    _request_mapping(item, f"inputs.requests[{index}]")
    for index, item in enumerate(_sequence(value, "inputs.requests"))
  )


def _signal_mapping(value: Any, path: str) -> SignalMapping:
  raw = _mapping(value, path)
  _only_keys(raw, {"buttons", "blocked_by", "signal_id", "debug_name", "hold_after_release_ms"}, path)
  return SignalMapping(
    buttons=_button_tuple(raw["buttons"], f"{path}.buttons"),
    blocked_by=tuple(_integer(item, f"{path}.blocked_by") for item in _sequence(raw.get("blocked_by", ()), f"{path}.blocked_by")),
    signal_id=_integer(raw["signal_id"], f"{path}.signal_id"),
    debug_name=raw["debug_name"],
    hold_after_release_ms=_integer(raw.get("hold_after_release_ms", 0), f"{path}.hold_after_release_ms"),
  )


def load_config(path: str | Path) -> PlanetJConfig:
  from planet_config import resolve_resource
  source_path = resolve_resource(path)
  root = _load_yaml_tree(source_path)
  target = _mapping(root.get("target", {}), "target")
  publisher = _mapping(root.get("publisher", {}), "publisher")
  inputs = _mapping(root.get("inputs", {}), "inputs")
  axes = _mapping(inputs.get("axes", {}), "inputs.axes")
  dpad = _mapping(inputs.get("dpad", {}), "inputs.dpad")
  _only_keys(target, {"host", "port"}, "target")
  _only_keys(publisher, {"hz", "ttl_ms"}, "publisher")
  _only_keys(inputs, {"axes", "dpad", "requests", "signals"}, "inputs")
  _only_keys(axes, set(AXIS_NAMES), "inputs.axes")
  _only_keys(dpad, {"x", "y"}, "inputs.dpad")
  try:
    return PlanetJConfig(
      version=_integer(root.get("version", 4), "version"),
      device=str(root.get("device", "/dev/input/js0")),
      target=TargetConfig(host=str(target.get("host", "127.0.0.1")), port=int(target.get("port", 50560))),
      publisher=PublisherConfig(hz=float(publisher.get("hz", 50.0)), ttl_ms=int(publisher.get("ttl_ms", 100))),
      inputs=InputMapping(
        axes=tuple((name, _axis_mapping(axes[name], f"inputs.axes.{name}")) for name in AXIS_NAMES),
        dpad_x=_dpad_mapping(dpad["x"], "inputs.dpad.x"),
        dpad_y=_dpad_mapping(dpad["y"], "inputs.dpad.y"),
        requests=_request_mappings(inputs.get("requests", ())),
        signals=tuple(_signal_mapping(item, f"inputs.signals[{index}]") for index, item in enumerate(_sequence(inputs.get("signals", ()), "inputs.signals"))),
      ),
      source_path=source_path,
    )
  except (KeyError, TypeError, ValueError) as error:
    if isinstance(error, PlanetJConfigError):
      raise
    raise PlanetJConfigError(f"invalid PlanetJ config value: {error}") from error


__all__ = [
  "AxisMapping", "DpadAxisMapping", "InputMapping", "PlanetJConfig",
  "PlanetJConfigError", "PublisherConfig", "RequestMapping", "SignalMapping",
  "TargetConfig", "load_config",
]
