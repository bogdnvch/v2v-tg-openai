from sqlalchemy import BigInteger, ARRAY, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncAttrs, AsyncSession

from bot.config import config

async_engine = create_async_engine(url=config.db_url, echo=False)
async_session = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=True)


class Base(AsyncAttrs, DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)


class User(Base):
    __tablename__ = "user"

    telegram_id: Mapped[BigInteger] = mapped_column(BigInteger, index=True, unique=True, nullable=False)
    thread_id: Mapped[str] = mapped_column(unique=True, nullable=True)
    values: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=True)

    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id})>"


async def create_table():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

