import os
import asyncio
import logging

from aiogram import Bot, Dispatcher

from config import config
from handlers import register_handlers

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.telegram_api_token)
dp = Dispatcher(bot=bot)
os.makedirs("../storage", exist_ok=True)  # creating storage for voice messages


async def main():
    register_handlers(dp)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
