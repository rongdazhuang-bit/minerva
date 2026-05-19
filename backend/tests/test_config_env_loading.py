"""Unit tests for single-profile dotenv discovery in app.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from app import config as config_module

_BACKEND_DIR = Path(config_module._BACKEND_DIR)


def test_discover_app_env_defaults_to_local_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When APP_ENV is not in the process environment, default profile is local."""
    monkeypatch.delenv("APP_ENV", raising=False)
    assert config_module._discover_app_env() == "local"


def test_discover_app_env_uses_process_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Process APP_ENV overrides the default."""
    monkeypatch.setenv("APP_ENV", "dev")
    assert config_module._discover_app_env() == "dev"


def test_env_file_paths_returns_single_existing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Only backend/.env.<profile> is returned when the file exists."""
    env_file = tmp_path / ".env.staging"
    env_file.write_text("APP_NAME=staging-test\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "_BACKEND_DIR", tmp_path)
    monkeypatch.setenv("APP_ENV", "staging")
    paths = config_module._env_file_paths()
    assert paths == (str(env_file),)


def test_env_file_paths_returns_none_when_file_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Missing dotenv file yields None so Settings falls back to code defaults."""
    monkeypatch.setattr(config_module, "_BACKEND_DIR", tmp_path)
    monkeypatch.setenv("APP_ENV", "missing")
    assert config_module._env_file_paths() is None


def test_env_file_paths_does_not_layer_dev_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Legacy .env.dev + .env.dev.local must not both be loaded."""
    (tmp_path / ".env.dev").write_text("APP_NAME=from-dev\n", encoding="utf-8")
    (tmp_path / ".env.dev.local").write_text("APP_NAME=from-overlay\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "_BACKEND_DIR", tmp_path)
    monkeypatch.setenv("APP_ENV", "dev")
    paths = config_module._env_file_paths()
    assert paths == (str(tmp_path / ".env.dev"),)
    assert len(paths) == 1
