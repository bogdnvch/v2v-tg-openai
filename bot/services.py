import os
import io
import re
import json
import uuid
import logging
import subprocess
from typing import Optional

from aiogram import types as aiogram_types
from openai import AsyncOpenAI
from openai.types.beta import Assistant, VectorStore
from openai.types.beta.threads import RequiredActionFunctionToolCall, Run

from bot import utils, mixins
from bot.config import config
from bot.database import requests
from bot.ampli import (
    ValueValidationEvent,
    PhotoRecognitionEvent
)


openai_client = AsyncOpenAI(api_key=config.openai_api_key)


class AssistantService(mixins.OpenAIClientMixin):
    """Сервис для работы с ассистентом"""

    assistant_name = "Voice Assistant"
    assistant_prompt = """
        You are a helpful assistant. Your task is to ask questions to the user and identify their key values during the conversation. 
        Call the `save_value` function when you find exactly one value. If there are multiple values, call the function multiple times. 
        For questions about 'anxiety', you must use `file_search` to retrieve and quote information from the Vector Store
        and you’re not allowed to come up with an answer to that, you can only use a file. 
        Ensure your answers about anxiety are short short short and do not explicitly reference the sources in your responses. 
        Speak in a relaxed and informal manner.
    """

    assistant: Assistant = None
    thread_id: str
    tg_user_id: int

    def __init__(self, tg_user_id: int, thread_id: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.thread_id = thread_id
        self.tg_user_id = tg_user_id

    async def initialize(self):
        if not self.assistant:
            if config.assistant_id:
                self.assistant = await self.client.beta.assistants.retrieve(assistant_id=config.assistant_id)
            else:
                self.assistant = await self.client.beta.assistants.create(
                    name=self.assistant_name,
                    instructions=self.assistant_prompt,
                    model=self.model,
                    tools=self._tools
                )
        await self._add_file_search_if_dont_have()
        return self

    async def _add_file_search_if_dont_have(self):
        file_search_tools = list(filter(lambda tool: tool.type == "file_search", self.assistant.tools))
        user_vector_store = await utils.get_user_vector_store_id(tg_user_id=self.tg_user_id)
        if not file_search_tools or not user_vector_store:
            service = AssistantFileSearch(assistant_id=self.assistant.id, client=self.client)
            await service.update_assistant(existing_tools=self._tools, tg_user_id=self.tg_user_id)

    @property
    def _tools(self):
        return [{
            "type": "function",
            "function": {
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
                    "required": ["value"],
                }
            }
        }]

    async def get_answer(self, message_text: str) -> str:
        try:
            answer_retriever = OpenAIAnswerRetrieveService(
                client=self.client,
                thread_id=self.thread_id,
                assistant_id=self.assistant.id
            )
            await answer_retriever.ask_question(message=message_text)
            assistant_answer = await answer_retriever.retrieve_answer(message=message_text, tg_user_id=self.tg_user_id)
            if assistant_answer:
                return assistant_answer
        except Exception as e:
            logging.error(f"Unexpected error when trying to get OpenAI response: {e}")


class OpenAIAnswerRetrieveService(mixins.OpenAIClientMixin):
    """Сервис получает ответ на заданный вопрос"""

    ASSISTANCE_COMPLETED_STATUS = "completed"
    ASSISTANCE_REQUIRES_ACTION_STATUS = "requires_action"

    assistant_id: str
    thread_id: str
    run: Run

    def __init__(self, assistant_id: str, thread_id: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.assistant_id = assistant_id
        self.thread_id = thread_id

    async def ask_question(self, message: str):
        await self.client.beta.threads.messages.create(
            thread_id=self.thread_id,
            role="user",
            content=message
        )
        self.run = await self.client.beta.threads.runs.create_and_poll(
            model=self.model,
            thread_id=self.thread_id,
            assistant_id=self.assistant_id,
            poll_interval_ms=1000
        )

    async def retrieve_answer(self, tg_user_id: int, message: str) -> Optional[str]:
        answer = None
        if self.run.status == self.ASSISTANCE_COMPLETED_STATUS:
            answer = await self._extract_answer()
        elif self.run.status == self.ASSISTANCE_REQUIRES_ACTION_STATUS:
            tool_calls = self.run.required_action.submit_tool_outputs.tool_calls
            tool_outputs = list(map(self._get_output_from_tool_call, tool_calls))
            await utils.validate_and_save_user_values(context=message, tool_outputs=tool_outputs, tg_user_id=tg_user_id)

            self.run = await self.client.beta.threads.runs.submit_tool_outputs_and_poll(
                thread_id=self.thread_id,
                run_id=self.run.id,
                tool_outputs=tool_outputs
            )
            if self.run.status == self.ASSISTANCE_COMPLETED_STATUS:
                answer = await self._extract_answer()
        return answer

    async def _extract_answer(self) -> str:
        messages = await self.client.beta.threads.messages.list(thread_id=self.thread_id)
        text = messages.data[0].content[0].text
        new_message = text.value
        if text.annotations:
            file_id = text.annotations[0].file_citation.file_id
            file = await openai_client.files.retrieve(file_id)
            new_message = self._remove_sources(new_message)
            new_message += f" Answer were taken from {file.filename}"
        return new_message

    @staticmethod
    def _remove_sources(text: str) -> str:
        return re.sub(r'【.*?】', "", text)

    @staticmethod
    def _get_output_from_tool_call(tool_call: RequiredActionFunctionToolCall) -> dict:
        value = json.loads(tool_call.function.arguments)["value"]
        return {
            "tool_call_id": tool_call.id,
            "output": value
        }


class VoiceToTextOpenAIService(mixins.OpenAIClientMixin, mixins.SaveFileLocallyMixin):
    """Сервис переводит сообщение из голоса в текст"""

    model = "whisper-1"

    async def voice_to_text(self, message: aiogram_types.Message) -> str:
        voice_local_path = await self._save_file_to_storage(message=message, type_of_file="voice")
        transcription_message = await self._openai_voice_to_text(voice_message_path=voice_local_path)
        return transcription_message

    async def _openai_voice_to_text(self, voice_message_path) -> str:
        with open(voice_message_path, "rb") as voice_file:
            transcription = await self.client.audio.transcriptions.create(
                model=self.model,
                language="ru",
                file=voice_file
            )
        return transcription.text


class TextToVoiceOpenAIService(mixins.OpenAIClientMixin):
    """Сервис переводит текст в .ogg файл"""

    model = "tts-1"

    _generated_filename: str

    async def text_to_voice(self, text: str) -> aiogram_types.BufferedInputFile:
        voice = await self.client.audio.speech.create(
            model=self.model,
            voice="nova",
            input=text
        )
        mp3_path = self._save_mp3_to_storage(voice=voice)
        ogg_voice_buffered = await self._mp3_to_ogg(mp3_path=mp3_path)
        ogg_voice_buffered = aiogram_types.BufferedInputFile(ogg_voice_buffered, self._generated_filename)
        return ogg_voice_buffered

    def _save_mp3_to_storage(self, voice) -> str:
        voice_uuid = uuid.uuid4()
        self._generated_filename = f"answer_{voice_uuid}"
        save_path = os.path.join(config.storage_dir, f"{self._generated_filename}.mp3")
        voice.stream_to_file(save_path)
        return save_path

    @staticmethod
    async def _mp3_to_ogg(mp3_path):
        try:
            with open(mp3_path, "rb") as mp3_file:
                mp3_io = io.BytesIO(mp3_file.read())
                ffmpeg_command = ["ffmpeg", "-i", "pipe:0", "-c:a", "libopus", "-f", "ogg", "pipe:1"]
                result = subprocess.run(ffmpeg_command, input=mp3_io.read(), capture_output=True)
                return result.stdout
        except Exception as e:
            logging.error(f"Error converting file: {e}")


class UserValueOpenAIValidator(mixins.OpenAIClientMixin):
    """Сервис для валидации ценности пользователя"""

    async def is_valid(self, context: str, value_to_validate: str, telegram_id: int, ):
        validation_result = await self._send_openai_request(
            context=context,
            value_to_validate=value_to_validate,
            telegram_id=telegram_id
        )
        return validation_result == "true"

    async def _send_openai_request(self, context: str, value_to_validate: str, telegram_id: int) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0.3,
            messages=[
                {
                    "role": "system",
                    "content": "You are an AI that validates user-selected values from the context. "
                            "If the value is a real interest or preference of the user, "
                            "return `validation_result` as `true`. If the value is incorrectly highlighted or "
                            "irrelevant, return `validation_result` as `false`."
                 },
                {
                    "role": "user", "content": context
                },
                {
                    "role": "system",
                    "content": f"Can this value `{value_to_validate}` be true for the user or is it just a context?"
                }
            ],
            tools=[{
                "type": "function",
                "function": self._function
            },],
            tool_choice={
                "type": "function",
                "function": {"name": self._function["name"]}
            }
        )
        await utils.send_event_to_amplitude(user_id=telegram_id, event=ValueValidationEvent())
        results = json.loads(response.choices[0].message.tool_calls[0].function.arguments)
        if result_value := results.get("value", None):
            return result_value["validation_result"]

    @property
    def _function(self):
        return {
            "name": "validate_value",
            "description": "Validation of the user's selected value from the context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "object",
                        "description": "The user's selected value from the context, "
                                       "including its name and possible validation results.",
                        "properties": {
                            "value_text": {"type": "string", "description": "The value text to validate."},
                            "validation_result": {
                                "type": "string",
                                "enum": ["true", "false"],
                                "description": "Validation result"
                            }
                        },
                        "required": ["value_text", "validation_result"]
                    }
                },
                "required": ["value"]
            }
        }


class ImageRecognitionService(mixins.OpenAIClientMixin, mixins.SaveFileLocallyMixin):
    """Сервис для распознавания настроения по фото лица пользователя"""

    type_of_file = "photo"

    async def recognize_mood_by_photo(self, message: aiogram_types.Message):
        photo_local_path = await self._save_file_to_storage(message=message, type_of_file="photo")
        base64_image = utils.encode_image(photo_local_path)
        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0.3,
            messages=[
                {
                    "role": "system",
                    "content": "You are an AI assistant with computer vision, "
                               "your task is to recognize the user’s mood by the face photo. "
                               "Choose mood result from enum. "
                               "If you are not sure or its not a human on photo you should return `Unknown`"
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Recognize the user's mood."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpg;base64,{base64_image}",
                            }
                        }
                    ]
                }
            ],
            tools=[{
                "type": "function",
                "function": self._function
            }, ],
            tool_choice={
                "type": "function",
                "function": {"name": self._function["name"]}
            }
        )
        results = json.loads(response.choices[0].message.tool_calls[0].function.arguments)
        result_mood = results.get("mood", "Unknown")
        await utils.send_event_to_amplitude(user_id=message.from_user.id, event=PhotoRecognitionEvent())
        return result_mood

    @property
    def _function(self):
        return {
            "name": "recognize_mood",
            "description": "Mood recognition by face photo",
            "parameters": {
                "type": "object",
                "properties": {
                    "mood": {
                        "type": "string",
                        "description": "Mood result",
                        "enum": ["Anger", "Fear", "Sadness", "Disgust", "Happiness", "Surprise", "Unknown"]
                    }
                },
                "required": ["mood"]
            }
        }


class AssistantFileSearch(mixins.OpenAIClientMixin):

    assistant_id: str

    _file_names = ["Тревожность.docx"]

    def __init__(self, assistant_id: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.assistant_id = assistant_id

    async def update_assistant(self, existing_tools: list, tg_user_id: int):
        vector_store = await self._create_vector_store(name="Anxiety", tg_user_id=tg_user_id)
        tool_parameters = self._get_file_search_assistant_kwargs(
            existing_tools=existing_tools,
            vector_store_id=vector_store.id
        )
        assistant = await self.client.beta.assistants.update(
            assistant_id=self.assistant_id,
            **tool_parameters
        )
        return assistant

    async def _create_vector_store(self, name: str, tg_user_id: int) -> VectorStore:
        vector_store = await self.client.beta.vector_stores.create(name=name)
        file_paths = [os.path.join(config.documents_file_search_dir, file_name) for file_name in self._file_names]
        file_streams = [open(path, "rb") for path in file_paths]

        await self.client.beta.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vector_store.id,
            files=file_streams
        )
        await self._save_vector_id_to_db(tg_user_id=tg_user_id, vector_store_id=vector_store.id)
        return vector_store

    @staticmethod
    async def _save_vector_id_to_db(tg_user_id: int, vector_store_id: str):
        user = await requests.get_user_by_telegram_id(telegram_id=tg_user_id)
        await requests.update_user(user_pk=user.id, added_vector_store_id=vector_store_id)

    @staticmethod
    def _get_file_search_assistant_kwargs(existing_tools: list, vector_store_id: str):
        tools = existing_tools + [{"type": "file_search"}]
        return {
            "tools": tools,
            "tool_resources": {"file_search": {"vector_store_ids": [vector_store_id]}}
        }
