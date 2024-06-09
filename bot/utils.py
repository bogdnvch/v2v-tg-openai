import io
import os
import json
import uuid
import logging
import subprocess

from aiogram import types

from config import config
from database import requests


ASSISTANCE_COMPLETED_STATUS = "completed"
ASSISTANCE_REQUIRES_ACTION_STATUS = "requires_action"


async def voice_to_text(client, voice_message_path):
    with open(voice_message_path, "rb") as voice_file:
        transcription = await client.audio.transcriptions.create(
            model="whisper-1",
            language="ru",
            file=voice_file
        )
    return transcription.text


async def text_to_mp3(client, text):
    voice = await client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=text
    )
    voice_uuid = uuid.uuid4()
    filename = f"answer_{voice_uuid}"
    save_path = os.path.join(config.storage_dir, f"{filename}.mp3")
    voice.stream_to_file(save_path)
    return save_path, filename


async def mp3_to_ogg(mp3_path):
    try:
        with open(mp3_path, "rb") as mp3_file:
            mp3_io = io.BytesIO(mp3_file.read())
            ffmpeg_command = ["ffmpeg", "-i", "pipe:0", "-c:a", "libopus", "-f", "ogg", "pipe:1"]
            result = subprocess.run(ffmpeg_command, input=mp3_io.read(), capture_output=True)
            return result.stdout
    except Exception as e:
        logging.error(f"Error converting file: {e}")


async def get_answer_from_assistant(client, assistant, thread, message):
    error_message = "Что-то пошло не так, повторите попытку позже"
    try:
        await client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=message
        )
        run = await client.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=assistant.id,
            poll_interval_ms=1000
        )
        if run.status == ASSISTANCE_COMPLETED_STATUS:
            messages = await client.beta.threads.messages.list(thread_id=thread.id)
            new_message = messages.data[0].content[0].text.value
            return new_message, True
        elif run.status == ASSISTANCE_REQUIRES_ACTION_STATUS:
            print(run)
            tool_calls = run.required_action.submit_tool_outputs.tool_calls
            tool_outputs = list(map(__get_output_from_tool_call, tool_calls))
            run = await client.beta.threads.runs.submit_tool_outputs_and_poll(
                thread_id=thread.id,
                run_id=run.id,
                tool_outputs=tool_outputs
            )
            if run.status == ASSISTANCE_COMPLETED_STATUS:
                messages = await client.beta.threads.messages.list(thread_id=thread.id)
                new_message = messages.data[0].content[0].text.value
                return new_message, True
            else:
                return error_message, False
        else:
            return error_message, False
    except Exception as e:
        logging.error(f"Unexpected error when trying to get OpenAI response: {e}")
        return error_message, False


def __get_output_from_tool_call(tool_call):
    value = json.loads(tool_call.function.arguments)["value"]
    return {
        "tool_call_id": tool_call.id,
        "output": value
    }


async def save_voice_to_storage(message: types.Message):
    voice = message.voice
    file_info = await message.bot.get_file(voice.file_id)
    download_path = file_info.file_path
    save_path = os.path.join(config.storage_dir, f"voice_{voice.file_id}.mp3")
    await message.bot.download_file(download_path, save_path)
    return save_path


async def get_or_create_assistant(client):
    # if config.assistant_id:
    if 1 == 2:
        assistant = await client.beta.assistants.retrieve(assistant_id=config.assistant_id)
        created = False
    else:
        assistant = await client.beta.assistants.create(
            name="Voice Assistant",
            instructions="""Ты полезный ассистент. Твоя задача задавать вопросы пользователю и искать его ключевые 
            ценности в процессе ведения диалога. Вызывай функцию `save_value`, когда найдешь ровно одну ценность.
            Если их несколько, то вызывай функцию несколько раз. Разговаривай в расслабленном неформальном формате.""",
            model="gpt-3.5-turbo",
            tools=[{"type": "function", "function": save_value_json}]
        )
        print(assistant)
        created = True
    return assistant, created


async def get_or_start_thread(client, tg_user_id):
    user = await requests.get_user_by_telegram_id(telegram_id=tg_user_id)
    user_pk = user.id
    if user.thread_id:
        thread = await client.beta.threads.retrieve(thread_id=user.thread_id)
    else:
        thread = await client.beta.threads.create()
        await requests.update_user(user_pk=user_pk, thread_id=thread.id)
    return thread


save_value_json = {
    "name": "save_value",
    "description": "Поиск ключевой ценности пользователя",
    "parameters": {
        "type": "object",
        "properties": {
            "value": {
                "type": "string",
                "description": "Ключевая ценность пользователя"
            },
        },
        "required": [
            "value"
        ],
    }
}