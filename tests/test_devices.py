"""Native SDL virtual hardware verifies mapping, hotplug and real PLNJ output."""

import ctypes
from dataclasses import replace
from pathlib import Path
import socket
import sys

import pytest
import yaml

from planetj import devices, runtime
from planetj.config import PlanetJConfigError, load_config
from planetj.protocol import JoystickFlags, decode_joystick_command
from planetj.upper_stream import JoystickSource, load_config as load_upper_config

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("platform,expected", [("darwin", "sdl:auto"), ("linux", "/dev/input/js0")])
def test_auto_device_and_explicit_overrides(platform, expected, monkeypatch):
    monkeypatch.setattr(devices.sys, "platform", platform)
    assert devices.resolve_device("auto") == expected
    assert devices.resolve_device("sdl:2") == "sdl:2"
    assert devices.resolve_device("/tmp/virtual-gamepad") == "/tmp/virtual-gamepad"


@pytest.mark.parametrize("selector", [None, False, 2, "", "sdl:", "sdl:-1", "sdl:1.5", "sdl:two"])
def test_bad_device_selection_fails_offline(selector, tmp_path):
    entry = tmp_path / "invalid.yaml"
    entry.write_text(yaml.safe_dump({"extends": str(ROOT / "configs/entry/entry_operator.yaml"),
                                    "device": selector}))
    with pytest.raises(PlanetJConfigError, match="device"):
        load_config(entry)


def test_macos_offline_check_needs_no_sdl_or_network(monkeypatch):
    monkeypatch.setattr(devices.sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "pygame", None)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("offline check opened network"))
    assert runtime.main(["--config", str(ROOT / "configs/entry/entry_operator.yaml"), "--check"]) == 0
    with pytest.raises(ValueError, match="requires pygame-ce"):
        devices.create_joystick("auto")


class VirtualSDL:
    """Drive SDL's own virtual joystick API; no fake pygame/controller methods."""

    def __init__(self, pg, controllers):
        self.pg, self.controllers = pg, controllers
        self.lib = ctypes.CDLL(controllers.__file__)
        for name, result, args in (
            ("SDL_JoystickAttachVirtual", ctypes.c_int, [ctypes.c_int] * 4),
            ("SDL_JoystickOpen", ctypes.c_void_p, [ctypes.c_int]),
            ("SDL_JoystickSetVirtualAxis", ctypes.c_int, [ctypes.c_void_p, ctypes.c_int, ctypes.c_int16]),
            ("SDL_JoystickSetVirtualButton", ctypes.c_int, [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint8]),
            ("SDL_JoystickClose", None, [ctypes.c_void_p]),
            ("SDL_JoystickDetachVirtual", ctypes.c_int, [ctypes.c_int]),
        ):
            function = getattr(self.lib, name)
            function.restype, function.argtypes = result, args
        self.pointer = self.index = None
        self.attach()

    def attach(self):
        self.index = self.lib.SDL_JoystickAttachVirtual(1, 6, 15, 0)
        assert self.index >= 0
        self.pointer = self.lib.SDL_JoystickOpen(self.index)
        assert self.pointer
        self.axis("TRIGGERLEFT", -32768)
        self.axis("TRIGGERRIGHT", -32768)
        self.pg.event.get()
        assert self.controllers.is_controller(self.index)

    def axis(self, name, value):
        index = getattr(self.pg, "CONTROLLER_AXIS_" + name)
        assert self.lib.SDL_JoystickSetVirtualAxis(self.pointer, index, value) == 0

    def buttons(self, *names):
        active = {getattr(self.pg, "CONTROLLER_BUTTON_" + name) for name in names}
        for i in range(15):
            assert self.lib.SDL_JoystickSetVirtualButton(self.pointer, i, int(i in active)) == 0

    def detach(self):
        if self.pointer is not None:
            self.lib.SDL_JoystickClose(self.pointer)
            assert self.lib.SDL_JoystickDetachVirtual(self.index) == 0
            self.pointer = self.index = None


@pytest.fixture
def hardware(monkeypatch):
    monkeypatch.setenv("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
    pg = pytest.importorskip("pygame", reason="install planetj[sdl] for native SDL tests")
    from pygame._sdl2 import controller
    pg.display.init()
    controller.init()
    virtual = VirtualSDL(pg, controller)
    try:
        yield virtual
    finally:
        virtual.detach()
        controller.quit()
        pg.display.quit()


@pytest.fixture
def gamepad(hardware):
    device = devices.create_joystick(f"sdl:{hardware.index}")
    try:
        yield device
    finally:
        device.close()


@pytest.mark.parametrize("pressed,expected", [
    (("A", "RIGHTSHOULDER"), [0, 5]),
    (("B", "RIGHTSHOULDER"), [1, 5]),
    (("X", "RIGHTSHOULDER"), [2, 5]),
    (("Y", "RIGHTSHOULDER"), [3, 5]),
    (("X", "LEFTSHOULDER"), [2, 4]),
    (("BACK", "LEFTSHOULDER"), [4, 6]),
    (("START", "LEFTSHOULDER"), [4, 7]),
    (("GUIDE",), [8]),
    (("LEFTSTICK", "RIGHTSTICK"), [9, 10]),
])
def test_native_sdl_buttons_preserve_linux_xbox_chords(hardware, gamepad, pressed, expected):
    hardware.buttons(*pressed)
    gamepad.poll(1.)
    assert gamepad.connected
    assert [i for i, down in enumerate(gamepad.buttons) if down] == expected


def test_native_sticks_triggers_and_dpad_match_existing_config(hardware, gamepad):
    gamepad.poll(0.)
    assert gamepad.connected and gamepad.axes == [0., 0., -1., 0., 0., -1., 0., 0.]
    hardware.axis("LEFTX", 16384)
    hardware.axis("LEFTY", -32768)
    hardware.axis("RIGHTX", 32767)
    hardware.axis("RIGHTY", -16384)
    hardware.axis("TRIGGERRIGHT", 32767)
    hardware.buttons("DPAD_UP", "DPAD_RIGHT")
    gamepad.poll(1.)
    assert gamepad.axes == pytest.approx([.50001526, -1., -1., 1., -.50001526, 1., 1., -1.])
    config = load_config(ROOT / "configs/xbox.yaml")
    command = runtime.map_operator_input(True, gamepad.buttons, gamepad.axes, config.inputs)
    assert command.dpad_x == command.dpad_y == 1
    assert command.axes[1] == 1. and command.axes[3] > 0
    assert command.axes[4:] == (-1., 1.)
    hardware.buttons("DPAD_DOWN", "DPAD_LEFT")
    gamepad.poll(1.02)
    command = runtime.map_operator_input(True, gamepad.buttons, gamepad.axes, config.inputs)
    assert command.dpad_x == command.dpad_y == -1


def test_hotplug_clears_controls_before_reconnecting(hardware):
    device = devices.create_joystick("sdl:auto")
    try:
        hardware.buttons("RIGHTSHOULDER", "X", "GUIDE")
        hardware.axis("LEFTY", -32768)
        device.poll(1.)
        assert device.connected and any(device.buttons)
        hardware.detach()
        device.poll(1.02)
        assert not device.connected and not any(device.buttons) and device.axes == [0.] * 8
        hardware.attach()
        device.poll(1.04)
        assert not device.connected  # A new device cannot hide the disconnect frame.
        device.poll(2.1)
        assert device.connected and not any(device.buttons)
        assert device.axes == [0., 0., -1., 0., 0., -1., 0., 0.]
    finally:
        device.close()


def test_unplug_during_read_does_not_keep_a_partial_sample(hardware, gamepad):
    hardware.buttons("GUIDE")
    gamepad.poll(1.)
    previous = gamepad._controller
    class Disappearing:
        def attached(self):
            return True
        def get_button(self, index):
            raise hardware.pg.error("device removed during read")
        def quit(self):
            previous.quit()
    gamepad._controller = Disappearing()
    gamepad.poll(1.02)
    assert not gamepad.connected and gamepad.axes == [0.] * 8 and not any(gamepad.buttons)


def test_native_input_reaches_real_plnj_packets(hardware):
    hardware.buttons("RIGHTSHOULDER", "X", "GUIDE", "DPAD_RIGHT")
    hardware.axis("LEFTY", -32768)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(.05)
        config = load_config(ROOT / "configs/entry/entry_operator.yaml")
        config = replace(config, device=f"sdl:{hardware.index}", target=replace(config.target, port=receiver.getsockname()[1]))
        runtime.run(config, duration_s=.12)
        packets = []
        while True:
            try:
                packets.append(decode_joystick_command(receiver.recv(65535)))
            except socket.timeout:
                break
    assert len(packets) >= 4
    assert all(p.flags & JoystickFlags.CONNECTED and p.flags & JoystickFlags.REQUEST_VALID for p in packets)
    assert all(p.request_id == 3 and p.signal_bits == 1 and p.dpad_x == 1 and p.axes[1] == 1. for p in packets)
    assert [p.packet_seq for p in packets] == list(range(len(packets)))


def test_list_and_monitor_never_open_network_or_play_sequences(hardware, monkeypatch, tmp_path, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("local input inspection opened a publisher")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(runtime, "_sequence_player", forbidden)
    hardware.buttons("RIGHTSHOULDER", "X")
    entry = tmp_path / "sdl.yaml"
    entry.write_text(yaml.safe_dump({"extends": str(ROOT / "configs/entry/entry_operator.yaml"), "device": "sdl:auto"}))
    assert runtime.main(["--config", str(entry), "--list-devices"]) == 0
    assert f"sdl:{hardware.index}:" in capsys.readouterr().out
    assert runtime.main(["--config", str(entry), "--monitor", "--duration-s", ".03"]) == 0
    output = capsys.readouterr().out
    assert "buttons=[2, 5]" in output and "request=3:LOCO" in output


def test_upper_stream_uses_same_native_backend_and_stops_on_disconnect(hardware):
    config = replace(load_upper_config(ROOT / "configs/entry/entry_upper_stream.yaml"), device="sdl:auto")
    source = JoystickSource(config)
    try:
        hardware.axis("LEFTY", -32768)
        assert source.sample(1.) != config.initial_position
        hardware.detach()
        assert source.sample(1.02) is None
    finally:
        source.close()
