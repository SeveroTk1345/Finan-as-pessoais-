"""Tabelas no SQLAlchemy Core. A fonte de verdade do esquema são as migrações Alembic;
estas definições servem para montar consultas com tipos.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    FetchedValue,
    Integer,
    MetaData,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=FetchedValue()),
    Column("username", Text, nullable=False),
    Column("display_name", Text, nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("is_active", Boolean, nullable=False, server_default=FetchedValue()),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=FetchedValue()),
)

accounts = Table(
    "accounts",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=FetchedValue()),
    Column("owner_id", UUID(as_uuid=True), nullable=False),
    Column("name", Text, nullable=False),
    Column("institution", Text),
    Column("kind", Text, nullable=False),
    Column("initial_balance_cents", BigInteger, nullable=False),
    Column("initial_balance_date", Date, nullable=False),
    Column("is_active", Boolean, nullable=False, server_default=FetchedValue()),
    Column("version", Integer, nullable=False, server_default=FetchedValue()),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=FetchedValue()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=FetchedValue()),
)
