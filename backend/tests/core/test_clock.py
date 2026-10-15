from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.core.clock import APP_TZ, FixedClock, SystemClock, now_sp, today_sp


def test_today_sp_na_virada_do_dia() -> None:
    # 02:00 UTC de 15/10/2026 ainda é 23:00 de 14/10 em São Paulo (UTC-3).
    clock = FixedClock(datetime(2026, 10, 15, 2, 0, tzinfo=UTC))
    assert today_sp(clock) == date(2026, 10, 14)
    assert now_sp(clock).hour == 23


def test_today_sp_logo_apos_meia_noite_local() -> None:
    clock = FixedClock(datetime(2026, 10, 15, 3, 0, tzinfo=UTC))
    assert today_sp(clock) == date(2026, 10, 15)


def test_virada_de_mes_e_de_ano() -> None:
    assert today_sp(FixedClock(datetime(2026, 11, 1, 2, 59, tzinfo=UTC))) == date(2026, 10, 31)
    assert today_sp(FixedClock(datetime(2027, 1, 1, 2, 59, tzinfo=UTC))) == date(2026, 12, 31)


def test_horario_de_verao_historico_vem_da_base_tz() -> None:
    # Em 15/01/2018 São Paulo estava em horário de verão (UTC-2). Um offset fixo de -3 erraria.
    clock = FixedClock(datetime(2018, 1, 15, 2, 30, tzinfo=UTC))
    assert now_sp(clock).utcoffset() == timedelta(hours=-2)
    assert today_sp(clock) == date(2018, 1, 15)


def test_fixed_clock_aceita_outro_fuso_e_exige_fuso() -> None:
    other = timezone(timedelta(hours=9))
    clock = FixedClock(datetime(2026, 10, 15, 10, 0, tzinfo=other))
    assert clock.now_utc() == datetime(2026, 10, 15, 1, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="fuso"):
        FixedClock(datetime(2026, 10, 15, 10, 0))  # noqa: DTZ001


def test_system_clock_retorna_utc_com_fuso() -> None:
    now = SystemClock().now_utc()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_fuso_configurado() -> None:
    assert str(APP_TZ) == "America/Sao_Paulo"
