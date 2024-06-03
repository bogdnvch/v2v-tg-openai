from aiogram import Dispatcher, Router, types
from aiogram.filters.command import Command
from openai import OpenAI

from config import config

from . import utils

router = Router()
client = OpenAI(api_key=config.openai_api_key)
# assistant = utils.get_or_create_assistant(client=client)


@router.message(Command("start"))
async def handle_start(message: types.Message):
    await message.answer("Отправь мне голосовое сообщение")


@router.message(lambda message: message.text)
async def handle_text(message: types.Message):
    await message.reply("Я так не понимаю, отправляй мне только голосовые сообщения")


@router.message(lambda message: message.voice)
async def handle_voice(message: types.Message):
    voice_path = await utils.save_voice_to_storage(message=message)
    # message_text = utils.voice_to_text(client=client, voice_message_path=voice_path)
    #
    # thread = utils.get_or_start_thread(client=client, user_id=message.from_user.id)
    # assistant_answer = utils.get_answer_from_assistant(
    #     client=client,
    #     assistant=assistant,
    #     thread=thread,
    #     question=message_text
    # )
    # answer_voice_path = utils.text_to_voice(client=client, text=assistant_answer)
    # await message.answer_voice(answer_voice_path)
    await message.answer("Скоро все будет")


def register_handlers(dp: Dispatcher):
    dp.include_router(router)
