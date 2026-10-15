"""Datas civis (sem hora e sem fuso) para regras financeiras.

Datas de vencimento, compra, recebimento e competência são ``datetime.date``.
Nada aqui converte para UTC: a data "hoje" vem de ``app.core.clock``.
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date


class DateError(ValueError):
    """Data inválida."""


def days_in_month(year: int, month: int) -> int:
    if not 1 <= month <= 12:
        raise DateError(f"mês inválido: {month}")
    return calendar.monthrange(year, month)[1]


def clamp_day(year: int, month: int, day: int) -> date:
    """Data com o dia limitado ao último dia do mês (31 em fevereiro vira 28 ou 29)."""
    if day < 1:
        raise DateError(f"dia inválido: {day}")
    return date(year, month, min(day, days_in_month(year, month)))


def add_months(d: date, months: int) -> date:
    """Soma meses mantendo o dia, limitado ao fim do mês.

    Atenção: encadear chamadas desloca o dia (31/01 -> 28/02 -> 28/03).
    Para recorrências use ``monthly_occurrence``, que parte sempre da âncora.
    """
    index = d.year * 12 + (d.month - 1) + months
    year, month0 = divmod(index, 12)
    if not date.min.year <= year <= date.max.year:
        raise DateError("data fora do intervalo suportado")
    return clamp_day(year, month0 + 1, d.day)


def monthly_occurrence(anchor: date, k: int) -> date:
    """k-ésima ocorrência mensal calculada a partir da data original.

    Âncora 31/01/2026: k=1 -> 28/02/2026, k=2 -> 31/03/2026, k=3 -> 30/04/2026.
    """
    return add_months(anchor, k)


def monthly_occurrences(anchor: date, start: date, end: date) -> Iterator[date]:
    """Ocorrências mensais da âncora dentro de [start, end], em ordem."""
    if end < start:
        return
    # Primeiro k candidato: diferença de meses entre a âncora e o início.
    k = max(0, (start.year - anchor.year) * 12 + (start.month - anchor.month))
    while True:
        occ = monthly_occurrence(anchor, k)
        if occ > end:
            return
        if occ >= start:
            yield occ
        k += 1


@dataclass(frozen=True, slots=True, order=True)
class YearMonth:
    """Mês de referência (competência), usado na navegação mensal."""

    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise DateError(f"mês inválido: {self.month}")

    @classmethod
    def of(cls, d: date) -> YearMonth:
        return cls(d.year, d.month)

    @property
    def first_day(self) -> date:
        return date(self.year, self.month, 1)

    @property
    def last_day(self) -> date:
        return date(self.year, self.month, days_in_month(self.year, self.month))

    def shift(self, months: int) -> YearMonth:
        moved = add_months(self.first_day, months)
        return YearMonth(moved.year, moved.month)

    def contains(self, d: date) -> bool:
        return d.year == self.year and d.month == self.month

    def __str__(self) -> str:
        return f"{self.month:02d}/{self.year:04d}"


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """Primeiro e último dia do mês."""
    ym = YearMonth(year, month)
    return ym.first_day, ym.last_day


_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_BR = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


def _build(year: str, month: str, day: str, raw: str) -> date:
    try:
        return date(int(year), int(month), int(day))
    except ValueError as exc:
        raise DateError(f"data inexistente: {raw!r}") from exc


def parse_iso_date(text: str) -> date:
    """``AAAA-MM-DD`` estrito (formato da API)."""
    m = _ISO.match(text.strip())
    if m is None:
        raise DateError(f"data deve estar em AAAA-MM-DD: {text!r}")
    return _build(m.group(1), m.group(2), m.group(3), text)


def parse_br_date(text: str) -> date:
    """``DD/MM/AAAA`` estrito (formato de exibição e de CSV brasileiro)."""
    m = _BR.match(text.strip())
    if m is None:
        raise DateError(f"data deve estar em DD/MM/AAAA: {text!r}")
    return _build(m.group(3), m.group(2), m.group(1), text)


def format_br_date(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}/{d.year:04d}"
