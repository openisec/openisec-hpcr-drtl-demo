import os
from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App
    APP_NAME: str = "HPCR-DRTL API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    # Database
    DATABASE_URL: str = ""
    # Security
    SECRET_KEY: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"
    # Gemini API (Google AI Studio)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    # HPCR-DRTL Volume limits (base)
    HISTORY_MAX_CHARS: int = 300
    HISTORY_MAX_CHARS_MEDIUM: int = 400
    HISTORY_MAX_CHARS_LONG: int = 600
    PRO_MAX_ITEMS: int = 10
    PRO_ITEM_MAX_CHARS: int = 50
    CON_MAX_ITEMS: int = 10
    CON_ITEM_MAX_CHARS: int = 50
    RECOMMENDATION_MAX_CHARS: int = 300
    RECOMMENDATION_MAX_CHARS_MEDIUM: int = 400
    RECOMMENDATION_MAX_CHARS_LONG: int = 500
    DECISION_MAX_CHARS: int = 1000
    LOG_SUMMARY_MAX_CHARS: int = 500
    # Query length thresholds
    QUERY_LENGTH_SHORT: int = 100
    QUERY_LENGTH_MEDIUM: int = 300
    # Input Guardrail
    INPUT_MAX_CHARS: int = 4000
    ALLOWED_INPUT_CONTENT_TYPES: list[str] = ["text/plain"]
    # Rate limiting
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10
    API_RATE_LIMIT_PER_MINUTE: int = 60
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

@lru_cache()
def get_settings() -> Settings:
    return Settings()