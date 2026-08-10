"""Application settings, loaded from TOML config + environment variables."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from platformdirs import user_config_dir, user_data_dir
from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from pydantic_settings.sources import TomlConfigSettingsSource

APP_NAME = "exodus90-printer"

OutputFormat = Literal["markdown", "pdf", "print"]


def default_config_path() -> Path:
    return Path(user_config_dir(APP_NAME)) / "config.toml"


def default_session_path() -> Path:
    return Path(user_data_dir(APP_NAME)) / "session" / "cookies.json"


class Settings(BaseSettings):
    """Typed settings.

    Precedence (lowest to highest):
    default values < config TOML file < environment variables (``EXODUS90_*``)
    < keyword arguments passed to the constructor.
    """

    base_url: str = "https://app.exodus90.com"
    """Base URL of the Exodus 90 web app."""

    program_id: int = 208
    """The user's active program/challenge. The program URL may change, so this
    is configurable: ``EXODUS90_PROGRAM_ID`` or ``program_id`` in the config."""

    output_dir: Path = Field(default_factory=lambda: Path.home() / "Desktop" / "exodus90-readings")
    """Where rendered files are written."""

    formats: list[OutputFormat] = ["pdf", "print"]
    """Which outputs to produce. Any subset of ``markdown``, ``pdf``, ``print``."""

    printer: str | None = None
    """CUPS printer name; empty means the system default printer."""

    pdf_font_dir: Path = Path("/usr/share/fonts/liberation-serif-fonts")
    """Directory holding the serif font files used for PDF generation."""

    pdf_font_family: str = "LiberationSerif"
    """Font family base name; looks for ``{family}-{Regular,Bold,Italic,BoldItalic}.ttf``."""

    model_config = SettingsConfigDict(
        env_prefix="EXODUS90_",
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    @property
    def session_path(self) -> Path:
        return default_session_path()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        toml_file = settings_cls.model_config.get("toml_file")
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings]
        if toml_file:
            sources.append(TomlConfigSettingsSource(settings_cls))
        return tuple(sources) + (dotenv_settings, file_secret_settings)


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings, optionally from an explicit TOML file."""

    toml_file = str(config_path if config_path is not None else default_config_path())

    class _Settings(Settings):
        model_config = SettingsConfigDict(
            env_prefix="EXODUS90_",
            extra="ignore",
            env_file=".env",
            env_file_encoding="utf-8",
            toml_file=toml_file,
        )

    return _Settings()
