import os
import io
import json
import uuid
import logging
import subprocess
from typing import Optional

from aiogram import types as aiogram_types
from openai import AsyncOpenAI
from openai.types.beta import Assistant
from openai.types.beta.threads import RequiredActionFunctionToolCall, Run

from bot import utils, mixins
from bot.config import config


openai_client = AsyncOpenAI(api_key=config.openai_api_key)


class AssistantService(mixins.OpenAIClientMixin):
    """Сервис для работы с ассистентом"""

    assistant_name = "Voice Assistant"
    assistant_prompt = """
        Ты полезный ассистент. Твоя задача задавать вопросы пользователю и искать его ключевые 
        ценности в процессе ведения диалога. Вызывай функцию `save_value`, когда найдешь ровно одну ценность.
        Если их несколько, то вызывай функцию несколько раз. Разговаривай в расслабленном неформальном формате.
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
        return self

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
        new_message = messages.data[0].content[0].text.value
        return new_message

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

    async def is_valid(self, context: str, value_to_validate: str):
        validation_result = await self._send_openai_request(context=context, value_to_validate=value_to_validate)
        return validation_result == "true"

    async def _send_openai_request(self, context: str, value_to_validate: str) -> str:
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
                        "description": "The user's selected value from the context, including its name and possible validation results.",
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
                        {"type": "text", "text": "What’s in this image?"},
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
