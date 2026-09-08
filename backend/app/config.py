from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    sec_user_agent: str = "Moat Research contact@yourdomain.com"

    database_url: str

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    groq_api_key: str = ""

    model_flagship: str = "openai/gpt-4o"
    model_cheap: str = "groq/llama-3.1-8b-instant"
    embed_model: str = "text-embedding-3-small"
    embed_dim: int = 1536

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    # Legacy Pro price id (alias for stripe_price_id_pro when that is empty).
    stripe_price_id: str = ""
    stripe_price_id_pro: str = ""
    stripe_price_id_team: str = ""

    # Auth API base, e.g. https://<project-ref>.supabase.co
    # (not DATABASE_URL — that is the Postgres host db.<ref>.supabase.co)
    supabase_url: str = ""

    # When true, /ask and user-scoped routes require a valid Bearer JWT.
    # Default false so local demos work before passwordless auth is enabled.
    auth_required: bool = False

    frontend_origin: str = "http://localhost:3000"
    frontend_url: str = "http://localhost:3000"

    metrics_token: str = ""

    answer_cache_enabled: bool = False

    # Soft per-user ask/agent rate limit (in-process; single instance only).
    rate_limit_per_minute: int = 30


settings = Settings()
