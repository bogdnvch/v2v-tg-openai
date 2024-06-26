from typing import Optional
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_api_token: str = Field(..., env="TELEGRAM_API_TOKEN")
    amplitude_api_key: str = Field(..., env="AMPLITUDE_API_KEY")
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    assistant_id: Optional[str] = Field(None, env="ASSISTANT_ID")

    storage_dir: str = str(Path(__file__).parent.parent / "storage")
    documents_file_search_dir: str = str(Path(__file__).parent / "documents")

    REDIS_HOST: str = Field(..., env="REDIS_HOST")
    REDIS_PORT: int = Field(..., env="REDIS_PORT")

    DB_HOST: str = Field(..., env="DB_HOST")
    DB_PORT: int = Field(..., env="DB_PORT")
    DB_USER: str = Field(..., env="DB_USER")
    DB_PASSWORD: str = Field(..., env="DB_PASSWORD")
    DB_NAME: str = Field(..., env="DB_NAME")

    @property
    def db_url(self):
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


config = Settings()
