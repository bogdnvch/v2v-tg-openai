import os
import asyncio
import logging

from aiogram import Bot, Dispatcher

from config import config
from handlers import register_handlers
from database.requests import get_user_by_telegram_id, update_user
from database import models

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.telegram_api_token)
dp = Dispatcher(bot=bot)
os.makedirs("../storage", exist_ok=True)  # creating storage for voice messages


async def main():
    register_handlers(dp)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # asyncio.run(models.create_table())
    asyncio.run(main())
