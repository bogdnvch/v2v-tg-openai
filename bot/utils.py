import base64

from openai.types.beta import Thread

from bot.database import requests
from bot.services import openai_client, UserValueOpenAIValidator


async def get_thread_for_user(tg_user_id: int) -> Thread:
    user = await requests.get_user_by_telegram_id(telegram_id=tg_user_id)
    user_pk = user.id
    if user.thread_id:
        thread = await openai_client.beta.threads.retrieve(thread_id=user.thread_id)
    else:
        thread = await openai_client.beta.threads.create()
        await requests.update_user(user_pk=user_pk, thread_id=thread.id)
    return thread


async def validate_and_save_user_values(context: str, tool_outputs: list[dict], tg_user_id: int):
    values = [output["output"] for output in tool_outputs]
    validated_values = []
    validator = UserValueOpenAIValidator(client=openai_client)
    for value in values:
        is_valid = await validator.is_valid(context=context, value_to_validate=value)
        if is_valid:
            validated_values.append(value)
    await requests.update_user_values(telegram_id=tg_user_id, values=validated_values)


def encode_image(image_path: str):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')
