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

    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_anon_key: str = os.getenv("SUPABASE_ANON_KEY", "")

    stripe_secret_key: str = os.getenv("STRIPE_SECRET_KEY", "")
    stripe_webhook_secret: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    stripe_price_id: str = os.getenv("STRIPE_PRICE_ID", "")

    posthog_public_key: str = os.getenv("POSTHOG_PUBLIC_KEY", "")
    posthog_host: str = os.getenv("POSTHOG_HOST", "https://eu.posthog.com")

    # --- Compass (the adaptive practice engine) ---
    # Org-global cap on LLM item generations per UTC day. Set per-user later in commit 4
    # when real users exist; during dev this is a single shared bucket.
    compass_daily_gen_cap: int = int(os.getenv("COMPASS_DAILY_GEN_CAP", "200"))
    # When false (the default), generated items land with archived=true so they're invisible
    # to the picker until a human flips them. Flip to true once first ~30 items audit clean.
    compass_autoapprove_generated: bool = os.getenv("COMPASS_AUTOAPPROVE_GENERATED", "false").lower() == "true"


settings = Settings()
