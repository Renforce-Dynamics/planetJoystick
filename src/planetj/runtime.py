"""Read a Linux joystick and publish generic latest-only PLNJ commands."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
import secrets
import socket
import struct
import time

from .config import InputMapping, PlanetJConfig, PlanetJConfigError, SignalMapping, load_config
from .protocol import JoystickCommandPacket, JoystickFlags, encode_joystick_command


_JS_EVENT = struct.Struct("IhBB")
_JS_EVENT_BUTTON = 0x01
_JS_EVENT_AXIS = 0x02
_JS_EVENT_INIT = 0x80


@dataclass(frozen=True, slots=True)
class MappedCommand:
  flags: JoystickFlags
  request_id: int
  request_debug_name: str | None
  signal_bits: int
  axes: tuple[float, float, float, float, float, float]
  dpad_x: int
  dpad_y: int


@dataclass(slots=True)
class SignalHoldLatch:
  """Keep a configured signal active after a short physical button press."""

  hold_s: float
  active_until_s: float = 0.0

  def trigger(self, now_s: float) -> None:
    self.active_until_s = max(self.active_until_s, float(now_s) + self.hold_s)

  def active(self, now_s: float) -> bool:
    return float(now_s) < self.active_until_s

  def reset(self) -> None:
    self.active_until_s = 0.0


def chord_active(buttons: list[bool], mapping) -> bool:
  return (
    all(button < len(buttons) and buttons[button] for button in mapping.buttons)
    and not any(button < len(buttons) and buttons[button] for button in mapping.blocked_by)
  )


def active_signal_mappings(
  buttons: list[bool], mappings: tuple[SignalMapping, ...],
) -> tuple[SignalMapping, ...]:
  return tuple(mapping for mapping in mappings if chord_active(buttons, mapping))


def _analog(raw_axes: list[float], index: int, scale: float, deadzone: float) -> float:
  raw = raw_axes[index] if index < len(raw_axes) else 0.0
  value = max(-1.0, min(1.0, float(raw) * scale))
  if abs(value) <= deadzone:
    return 0.0
  return max(-1.0, min(1.0, (abs(value) - deadzone) / (1.0 - deadzone))) * (1.0 if value > 0.0 else -1.0)


def _dpad(raw_axes: list[float], index: int, scale: float, threshold: float) -> int:
  raw = raw_axes[index] if index < len(raw_axes) else 0.0
  value = max(-1.0, min(1.0, float(raw) * scale))
  return 1 if value >= threshold else (-1 if value <= -threshold else 0)


def map_operator_input(
  connected: bool,
  buttons: list[bool],
  raw_axes: list[float],
  inputs: InputMapping,
  forced_signal_ids: tuple[int, ...] = (),
) -> MappedCommand:
  if not connected:
    return MappedCommand(JoystickFlags(0), 0, None, 0, (0.0,) * 6, 0, 0)
  flags = JoystickFlags.CONNECTED
  request_id = 0
  request_name = None
  # The most specific chord wins; YAML order breaks ties.
  for _, mapping in sorted(enumerate(inputs.requests), key=lambda item: -len(item[1].buttons)):
    if chord_active(buttons, mapping):
      flags |= JoystickFlags.REQUEST_VALID
      request_id = mapping.request_id
      request_name = mapping.debug_name
      break
  signal_ids = {mapping.signal_id for mapping in active_signal_mappings(buttons, inputs.signals)}
  signal_ids.update(int(signal_id) for signal_id in forced_signal_ids)
  signal_bits = sum(1 << signal_id for signal_id in signal_ids if 0 <= signal_id < 32)
  axes = tuple(_analog(raw_axes, mapping.index, mapping.scale, mapping.deadzone) for _, mapping in inputs.axes)
  return MappedCommand(
    flags, request_id, request_name, signal_bits, axes,
    _dpad(raw_axes, inputs.dpad_x.index, inputs.dpad_x.scale, inputs.dpad_x.threshold),
    _dpad(raw_axes, inputs.dpad_y.index, inputs.dpad_y.scale, inputs.dpad_y.threshold),
  )


class LinuxJoystick:
  def __init__(self, path: str) -> None:
    self.path = str(path)
    self.fd: int | None = None
    self.buttons = [False] * 11
    self.axes = [0.0] * 8
    self._last_open_attempt = 0.0

  @property
  def connected(self) -> bool:
    return self.fd is not None

  def close(self) -> None:
    if self.fd is not None:
      os.close(self.fd)
      self.fd = None
    self.buttons = [False] * len(self.buttons)
    self.axes = [0.0] * len(self.axes)

  def poll(self, now_s: float) -> None:
    if self.fd is None:
      if now_s - self._last_open_attempt < 1.0:
        return
      self._last_open_attempt = now_s
      try:
        self.fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)
      except OSError:
        return
    try:
      while True:
        data = os.read(self.fd, _JS_EVENT.size)
        if len(data) != _JS_EVENT.size:
          raise OSError("short joystick event")
        _, value, event_type, number = _JS_EVENT.unpack(data)
        event_type &= ~_JS_EVENT_INIT
        if event_type == _JS_EVENT_AXIS:
          if number >= len(self.axes):
            self.axes.extend([0.0] * (number + 1 - len(self.axes)))
          self.axes[number] = max(-1.0, min(1.0, float(value) / 32767.0))
        elif event_type == _JS_EVENT_BUTTON:
          if number >= len(self.buttons):
            self.buttons.extend([False] * (number + 1 - len(self.buttons)))
          self.buttons[number] = bool(value)
    except BlockingIOError:
      return
    except OSError:
      self.close()


def _argument_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--config", default="pkg://planetj/data/xbox.yaml")
  parser.add_argument("--check", action="store_true", help="Validate configuration without opening a joystick")
  parser.add_argument("--check-remote", action="store_true", help="Validate bindings against the configured operator endpoint and exit")
  parser.add_argument("--remote-timeout-s", type=float, default=1.0, help="Timeout for --check-remote")
  parser.add_argument("--duration-s", type=float, default=0.0, help="Stop after this duration; 0 runs until interrupted")
  return parser


def parse_args(argv=None):
  return _argument_parser().parse_args(argv)


def run(config: PlanetJConfig, duration_s: float = 0.0) -> int:
  publisher = config.publisher
  joystick = LinuxJoystick(config.device)
  transport = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  transport.connect((config.target.host, config.target.port))
  session_id = secrets.randbits(32)
  sequence = 0
  signal_sequence = 0
  previous_connected: bool | None = None
  previous_request: tuple[int, str] | None = None
  previous_direct_signals: set[int] = set()
  latches = {
    mapping.signal_id: SignalHoldLatch(mapping.hold_after_release_ms / 1000.0)
    for mapping in config.inputs.signals if mapping.hold_after_release_ms > 0
  }
  next_tick = time.monotonic()
  started = next_tick
  print(
    f"[PlanetJ] config={config.source_path} device={config.device} "
    f"target={config.target.host}:{config.target.port} protocol=PLNJ-v3"
  )
  try:
    while duration_s <= 0 or time.monotonic() - started < duration_s:
      now = time.monotonic()
      joystick.poll(now)
      active_mappings = active_signal_mappings(joystick.buttons, config.inputs.signals)
      direct_signals = {mapping.signal_id for mapping in active_mappings}
      rising_signals = direct_signals - previous_direct_signals
      if rising_signals:
        signal_sequence = (signal_sequence + 1) & 0xFFFFFFFF
        for mapping in active_mappings:
          if mapping.signal_id in rising_signals:
            print(f"[PlanetJ] signal id={mapping.signal_id} name={mapping.debug_name} seq={signal_sequence}")
      previous_direct_signals = direct_signals
      for mapping in active_mappings:
        latch = latches.get(mapping.signal_id)
        if latch is not None:
          latch.trigger(now)
      held_signals = tuple(signal_id for signal_id, latch in latches.items() if latch.active(now))
      logical_connected = joystick.connected or bool(held_signals)
      command = map_operator_input(
        logical_connected, joystick.buttons, joystick.axes, config.inputs, held_signals,
      )
      if joystick.connected != previous_connected:
        state = "connected" if joystick.connected else "disconnected; controls=zero"
        print(f"[PlanetJ] joystick {state}")
        previous_connected = joystick.connected
      request = None if command.request_debug_name is None else (command.request_id, command.request_debug_name)
      if request != previous_request:
        if request is not None:
          print(f"[PlanetJ] request id={request[0]} name={request[1]}")
        previous_request = request
      packet = JoystickCommandPacket(
        session_id=session_id, packet_seq=sequence, source_age_us=0,
        ttl_ms=publisher.ttl_ms, flags=command.flags,
        request_id=command.request_id, signal_bits=command.signal_bits,
        signal_seq=signal_sequence, axes=command.axes,
        dpad_x=command.dpad_x, dpad_y=command.dpad_y,
      )
      sequence = (sequence + 1) & 0xFFFFFFFF
      try:
        transport.send(encode_joystick_command(packet))
      except OSError:
        pass
      next_tick += 1.0 / publisher.hz
      time.sleep(max(0.0, next_tick - time.monotonic()))
      if next_tick < time.monotonic() - 1.0 / publisher.hz:
        next_tick = time.monotonic()
  except KeyboardInterrupt:
    return 0
  finally:
    joystick.close()
    transport.close()


def main(argv=None) -> int:
  parser = _argument_parser()
  args = parser.parse_args(argv)
  try:
    config = load_config(args.config)
  except PlanetJConfigError as error:
    parser.error(str(error))
  if args.check_remote:
    try:
      check_remote(config, timeout_s=args.remote_timeout_s)
    except (OSError, ValueError) as error:
      parser.error(f"remote binding check failed: {error}")
    print(f"PlanetJ remote bindings valid: {config.target.host}:{config.target.port}")
    return 0
  if args.check:
    print(f"PlanetJ configuration valid: {config.source_path}")
    return 0
  return run(config, args.duration_s)


def check_remote(config: PlanetJConfig, *, timeout_s: float = 1.0):
  """Describe the live catalog without publishing a state request or opening input."""
  from planet_protocol.client import OperatorClient
  missing = [mapping.debug_name for mapping in config.inputs.requests if mapping.state_key is None]
  if missing:
    raise PlanetJConfigError(
      "remote checks require state_key on legacy list bindings: " + ", ".join(missing)
      + "; alternatively use a mapping keyed by state name"
    )
  with OperatorClient(config.target.host, config.target.port, timeout_s=timeout_s) as client:
    return client.validate_bindings([
      (mapping.request_id, mapping.state_key) for mapping in config.inputs.requests
    ])
