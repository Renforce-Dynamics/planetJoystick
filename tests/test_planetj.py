from pathlib import Path

import pytest
import yaml

from planetj.config import PlanetJConfigError, load_config
from planetj.protocol import (
  JoystickCommandPacket, JoystickFlags,
  decode_joystick_command, encode_joystick_command,
)
from planetj.runtime import SignalHoldLatch, map_operator_input, parse_args


def test_planetj_yaml_profiles_load():
  local = load_config("tests/fixtures/configs/common/planetj.yaml")
  with_fast_rally = load_config("tests/fixtures/configs/common/planetj_with_fast_rally.yaml")
  assert local.version == 4
  assert local.target.host == "127.0.0.1"
  assert {item.request_id for item in local.inputs.requests} == set(range(8))
  assert {item.request_id for item in with_fast_rally.inputs.requests} == set(range(9))
  assert {item.signal_id for item in local.inputs.signals} == {0, 1}
  assert with_fast_rally.inputs.signals == local.inputs.signals

  real = load_config("tests/fixtures/configs/a3/sites/ad201/planetj.yaml")
  assert real.target.host == "192.168.120.121"
  assert real.inputs == local.inputs

  for site in ("ad201", "iceribbon", "icefinal"):
    default = load_config(f"tests/fixtures/configs/a3/sites/{site}/planetj.yaml")
    blue = load_config(f"tests/fixtures/configs/a3/sites/{site}/planetj_blue.yaml")
    white = load_config(f"tests/fixtures/configs/a3/sites/{site}/planetj_white.yaml")
    expected_default = white if site == "icefinal" else blue
    assert default.target.host == expected_default.target.host
    assert blue.target.host == "192.168.120.121"
    assert white.target.host == "192.168.120.122"
    expected_inputs = with_fast_rally.inputs if site == "icefinal" else local.inputs
    assert default.inputs == blue.inputs == white.inputs == expected_inputs

  sim = load_config("tests/fixtures/configs/a3/sites/mujoco/planetj.yaml")
  assert sim.target.host == "127.0.0.1"
  assert sim.inputs == local.inputs


def test_planetj_extends_deep_merges_mappings_and_replaces_lists(tmp_path):
  base = tmp_path / "base.yaml"
  base.write_text(Path("tests/fixtures/configs/common/planetj.yaml").read_text(), encoding="utf-8")
  child = tmp_path / "child.yaml"
  child.write_text(
    "extends: base.yaml\n"
    "target:\n  host: 10.0.0.2\n"
    "inputs:\n  signals: []\n",
    encoding="utf-8",
  )
  config = load_config(child)
  assert (config.target.host, config.target.port) == ("10.0.0.2", 50560)
  assert config.inputs.requests
  assert config.inputs.signals == ()


def test_planetj_extends_rejects_cycle(tmp_path):
  first = tmp_path / "first.yaml"
  second = tmp_path / "second.yaml"
  first.write_text("extends: second.yaml\n", encoding="utf-8")
  second.write_text("extends: first.yaml\n", encoding="utf-8")
  with pytest.raises(PlanetJConfigError, match="extends cycle"):
    load_config(first)


def test_planetj_config_rejects_unknown_keys(tmp_path):
  path = tmp_path / "planetj.yaml"
  path.write_text("version: 4\nunknown: true\n", encoding="utf-8")
  with pytest.raises(PlanetJConfigError, match="unknown keys: unknown"):
    load_config(path)


def test_planetj_config_rejects_duplicate_request_ids(tmp_path):
  raw = yaml.safe_load(Path("tests/fixtures/configs/common/planetj.yaml").read_text())
  raw["inputs"]["requests"][1]["request_id"] = 6
  path = tmp_path / "planetj.yaml"
  path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
  with pytest.raises(PlanetJConfigError, match="request IDs must be unique"):
    load_config(path)


def test_request_ids_and_debug_names_are_config_driven():
  config = load_config("tests/fixtures/configs/common/planetj.yaml")
  buttons = [False] * 11
  buttons[5] = buttons[4] = True
  hold_static = map_operator_input(True, buttons, [0.0] * 8, config.inputs)
  assert hold_static.flags & JoystickFlags.REQUEST_VALID
  assert (hold_static.request_id, hold_static.request_debug_name) == (
    4, "HOLD_STATIC"
  )

  buttons = [False] * 11
  buttons[4] = buttons[0] = True
  serve = map_operator_input(True, buttons, [0.0] * 8, config.inputs)
  assert (serve.request_id, serve.request_debug_name) == (6, "SERVE")

  # RB blocks SERVE so RB+A remains the unambiguous FIXEDPOS chord.
  buttons[5] = True
  fixedpos = map_operator_input(True, buttons, [0.0] * 8, config.inputs)
  assert (fixedpos.request_id, fixedpos.request_debug_name) == (2, "FIXEDPOS")


def test_fast_rally_profile_maps_lb_y_and_keeps_rb_y_strike():
  config = load_config("tests/fixtures/configs/common/planetj_with_fast_rally.yaml")
  buttons = [False] * 11
  buttons[4] = buttons[3] = True
  fast_rally = map_operator_input(True, buttons, [0.0] * 8, config.inputs)
  assert (fast_rally.request_id, fast_rally.request_debug_name) == (
    8, "FAST_RALLY"
  )

  # RB blocks the LB+Y chord, so holding both shoulders preserves RB+Y STRIKE.
  buttons[5] = True
  strike = map_operator_input(True, buttons, [0.0] * 8, config.inputs)
  assert (strike.request_id, strike.request_debug_name) == (7, "STRIKE")

  # The original two-shoulder chord remains HOLD_STATIC when Y is released.
  buttons[3] = False
  hold_static = map_operator_input(True, buttons, [0.0] * 8, config.inputs)
  assert (hold_static.request_id, hold_static.request_debug_name) == (
    4, "HOLD_STATIC"
  )


def test_signals_axes_and_dpad_are_generic_inputs():
  config = load_config("tests/fixtures/configs/common/planetj.yaml")
  buttons = [False] * 11
  buttons[8] = True
  axes = [0.0] * 8
  axes[0] = 0.56
  axes[1] = -1.0
  axes[3] = -0.5
  axes[6] = -1.0
  axes[7] = -1.0
  command = map_operator_input(True, buttons, axes, config.inputs)
  assert command.signal_bits == 1
  assert command.axes[0] == pytest.approx(0.5)
  assert command.axes[1] == pytest.approx(1.0)
  assert command.axes[2] == pytest.approx(-0.43181818)
  assert command.dpad_x == -1
  assert command.dpad_y == 1

  # A request chord is independent of the generic emergency signal.
  buttons[8] = False
  buttons[0] = True
  buttons[5] = True
  command = map_operator_input(True, buttons, axes, config.inputs)
  assert command.signal_bits == 0
  assert command.request_id == 2


def test_disconnected_input_is_zero_and_forced_signal_can_be_repeated():
  config = load_config("tests/fixtures/configs/common/planetj.yaml")
  disconnected = map_operator_input(
    False, [True] * 11, [1.0] * 8, config.inputs, (0,),
  )
  assert disconnected.flags == 0
  assert disconnected.signal_bits == 0
  assert disconnected.axes == (0.0,) * 6

  repeated = map_operator_input(
    True, [False] * 11, [0.0] * 8, config.inputs, (0,),
  )
  assert repeated.signal_bits == 1


def test_signal_hold_latch():
  latch = SignalHoldLatch(hold_s=0.5)
  latch.trigger(10.0)
  assert latch.active(10.49)
  assert not latch.active(10.5)
  latch.trigger(11.0)
  latch.reset()
  assert not latch.active(11.0)


def test_planetj_cli_only_selects_config():
  args = parse_args([])
  assert args.config == "pkg://planetj/data/xbox.yaml"
  with pytest.raises(SystemExit):
    parse_args(["--stroke", "forehand"])


def test_planetj_v3_protocol_round_trip_crc_and_golden_packet():
  packet = JoystickCommandPacket(
    session_id=0x01020304, packet_seq=7, source_age_us=1234, ttl_ms=100,
    flags=JoystickFlags.CONNECTED | JoystickFlags.REQUEST_VALID,
    request_id=8, signal_bits=5, signal_seq=42,
    axes=(0.25, -0.5, 0.75, -1.0, 0.0, 1.0),
    dpad_x=-1, dpad_y=1,
  )
  raw = encode_joystick_command(packet)
  assert len(raw) == 72
  assert decode_joystick_command(raw) == packet
  fixture = Path("tests/fixtures/planetj_v3.hex")
  if fixture.exists():
    assert raw == bytes.fromhex(fixture.read_text().strip())
  damaged = bytearray(raw)
  damaged[30] ^= 1
  with pytest.raises(ValueError, match="crc"):
    decode_joystick_command(damaged)
