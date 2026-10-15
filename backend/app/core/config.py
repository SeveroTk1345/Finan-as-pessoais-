"""Configuração lida de variáveis de ambiente (prefixo ``FIN_``)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIN_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    app_version: str = "0.1.0"

    # URLs contêm senha: SecretStr evita que apareçam em logs e mensagens de erro.
    # database_url: papel da aplicação (fin_app), sujeito a Row-Level Security.
    # database_admin_url: usado só por migrações, backups e linha de comando.
    database_url: SecretStr | None = None
    database_admin_url: SecretStr | None = None

    # Origens aceitas em requisições que alteram dados (proteção CSRF).
    # Ex.: "https://financas.exemplo.com,http://localhost:3000"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000"

    # Pasta do site estático (frontend/out). Vazio: a API não serve o site.
    static_dir: Path | None = None

    # Sessões (decisão D10).
    session_remember_max_seconds: int = 30 * 24 * 3600
    session_remember_idle_seconds: int = 7 * 24 * 3600
    session_short_max_seconds: int = 12 * 3600
    session_short_idle_seconds: int = 30 * 60

    # Limite de tentativas de login.
    login_window_seconds: int = 15 * 60
    login_max_failures_per_user: int = 5
    login_max_failures_per_ip: int = 20

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def origins(self) -> frozenset[str]:
        return frozenset(o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip())

    @property
    def cookie_secure(self) -> bool:
        # Em produção o cookie só trafega por HTTPS. Em desenvolvimento local (http)
        # o navegador recusaria um cookie Secure.
        return self.is_production


@lru_cache
def get_settings() -> Settings:
    return Settings()
