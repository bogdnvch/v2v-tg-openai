import os
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage, Redis

from config import config
from handlers import register_handlers

logging.basicConfig(level=logging.INFO)

redis = Redis(host=config.REDIS_HOST, port=config.REDIS_PORT)
bot = Bot(token=config.telegram_api_token)
dp = Dispatcher(bot=bot, storage=RedisStorage(redis=redis))
os.makedirs(config.storage_dir, exist_ok=True)  # creating local storage for mp3 and jpg


async def main():
    register_handlers(dp)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
