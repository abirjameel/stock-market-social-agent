"""Central application configuration.

All tunables live here so the rest of the codebase never reaches into
`os.environ` directly. Secrets (tokens/keys) are resolved lazily via
`services.secrets.get_secret` so importing this module never fails just
because a secret isn't configured yet.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

from services.secrets import get_secret

load_dotenv()


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Config:
    # --- GCP ---
    gcp_project: str = field(default_factory=lambda: os.environ.get("GOOGLE_CLOUD_PROJECT", ""))
    gcp_location: str = field(default_factory=lambda: _env("GOOGLE_CLOUD_LOCATION", "us-central1"))
    firestore_collection_drafts: str = field(
        default_factory=lambda: _env("FIRESTORE_COLLECTION_DRAFTS", "post_drafts")
    )
    firestore_collection_history: str = field(
        default_factory=lambda: _env("FIRESTORE_COLLECTION_HISTORY", "post_history")
    )

    # --- Gemini / ADK ---
    content_model: str = field(default_factory=lambda: _env("CONTENT_MODEL", "gemini-2.5-flash"))
    image_model: str = field(default_factory=lambda: _env("IMAGE_MODEL", "gemini-2.5-flash-image"))

    # --- Market data ---
    market_indices: tuple[str, ...] = (
        ("^GSPC", "S&P 500"),
        ("^DJI", "Dow Jones"),
        ("^IXIC", "Nasdaq Composite"),
    )
    watchlist: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            _env(
                "MARKET_WATCHLIST",
                "AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,BRK-B,JPM,XOM",
            ).split(",")
        )
    )

    # --- Approval / drafts ---
    draft_expiry_hours: int = field(default_factory=lambda: int(_env("DRAFT_EXPIRY_HOURS", "12")))

    # --- Telegram ---
    telegram_chat_id: str = field(default_factory=lambda: _env("TELEGRAM_CHAT_ID", ""))

    # --- Instagram ---
    post_to_instagram: bool = field(
        default_factory=lambda: _env("POST_TO_INSTAGRAM", "true").lower() == "true"
    )
    instagram_business_account_id: str = field(
        default_factory=lambda: _env("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
    )
    instagram_graph_api_version: str = field(
        default_factory=lambda: _env("INSTAGRAM_GRAPH_API_VERSION", "v21.0")
    )
    instagram_container_poll_attempts: int = field(
        default_factory=lambda: int(_env("INSTAGRAM_CONTAINER_POLL_ATTEMPTS", "10"))
    )
    instagram_container_poll_delay_seconds: float = field(
        default_factory=lambda: float(_env("INSTAGRAM_CONTAINER_POLL_DELAY_SECONDS", "3"))
    )

    # --- LinkedIn ---
    linkedin_person_urn: str = field(default_factory=lambda: _env("LINKEDIN_PERSON_URN", ""))
    linkedin_organization_urn: str = field(
        default_factory=lambda: _env("LINKEDIN_ORGANIZATION_URN", "")
    )
    linkedin_api_version: str = field(default_factory=lambda: _env("LINKEDIN_API_VERSION", "202601"))
    post_to_linkedin_personal: bool = field(
        default_factory=lambda: _env("POST_TO_LINKEDIN_PERSONAL", "true").lower() == "true"
    )
    post_to_linkedin_organization: bool = field(
        default_factory=lambda: _env("POST_TO_LINKEDIN_ORGANIZATION", "true").lower() == "true"
    )

    # --- Dropbox ---
    dropbox_folder: str = field(default_factory=lambda: _env("DROPBOX_FOLDER", "/market-social-agent/posts"))

    # secrets (not cached on the dataclass instance - resolved on demand)
    def telegram_bot_token(self) -> str:
        return get_secret("TELEGRAM_BOT_TOKEN")

    def telegram_webhook_secret(self) -> str:
        return get_secret("TELEGRAM_WEBHOOK_SECRET", required=False, default="")

    def scheduler_secret(self) -> str:
        # Shared secret Cloud Scheduler sends as a header on its HTTP target
        # requests. The Cloud Run service is deployed publicly (it must be,
        # for the Telegram webhook), so this is what stops anyone else who
        # finds the URL from triggering a real post.
        return get_secret("SCHEDULER_SECRET", required=False, default="")

    def gemini_api_key(self) -> str | None:
        # Optional: only needed when NOT using Vertex AI (GOOGLE_GENAI_USE_VERTEXAI=false).
        return get_secret("GEMINI_API_KEY", required=False, default=None)

    def finnhub_api_key(self) -> str | None:
        return get_secret("FINNHUB_API_KEY", required=False, default=None)

    def dropbox_access_token(self) -> str:
        return get_secret("DROPBOX_ACCESS_TOKEN")

    def dropbox_refresh_token(self) -> str | None:
        return get_secret("DROPBOX_REFRESH_TOKEN", required=False, default=None)

    def dropbox_app_key(self) -> str | None:
        return get_secret("DROPBOX_APP_KEY", required=False, default=None)

    def dropbox_app_secret(self) -> str | None:
        return get_secret("DROPBOX_APP_SECRET", required=False, default=None)

    def instagram_access_token(self) -> str:
        return get_secret("INSTAGRAM_ACCESS_TOKEN")

    def linkedin_access_token(self) -> str:
        return get_secret("LINKEDIN_ACCESS_TOKEN")


config = Config()
