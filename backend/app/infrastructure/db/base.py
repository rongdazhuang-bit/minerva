"""SQLAlchemy declarative metadata root for ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base table registry for Alembic/autogenerate."""

    pass
