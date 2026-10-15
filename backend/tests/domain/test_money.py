from __future__ import annotations

from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.money import (
    MAX_ABS_CENTS,
    Money,
    MoneyError,
    format_brl,
    parse_brl,
    round_to_cents,
    split_installments,
    total,
)

# --- construção ---------------------------------------------------------------


def test_money_aceita_int() -> None:
    assert Money(123456).cents == 123456


@pytest.mark.parametrize("bad", [1.5, 0.1, "100", Decimal("1"), True, None])
def test_money_rejeita_tipos_que_nao_sao_int(bad: object) -> None:
    with pytest.raises(MoneyError):
        Money(bad)  # type: ignore[arg-type]


def test_money_rejeita_valor_acima_do_limite() -> None:
    Money(MAX_ABS_CENTS)
    with pytest.raises(MoneyError):
        Money(MAX_ABS_CENTS + 1)
    with pytest.raises(MoneyError):
        Money(-MAX_ABS_CENTS - 1)


def test_limite_cabe_em_inteiro_exato_do_javascript() -> None:
    assert MAX_ABS_CENTS < 2**53 - 1


def test_aritmetica_exata() -> None:
    # O clássico 0,1 + 0,2 != 0,3 do float não acontece com centavos.
    assert Money(10) + Money(20) == Money(30)
    assert Money(30) - Money(50) == Money(-20)
    assert -Money(5) == Money(-5)
    assert abs(Money(-7)) == Money(7)
    assert total([Money(1)] * 10) == Money(10)
    assert total([]) == Money.zero()


def test_soma_com_tipo_errado_falha() -> None:
    with pytest.raises(TypeError):
        Money(1) + 1  # type: ignore[operator]


# --- parse_brl ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "cents"),
    [
        ("1.234,56", 123456),
        ("1234,56", 123456),
        ("1234", 123400),
        ("1.234", 123400),  # ponto é sempre milhar no formato BR
        ("0,5", 50),
        ("0,05", 5),
        ("0", 0),
        ("R$ 1.234,56", 123456),
        ("R$1.234,56", 123456),
        ("R$\u00a01.234,56", 123456),  # espaço não separável (Intl/Excel)
        ("  12,30  ", 1230),
        ("1.000.000,00", 100000000),
    ],
)
def test_parse_brl_valido(text: str, cents: int) -> None:
    assert parse_brl(text) == Money(cents)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "abc",
        "12.34",  # decimal com ponto: formato americano
        "1,234.56",
        "1,234",  # vírgula com 3 casas não é decimal válido
        "1,999",
        "1.23,00",  # milhar irregular
        "1.2345,00",
        "1,",
        ",50",
        "R$",
        "1 234,56",
        "--1,00",
        "+1,00",
        "1e3",
        "NaN",
    ],
)
def test_parse_brl_invalido(text: str) -> None:
    with pytest.raises(MoneyError):
        parse_brl(text)


def test_parse_brl_negativo_bloqueado_por_padrao() -> None:
    with pytest.raises(MoneyError, match="negativo"):
        parse_brl("-10,00")


@pytest.mark.parametrize("text", ["-1.234,56", "R$ -1.234,56", "-R$ 1.234,56"])
def test_parse_brl_negativo_quando_permitido(text: str) -> None:
    assert parse_brl(text, allow_negative=True) == Money(-123456)


def test_parse_brl_sinal_duplicado() -> None:
    with pytest.raises(MoneyError):
        parse_brl("-R$ -1,00", allow_negative=True)


def test_parse_brl_acima_do_limite() -> None:
    with pytest.raises(MoneyError):
        parse_brl("99999999999999999,99")


# --- format_brl ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("cents", "text"),
    [
        (0, "R$ 0,00"),
        (5, "R$ 0,05"),
        (100, "R$ 1,00"),
        (123456, "R$ 1.234,56"),
        (100000000, "R$ 1.000.000,00"),
        (-123456, "-R$ 1.234,56"),
        (-5, "-R$ 0,05"),
    ],
)
def test_format_brl(cents: int, text: str) -> None:
    assert format_brl(Money(cents)) == text


@given(st.integers(min_value=-MAX_ABS_CENTS, max_value=MAX_ABS_CENTS))
def test_format_e_parse_sao_inversos(cents: int) -> None:
    assert parse_brl(format_brl(Money(cents)), allow_negative=True) == Money(cents)


# --- split_installments -------------------------------------------------------


def test_parcelas_exemplo_da_auditoria() -> None:
    assert split_installments(Money(10000), 3) == [Money(3334), Money(3333), Money(3333)]


@pytest.mark.parametrize(
    ("amount", "count", "expected"),
    [
        (100, 1, [100]),
        (100, 4, [25, 25, 25, 25]),
        (1, 1, [1]),
        (2, 3, [2, 0, 0]),  # valor menor que a quantidade de parcelas
        (10001, 2, [5001, 5000]),
        (99999, 12, [8336, 8333, 8333, 8333, 8333, 8333, 8333, 8333, 8333, 8333, 8333, 8333]),
    ],
)
def test_parcelas_casos(amount: int, count: int, expected: list[int]) -> None:
    assert split_installments(Money(amount), count) == [Money(c) for c in expected]


@pytest.mark.parametrize("count", [0, -1, True])
def test_parcelas_quantidade_invalida(count: int) -> None:
    with pytest.raises(MoneyError):
        split_installments(Money(100), count)


@pytest.mark.parametrize("amount", [0, -100])
def test_parcelas_valor_nao_positivo(amount: int) -> None:
    with pytest.raises(MoneyError):
        split_installments(Money(amount), 2)


@given(
    st.integers(min_value=1, max_value=MAX_ABS_CENTS),
    st.integers(min_value=1, max_value=48),
)
def test_parcelas_somam_exatamente_o_total(amount: int, count: int) -> None:
    parts = split_installments(Money(amount), count)
    assert len(parts) == count
    assert total(parts) == Money(amount)
    # Todas as parcelas, exceto a primeira, são iguais; a primeira absorve o resto.
    assert len({p.cents for p in parts[1:]}) <= 1
    assert parts[0].cents - parts[-1].cents < count


# --- round_to_cents -----------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "mode", "cents"),
    [
        ("1.005", ROUND_HALF_UP, 101),
        ("1.005", ROUND_HALF_EVEN, 100),
        ("1.015", ROUND_HALF_EVEN, 102),
        ("-1.005", ROUND_HALF_UP, -101),
        ("0.004", ROUND_HALF_UP, 0),
        ("12.3", ROUND_HALF_UP, 1230),
    ],
)
def test_round_to_cents(value: str, mode: str, cents: int) -> None:
    assert round_to_cents(Decimal(value), mode) == Money(cents)


def test_round_to_cents_rejeita_float_e_infinito() -> None:
    with pytest.raises(MoneyError):
        round_to_cents(1.005, ROUND_HALF_UP)  # type: ignore[arg-type]
    with pytest.raises(MoneyError):
        round_to_cents(Decimal("Infinity"), ROUND_HALF_UP)
