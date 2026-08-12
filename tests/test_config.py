"""Tests for settings loading and precedence."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from exodus90_printer.config import Settings, load_settings


def _write_toml(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_required_user_fields_have_no_default() -> None:
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_program_id_optional_defaults_to_none(make_settings: Callable[..., Settings]) -> None:
    settings = Settings(output_dir=Path("/tmp/out"), formats=["pdf"])
    assert settings.program_id is None


def test_constant_fields_keep_defaults(make_settings: Callable[..., Settings]) -> None:
    settings = make_settings()
    assert settings.base_url == "https://app.exodus90.com"
    assert settings.formats == ["pdf"]
    assert settings.printer is None


def test_load_settings_reads_toml(tmp_path: Path) -> None:
    cfg = _write_toml(
        tmp_path / "config.toml",
        """
        base_url = "https://example.com"
        program_id = 999
        output_dir = "/tmp/out"
        formats = ["markdown"]
        """,
    )
    settings = load_settings(cfg)
    assert settings.base_url == "https://example.com"
    assert settings.program_id == 999
    assert settings.output_dir == Path("/tmp/out")
    assert settings.formats == ["markdown"]


def test_load_settings_missing_required_field_raises(tmp_path: Path) -> None:
    cfg = _write_toml(tmp_path / "config.toml", 'output_dir = "/tmp/out"\n')
    with pytest.raises(ValidationError):
        load_settings(cfg)


def test_env_overrides_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _write_toml(
        tmp_path / "config.toml",
        'program_id = 999\noutput_dir = "/tmp/out"\nformats = ["pdf"]\n',
    )
    monkeypatch.setenv("EXODUS90_PROGRAM_ID", "42")
    settings = load_settings(cfg)
    assert settings.program_id == 42


def test_env_sets_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXODUS90_BASE_URL", "https://example.com")
    monkeypatch.setenv("EXODUS90_PROGRAM_ID", "123")
    monkeypatch.setenv("EXODUS90_OUTPUT_DIR", "/tmp/out")
    monkeypatch.setenv("EXODUS90_FORMATS", '["pdf", "print"]')
    settings = load_settings(tmp_path / "missing.toml")
    assert settings.base_url == "https://example.com"
    assert settings.program_id == 123
    assert settings.formats == ["pdf", "print"]


def test_load_settings_prefers_cwd_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_toml(
        tmp_path / "config.toml",
        'program_id = 111\noutput_dir = "/tmp/out"\nformats = ["print"]\n',
    )
    monkeypatch.chdir(tmp_path)
    settings = load_settings()
    assert settings.program_id == 111
