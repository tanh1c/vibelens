"""Configuration management for VibeLens"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    """Global settings for VibeLens"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM Providers
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    browser_use_api_key: str | None = None

    # Proxy
    http_proxy: str | None = None
    https_proxy: str | None = None

    # Browser
    default_browser: Literal["chromium", "firefox", "webkit"] = "chromium"

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Telemetry
    anonymized_telemetry: bool = True


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get settings instance"""
    return settings
