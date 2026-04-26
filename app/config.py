from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "WoSB Guild"
    secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    session_cookie_name: str = "wosb_session"
    session_max_age_seconds: int = 60 * 60 * 24 * 14

    database_url: str = "sqlite+aiosqlite:///./wosb.db"

    discord_client_id: str = ""
    discord_client_secret: str = ""
    discord_redirect_uri: str = "http://127.0.0.1:8000/auth/callback"
    discord_bot_token: str = ""
    discord_guild_id: str = ""
    # Optional: only treat users in this voice channel as "in roster voice" (Discord snowflake). Empty = any voice.
    discord_roster_voice_channel_id: str = ""

    discord_role_admiral_id: str = ""
    discord_role_leader_id: str = ""
    discord_role_alliance_leader_id: str = ""
    discord_role_officer_id: str = ""
    discord_role_member_id: str = ""

    # Optional: assign members to a guild roster tab from these Discord roles (right-click role → Copy ID).
    discord_role_guild_tif_id: str = ""
    discord_role_guild_bwc_id: str = ""
    discord_role_guild_sva_id: str = ""
    discord_role_guild_lp_id: str = ""
    # Comma-separated home guild tags allowed to submit reimbursement claims.
    reimbursement_enabled_guild_tags: str = "TIF,BWC"

    # Full URL path to a file under ./static/ (e.g. /static/images/harbour.jpg). Leave empty for no photo layer.
    site_background_image: str = ""

    @field_validator("site_background_image")
    @classmethod
    def validate_site_background_image(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            return ""
        if not v.startswith("/static/"):
            raise ValueError("SITE_BACKGROUND_IMAGE must start with /static/ (example: /static/images/harbour.jpg)")
        return v

    @field_validator("reimbursement_enabled_guild_tags")
    @classmethod
    def validate_reimbursement_enabled_guild_tags(cls, v: str) -> str:
        # Normalize for predictable comparisons and cleaner display in templates.
        tags = [part.strip().upper() for part in (v or "").split(",") if part.strip()]
        return ",".join(tags)


@lru_cache
def get_settings() -> Settings:
    return Settings()
