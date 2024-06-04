import io
import os
import uuid
import shelve
import logging
import subprocess

from aiogram import types

from config import config


ASSISTANCE_COMPLETED_STATUS = "completed"
ASSISTANCE_INCOMPLETE_STATUS = "incomplete"
ASSISTANCE_CANCELLED_STATUS = "cancelled"
ASSISTANCE_FAILED_STATUS = "failed"
ASSISTANCE_EXPIRED_STATUS = "expired"


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


async def get_answer_from_assistant(client, assistant, thread, question):
    error_message = "Что-то пошло не так, повторите попытку позже"
    try:
        await client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=question
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
        else:
            return error_message, False
    except Exception as e:
        logging.error(f"Unexpected error when trying to get OpenAI response: {e}")
        return error_message, False


async def save_voice_to_storage(message: types.Message):
    voice = message.voice
    file_info = await message.bot.get_file(voice.file_id)
    download_path = file_info.file_path
    save_path = os.path.join(config.storage_dir, f"voice_{voice.file_id}.mp3")
    await message.bot.download_file(download_path, save_path)
    return save_path


async def get_or_create_assistant(client):
    if config.assistance_id:
        assistant = await client.beta.assistants.retrieve(assistant_id=config.assistance_id)
    else:
        assistant = await client.beta.assistants.create(
            name="Voice Assistant",
            instructions="Ты полезный ассистент. Твоя задача отвечать на вопросы пользователей на русском языке.",
            model="gpt-3.5-turbo"
        )
    return assistant


async def get_or_start_thread(client, user_id):
    user_id = str(user_id)
    if thread_id := __get_thread(user_id=user_id):
        thread = await client.beta.threads.retrieve(thread_id=thread_id)
    else:
        thread = await client.beta.threads.create()
        __save_thread_to_db(user_id=user_id, thread_id=thread.id)
    return thread


def __get_thread(user_id):
    with shelve.open("threads_db") as db:
        return db.get(user_id)


def __save_thread_to_db(user_id, thread_id):
    with shelve.open("threads_db", writeback=True) as db:
        db[user_id] = thread_id
