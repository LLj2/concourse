from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseModel):
    app_env: str = os.getenv("APP_ENV", "development")
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
    session_secret: str = os.getenv("SESSION_SECRET", "dev-secret-change-me")

    database_url: str = os.getenv("DATABASE_URL", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")

    stripe_secret_key: str = os.getenv("STRIPE_SECRET_KEY", "")
    stripe_webhook_secret: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    stripe_price_id: str = os.getenv("STRIPE_PRICE_ID", "")

    posthog_public_key: str = os.getenv("POSTHOG_PUBLIC_KEY", "")
    posthog_host: str = os.getenv("POSTHOG_HOST", "https://eu.posthog.com")


settings = Settings()
