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

    # ─── Cost / abuse (no Redis; usage_log + users table) ────────────
    # Kill switches — flip without code changes.
    llm_enabled: bool = True
    agent_enabled: bool = True
    # Free plan: Agent on by default (shares monthly ask quota — demo-friendly).
    # Set FREE_AGENT_ENABLED=false to lock Agent to Pro/Team only.
    free_agent_enabled: bool = True
    # Daily USD caps from usage_log.cost_usd (0 = disabled).
    daily_cost_usd_per_user: float = 1.0
    daily_cost_usd_global: float = 25.0
    # Agent loop bounds (LangGraph recursion ≈ 2 * rounds + 1).
    agent_max_tool_rounds: int = 6
    agent_max_cost_usd_per_run: float = 0.5
    # Signup soft-gates.
    block_disposable_email: bool = True
    blocked_email_domains: str = ""
    max_signups_per_hour: int = 30


settings = Settings()
