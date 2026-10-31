from __future__ import annotations

from collections.abc import Generator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def build_engine(database_url: str) -> Engine:
    options: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    return create_engine(database_url, **options)


def get_db(request: Request) -> Generator[Session, None, None]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session
