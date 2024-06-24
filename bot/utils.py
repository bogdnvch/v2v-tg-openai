import base64
import asyncio
from typing import Union, Optional

from openai.types.beta import Thread

from database import requests
from services import openai_client, UserValueOpenAIValidator
from ampli import executor, amplitude, Event


async def send_event_to_amplitude(user_id: Union[str, int], event: Event):
    user_id = str(user_id)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(executor, amplitude.track, user_id, event)


async def get_thread_for_user(tg_user_id: int) -> Thread:
    user = await requests.get_user_by_telegram_id(telegram_id=tg_user_id)
    user_pk = user.id
    if user.thread_id:
        thread = await openai_client.beta.threads.retrieve(thread_id=user.thread_id)
    else:
        thread = await openai_client.beta.threads.create()
        await requests.update_user(user_pk=user_pk, thread_id=thread.id)
    return thread


async def get_user_vector_store_id(tg_user_id: int) -> Optional[str]:
    user = await requests.get_user_by_telegram_id(telegram_id=tg_user_id)
    return user.added_vector_store_id


async def validate_and_save_user_values(context: str, tool_outputs: list[dict], tg_user_id: int):
    values = [output["output"] for output in tool_outputs]
    validated_values = []
    validator = UserValueOpenAIValidator(client=openai_client)
    for value in values:
        is_valid = await validator.is_valid(context=context, value_to_validate=value, telegram_id=tg_user_id)
        if is_valid:
            validated_values.append(value)
    await requests.update_user_values(telegram_id=tg_user_id, values=validated_values)


def encode_image(image_path: str):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')
