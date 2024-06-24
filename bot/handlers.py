from aiogram import Dispatcher, Router, types
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from openai import AsyncOpenAI

from ampli import (
    UserRegistrationEvent,
    UserSendTextEvent,
    UserSendVoiceEvent,
    UserSendPhotoEvent,
)
from config import config
from database import requests
import utils
from services import (
    AssistantService,
    VoiceToTextOpenAIService,
    TextToVoiceOpenAIService,
    ImageRecognitionService
)
from states import UserInfo


router = Router()
client = AsyncOpenAI(api_key=config.openai_api_key)


@router.message(Command("start"))
async def handle_start(message: types.Message):
    await utils.send_event_to_amplitude(user_id=message.from_user.id, event=UserRegistrationEvent())
    await requests.create_user_if_not_exists(telegram_id=message.from_user.id)
    await message.answer("Send me voice message")


@router.message(lambda message: message.text)
async def handle_text(message: types.Message):
    await utils.send_event_to_amplitude(user_id=message.from_user.id, event=UserSendTextEvent())
    await message.reply("I don’t get it, just send me voice messages")


@router.message(lambda message: message.voice)
async def handle_voice(message: types.Message, state: FSMContext):
    await state.set_state(UserInfo.thread_id)
    await utils.send_event_to_amplitude(user_id=message.from_user.id, event=UserSendVoiceEvent())
    thread = await utils.get_or_create_thread_for_user(tg_user_id=message.from_user.id)
    await state.update_data(thread_id=thread.id)
    data = await state.get_data()
    print("Print just to show that thread_id was stored in the state |", data["thread_id"])
    await state.clear()
    message_text = await VoiceToTextOpenAIService(client=client).voice_to_text(message=message)
    assistant_service = await AssistantService(
        client=client,
        thread_id=thread.id,
        tg_user_id=message.from_user.id
    ).initialize()
    answer = await assistant_service.get_answer(message_text=message_text)

    if not answer:
        await message.reply("Something went wrong, try again later")
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
