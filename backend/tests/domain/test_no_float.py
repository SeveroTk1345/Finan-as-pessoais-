"""Garante que o domínio financeiro não usa ponto flutuante binário."""

from __future__ import annotations

import ast
from pathlib import Path

DOMAIN_DIR = Path(__file__).resolve().parents[2] / "app" / "domain"

# Módulos com matemática de juros e rentabilidade precisam de divisão com Decimal.
# Neles a divisão "/" é permitida, mas literais float e float() continuam proibidos.
DECIMAL_MATH_MODULES = {"debts.py", "investments.py", "goals.py"}


def _float_usages(source: str, *, allow_div: bool = False) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            found.append(f"linha {node.lineno}: literal float {node.value!r}")
        elif isinstance(node, ast.Name) and node.id == "float":
            found.append(f"linha {node.lineno}: uso de 'float'")
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and not allow_div:
            found.append(f"linha {node.lineno}: divisão '/' (use // ou Decimal)")
    return found


def test_detector_funciona() -> None:
    assert _float_usages("x = 1.5")
    assert _float_usages("y = float('1')")
    assert _float_usages("z = 3 / 2")
    assert not _float_usages("w = 3 // 2")


def test_dominio_sem_float() -> None:
    files = sorted(DOMAIN_DIR.rglob("*.py"))
    assert files, "nenhum arquivo de domínio encontrado"
    problems = {
        str(f.relative_to(DOMAIN_DIR)): usages
        for f in files
        if (usages := _float_usages(f.read_text(encoding="utf-8"), allow_div=f.name in DECIMAL_MATH_MODULES))
    }
    assert problems == {}


def test_modulos_com_divisao_usam_decimal() -> None:
    for name in DECIMAL_MATH_MODULES:
        source = (DOMAIN_DIR / name).read_text(encoding="utf-8")
        assert "from decimal import" in source, name
