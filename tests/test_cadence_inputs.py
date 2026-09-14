from contextlib import contextmanager
from dataclasses import replace
import json
import socket
import threading

import pytest
import yaml

from planetj.config import PlanetJConfigError, load_config
from planetj.runtime import check_remote, main
from planetj.upper_stream import (
    DemoSource, JoystickSource, UpperStreamSender, axis_target,
    load_config as load_upper_config, main as upper_main, run as run_upper,
)


def overlay(tmp_path, overrides, base="pkg://planetj/data/cadence.yaml"):
    path = tmp_path / "overlay.yaml"
    path.write_text(yaml.safe_dump({"extends": base, **overrides}))
    return path


def test_named_request_inheritance_disable_and_default_names(tmp_path):
    config = load_config(overlay(tmp_path, {"inputs": {"requests": {
        "loco": {"buttons": [5, 3]}, "passive": None,
        "custom": {"buttons": [4, 0], "request_id": 9},
    }}}))
    bindings = {item.state_key: item for item in config.inputs.requests}
    assert set(bindings) == {"damping", "fixedpos", "loco", "custom"}
    assert bindings["loco"].request_id == 3
    assert bindings["loco"].buttons == (5, 3)
    assert bindings["custom"].debug_name == "CUSTOM"
    assert load_config("pkg://planetj/data/cadence.yaml").inputs.signals == load_config("pkg://planetj/data/xbox.yaml").inputs.signals


def test_named_request_rejects_duplicate_ids(tmp_path):
    path = overlay(tmp_path, {"inputs": {"requests": {
        "custom": {"buttons": [4, 0], "request_id": 3},
    }}})
    with pytest.raises(PlanetJConfigError, match="request IDs"):
        load_config(path)


def test_legacy_list_still_replaces_requests_and_accepts_explicit_state_key(tmp_path):
    config = load_config(overlay(tmp_path, {"inputs": {"requests": [
        {"buttons": [1], "request_id": 3, "state_key": "loco", "debug_name": "WALK"},
    ]}}))
    assert len(config.inputs.requests) == 1
    assert config.inputs.requests[0].state_key == "loco"


@contextmanager
def udp_server(handler):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(0.05)
    endpoint = sock.getsockname()
    stop = threading.Event()

    def serve():
        while not stop.is_set():
            try:
                data, peer = sock.recvfrom(65535)
            except socket.timeout:
                continue
            response = handler(json.loads(data))
            sock.sendto(json.dumps(response).encode(), peer)

    thread = threading.Thread(target=serve)
    thread.start()
    try:
        yield endpoint
    finally:
        stop.set()
        thread.join(1)
        sock.close()
        assert not thread.is_alive()


def description(request):
    assert request["type"] == "describe"
    return {
        "schema": "cadence.operator.v1", "type": "description",
        "states": [{"id": index, "key": key} for index, key in enumerate(("passive", "damping", "fixedpos", "loco"))],
        "aliases": {"lower_loco": "loco"}, "reset_state_id": 0,
        "safety_fallback_state_id": 1,
    }


def test_check_remote_validates_alias_and_reports_mismatch(tmp_path):
    with udp_server(description) as (host, port):
        path = overlay(tmp_path, {
            "target": {"host": host, "port": port},
            "inputs": {"requests": {"loco": {"state_key": "lower_loco"}}},
        })
        assert main(["--config", str(path), "--check-remote"]) == 0
        config = load_config(path)
        wrong = replace(config.inputs.requests[-1], request_id=99)
        config = replace(config, inputs=replace(config.inputs, requests=(wrong,)))
        with pytest.raises(ValueError, match="request 99"):
            check_remote(config)


def test_offline_check_does_not_open_socket_or_joystick(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline check attempted I/O")
    monkeypatch.setattr(socket, "socket", forbidden)
    assert main(["--config", "pkg://planetj/data/cadence.yaml", "--check"]) == 0
    assert upper_main(["--check"]) == 0


def test_remote_check_failure_is_explicit(tmp_path):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        unused = sock.getsockname()[1]
    config = load_config(overlay(tmp_path, {"target": {"port": unused}}))
    with pytest.raises(OSError):
        check_remote(config, timeout_s=0.05)


def test_upper_default_is_fourteen_joints_with_bounded_axis_offsets():
    config = load_upper_config("pkg://planetj/data/cadence_upper_stream.yaml")
    assert len(config.names) == 14
    assert axis_target(config, [0] * 8) == config.initial_position
    target = axis_target(config, [1] * 8)
    assert target[0] == pytest.approx(0.18)
    assert target[3] == pytest.approx(0.95)
    assert all(lo <= q <= hi for q, lo, hi in zip(target, config.position_min, config.position_max))
    sine = DemoSource(config, "sine", 0)
    assert sine.sample(0) == config.initial_position
    assert sine.sample(1)[3] == pytest.approx(0.95)
    scripted = DemoSource(config, "scripted", 0)
    assert scripted.sample(100) == config.scripted_frames[-1]


def test_upper_source_uses_physical_connection_and_stops_on_disconnect():
    config = load_upper_config("pkg://planetj/data/cadence_upper_stream.yaml")
    source = JoystickSource(config)

    class Device:
        connected = True
        axes = [1] * 8
        logical_connected = True  # Represents a separately held emergency signal.
        def poll(self, now):
            pass
        def close(self):
            self.connected = False

    source.device = Device()
    assert source.sample(0) != config.initial_position
    source.device.connected = False
    assert source.sample(1) is None


class SampleSource:
    def __init__(self, target):
        self.target = target
    def sample(self, now):
        return self.target


class Client:
    activation = 11
    fail_send = False
    def __init__(self, n):
        self.n, self.calls = n, []
    def status(self):
        return {"activation": self.activation, "dimension": self.n}
    def send(self, activation, sequence, q_des):
        self.calls.append((activation, sequence, q_des))
        if self.fail_send:
            raise TimeoutError("receipt lost")
        return {"accepted": True}


def test_sender_new_activation_resets_sequence_but_disconnect_never_sends_default():
    config = load_upper_config("pkg://planetj/data/cadence_upper_stream.yaml")
    client = Client(14)
    source = SampleSource(tuple(0.5 for _ in range(14)))
    sender = UpperStreamSender(config, client, source)
    sender.tick(0)
    sender.tick(0.01)
    assert [call[:2] for call in client.calls] == [(11, 0), (11, 1)]
    source.target = None
    sender.tick(0.3)
    assert len(client.calls) == 2
    source.target = config.scripted_frames[-1]
    sender.tick(0.31)
    assert client.calls[-1][:2] == (11, 2)
    client.activation = 12
    sender.tick(0.6)
    assert client.calls[-1][:2] == (12, 0)
    client.activation = None
    sender.tick(1)
    assert client.calls[-1][:2] == (12, 0)


def test_receipt_loss_pauses_and_preserves_sequence_for_same_activation():
    config = load_upper_config("pkg://planetj/data/cadence_upper_stream.yaml")
    client = Client(14)
    sender = UpperStreamSender(config, client, SampleSource(config.initial_position))
    client.fail_send = True
    sender.tick(0)
    sender.tick(0.01)
    assert len(client.calls) == 1
    client.fail_send = False
    sender.tick(0.3)
    assert [call[:2] for call in client.calls] == [(11, 0), (11, 1)]


def test_sender_fails_on_receiver_dimension_mismatch():
    config = load_upper_config("pkg://planetj/data/cadence_upper_stream.yaml")
    sender = UpperStreamSender(config, Client(2), SampleSource(config.initial_position))
    with pytest.raises(ValueError, match="configured 14"):
        sender.tick(0)


def test_explicit_sine_demo_streams_over_udp_without_hardware():
    frames = []
    def receive(request):
        if request["type"] == "status":
            return {"schema": request["schema"], "type": "status", "activation": 21, "dimension": 14}
        frames.append(request)
        return {"schema": request["schema"], "type": "receipt", "accepted": True,
                "activation": request["activation"], "sequence": request["sequence"]}
    with udp_server(receive) as (host, port):
        config = replace(load_upper_config("pkg://planetj/data/cadence_upper_stream.yaml"), host=host, port=port)
        assert run_upper(config, source_kind="sine", duration_s=0.15) == 0
    assert len(frames) >= 3
    assert [frame["sequence"] for frame in frames] == list(range(len(frames)))
    assert frames[0]["q_des"] != frames[-1]["q_des"]


def test_upper_config_supports_another_joint_count_and_rejects_bad_limits(tmp_path):
    axes = {name: None for name in ("left_shoulder_pitch_joint", "left_elbow_joint", "right_shoulder_pitch_joint", "right_elbow_joint")}
    axes["arm"] = {"index": 0, "scale_rad": 0.2, "deadzone": 0.1}
    path = overlay(tmp_path, {
        "joints": {"names": ["arm"], "initial_position": [0.1], "position_min": [-1], "position_max": [1]},
        "axes": axes,
        "demo": {"scripted_frames": [[0.2]]},
    }, "pkg://planetj/data/cadence_upper_stream.yaml")
    config = load_upper_config(path)
    assert len(config.names) == 1
    raw = yaml.safe_load(path.read_text())
    raw["joints"]["position_max"] = [0]
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="initial_position"):
        load_upper_config(path)
