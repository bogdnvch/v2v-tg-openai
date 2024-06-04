import os
import asyncio
import logging

from aiogram import Bot, Dispatcher

from config import config
from handlers import router

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.telegram_api_token)
dp = Dispatcher(bot=bot)
os.makedirs(config.storage_dir, exist_ok=True)  # creating storage for voice messages


async def main():
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
