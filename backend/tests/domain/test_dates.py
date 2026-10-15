from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.dates import (
    DateError,
    YearMonth,
    add_months,
    clamp_day,
    days_in_month,
    format_br_date,
    month_bounds,
    monthly_occurrence,
    monthly_occurrences,
    parse_br_date,
    parse_iso_date,
)


@pytest.mark.parametrize(
    ("year", "month", "days"),
    [(2026, 1, 31), (2026, 2, 28), (2028, 2, 29), (2100, 2, 28), (2000, 2, 29), (2026, 4, 30)],
)
def test_days_in_month(year: int, month: int, days: int) -> None:
    assert days_in_month(year, month) == days


def test_clamp_day() -> None:
    assert clamp_day(2028, 2, 31) == date(2028, 2, 29)
    assert clamp_day(2026, 2, 31) == date(2026, 2, 28)
    assert clamp_day(2026, 4, 31) == date(2026, 4, 30)
    assert clamp_day(2026, 3, 15) == date(2026, 3, 15)
    with pytest.raises(DateError):
        clamp_day(2026, 3, 0)
    with pytest.raises(DateError):
        clamp_day(2026, 13, 1)


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2028, 1, 31), 1, date(2028, 2, 29)),
        (date(2026, 12, 15), 1, date(2027, 1, 15)),  # virada de ano
        (date(2026, 1, 15), -1, date(2025, 12, 15)),
        (date(2026, 3, 31), -1, date(2026, 2, 28)),
        (date(2026, 1, 31), 12, date(2027, 1, 31)),
        (date(2026, 5, 10), 0, date(2026, 5, 10)),
    ],
)
def test_add_months(start: date, months: int, expected: date) -> None:
    assert add_months(start, months) == expected


def test_encadear_add_months_desliza_por_isso_existe_monthly_occurrence() -> None:
    # Documenta o problema que monthly_occurrence evita.
    d = date(2026, 1, 31)
    chained = add_months(add_months(d, 1), 1)
    assert chained == date(2026, 3, 28)
    assert monthly_occurrence(d, 2) == date(2026, 3, 31)


def test_recorrencia_no_dia_31_nao_desliza() -> None:
    anchor = date(2026, 1, 31)
    assert [monthly_occurrence(anchor, k) for k in range(6)] == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
        date(2026, 5, 31),
        date(2026, 6, 30),
    ]


def test_recorrencia_em_ano_bissexto() -> None:
    assert monthly_occurrence(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert monthly_occurrence(date(2028, 1, 29), 1) == date(2028, 2, 29)
    assert monthly_occurrence(date(2028, 2, 29), 12) == date(2029, 2, 28)
    assert monthly_occurrence(date(2028, 2, 29), 48) == date(2032, 2, 29)


@given(
    st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31)),
    st.integers(min_value=0, max_value=240),
)
def test_recorrencia_preserva_o_dia_quando_o_mes_tem_o_dia(anchor: date, k: int) -> None:
    occ = monthly_occurrence(anchor, k)
    assert occ.day == min(anchor.day, days_in_month(occ.year, occ.month))
    months_apart = (occ.year - anchor.year) * 12 + (occ.month - anchor.month)
    assert months_apart == k


def test_monthly_occurrences_dentro_do_intervalo() -> None:
    anchor = date(2026, 1, 31)
    got = list(monthly_occurrences(anchor, date(2026, 2, 1), date(2026, 4, 30)))
    assert got == [date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]


def test_monthly_occurrences_inclui_bordas_e_nao_vai_antes_da_ancora() -> None:
    anchor = date(2026, 3, 10)
    got = list(monthly_occurrences(anchor, date(2026, 1, 1), date(2026, 5, 10)))
    assert got == [date(2026, 3, 10), date(2026, 4, 10), date(2026, 5, 10)]


def test_monthly_occurrences_intervalo_vazio_ou_invertido() -> None:
    anchor = date(2026, 1, 15)
    assert list(monthly_occurrences(anchor, date(2026, 3, 16), date(2026, 4, 14))) == []
    assert list(monthly_occurrences(anchor, date(2026, 5, 1), date(2026, 4, 1))) == []


def test_year_month() -> None:
    ym = YearMonth(2026, 12)
    assert ym.shift(1) == YearMonth(2027, 1)
    assert ym.shift(-12) == YearMonth(2025, 12)
    assert YearMonth(2028, 2).last_day == date(2028, 2, 29)
    assert YearMonth.of(date(2026, 10, 15)) == YearMonth(2026, 10)
    assert YearMonth(2026, 10).contains(date(2026, 10, 31))
    assert not YearMonth(2026, 10).contains(date(2026, 11, 1))
    assert str(YearMonth(2026, 3)) == "03/2026"
    assert YearMonth(2026, 1) < YearMonth(2026, 2) < YearMonth(2027, 1)
    with pytest.raises(DateError):
        YearMonth(2026, 0)


def test_month_bounds() -> None:
    assert month_bounds(2026, 2) == (date(2026, 2, 1), date(2026, 2, 28))
    assert month_bounds(2026, 12) == (date(2026, 12, 1), date(2026, 12, 31))


def test_parse_e_format_datas() -> None:
    assert parse_iso_date("2026-10-15") == date(2026, 10, 15)
    assert parse_br_date("15/10/2026") == date(2026, 10, 15)
    assert format_br_date(date(2026, 1, 5)) == "05/01/2026"


@pytest.mark.parametrize("text", ["2026-02-30", "2026-13-01", "2026-1-5", "15/10/2026", ""])
def test_parse_iso_invalido(text: str) -> None:
    with pytest.raises(DateError):
        parse_iso_date(text)


@pytest.mark.parametrize("text", ["30/02/2026", "5/1/2026", "2026-10-15", "29/02/2027"])
def test_parse_br_invalido(text: str) -> None:
    with pytest.raises(DateError):
        parse_br_date(text)


@given(st.dates(min_value=date(1900, 1, 1), max_value=date(2200, 12, 31)))
def test_format_e_parse_br_sao_inversos(d: date) -> None:
    assert parse_br_date(format_br_date(d)) == d
