from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    sec_user_agent: str = "Moat Research contact@yourdomain.com"

    database_url: str

    openai_api_key: str = ""
    anthropic_api_key: str = ""

    model_flagship: str = "anthropic/claude-sonnet-5"
    model_cheap: str = "openai/gpt-4o-mini"
    embed_model: str = "text-embedding-3-small"
    embed_dim: int = 1536

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

settings = Settings()