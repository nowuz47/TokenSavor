from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(default="sqlite:///./scrooge.db", alias="SCROOGE_DATABASE_URL")
    store_prompt_bodies: bool = Field(default=False, alias="SCROOGE_STORE_PROMPT_BODIES")
    default_provider: str = Field(default="openai", alias="SCROOGE_DEFAULT_PROVIDER")
    default_model: str = Field(default="gpt-5.4-mini", alias="SCROOGE_DEFAULT_MODEL")
    upstream_openai: AnyHttpUrl | None = Field(
        default="https://api.openai.com", alias="SCROOGE_UPSTREAM_OPENAI"
    )
    upstream_anthropic: AnyHttpUrl | None = Field(
        default="https://api.anthropic.com", alias="SCROOGE_UPSTREAM_ANTHROPIC"
    )
    upstream_gemini: AnyHttpUrl | None = Field(
        default="https://generativelanguage.googleapis.com", alias="SCROOGE_UPSTREAM_GEMINI"
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def upstream_for(self, provider: str) -> str | None:
        value = getattr(self, f"upstream_{provider.lower()}", None)
        return str(value).rstrip("/") if value else None


@lru_cache
def get_settings() -> Settings:
    return Settings()

