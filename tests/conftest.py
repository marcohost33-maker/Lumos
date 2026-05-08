"""Shared fixtures for the Lumos test suite."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from lumos import Lumos
from lumos.config import Config


@pytest.fixture
def tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "lumos-home"
    monkeypatch.setenv("LUMOS_HOME", str(home))
    return home


@pytest.fixture
def config(tmp_home: Path) -> Config:
    return Config.for_home(tmp_home)


@pytest.fixture
def app(config: Config) -> Lumos:
    a = Lumos(config=config)
    try:
        yield a
    finally:
        a.close()


@pytest.fixture(autouse=True)
def _set_tz(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin tz so date parsing is deterministic across CI hosts."""
    monkeypatch.setenv("TZ", "UTC")
    if hasattr(os, "tzset"):
        import time

        time.tzset()
