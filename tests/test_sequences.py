from dataclasses import replace
from pathlib import Path
import threading
import time

import numpy as np
import pytest

import planetj.sequences as module
from planetj.sequences import JointSequence, SequenceConfig, SequencePlayer, SequenceSpec


def values():
    return {"time_s": np.array([0, .07, .13]),
            "joint_pos": np.array([[.1, -.1], [.2, -.3], [.5, -.4]]),
            "joint_names": np.array(["joint_a", "joint_b"])}


def configuration(tmp_path, **overrides):
    path = tmp_path / "motion.npz"
    np.savez(path, **values())
    spec = SequenceSpec("motion", path, (4, 0), (5,), 4, "stream",
                        entry_duration_s=.04, playback_speed=1)
    raw = dict(target_host="127.0.0.1", target_port=15100, sequences=(spec,),
               hz=120, status_hz=60, timeout_s=.01, cancel_buttons=(4, 1), cancel_blocked_by=(5,))
    raw.update(overrides)
    return SequenceConfig(**raw)


def buttons(*pressed):
    return tuple(index in pressed for index in range(11))


def wait_for(predicate, timeout=1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.002)
    raise AssertionError("sequence worker did not reach expected condition")


class Receiver:
    """In-memory endpoint with bounded RPC faults; no physical I/O."""

    def __init__(self):
        self.lock = threading.Lock()
        self.metadata = {"activation": 123456789, "dimension": 2,
                         "state_id": 4, "state_key": "stream",
                         "joint_names": ["joint_b", "joint_a"],
                         "q_des": [-.8, .7], "sequence": None}
        self.sent, self.exchanges, self.clients = [], [], []
        self.status_entered = threading.Event()
        self.status_gate = None
        self.lose_first = self.lose_final = False
        self.lost = False
        self.wrong_receipt = False

    def factory(self, host, port, timeout_s):
        receiver = self

        class Client:
            closed = False

            def status(self):
                receiver.status_entered.set()
                if receiver.status_gate is not None:
                    receiver.status_gate.wait(1)
                with receiver.lock:
                    receiver.exchanges.append((id(self), "status"))
                    return dict(receiver.metadata)

            def send(self, activation, sequence, target):
                target = np.asarray(target).copy()
                with receiver.lock:
                    receiver.exchanges.append((id(self), "send", sequence))
                    receiver.sent.append((activation, sequence, target, time.monotonic(), id(self)))
                    previous = receiver.metadata["sequence"]
                    accepted = (activation == receiver.metadata["activation"]
                                and (previous is None or sequence > previous))
                    if accepted:
                        receiver.metadata["sequence"] = sequence
                        receiver.metadata["q_des"] = target.tolist()
                    final = np.array_equal(target, [-.4, .5])
                    lose = not receiver.lost and (receiver.lose_first or (receiver.lose_final and final))
                    if lose:
                        receiver.lost = True
                if lose:
                    time.sleep(.08)
                    raise TimeoutError("receipt lost after receiver accepted frame")
                return {"accepted": accepted, "activation": activation - 1 if receiver.wrong_receipt else activation,
                        "sequence": sequence}

            def close(self):
                self.closed = True

        client = Client()
        self.clients.append(client)
        return client


@pytest.fixture
def receiver(monkeypatch):
    result = Receiver()
    monkeypatch.setattr(module, "JointTargetClient", result.factory)
    return result


def trigger(player):
    player.poll_input(True, buttons())
    player.poll_input(True, buttons(4, 0))


def test_npz_time_interpolation_and_names_are_generic(tmp_path):
    config = configuration(tmp_path)
    clip = JointSequence.load(config.sequences[0].path)
    np.testing.assert_allclose(clip.target(.035), [.15, -.2])
    np.testing.assert_array_equal(clip.target(999, [1, 0]), [-.4, .5])
    assert clip.joint_names == ("joint_a", "joint_b")
    with pytest.raises(ValueError):
        clip.joint_pos[0, 0] = 9
    with pytest.raises(ValueError):
        clip.target(float("nan"))
    # Task-specific data are ignored, even when their shape differs.
    np.savez(config.sequences[0].path, **values(), root=np.full((100, 3), 999), phase=["arbitrary"])
    assert JointSequence.load(config.sequences[0].path).duration_s == .13


@pytest.mark.parametrize("field,value", [
    ("time_s", [0, .1, .1]), ("time_s", [.1, .2, .3]),
    ("time_s", [0, float("nan"), .3]), ("time_s", [[0, .1, .2]]),
    ("time_s", np.array([0, 2, 1], dtype=np.uint64)),
    ("time_s", np.array([0, 2 ** 63, 2 ** 63 + 1], dtype=np.uint64)),
    ("joint_pos", np.zeros((3, 3))), ("joint_pos", np.full((3, 2), np.inf)),
    ("joint_pos", np.full((3, 2), True)),
    ("joint_names", ["same", "same"]), ("joint_names", ["", "joint_b"]),
    ("joint_names", np.array(["joint_a", "joint_b"], dtype=object)),
])
def test_invalid_npz_is_rejected_before_worker_starts(tmp_path, field, value):
    config = configuration(tmp_path)
    data = values()
    data[field] = value
    np.savez(config.sequences[0].path, **data)
    with pytest.raises(ValueError):
        SequencePlayer(config)


@pytest.mark.parametrize("field,value", [
    ("name", ""), ("path", Path("relative.npz")), ("buttons", (True,)),
    ("buttons", (4, 4)), ("blocked_by", (4,)), ("required_state_id", True),
    ("required_state_key", ""), ("entry_duration_s", 0),
    ("entry_duration_s", float("inf")), ("playback_speed", False),
])
def test_invalid_sequence_spec(tmp_path, field, value):
    spec = configuration(tmp_path).sequences[0]
    with pytest.raises(ValueError):
        replace(spec, **{field: value})


@pytest.mark.parametrize("field,value", [
    ("target_host", ""), ("target_port", True), ("target_port", 0),
    ("hz", 0), ("status_hz", 121), ("timeout_s", float("nan")),
    ("cancel_buttons", (True,)), ("cancel_blocked_by", (4,)), ("sequences", ()),
])
def test_invalid_sequence_configuration(tmp_path, field, value):
    with pytest.raises(ValueError):
        replace(configuration(tmp_path), **{field: value})


def test_duplicate_specs_and_bindings_are_rejected(tmp_path):
    cfg = configuration(tmp_path)
    spec = cfg.sequences[0]
    with pytest.raises(ValueError, match="names"):
        replace(cfg, sequences=(spec, replace(spec, buttons=(4, 2))))
    with pytest.raises(ValueError, match="bindings"):
        replace(cfg, sequences=(spec, replace(spec, name="other")))
    with pytest.raises(ValueError, match="cancel binding"):
        replace(cfg, cancel_buttons=spec.buttons, cancel_blocked_by=spec.blocked_by)


def test_initialization_and_unstarted_close_do_not_open_network(tmp_path, receiver):
    player = SequencePlayer(configuration(tmp_path))
    assert receiver.clients == []
    player.close()
    player.close()
    assert player.status["phase"] == "CLOSED" and receiver.clients == []
    with pytest.raises(RuntimeError):
        player.start()


def test_play_once_name_mapping_entry_blend_last_frame_and_retrigger(tmp_path, receiver):
    config = configuration(tmp_path)
    with SequencePlayer(config) as player:
        trigger(player)
        wait_for(lambda: player.status["phase"] == "HOLD")
        first, last = receiver.sent[0], receiver.sent[-1]
        assert first[0] == 123456789 and first[1] == 0
        np.testing.assert_allclose(first[2], [-.8, .7], atol=.02)
        np.testing.assert_array_equal(last[2], [-.4, .5])
        assert last[3] - first[3] >= .15
        assert any(np.linalg.norm(row[2] - first[2]) > .05 for row in receiver.sent[1:-1])
        count = len(receiver.sent)
        time.sleep(.03)
        player.poll_input(True, buttons(4, 0))
        time.sleep(.02)
        assert len(receiver.sent) == count
        trigger(player)
        wait_for(lambda: len(receiver.sent) > count)
        assert receiver.sent[count][1] == last[1] + 1
        np.testing.assert_allclose(receiver.sent[count][2], last[2], atol=.02)
    assert all(client.closed for client in receiver.clients)


def test_held_at_connection_or_unblocked_without_release_does_not_trigger(tmp_path, receiver):
    with SequencePlayer(configuration(tmp_path)) as player:
        player.poll_input(True, buttons(4, 0))
        time.sleep(.02)
        assert not receiver.clients
        player.poll_input(True, buttons())
        player.poll_input(True, buttons(4, 0, 5))
        player.poll_input(True, buttons(4, 0))
        time.sleep(.02)
        assert not receiver.clients
        trigger(player)
        wait_for(lambda: bool(receiver.sent))


def test_busy_trigger_is_ignored_without_a_queue(tmp_path, receiver):
    config = configuration(tmp_path)
    other = replace(config.sequences[0], name="other", buttons=(4, 2))
    with SequencePlayer(replace(config, sequences=(*config.sequences, other))) as player:
        trigger(player)
        wait_for(lambda: bool(receiver.sent))
        player.poll_input(True, buttons())
        player.poll_input(True, buttons(4, 2))
        wait_for(lambda: player.status["phase"] == "HOLD")
        time.sleep(.03)
        assert player.status["name"] == "motion" and len(receiver.clients) == 1


@pytest.mark.parametrize("action", ["disconnect", "cancel", "signal", "request"])
def test_cancellation_stops_without_a_neutral_joint_frame(tmp_path, receiver, action):
    with SequencePlayer(configuration(tmp_path)) as player:
        trigger(player)
        wait_for(lambda: bool(receiver.sent))
        player.poll_input(action != "disconnect", buttons(4, 1) if action == "cancel" else buttons(),
                          request_id=2 if action == "request" else None,
                          signal_bits=1 if action == "signal" else 0)
        wait_for(lambda: player.status["phase"] == "CANCELLED" and player._active is None)
        count = len(receiver.sent)
        time.sleep(.03)
        assert len(receiver.sent) == count
        assert all(np.any(row[2]) for row in receiver.sent)
        if action == "disconnect":
            player.poll_input(True, buttons(4, 0))
            time.sleep(.02)
            assert len(receiver.sent) == count
            trigger(player)
            wait_for(lambda: len(receiver.sent) > count)


def test_cancel_blocked_by_does_not_interrupt_playback(tmp_path, receiver):
    with SequencePlayer(configuration(tmp_path)) as player:
        trigger(player)
        wait_for(lambda: bool(receiver.sent))
        player.poll_input(True, buttons(4, 1, 5))
        wait_for(lambda: player.status["phase"] == "HOLD")


@pytest.mark.parametrize("field,value", [
    ("activation", None), ("q_des", None), ("joint_names", None),
    ("joint_names", ["joint_a", "unknown"]), ("state_id", 3), ("state_key", "wrong"),
])
def test_unavailable_or_wrong_state_never_waits_for_later_activation(tmp_path, receiver, field, value):
    original = receiver.metadata[field]
    receiver.metadata[field] = value
    with SequencePlayer(configuration(tmp_path)) as player:
        trigger(player)
        wait_for(lambda: player.status["phase"] == "ERROR")
        assert player.status["last_error"] and not receiver.sent
        receiver.metadata[field] = original
        player.poll_input(True, buttons(4, 0))
        time.sleep(.03)
        assert not receiver.sent
        trigger(player)
        wait_for(lambda: bool(receiver.sent))


@pytest.mark.parametrize("activation", [None, 999999999])
def test_receiver_activation_change_cancels_old_playback(tmp_path, receiver, activation):
    with SequencePlayer(configuration(tmp_path)) as player:
        trigger(player)
        wait_for(lambda: bool(receiver.sent))
        with receiver.lock:
            receiver.metadata["activation"] = activation
            receiver.metadata["sequence"] = None
        wait_for(lambda: player.status["phase"] == "CANCELLED")
        assert all(row[0] == 123456789 for row in receiver.sent)
        count = len(receiver.sent)
        time.sleep(.03)
        assert len(receiver.sent) == count


def test_slow_status_does_not_block_input_poll_or_status_property(tmp_path, receiver):
    receiver.status_gate = threading.Event()
    with SequencePlayer(configuration(tmp_path)) as player:
        trigger(player)
        assert receiver.status_entered.wait(.2)
        started = time.monotonic()
        for _ in range(100):
            player.poll_input(True, buttons(4, 0), request_id=4)
            assert player.status["name"] == "motion"
        assert time.monotonic() - started < .03
        player.poll_input(True, buttons(), signal_bits=1)
        receiver.status_gate.set()
        wait_for(lambda: player._active is None)
        assert not receiver.sent


def test_timeout_recovers_on_new_socket_at_current_time_and_never_reuses_sequence(tmp_path, receiver):
    config = configuration(tmp_path)
    config = replace(config, sequences=(replace(config.sequences[0], entry_duration_s=.005, playback_speed=10),))
    receiver.metadata["sequence"] = 40
    receiver.lose_first = True
    with SequencePlayer(config) as player:
        trigger(player)
        wait_for(lambda: player.status["phase"] == "HOLD")
        assert len(receiver.sent) == 2
        assert [row[1] for row in receiver.sent] == [41, 42]
        assert receiver.sent[0][4] != receiver.sent[1][4]
        np.testing.assert_array_equal(receiver.sent[1][2], [-.4, .5])
        second_client = receiver.sent[1][4]
        assert next(row for row in receiver.exchanges if row[0] == second_client)[1] == "status"


def test_final_frame_lost_receipt_is_confirmed_again_before_holding(tmp_path, receiver):
    receiver.lose_final = True
    with SequencePlayer(configuration(tmp_path)) as player:
        trigger(player)
        wait_for(lambda: player.status["phase"] == "HOLD")
        assert receiver.lost
        np.testing.assert_array_equal(receiver.sent[-2][2], receiver.sent[-1][2])
        assert receiver.sent[-1][1] == receiver.sent[-2][1] + 1


def test_stale_receipt_from_another_activation_is_never_accepted(tmp_path, receiver):
    receiver.wrong_receipt = True
    with SequencePlayer(configuration(tmp_path)) as player:
        trigger(player)
        wait_for(lambda: player.status["phase"] == "ERROR")
        assert "activation" in player.status["last_error"]
        assert len(receiver.sent) == 1


def test_close_is_bounded_even_if_a_platform_call_ignores_timeout(tmp_path, receiver):
    receiver.status_gate = threading.Event()
    player = SequencePlayer(configuration(tmp_path)).start()
    trigger(player)
    assert receiver.status_entered.wait(.2)
    started = time.monotonic()
    player.close()
    assert time.monotonic() - started < .3
    assert player.status["phase"] == "CLOSED"
    receiver.status_gate.set()
    wait_for(lambda: not player._thread.is_alive())
    assert not receiver.sent and all(client.closed for client in receiver.clients)
