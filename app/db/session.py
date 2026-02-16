from contextlib import contextmanager

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import settings

# Base class for models
Base = declarative_base()

# ============================================================================
# ASYNC SQLAlchemy (for FastAPI)
# ============================================================================

# Create async engine
engine = create_async_engine(
    settings.database_url,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    echo=settings.log_sql,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# ============================================================================
# SYNC SQLAlchemy (for Celery tasks)
# ============================================================================

# Convert asyncpg URL to psycopg2 URL for sync operations
# postgresql+asyncpg:// -> postgresql://
sync_database_url = settings.database_url.replace("+asyncpg", "")

# Create sync engine
sync_engine = create_engine(
    sync_database_url,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    echo=settings.log_sql,
)

# Create sync session factory
SessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """Dependency for getting async database session (for FastAPI endpoints)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@contextmanager
def get_sync_db() -> Session:
    """Context manager for getting sync database session (for Celery tasks)."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
