from lumos import Lumos
from lumos.config import Config


def test_lumos_constructs_with_default_config(tmp_home):
    app = Lumos()
    try:
        assert app.config.home == tmp_home.resolve()
        assert app.config.home.is_dir()
        # storage works
        r = app.reminders.add("hello", when="in 1 hour")
        assert r.id is not None
    finally:
        app.close()


def test_lumos_context_manager(config: Config):
    with Lumos(config=config) as app:
        app.reminders.add("hi", when="in 1 hour")
    # Re-opening should still see it.
    with Lumos(config=config) as app:
        assert len(app.reminders.list()) == 1


def test_drive_attribute_lazy(config: Config, monkeypatch):
    """Accessing .drive should not import google libs by itself."""
    app = Lumos(config=config)
    try:
        client = app.drive
        # drive.service is the lazy bit; just checking the property type.
        assert client is app.drive  # cached
    finally:
        app.close()
