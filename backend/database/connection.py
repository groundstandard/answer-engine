from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from backend.config.settings import settings

# statement_cache_size=0 is required when connecting through a pgbouncer pooler
# (Supabase session pooler); it's harmless on a direct connection.
# .strip() guards against a stray trailing newline/space in the DATABASE_URL env
# var (a common paste artifact in hosting dashboards) that would otherwise make the
# driver look for a database literally named "postgres\n".
engine = create_async_engine(
    settings.DATABASE_URL.strip(),
    echo=False,
    connect_args={"statement_cache_size": 0},
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
