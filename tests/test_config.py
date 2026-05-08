from pathlib import Path

from lumos.config import Config


def test_default_uses_lumos_home_env(monkeypatch, tmp_path):
    monkeypatch.setenv("LUMOS_HOME", str(tmp_path / "x"))
    cfg = Config.default()
    assert cfg.home == (tmp_path / "x").resolve()
    assert cfg.db_path.name == "lumos.db"
    assert cfg.credentials_path.name == "credentials.json"
    assert cfg.token_path.name == "token.json"


def test_for_home_resolves_path(tmp_path: Path):
    cfg = Config.for_home(tmp_path / "y")
    assert cfg.home == (tmp_path / "y").resolve()


def test_ensure_dirs_creates_directory(tmp_path: Path):
    cfg = Config.for_home(tmp_path / "deep" / "nested")
    assert not cfg.home.exists()
    cfg.ensure_dirs()
    assert cfg.home.is_dir()
