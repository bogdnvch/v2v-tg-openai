from aiogram import Router, types
from aiogram.filters.command import Command
from openai import AsyncOpenAI

import utils
from config import config


router = Router()
client = AsyncOpenAI(api_key=config.openai_api_key)


@router.message(Command("start"))
async def handle_start(message: types.Message):
    await message.answer("Отправь мне голосовое сообщение")


@router.message(lambda message: message.text)
async def handle_text(message: types.Message):
    await message.reply("Я так не понимаю, отправляй мне только голосовые сообщения")


@router.message(lambda message: message.voice)
async def handle_voice(message: types.Message):
    assistant = await utils.get_or_create_assistant(client=client)

    voice_local_path = await utils.save_voice_to_storage(message=message)
    message_text = await utils.voice_to_text(client=client, voice_message_path=voice_local_path)
    thread = await utils.get_or_start_thread(client=client, user_id=message.from_user.id)
    assistant_answer, is_retrieved = await utils.get_answer_from_assistant(
        client=client,
        assistant=assistant,
        thread=thread,
        question=message_text
    )
    if not is_retrieved:
        await message.reply(assistant_answer)
    else:
        answer_mp3_path, answer_filename = await utils.text_to_mp3(client=client, text=assistant_answer)
        ogg_voice_buffered = await utils.mp3_to_ogg(mp3_path=answer_mp3_path)
        ogg_voice_buffered = types.BufferedInputFile(ogg_voice_buffered, answer_filename)
        await message.answer_voice(ogg_voice_buffered)
