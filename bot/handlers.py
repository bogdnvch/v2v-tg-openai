from aiogram import Dispatcher, Router, types
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from openai import AsyncOpenAI

from bot.ampli import (
    UserRegistrationEvent,
    UserSendTextEvent,
    UserSendVoiceEvent,
    UserSendPhotoEvent,
)
from bot.config import config
from bot.database import requests
from bot import utils
from bot.services import (
    AssistantService,
    VoiceToTextOpenAIService,
    TextToVoiceOpenAIService,
    ImageRecognitionService
)


router = Router()
client = AsyncOpenAI(api_key=config.openai_api_key)


@router.message(Command("start"))
async def handle_start(message: types.Message, state: FSMContext):
    print(state)
    await utils.send_event_to_amplitude(user_id=message.from_user.id, event=UserRegistrationEvent())
    await requests.create_user_if_not_exists(telegram_id=message.from_user.id)
    await message.answer("Отправь мне голосовое сообщение")


@router.message(lambda message: message.text)
async def handle_text(message: types.Message):
    await utils.send_event_to_amplitude(user_id=message.from_user.id, event=UserSendTextEvent())
    await message.reply("Я так не понимаю, отправляй мне только голосовые сообщения")


@router.message(lambda message: message.voice)
async def handle_voice(message: types.Message):
    await utils.send_event_to_amplitude(user_id=message.from_user.id, event=UserSendVoiceEvent())
    thread = await utils.get_thread_for_user(tg_user_id=message.from_user.id)
    message_text = await VoiceToTextOpenAIService(client=client).voice_to_text(message=message)
    assistant_service = await AssistantService(
        client=client,
        thread_id=thread.id,
        tg_user_id=message.from_user.id
    ).initialize()
    answer = await assistant_service.get_answer(message_text=message_text)

    if not answer:
        await message.reply("Что-то пошло не так, повторите попытку позже")
        return

    ogg_voice = await TextToVoiceOpenAIService(client=client).text_to_voice(text=answer)
    await message.answer_voice(ogg_voice)


@router.message(lambda message: message.photo)
async def handle_image(message: types.Message):
    await utils.send_event_to_amplitude(user_id=message.from_user.id, event=UserSendPhotoEvent())
    service = ImageRecognitionService(client=client)
    mood_result = await service.recognize_mood_by_photo(message=message)
    await message.answer(mood_result)


def register_handlers(dp: Dispatcher):
    dp.include_router(router)
