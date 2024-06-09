from typing import Optional

from sqlalchemy import select

from . import models


async def create_user_if_not_exists(**kwargs):
    async with models.async_session() as session:
        stmt = select(models.User).filter_by(**kwargs)
        user: Optional[models.User] = await session.scalar(stmt)
        created = False
        if not user:
            user = models.User(**kwargs)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            created = True
        return user, created


async def get_user_by_telegram_id(telegram_id):
    async with models.async_session() as session:
        stmt = select(models.User).where(models.User.telegram_id == telegram_id)
        user: Optional[models.User] = await session.scalar(stmt)
        return user


async def update_user(user_pk, **kwargs):
    async with models.async_session() as session:
        user = await session.get(models.User, user_pk)
        for field, value in kwargs.items():
            setattr(user, field, value)
        await session.commit()
