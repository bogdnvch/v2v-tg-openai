import os
import time
import uuid
import shelve

from aiogram import types

from config import config


ASSISTANCE_COMPLETED_STATUS = "completed"


def voice_to_text(client, voice_message_path):
    with open(voice_message_path, "rb") as voice_file:
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            language="ru",
            file=voice_file
        )
    return transcription.text


def text_to_voice(client, text):
    voice = client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=text
    )
    voice_uuid = uuid.uuid4()
    save_path = os.path.join(config.storage_dir, "answers", f"answer_{voice_uuid}.mp3")
    voice.stream_to_file(save_path)
    return save_path


def get_answer_from_assistant(client, assistant, thread, question):
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=question
    )

    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant.id
    )
    while run.status != ASSISTANCE_COMPLETED_STATUS:
        time.sleep(0.5)
        run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)

    messages = client.beta.threads.messages.list(thread_id=thread.id)
    new_message = messages.data[0].content[0].text.value
    return new_message


async def save_voice_to_storage(message: types.Message):
    voice = message.voice
    file_info = await message.bot.get_file(voice.file_id)
    download_path = file_info.file_path
    save_path = os.path.join(config.storage_dir, "voices", f"voice_{voice.file_id}.mp3")
    await message.bot.download_file(download_path, save_path)
    return save_path


def get_or_create_assistant(client):
    if config.assistance_id:
        assistant = client.beta.assistants.retrieve(assistant_id=config.assistance_id)
    else:
        assistant = client.beta.assistants.create(
            name="Voice Assistant",
            instructions="Ты полезный ассистент. Твоя задача отвечать на вопросы пользователей.",
            model="gpt-3.5-turbo"
        )
    return assistant


def get_or_start_thread(client, user_id):
    if thread_id := __get_thread(user_id=user_id):
        thread = client.beta.threads.retrieve(thread_id=thread_id)
    else:
        thread = client.beta.threads.create()
        __save_thread_to_db(user_id=user_id, thread_id=thread.id)
    return thread


def __get_thread(user_id):
    with shelve.open("threads_db") as db:
        return db.get(user_id)


def __save_thread_to_db(user_id, thread_id):
    with shelve.open("threads_db", writeback=True) as db:
        db[user_id] = thread_id
