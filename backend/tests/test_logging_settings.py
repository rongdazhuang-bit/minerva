"""Tests for logging settings defaults."""

from app.config import settings


def test_logging_settings_defaults() -> None:
    """Logging settings expose the configured default values."""

    assert settings.log_level == "INFO"
    assert settings.log_dir == "logs"
    assert settings.log_retention_days == 7
    assert settings.log_body_enabled is True
    assert settings.log_body_max_chars == 20000
    assert settings.log_file_enabled is True
    assert settings.log_stdout_enabled is True
