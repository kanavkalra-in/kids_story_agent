from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession

async def get_db_session() -> AsyncSession:
    """Dependency for getting database session"""
    async for session in get_db():
        yield session
