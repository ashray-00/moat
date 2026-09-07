"""Async SQLAlchemy engine + session. The engine is lazy: it does not open a 
connection until first use, so importing this module never requires a live DB."""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings

engine = create_async_engine(settings.database_url, pool_size=10, max_overflow=20,
                             pool_pre_ping=True)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        