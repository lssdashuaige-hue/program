from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    frontend_origin: str = "http://localhost:3000"
    supabase_url: str | None = None
    supabase_publishable_key: str | None = None
    supabase_secret_key: str | None = None
    llm_provider: Literal["auto", "openai", "deepseek"] = "auto"
    openai_api_key: str | None = None
    openai_reflection_model: str = "gpt-5.6-terra"
    openai_review_model: str = "gpt-5.6-terra"
    openai_reflection_reasoning_effort: Literal[
        "none", "low", "medium", "high", "xhigh", "max"
    ] = "medium"
    openai_review_reasoning_effort: Literal[
        "none", "low", "medium", "high", "xhigh", "max"
    ] = "medium"
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_reflection_model: str = "deepseek-v4-pro"
    deepseek_review_model: str = "deepseek-v4-pro"
    deepseek_reflection_reasoning_effort: Literal["high", "max"] = "high"
    deepseek_review_reasoning_effort: Literal["high", "max"] = "high"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
