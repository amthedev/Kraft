from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

_connect_args = {}
if settings.ssl_context is not None:
    _connect_args["ssl"] = settings.ssl_context

engine = create_async_engine(
    settings.database_url,
    echo=not settings.is_production,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


def make_session_factory():
    """Cria um engine + session factory novos — necessário dentro de workers
    que rodam asyncio.run() em threads separadas (cada chamada cria seu próprio loop)."""
    _ca = {}
    if settings.ssl_context is not None:
        _ca["ssl"] = settings.ssl_context
    _engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        connect_args=_ca,
    )
    return async_sessionmaker(bind=_engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
