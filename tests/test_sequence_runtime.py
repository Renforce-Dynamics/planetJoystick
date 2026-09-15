"""A delayed upper-target endpoint must not stall PLNJ or emergency signals."""

from dataclasses import replace
from pathlib import Path
import socket
import threading
import time

from planetj.config import load_config
from planetj.protocol import decode_joystick_command, JoystickFlags
from planetj import runtime, sequences


ROOT = Path(__file__).resolve().parents[1]


def test_plnj_and_emergency_keep_running_while_sequence_status_blocks(monkeypatch):
    received = []
    joint_sends = []
    status_started = threading.Event()
    status_finished = threading.Event()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(.02)
    stop = threading.Event()

    def receive():
        while not stop.is_set():
            try:
                packet = decode_joystick_command(sock.recv(65535))
            except socket.timeout:
                continue
            received.append((time.monotonic(), packet, status_started.is_set(), status_finished.is_set()))

    class Device:
        connected = True
        def __init__(self, path):
            self.start = time.monotonic()
            self.buttons, self.axes = [False] * 11, [0.] * 8
        def poll(self, now):
            elapsed = now - self.start
            self.buttons = [False] * 11
            if .04 <= elapsed < .09:
                self.buttons[4] = self.buttons[3] = True
            if .12 <= elapsed < .19:
                self.buttons[8] = True
            if .22 <= elapsed < .29:
                self.buttons[5] = self.buttons[1] = True
        def close(self):
            self.connected = False

    class SlowClient:
        def __init__(self, *args, **kwargs):
            pass
        def status(self):
            status_started.set()
            time.sleep(.3)
            status_finished.set()
            return {"activation": 42, "sequence": None, "state_id": 5,
                    "state_key": "upper_stream", "dimension": 2,
                    "joint_names": ["joint_a", "joint_b"], "q_des": [0., 0.]}
        def send(self, *args):
            joint_sends.append(args)
            raise AssertionError("cancelled sequence sent a joint target")
        def close(self):
            pass

    monkeypatch.setattr(runtime, "LinuxJoystick", Device)
    monkeypatch.setattr(sequences, "JointTargetClient", SlowClient)
    config = load_config(ROOT / "configs/entry/entry_sequences.yaml")
    config = replace(config, target=replace(config.target, host=sock.getsockname()[0], port=sock.getsockname()[1]))
    thread = threading.Thread(target=receive)
    thread.start()
    try:
        runtime.run(config, duration_s=.45)
    finally:
        stop.set()
        thread.join(1)
        sock.close()
    during = [packet for _, packet, begun, finished in received if begun and not finished]
    assert len(during) >= 8, "upper-target I/O stalled normal operator publication"
    assert any(packet.signal_bits & 1 for packet in during)
    assert any(packet.flags & JoystickFlags.REQUEST_VALID and packet.request_id == 1 for packet in during)
    assert not joint_sends
