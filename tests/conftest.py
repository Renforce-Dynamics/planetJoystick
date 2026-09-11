from pathlib import Path
import pytest

@pytest.fixture(autouse=True)
def repository_working_directory(monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
