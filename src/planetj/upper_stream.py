"""Continuously publish upper-joint position targets from a local input device.

This producer owns no robot state machine, PD gains or timeout fallback. While
input is disconnected it sends no targets, leaving the receiver's last target
intact. Demonstration sources require an explicit --source selection.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from pathlib import Path
import time

from planet_config import load_config as load_composed_config

from .runtime import LinuxJoystick, _analog


def _mapping(value, keys, name):
    if not isinstance(value, Mapping) or set(value) != set(keys):
        raise ValueError(f"{name} requires exactly {', '.join(sorted(keys))}")
    return value


def _number(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be finite")
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _vector(value, dimension, name):
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != dimension:
        raise ValueError(f"{name} requires {dimension} joint values")
    return tuple(_number(item, name) for item in value)


@dataclass(frozen=True, slots=True)
class AxisDrive:
    joint: int
    index: int
    scale_rad: float
    deadzone: float


@dataclass(frozen=True, slots=True)
class UpperStreamConfig:
    host: str
    port: int
    device: str
    hz: float
    status_hz: float
    timeout_s: float
    names: tuple[str, ...]
    initial_position: tuple[float, ...]
    position_min: tuple[float, ...]
    position_max: tuple[float, ...]
    axes: tuple[AxisDrive, ...]
    sine_hz: float
    scripted_frames: tuple[tuple[float, ...], ...]
    source_path: Path


def load_config(path) -> UpperStreamConfig:
    if "://" in str(path):
        raise ValueError("configuration must be an explicit filesystem entry")
    source = Path(path).expanduser().resolve()
    raw = load_composed_config(source).data
    _mapping(raw, {"version", "target", "device", "publisher", "joints", "axes", "demo"}, "upper stream")
    if raw["version"] != 1 or isinstance(raw["version"], bool):
        raise ValueError("upper stream version must be 1")
    target = _mapping(raw["target"], {"host", "port"}, "target")
    if not isinstance(target["host"], str) or not target["host"].strip():
        raise ValueError("target.host must be a nonempty hostname or IP address")
    port = target["port"]
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("target.port must be an integer in [1, 65535]")
    if not isinstance(raw["device"], str) or not raw["device"].strip():
        raise ValueError("device must be a nonempty path")
    publisher = _mapping(raw["publisher"], {"hz", "status_hz", "timeout_s"}, "publisher")
    hz, status_hz, timeout = (_number(publisher[key], f"publisher.{key}") for key in ("hz", "status_hz", "timeout_s"))
    if min(hz, status_hz, timeout) <= 0 or status_hz > hz:
        raise ValueError("publisher frequencies/timeout must be positive and status_hz <= hz")
    joints = _mapping(raw["joints"], {"names", "initial_position", "position_min", "position_max"}, "joints")
    if not isinstance(joints["names"], list) or not joints["names"]:
        raise ValueError("joints.names must be a nonempty list")
    names = tuple(joints["names"])
    if any(not isinstance(name, str) or not name.strip() for name in names) or len(set(names)) != len(names):
        raise ValueError("joints.names must be unique nonempty strings")
    n = len(names)
    initial, low, high = (_vector(joints[key], n, f"joints.{key}") for key in ("initial_position", "position_min", "position_max"))
    if any(not lo <= q <= hi for q, lo, hi in zip(initial, low, high)):
        raise ValueError("initial_position must lie within ordered position limits")
    if not isinstance(raw["axes"], Mapping):
        raise ValueError("axes must map joint names to axis settings")
    axes = []
    for name, settings in raw["axes"].items():
        if settings is None:
            continue
        if name not in names:
            raise ValueError(f"axes names unknown joint {name!r}")
        settings = _mapping(settings, {"index", "scale_rad", "deadzone"}, f"axes.{name}")
        index = settings["index"]
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError(f"axes.{name}.index must be a nonnegative integer")
        scale = _number(settings["scale_rad"], f"axes.{name}.scale_rad")
        deadzone = _number(settings["deadzone"], f"axes.{name}.deadzone")
        if scale == 0 or not 0 <= deadzone < 1:
            raise ValueError("axis scale must be nonzero and deadzone in [0, 1)")
        axes.append(AxisDrive(names.index(name), index, scale, deadzone))
    demo = _mapping(raw["demo"], {"sine_hz", "scripted_frames"}, "demo")
    sine_hz = _number(demo["sine_hz"], "demo.sine_hz")
    if sine_hz <= 0:
        raise ValueError("demo.sine_hz must be positive")
    if not isinstance(demo["scripted_frames"], list) or not demo["scripted_frames"]:
        raise ValueError("demo.scripted_frames must be a nonempty frame list")
    scripted = tuple(_vector(frame, n, "demo.scripted_frames") for frame in demo["scripted_frames"])
    if any(not lo <= q <= hi for frame in scripted for q, lo, hi in zip(frame, low, high)):
        raise ValueError("scripted target exceeds configured joint limits")
    return UpperStreamConfig(target["host"], port, raw["device"], hz, status_hz, timeout,
                             names, initial, low, high, tuple(axes), sine_hz, scripted, source)


def axis_target(config, raw_axes):
    target = list(config.initial_position)
    for mapping in config.axes:
        value = _analog(raw_axes, mapping.index, 1.0, mapping.deadzone)
        target[mapping.joint] += value * mapping.scale_rad
    return tuple(max(lo, min(hi, q)) for q, lo, hi in zip(target, config.position_min, config.position_max))


class JoystickSource:
    def __init__(self, config):
        self.config = config
        self.device = LinuxJoystick(config.device)

    def sample(self, now_s):
        self.device.poll(now_s)
        # PLNJ's logical CONNECTED may outlive a device for an emergency latch;
        # upper targets depend solely on the physical device connection.
        if not self.device.connected:
            return None
        return axis_target(self.config, self.device.axes)

    def close(self):
        self.device.close()


class DemoSource:
    def __init__(self, config, kind, started_s):
        self.config, self.kind, self.started_s = config, kind, started_s

    def sample(self, now_s):
        elapsed = max(0.0, now_s - self.started_s)
        if self.kind == "scripted":
            return self.config.scripted_frames[min(int(elapsed * self.config.hz), len(self.config.scripted_frames) - 1)]
        sine = math.sin(2 * math.pi * self.config.sine_hz * elapsed)
        target = list(self.config.initial_position)
        for mapping in self.config.axes:
            target[mapping.joint] += mapping.scale_rad * sine
        return tuple(max(lo, min(hi, q)) for q, lo, hi in zip(target, self.config.position_min, self.config.position_max))

    def close(self):
        pass


class UpperStreamSender:
    """One latest sample per tick; sequences survive transport reconnects."""

    def __init__(self, config, client, source):
        self.config, self.client, self.source = config, client, source
        self.activation = None
        self.sequence = 0
        self.available = False
        self.next_status_s = -math.inf
        self.sent = 0
        self.accepted = 0

    def tick(self, now_s):
        if now_s >= self.next_status_s:
            self.next_status_s = now_s + 1 / self.config.status_hz
            try:
                status = self.client.status()
            except OSError:
                self.available = False
            else:
                if status["dimension"] != len(self.config.names):
                    raise ValueError(f"receiver has {status['dimension']} joints; configured {len(self.config.names)}")
                if status.get("joint_names") is not None and tuple(status["joint_names"]) != self.config.names:
                    raise ValueError("receiver joint order differs from configured joints.names")
                activation = status["activation"]
                if activation != self.activation:
                    self.activation, self.sequence = activation, 0
                if status.get("sequence") is not None:
                    self.sequence = max(self.sequence, status["sequence"] + 1)
                self.available = activation is not None
        target = self.source.sample(now_s)
        if target is None or not self.available:
            return None
        sequence = self.sequence
        # A lost receipt may still mean the receiver accepted this sequence.
        self.sequence += 1
        self.sent += 1
        try:
            receipt = self.client.send(self.activation, sequence, target)
        except OSError:
            self.available = False
            return None
        if receipt["accepted"]:
            self.accepted += 1
        elif receipt.get("reason") == "invalid":
            raise ValueError("receiver rejected target: " + receipt.get("error", "invalid joint positions"))
        else:
            self.available = False
            self.next_status_s = now_s
        return receipt


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Explicit entry YAML, e.g. configs/entry/entry_upper_stream.yaml")
    parser.add_argument("--source", choices=("joystick", "sine", "scripted"), default="joystick")
    parser.add_argument("--duration-s", type=float, default=0.0)
    parser.add_argument("--check", action="store_true", help="validate config offline and exit")
    return parser


def run(config, *, source_kind="joystick", duration_s=0.0):
    from planet_protocol.client import JointTargetClient
    if not math.isfinite(duration_s) or duration_s < 0:
        raise ValueError("duration_s must be finite and nonnegative")
    if source_kind not in {"joystick", "sine", "scripted"}:
        raise ValueError("unknown input source")
    started = next_tick = time.monotonic()
    source = JoystickSource(config) if source_kind == "joystick" else DemoSource(config, source_kind, started)
    try:
        with JointTargetClient(config.host, config.port, timeout_s=config.timeout_s) as client:
            sender = UpperStreamSender(config, client, source)
            print(f"[planetj-upper] source={source_kind} joints={len(config.names)} udp={config.host}:{config.port}")
            while duration_s == 0 or time.monotonic() - started < duration_s:
                sender.tick(time.monotonic())
                next_tick += 1 / config.hz
                now = time.monotonic()
                if next_tick < now:
                    next_tick = now
                time.sleep(max(0.0, next_tick - now))
            print(f"[planetj-upper] sent={sender.sent} received={sender.accepted}")
    except KeyboardInterrupt:
        return 0
    finally:
        source.close()
    return 0


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if args.check:
            print(f"Upper stream configuration valid: {config.source_path}")
            return 0
        return run(config, source_kind=args.source, duration_s=args.duration_s)
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
