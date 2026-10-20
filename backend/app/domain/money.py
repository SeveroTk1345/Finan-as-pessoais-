"""Dinheiro em centavos inteiros.

Regras deste módulo:
* Todo valor monetário é um ``int`` de centavos. ``float`` é rejeitado na entrada.
* Arredondamento só acontece em ``round_to_cents``, e o modo é sempre explícito
  (a regra padrão de arredondamento ainda é a decisão pendente A7).
* Somas e divisões em parcelas nunca perdem nem criam centavos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

# Limite de magnitude: 1 trilhão de reais. Mantém os valores muito abaixo do
# maior inteiro exato do JavaScript (2^53 - 1), já que a API trafega centavos em JSON.
MAX_ABS_CENTS = 100_000_000_000_000


class MoneyError(ValueError):
    """Valor monetário inválido."""


def _check_cents(value: object) -> int:
    # bool é subclasse de int em Python; True como "1 centavo" seria um bug silencioso.
    if isinstance(value, bool) or not isinstance(value, int):
        raise MoneyError(f"centavos devem ser int, recebido {type(value).__name__}")
    if abs(value) > MAX_ABS_CENTS:
        raise MoneyError("valor fora do limite permitido")
    return value


@dataclass(frozen=True, slots=True, order=True)
class Money:
    """Valor em centavos. Imutável e comparável."""

    cents: int

    def __post_init__(self) -> None:
        _check_cents(self.cents)

    @classmethod
    def zero(cls) -> Money:
        return cls(0)

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.cents + other.cents)

    def __sub__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.cents - other.cents)

    def __neg__(self) -> Money:
        return Money(-self.cents)

    def __abs__(self) -> Money:
        return Money(abs(self.cents))

    def is_negative(self) -> bool:
        return self.cents < 0

    def is_zero(self) -> bool:
        return self.cents == 0


def total(values: list[Money]) -> Money:
    """Soma exata de uma lista de valores."""
    acc = 0
    for v in values:
        acc += v.cents
    return Money(acc)


# Formato brasileiro: milhar com ponto (grupos de 3), decimal com vírgula, até 2 casas.
_BRL_PATTERN = re.compile(
    r"""^
    (?P<sign1>-)?\s*
    (?:R\$\s*)?
    (?P<sign2>-)?\s*
    (?P<int>\d{1,3}(?:\.\d{3})+|\d+)
    (?:,(?P<dec>\d{1,2}))?
    $""",
    re.VERBOSE,
)


def parse_brl(text: str, *, allow_negative: bool = False) -> Money:
    """Converte texto no formato brasileiro para Money.

    Aceita: ``"1.234,56"``, ``"1234,56"``, ``"1234"``, ``"R$ 1.234,56"``, ``"0,5"``.
    Rejeita: separador decimal com ponto (``"12.34"``), mais de 2 casas decimais,
    agrupamento de milhar irregular (``"1.23,00"``) e texto vazio.

    O ponto é sempre separador de milhar. ``"1.234"`` vale R$ 1.234,00. Arquivos em
    formato americano devem ser declarados como tal na importação, nunca adivinhados.
    """
    if not isinstance(text, str):
        raise MoneyError("valor deve ser texto")
    normalized = text.replace("\u00a0", " ").strip()
    match = _BRL_PATTERN.match(normalized)
    if match is None:
        raise MoneyError(f"valor em formato inválido: {text!r}")
    if match.group("sign1") and match.group("sign2"):
        raise MoneyError(f"sinal duplicado: {text!r}")
    negative = bool(match.group("sign1") or match.group("sign2"))

    reais = int(match.group("int").replace(".", ""))
    dec = match.group("dec") or "0"
    centavos = int(dec.ljust(2, "0"))
    cents = reais * 100 + centavos
    if negative:
        if not allow_negative:
            raise MoneyError("valor negativo não permitido")
        cents = -cents
    return Money(cents)


def format_brl(value: Money) -> str:
    """Formata como ``R$ 1.234,56`` (negativo: ``-R$ 1.234,56``)."""
    cents = value.cents
    sign = "-" if cents < 0 else ""
    reais, centavos = divmod(abs(cents), 100)
    grouped = f"{reais:,}".replace(",", ".")
    return f"{sign}R$ {grouped},{centavos:02d}"


def split_installments(amount: Money, count: int) -> list[Money]:
    """Divide um valor em ``count`` parcelas inteiras cuja soma é exatamente o valor.

    O resto da divisão vai inteiro para a primeira parcela (decisão 5.3 da auditoria):
    R$ 100,00 em 3x resulta em 33,34 + 33,33 + 33,33.
    """
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise MoneyError("quantidade de parcelas deve ser inteiro >= 1")
    if amount.cents <= 0:
        raise MoneyError("valor parcelado deve ser positivo")
    base, remainder = divmod(amount.cents, count)
    return [Money(base + remainder)] + [Money(base)] * (count - 1)


def round_to_cents(value: Decimal, rounding: str) -> Money:
    """Arredonda um Decimal em reais para centavos com o modo informado.

    ``rounding`` é um modo do módulo ``decimal`` (ex.: ``decimal.ROUND_HALF_UP``).
    Não há modo padrão de propósito: a regra de arredondamento é a decisão A7.
    """
    if not isinstance(value, Decimal):
        raise MoneyError("use Decimal para cálculos com frações de centavo")
    if not value.is_finite():
        raise MoneyError("valor não finito")
    quantized = value.quantize(Decimal("0.01"), rounding=rounding)
    return Money(int(quantized * 100))
