from pathlib import Path
import socket

import numpy as np
import pytest
import yaml

from planetj.config import PlanetJConfigError, load_config
from planetj.runtime import main


ROOT = Path(__file__).resolve().parents[1]


def profile(tmp_path):
    clip = tmp_path / "clip.npz"
    np.savez(clip, time_s=[0., .5, 1.], joint_pos=[[0., 0.], [.1, -.1], [0., 0.]],
             joint_names=["joint_a", "joint_b"])
    raw = {
        "extends": str(ROOT / "configs/entry/entry_operator.yaml"),
        "sequences": {
            "target": {"host": "127.0.0.1", "port": 15100},
            "publisher": {"hz": 60, "status_hz": 10, "timeout_s": .03},
            "cancel": {"buttons": [4, 1], "blocked_by": [5]},
            "motions": {"first": {
                "buttons": [4, 3], "blocked_by": [5],
                "state": {"id": 5, "key": "upper_stream"}, "trajectory": "clip.npz",
                "entry_duration_s": 2., "playback_speed": 1.,
            }},
        },
    }
    entry = tmp_path / "entry_base.yaml"
    entry.write_text(yaml.safe_dump(raw))
    return entry, raw


def test_inherited_clip_resolves_at_declaring_file_from_another_directory(tmp_path, monkeypatch):
    base, _ = profile(tmp_path)
    child = tmp_path / "child"
    child.mkdir()
    entry = child / "entry.yaml"
    entry.write_text("extends: ../entry_base.yaml\nsequences:\n  publisher:\n    hz: 50\n")
    monkeypatch.chdir("/tmp")
    config = load_config(entry)
    assert config.sequences.sequences[0].path == tmp_path / "clip.npz"
    assert config.sequences.hz == 50
    assert config.sequences.cancel_blocked_by == (5,)


def test_sequence_offline_check_loads_clip_without_sockets(tmp_path, monkeypatch):
    entry, _ = profile(tmp_path)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("offline socket creation"))
    assert main(["--config", str(entry), "--check"]) == 0
    np.savez(tmp_path / "clip.npz", time_s=[0., .5, .4], joint_pos=np.zeros((3, 2)),
             joint_names=["joint_a", "joint_b"])
    with pytest.raises(SystemExit):
        main(["--config", str(entry), "--check"])


@pytest.mark.parametrize("path", ["pkg://clip.npz", "missing.npz", 12, "file:clip.npz"])
def test_invalid_trajectory_path_fails_config(tmp_path, path):
    entry, raw = profile(tmp_path)
    raw["sequences"]["motions"]["first"]["trajectory"] = path
    entry.write_text(yaml.safe_dump(raw))
    with pytest.raises(PlanetJConfigError):
        load_config(entry)


def test_sequence_cannot_share_a_state_request_chord(tmp_path):
    entry, raw = profile(tmp_path)
    raw["sequences"]["motions"]["first"].update(buttons=[5, 2], blocked_by=[])
    entry.write_text(yaml.safe_dump(raw))
    with pytest.raises(PlanetJConfigError, match="duplicates a state request"):
        load_config(entry)


def test_sequence_configuration_can_be_disabled_in_child(tmp_path):
    profile(tmp_path)
    child = tmp_path / "entry_disabled.yaml"
    child.write_text("extends: entry_base.yaml\nsequences: null\n")
    assert load_config(child).sequences is None


def test_shipped_sequence_profile_is_code_and_runtime_independent():
    assert main(["--config", str(ROOT / "configs/entry/entry_sequences.yaml"), "--check"]) == 0
