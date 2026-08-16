import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    return os.getenv(
        "ARCHIVE_DATABASE_URL",
        "postgresql+psycopg://lumina:lumina_local_only@archive-db:5432/lumina_archive",
    )


def make_engine(url: str | None = None):
    resolved_url = url or database_url()
    options = {"pool_pre_ping": True}
    if resolved_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    return create_engine(resolved_url, **options)


def make_session_factory(url: str | None = None):
    return sessionmaker(bind=make_engine(url), autocommit=False, autoflush=False)
