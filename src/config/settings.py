"""
Central configuration with validation and env loading.
"""
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from growth-tools directory so it works when run from repo root
_GROWTH_TOOLS_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _GROWTH_TOOLS_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE if _ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Reddit
    reddit_client_id: Optional[str] = Field(default=None, description="Reddit API client ID")
    reddit_client_secret: Optional[str] = Field(default=None, description="Reddit API secret")
    reddit_user_agent: str = Field(
        default="growth-tools-lead-finder/1.0",
        description="Reddit user agent",
    )

    # OpenAI
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")

    # Supabase
    supabase_url: Optional[str] = Field(default=None, description="Supabase project URL")
    supabase_service_role_key: Optional[str] = Field(default=None, description="Supabase service role key")

    # Discord
    discord_token: Optional[str] = Field(default=None, description="Discord bot token")

    # GitHub
    github_token: Optional[str] = Field(default=None, description="GitHub token for API")

    # Growth config
    lead_intent_threshold: int = Field(default=70, ge=0, le=100, description="Min intent score to treat as lead")
    discord_confidence_threshold: float = Field(default=0.75, ge=0, le=1, description="Min confidence for Discord reply")
    openai_model: str = Field(default="gpt-4.1-mini", description="OpenAI model for classification/generation")

    def require_reddit(self) -> None:
        if not self.reddit_client_id or not self.reddit_client_secret:
            raise ValueError("REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are required")

    def require_openai(self) -> None:
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required")

    def require_supabase(self) -> None:
        if not self.supabase_url or not self.supabase_service_role_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")

    def require_discord(self) -> None:
        if not self.discord_token:
            raise ValueError("DISCORD_TOKEN is required")


@lru_cache
def get_settings() -> Settings:
    return Settings()
