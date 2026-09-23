import os
from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App
    APP_NAME: str = "Openisec HPCRDTL API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    # Database
    DATABASE_URL: str = ""
    # Security
    SECRET_KEY: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"
    # Cookie設定
    # ローカル開発(localhost, http通信): .envで以下を上書き
    #   COOKIE_SECURE=False
    #   COOKIE_DOMAIN=  (空文字。Domain属性なしでSet-Cookie→ブラウザがlocalhostに自動限定)
    # dev/stg/prd/demo(Cloud Run, https通信): デフォルト値のままでOK(明示的な.env設定は不要)
    #   COOKIE_SECURE=True
    #   COOKIE_DOMAIN=.openisec.com
    # 【注意】本番系(stg/prd/demo)の環境変数にCOOKIE_SECURE=Falseを
    # 誤って設定しないこと。Secure属性が外れるとCookieがhttp経由でも
    # 送信可能になり、盗聴・中間者攻撃のリスクが生じる。
    COOKIE_DOMAIN: str = ".openisec.com"
    COOKIE_SECURE: bool = True 
    # Vertex AI
    VERTEX_PROJECT: str = "openisec-dev-488314"
    VERTEX_LOCATION: str = "global"
    GEMINI_MODEL: str = "gemini-2.5-flash"
    # Mail (Resend)
    RESEND_API_KEY: str = ""
    MAIL_FROM: str = "Openisec <noreply@mail.openisec.com>"
    FRONTEND_URL: str = "http://localhost:3000"
    # 追加で許可するCORSオリジン(カンマ区切り)。カスタムドメイン未マッピング時の
    # Cloud Run生URL(https://xxx-xxx.a.run.app)など、FRONTEND_URL以外に
    # 許可したいオリジンがある場合に環境変数で指定する。
    ADDITIONAL_CORS_ORIGINS: str = ""
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30
    EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES: int = 30
    # Consent (Terms / Privacy Policy versions)
    TERMS_VERSION: str = "1.0"
    PRIVACY_POLICY_VERSION: str = "1.0"
    # HPCRDTL Volume limits (base)
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
    # Model Armor (LLM01: prompt injection / jailbreak detection, defense-in-depth
    # alongside the regex-based validate_input() check)
    MODEL_ARMOR_ENABLED: bool = True
    MODEL_ARMOR_LOCATION: str = "us-central1"
    MODEL_ARMOR_TEMPLATE: str = "hpcr-drtl-pi-guard"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

@lru_cache()
def get_settings() -> Settings:
    return Settings()