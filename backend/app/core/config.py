"""Configuração lida de variáveis de ambiente (prefixo ``FIN_``)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIN_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    app_version: str = "0.1.0"

    # URLs contêm senha: SecretStr evita que apareçam em logs e mensagens de erro.
    # database_url: papel da aplicação (fin_app), sujeito a Row-Level Security.
    # database_admin_url: usado só por migrações e backups, nunca pela API.
    database_url: SecretStr | None = None
    database_admin_url: SecretStr | None = None

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
