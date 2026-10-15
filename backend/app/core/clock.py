"""Relógio da aplicação: única fonte de "agora" e "hoje".

Regra: nenhuma regra de negócio usa ``date.today()``, ``datetime.now()`` ou
``CURRENT_DATE`` do banco. Tudo passa por um ``Clock``, que pode ser trocado
por um relógio fixo nos testes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

APP_TZ = ZoneInfo("America/Sao_Paulo")


class Clock(Protocol):
    def now_utc(self) -> datetime: ...


class SystemClock:
    def now_utc(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """Relógio parado em um instante, para testes."""

    def __init__(self, instant: datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError("FixedClock exige datetime com fuso")
        self._instant = instant.astimezone(UTC)

    def now_utc(self) -> datetime:
        return self._instant


def now_sp(clock: Clock) -> datetime:
    """Agora no fuso de São Paulo."""
    return clock.now_utc().astimezone(APP_TZ)


def today_sp(clock: Clock) -> date:
    """Data civil de hoje em São Paulo."""
    return now_sp(clock).date()
