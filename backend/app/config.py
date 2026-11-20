import json
import os
from typing import List
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

_DEVELOPMENT_SECRET = "ai-foodie-super-secret-jwt-key-expo-2026-demo-secure"
_DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
]


def _load_allowed_origins() -> List[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "").strip()
    if not raw:
        origins = _DEFAULT_ALLOWED_ORIGINS.copy()
    else:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = [origin.strip() for origin in raw.split(",") if origin.strip()]
        if not isinstance(parsed, list) or any(not isinstance(origin, str) for origin in parsed):
            raise ValueError("ALLOWED_ORIGINS must be a JSON array or comma-separated list of origins")
        origins = [origin.rstrip("/") for origin in parsed if origin.strip()]

    if os.getenv("ENVIRONMENT", "development").lower() == "production" and "*" in origins:
        raise ValueError("ALLOWED_ORIGINS cannot contain '*' in production")
    return origins

class Settings(BaseModel):
    APP_NAME: str = os.getenv("APP_NAME", "AI Foodie")
    APP_DESCRIPTION: str = os.getenv(
        "APP_DESCRIPTION",
        "Smart Food. Smarter Choices. - Intelligent Food Ordering & Restaurant Management"
    )
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    SECRET_KEY: str = os.getenv("SECRET_KEY", _DEVELOPMENT_SECRET)
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
    
    # Database URL
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./database/aifoodie.db")
    
    # Server host & port
    BACKEND_HOST: str = os.getenv("BACKEND_HOST", "127.0.0.1")
    BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))
    
    # CORS
    ALLOWED_ORIGINS: List[str] = _load_allowed_origins()
    
    # Optional LLM Key
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GEMINI_API_URL: str = os.getenv(
        "GEMINI_API_URL",
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
    )
    OPENAI_API_URL: str = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    PAYMENT_PROVIDER: str = os.getenv("PAYMENT_PROVIDER", "sandbox").lower()
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_PUBLISHABLE_KEY: str = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

settings = Settings()

if settings.ENVIRONMENT.lower() == "production" and (
    settings.SECRET_KEY == _DEVELOPMENT_SECRET
    or len(settings.SECRET_KEY) < 32
    or settings.SECRET_KEY.startswith("REPLACE_WITH")
):
    raise RuntimeError("Set a unique SECRET_KEY with at least 32 characters before running in production")
