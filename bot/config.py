from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_api_token: str = Field(..., env="TELEGRAM_API_TOKEN")
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    assistance_id: Optional[str] = Field(None, env="ASSISTANCE_ID")
    storage_dir: str = "./storage"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


config = Settings()
