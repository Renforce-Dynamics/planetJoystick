from pathlib import Path
import socket

import pytest

from planetj.config import PlanetJConfigError, load_config
from planetj.runtime import main
from planetj.upper_stream import main as upper_main


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('entry,cli', [
    ('entry_joystick.yaml', main), ('entry_operator.yaml', main),
    ('entry_upper_stream.yaml', upper_main),
])
def test_explicit_root_entry_checks_from_another_directory_without_io(entry, cli, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(socket, 'socket', lambda *a, **k: pytest.fail('offline check opened a socket'))
    assert cli(['--config', str(ROOT / 'configs/entry' / entry), '--check']) == 0
    with pytest.raises(SystemExit) as error:
        cli(['--check'])
    assert error.value.code == 2


def test_device_and_operator_entries_are_distinct():
    device = load_config(ROOT / 'configs/entry/entry_joystick.yaml')
    operator = load_config(ROOT / 'configs/entry/entry_operator.yaml')
    assert not device.inputs.requests
    assert {(r.request_id, r.state_key) for r in operator.inputs.requests} == {
        (0, 'passive'), (1, 'damping'), (2, 'fixedpos'), (3, 'loco'),
    }
    assert device.inputs.axes == operator.inputs.axes


def test_missing_entry_never_falls_back_to_installed_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(PlanetJConfigError):
        load_config('configs/entry/entry_operator.yaml')
    with pytest.raises(PlanetJConfigError, match='filesystem entry'):
        load_config('pkg://planetj/data/operator.yaml')
    assert not list((ROOT / 'src').rglob('*.yaml'))
