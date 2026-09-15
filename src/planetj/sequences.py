"""Background playback of named joint-position sequences.

Input polling never touches files or the network. A single worker owns its UDP
client and publishes the current time sample, without a queue of old frames.
Receipts acknowledge reception; the receiver owns execution and final holding.
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral, Real
from pathlib import Path
import threading
import time

import numpy as np

from planet_protocol.client import JointTargetClient


def _name(value, label):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonempty, unpadded string")
    return value


def _number(value, label, minimum, maximum):
    if (isinstance(value, bool) or not isinstance(value, Real)
            or not np.isfinite(value) or not minimum <= value <= maximum):
        raise ValueError(f"{label} must be finite in [{minimum}, {maximum}]")


def _integer(value, label, minimum=0, maximum=65535):
    if isinstance(value, bool) or not isinstance(value, Integral) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer in [{minimum}, {maximum}]")


def _buttons(value, label, *, empty=False):
    if not isinstance(value, tuple) or (not empty and not value):
        raise ValueError(f"{label} must be {'a' if empty else 'a nonempty'} tuple")
    for index in value:
        _integer(index, label, 0, 255)
    if len(set(value)) != len(value):
        raise ValueError(f"{label} contains duplicate buttons")


@dataclass(frozen=True, slots=True)
class SequenceSpec:
    name: str
    path: Path
    buttons: tuple[int, ...]
    blocked_by: tuple[int, ...]
    required_state_id: int
    required_state_key: str
    entry_duration_s: float = 2.0
    playback_speed: float = 1.0

    def __post_init__(self):
        _name(self.name, "sequence name")
        _name(self.required_state_key, "required_state_key")
        _integer(self.required_state_id, "required_state_id")
        _buttons(self.buttons, "sequence buttons")
        _buttons(self.blocked_by, "sequence blocked_by", empty=True)
        if set(self.buttons) & set(self.blocked_by):
            raise ValueError("sequence buttons overlap blocked_by")
        if not isinstance(self.path, Path) or not self.path.is_absolute():
            raise ValueError("sequence path must be a resolved absolute Path")
        _number(self.entry_duration_s, "entry_duration_s", 0.001, 3600)
        _number(self.playback_speed, "playback_speed", 0.001, 100)


@dataclass(frozen=True, slots=True)
class SequenceConfig:
    target_host: str
    target_port: int
    sequences: tuple[SequenceSpec, ...]
    hz: float = 60.0
    status_hz: float = 10.0
    timeout_s: float = 0.03
    cancel_buttons: tuple[int, ...] = (4, 1)
    cancel_blocked_by: tuple[int, ...] = ()

    def __post_init__(self):
        _name(self.target_host, "target_host")
        _integer(self.target_port, "target_port", 1)
        _number(self.hz, "hz", 1, 1000)
        _number(self.status_hz, "status_hz", 0.1, self.hz)
        _number(self.timeout_s, "timeout_s", 0.001, 1)
        _buttons(self.cancel_buttons, "cancel_buttons")
        _buttons(self.cancel_blocked_by, "cancel_blocked_by", empty=True)
        if set(self.cancel_buttons) & set(self.cancel_blocked_by):
            raise ValueError("cancel_buttons overlap cancel_blocked_by")
        if (not isinstance(self.sequences, tuple) or not self.sequences
                or any(not isinstance(spec, SequenceSpec) for spec in self.sequences)):
            raise ValueError("sequences must be a nonempty tuple of SequenceSpec")
        if len({spec.name for spec in self.sequences}) != len(self.sequences):
            raise ValueError("sequence names must be unique")
        bindings = [(frozenset(spec.buttons), frozenset(spec.blocked_by)) for spec in self.sequences]
        if len(set(bindings)) != len(bindings):
            raise ValueError("sequence button bindings must be unique")
        if (frozenset(self.cancel_buttons), frozenset(self.cancel_blocked_by)) in bindings:
            raise ValueError("a sequence binding cannot also be its cancel binding")


@dataclass(frozen=True, slots=True)
class JointSequence:
    """Robot-independent NPZ subset: time_s, joint_pos and joint_names."""

    time_s: np.ndarray
    joint_pos: np.ndarray
    joint_names: tuple[str, ...]

    @classmethod
    def load(cls, path):
        if not isinstance(path, Path) or not path.is_absolute():
            raise ValueError("sequence path must be a resolved absolute Path")
        with np.load(path, allow_pickle=False) as data:
            if not {"time_s", "joint_pos", "joint_names"}.issubset(data.files):
                raise ValueError("sequence NPZ requires time_s, joint_pos and joint_names")
            times, positions, names = (np.asarray(data[key]) for key in ("time_s", "joint_pos", "joint_names"))
            if (times.dtype.kind not in "fiu" or times.ndim != 1 or len(times) < 2
                    or not np.all(np.isfinite(times)) or times[0] != 0 or np.any(times[1:] <= times[:-1])):
                raise ValueError("time_s must be finite, start at zero and strictly increase")
            if (names.dtype.kind not in "US" or names.ndim != 1 or not len(names)):
                raise ValueError("joint_names must be a nonempty vector of strings")
            joint_names = tuple(names.astype(str).tolist())
            for name in joint_names:
                _name(name, "joint_names")
            if len(set(joint_names)) != len(joint_names):
                raise ValueError("joint_names must be unique")
            if (positions.dtype.kind not in "fiu" or positions.shape != (len(times), len(names))
                    or not np.all(np.isfinite(positions))):
                raise ValueError("joint_pos must be a finite time-by-joint matrix")
            times, positions = times.astype(np.float64), positions.astype(np.float64)
            if np.any(times[1:] <= times[:-1]):
                raise ValueError("time_s must remain strictly increasing at float64 precision")
        times.setflags(write=False)
        positions.setflags(write=False)
        return cls(times, positions, joint_names)

    @property
    def duration_s(self):
        return float(self.time_s[-1])

    def target(self, elapsed_s, columns=None):
        _number(elapsed_s, "sample time", 0, np.finfo(float).max)
        if elapsed_s >= self.duration_s:
            result = self.joint_pos[-1].copy()
        else:
            right = min(int(np.searchsorted(self.time_s, elapsed_s, side="right")), len(self.time_s) - 1)
            left = max(0, right - 1)
            alpha = (elapsed_s - self.time_s[left]) / (self.time_s[right] - self.time_s[left])
            result = (1 - alpha) * self.joint_pos[left] + alpha * self.joint_pos[right]
        return result if columns is None else result[columns]


class _Cancelled(Exception):
    pass


class SequencePlayer:
    """One worker and at most one active trigger; input edges never queue."""

    def __init__(self, config: SequenceConfig):
        if not isinstance(config, SequenceConfig):
            raise TypeError("config must be SequenceConfig")
        self.config = config
        self._clips = tuple(JointSequence.load(spec.path) for spec in config.sequences)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread = None
        self._closed = False
        self._connected = False
        self._held = tuple(False for _ in config.sequences)
        self._generation = 0
        self._job = self._active = None
        self._status = {"name": None, "phase": "IDLE", "last_error": None}

    @property
    def status(self):
        with self._lock:
            return dict(self._status)

    def start(self):
        with self._lock:
            if self._closed:
                raise RuntimeError("sequence player is closed")
            if self._thread is not None:
                return self
            self._thread = threading.Thread(target=self._run, name="planetj-sequences", daemon=True)
            self._thread.start()
        return self

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.close()

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._generation += 1
            self._job = None
            self._status["phase"] = "CLOSED"
            thread = self._thread
        self._wake.set()
        if thread is not None and thread is not threading.current_thread():
            # Socket exchanges are bounded. DNS may be platform-blocking; the
            # daemon checks cancellation before any subsequent exchange.
            thread.join(timeout=max(0.2, 2 * self.config.timeout_s + 0.1))

    @staticmethod
    def _down(buttons, indices):
        return all(index < len(buttons) and buttons[index] for index in indices)

    @staticmethod
    def _blocked(buttons, indices):
        return any(index < len(buttons) and buttons[index] for index in indices)

    def poll_input(self, connected, buttons, request_id=None, signal_bits=0):
        """Local edge detection only: no I/O, sleeps, joins, or network locks."""
        pressed = tuple(bool(value) for value in buttons)
        held = tuple(self._down(pressed, spec.buttons) for spec in self.config.sequences)
        cancel = self._down(pressed, self.config.cancel_buttons) and not self._blocked(pressed, self.config.cancel_blocked_by)
        wake = False
        with self._lock:
            if self._closed:
                return
            previous_connected, previous_held = self._connected, self._held
            self._connected, self._held = bool(connected), held
            job = self._active if self._active is not None else self._job
            conflicting_request = (job is not None and request_id is not None
                                   and request_id != self.config.sequences[job[1]].required_state_id)
            if not connected or cancel or signal_bits or conflicting_request:
                if job is not None and job[0] == self._generation:
                    self._generation += 1
                    self._job = None
                    self._status["phase"] = "CANCELLED"
                    wake = True
            elif previous_connected and self._thread is not None and job is None:
                for index, spec in sorted(enumerate(self.config.sequences), key=lambda pair: -len(pair[1].buttons)):
                    if (held[index] and not previous_held[index]
                            and not self._blocked(pressed, spec.blocked_by)
                            and request_id in (None, spec.required_state_id)):
                        self._generation += 1
                        self._job = (self._generation, index)
                        self._status = {"name": spec.name, "phase": "STARTING", "last_error": None}
                        wake = True
                        break
        if wake:
            self._wake.set()

    def _valid(self, job):
        with self._lock:
            return not self._closed and self._generation == job[0]

    def _check(self, job):
        if not self._valid(job):
            raise _Cancelled()

    def _publish_status(self, job, phase, error=None):
        with self._lock:
            if not self._closed and self._generation == job[0]:
                self._status = {"name": self.config.sequences[job[1]].name,
                                "phase": phase, "last_error": error}

    def _run(self):
        while True:
            self._wake.wait()
            with self._lock:
                self._wake.clear()
                if self._closed:
                    return
                job, self._job = self._job, None
                if job is None:
                    continue
                self._active = job
            try:
                self._play(job)
            except _Cancelled:
                pass
            except Exception as error:
                self._publish_status(job, "ERROR", str(error))
            finally:
                with self._lock:
                    self._active = None

    @staticmethod
    def _receiver(status, spec, clip):
        if not isinstance(status, dict):
            raise ValueError("joint-target status must be an object")
        activation = status.get("activation")
        if activation is None:
            raise ValueError("required joint-target state is inactive; trigger again after entering it")
        _integer(activation, "status.activation", 1, 2 ** 53 - 1)
        _integer(status.get("state_id"), "status.state_id")
        if status.get("state_id") != spec.required_state_id or status.get("state_key") != spec.required_state_key:
            raise ValueError("receiver state_id/state_key is missing or does not match the required state")
        names = status.get("joint_names")
        if (not isinstance(names, (list, tuple)) or len(names) != len(clip.joint_names)
                or any(not isinstance(name, str) for name in names)
                or len(set(names)) != len(names) or set(names) != set(clip.joint_names)):
            raise ValueError("receiver joint_names must uniquely match the sequence joints")
        _integer(status.get("dimension"), "status.dimension", 1)
        if status.get("dimension") != len(names):
            raise ValueError("receiver dimension does not match joint_names")
        current = status.get("q_des")
        if current is None:
            raise ValueError("receiver has no committed q_des; trigger again after its first command")
        current = np.asarray(current)
        if current.dtype.kind not in "fiu" or current.shape != (len(names),) or not np.all(np.isfinite(current)):
            raise ValueError("receiver q_des must be a finite joint vector")
        sequence = status.get("sequence")
        if "sequence" not in status:
            raise ValueError("receiver sequence metadata is missing")
        if sequence is not None:
            _integer(sequence, "status.sequence", 0, 2 ** 53 - 2)
        columns = [clip.joint_names.index(name) for name in names]
        return int(activation), tuple(names), current.astype(np.float64), 0 if sequence is None else int(sequence) + 1, columns

    def _client(self):
        return JointTargetClient(self.config.target_host, self.config.target_port, timeout_s=self.config.timeout_s)

    def _play(self, job):
        spec, clip = self.config.sequences[job[1]], self._clips[job[1]]
        client = None
        try:
            self._check(job)
            client = self._client()
            self._check(job)
            initial = self._receiver(client.status(), spec, clip)
            self._check(job)
            activation, names, current, sequence, columns = initial
            started = time.monotonic()
            next_status = started + 1 / self.config.status_hz
            next_tick = started
            first = clip.target(0, columns)
            while True:
                self._check(job)
                now = time.monotonic()
                if now < next_tick:
                    self._wake.wait(next_tick - now)
                    self._wake.clear()
                    continue
                try:
                    if client is None:
                        client = self._client()
                        self._check(job)
                        next_status = -float("inf")
                    if now >= next_status:
                        response = client.status()
                        self._check(job)
                        if response.get("activation") != activation:
                            self._publish_status(job, "CANCELLED", "receiver activation changed or became inactive")
                            return
                        observed = self._receiver(response, spec, clip)
                        if observed[0] != activation or observed[1] != names:
                            self._publish_status(job, "CANCELLED", "receiver activation or joint order changed")
                            return
                        sequence = max(sequence, observed[3])
                        next_status = time.monotonic() + 1 / self.config.status_hz
                    elapsed = max(0.0, time.monotonic() - started)
                    if elapsed < spec.entry_duration_s:
                        progress = elapsed / spec.entry_duration_s
                        alpha = progress * progress * (3 - 2 * progress)
                        target = (1 - alpha) * current + alpha * first
                        phase, final = "ENTERING", False
                    else:
                        playback_s = (elapsed - spec.entry_duration_s) * spec.playback_speed
                        target = clip.target(playback_s, columns)
                        phase, final = "PLAYING", playback_s >= clip.duration_s
                    self._check(job)
                    self._publish_status(job, phase)
                    sent_sequence = sequence
                    sequence += 1  # Lost receipts never make a sequence reusable.
                    receipt = client.send(activation, sent_sequence, target)
                    self._check(job)
                    if (receipt.get("activation") != activation or receipt.get("sequence") != sent_sequence
                            or type(receipt.get("accepted")) is not bool):
                        raise ValueError("receipt does not match this activation and sequence")
                    if not receipt["accepted"]:
                        client.close()
                        client = None
                        self._publish_status(job, "RECOVERING", "receiver did not accept the target")
                    elif final:
                        self._publish_status(job, "HOLD")
                        return
                    # Schedule from the current clock, without accumulating old ticks.
                    next_tick = max(now + 1 / self.config.hz, time.monotonic())
                except OSError as error:
                    self._check(job)
                    self._publish_status(job, "RECOVERING", str(error))
                    if client is not None:
                        client.close()
                        client = None
                    # A new socket drops delayed replies from the old exchange.
                    # Recovery always queries activation before sending a new target.
                    next_tick = time.monotonic() + 1 / self.config.status_hz
        finally:
            if client is not None:
                client.close()
