from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models import Base

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
        )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


def _sqlite_add_reimbursement_fight_description(connection) -> None:
    """Add fight_description to existing SQLite DBs (create_all does not alter tables)."""
    from sqlalchemy import inspect, text

    if getattr(connection.dialect, "name", "") != "sqlite":
        return

    insp = inspect(connection)
    if not insp.has_table("repair_reimbursement_requests"):
        return
    cols = {c["name"] for c in insp.get_columns("repair_reimbursement_requests")}
    if "fight_description" in cols:
        return
    connection.execute(
        text(
            "ALTER TABLE repair_reimbursement_requests "
            "ADD COLUMN fight_description TEXT NOT NULL DEFAULT ''"
        )
    )


def _sqlite_add_reimbursement_submitter_guild_tag(connection) -> None:
    """Add submitter_guild_tag to existing SQLite DBs."""
    from sqlalchemy import inspect, text

    if getattr(connection.dialect, "name", "") != "sqlite":
        return

    insp = inspect(connection)
    if not insp.has_table("repair_reimbursement_requests"):
        return
    cols = {c["name"] for c in insp.get_columns("repair_reimbursement_requests")}
    if "submitter_guild_tag" in cols:
        return
    connection.execute(
        text(
            "ALTER TABLE repair_reimbursement_requests "
            "ADD COLUMN submitter_guild_tag VARCHAR(32) NOT NULL DEFAULT ''"
        )
    )


def _sqlite_add_user_is_officer(connection) -> None:
    from sqlalchemy import inspect, text

    if getattr(connection.dialect, "name", "") != "sqlite":
        return
    insp = inspect(connection)
    if not insp.has_table("users"):
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    if "is_officer" in cols:
        return
    connection.execute(text("ALTER TABLE users ADD COLUMN is_officer BOOLEAN NOT NULL DEFAULT 0"))


def _sqlite_add_user_is_member(connection) -> None:
    from sqlalchemy import inspect, text

    if getattr(connection.dialect, "name", "") != "sqlite":
        return
    insp = inspect(connection)
    if not insp.has_table("users"):
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    if "is_member" in cols:
        return
    connection.execute(text("ALTER TABLE users ADD COLUMN is_member BOOLEAN NOT NULL DEFAULT 0"))


async def init_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_sqlite_add_reimbursement_fight_description)
        await conn.run_sync(_sqlite_add_reimbursement_submitter_guild_tag)
        await conn.run_sync(_sqlite_add_user_is_officer)
        await conn.run_sync(_sqlite_add_user_is_member)


async def get_db() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session
