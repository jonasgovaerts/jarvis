from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from jarvis_core.db.models import Base


def create_engine_and_factory(database_url: str) -> tuple[AsyncEngine, async_sessionmaker]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def init_models(engine: AsyncEngine) -> None:
    """create_all keeps the single-user schema in sync; Alembic can take over
    once migrations matter."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
