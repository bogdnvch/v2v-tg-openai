import os
from typing import Literal, Optional

from aiogram import types
from openai import AsyncOpenAI

from bot.config import config


class OpenAIClientMixin:
    """Миксин, используется везде, где нужен клиент опенаи"""

    model = "gpt-4o"

    def __init__(self, client: AsyncOpenAI, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = client


class SaveFileLocallyMixin:
    file_extension_mapping = {
        "voice": "mp3",
        "photo": "jpg",
    }

    async def _save_file_to_storage(
            self,
            message: types.Message,
            type_of_file: Literal["voice", "photo"]
    ) -> Optional[str]:
        file_obj = getattr(message, type_of_file, None)
        if not file_obj:
            return
        elif hasattr(file_obj, "__getitem__"):
            file_obj = file_obj[-1]
        file_info = await message.bot.get_file(file_obj.file_id)
        download_path = file_info.file_path
        save_path = os.path.join(
            config.storage_dir,
            f"{type_of_file}_{file_obj.file_id}.{self.file_extension_mapping[type_of_file]}"
        )
        await message.bot.download_file(download_path, save_path)
        return save_path
