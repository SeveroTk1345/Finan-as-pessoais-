"""Dados iniciais de um usuário novo (categorias padrão)."""

from __future__ import annotations

from sqlalchemy import Connection, text

# Nomes do dia a dia, na ordem em que aparecem nos botões. "Juros e tarifas" é
# usada automaticamente nos encargos de cartão (services/cards.py).
DEFAULT_EXPENSE_CATEGORIES = [
    "Mercado",
    "Contas da casa",
    "Casa",
    "Carro",
    "Transporte",
    "Medicamentos e saúde",
    "Faculdade e cursos",
    "Roupas e acessórios",
    "Restaurante e lanche",
    "Cuidados pessoais",
    "Lazer",
    "Assinaturas",
    "Presentes",
    "Juros e tarifas",
    "Outros",
]
DEFAULT_INCOME_CATEGORIES = ["Salário", "Aposentadoria", "Renda extra", "Benefícios", "Outros"]


def seed_user_defaults(conn: Connection, user_id: object) -> None:
    """Cria as categorias padrão, se a tabela já existir nesta versão do banco."""
    has_categories = conn.execute(text("SELECT to_regclass('public.categories')")).scalar()
    if not has_categories:
        return
    for kind, names in (
        ("despesa", DEFAULT_EXPENSE_CATEGORIES),
        ("receita", DEFAULT_INCOME_CATEGORIES),
    ):
        for position, name in enumerate(names):
            conn.execute(
                text(
                    "INSERT INTO categories (owner_id, name, kind, position, is_system) "
                    "VALUES (:o, :n, :k, :p, true) ON CONFLICT DO NOTHING"
                ),
                {"o": user_id, "n": name, "k": kind, "p": position},
            )
