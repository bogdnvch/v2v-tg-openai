import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot.handlers import register_handlers
from config import config

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.telegram_api_token)
dp = Dispatcher(bot=bot)


async def main():
    register_handlers(dp)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
