from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    sec_user_agent: str = "Moat Research contact@yourdomain.com"

    database_url: str

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    groq_api_key: str = ""
    cohere_api_key: str = ""

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
    # Default true for safe deploys; set AUTH_REQUIRED=false only for local demos.
    auth_required: bool = True

    frontend_origin: str = "http://localhost:3000"
    frontend_url: str = "http://localhost:3000"

    metrics_token: str = ""

    answer_cache_enabled: bool = False

    # Soft per-user ask/agent rate limit (in-process unless REDIS_URL is set).
    rate_limit_per_minute: int = 30

    # Comma-separated tickers; empty → builtin mega-cap seed list.
    moat_default_universe: str = ""

    # Optional shared rate-limit backend. Empty → in-process memory.
    redis_url: str = ""

    # Comma-separated user ids allowed to call /admin.
    admin_user_ids: str = ""

    # Persist LangGraph agent state with AsyncPostgresSaver (same DATABASE_URL).
    agent_checkpoint: bool = True

    # Rerank: local (CrossEncoder), cohere (hosted API), or none (hybrid only).
    rerank_provider: str = "local"
    cohere_rerank_model: str = "rerank-english-v3.0"


settings = Settings()
