"""Scheduled token refresh for the two integrations that have short-lived
tokens: Instagram (60-day long-lived tokens) and LinkedIn (60-day access
tokens, refreshable only if your app has been granted refresh-token rotation
by LinkedIn - a separate, optional approval on top of basic API access).

Dropbox is deliberately not handled here: `services.dropbox_store` uses the
`dropbox` SDK's built-in refresh-token flow, which refreshes transparently on
every call as long as `DROPBOX_REFRESH_TOKEN` is configured, so no cron is
needed for it.

Intended to run weekly via Cloud Scheduler (well within the 60-day expiry
windows) - see deploy/scheduler_setup.sh.
"""

from __future__ import annotations

import requests
from linkedin_api.clients.auth.client import AuthClient

from services.config import config
from services.secrets import add_secret_version, get_secret

INSTAGRAM_REFRESH_URL = "https://graph.instagram.com/refresh_access_token"


def refresh_instagram_token() -> dict:
    if not config.post_to_instagram:
        return {"skipped": True, "reason": "Instagram posting disabled via POST_TO_INSTAGRAM"}

    current_token = config.instagram_access_token()
    response = requests.get(
        INSTAGRAM_REFRESH_URL,
        params={"grant_type": "ig_refresh_token", "access_token": current_token},
        timeout=15,
    )
    body = response.json()
    if response.status_code != 200 or "access_token" not in body:
        raise RuntimeError(f"Instagram token refresh failed: {body}")

    add_secret_version("INSTAGRAM_ACCESS_TOKEN", body["access_token"])
    return {"expires_in_seconds": body.get("expires_in")}


def refresh_linkedin_token() -> dict:
    refresh_token = get_secret("LINKEDIN_REFRESH_TOKEN", required=False, default=None)
    client_id = get_secret("LINKEDIN_CLIENT_ID", required=False, default=None)
    client_secret = get_secret("LINKEDIN_CLIENT_SECRET", required=False, default=None)

    if not (refresh_token and client_id and client_secret):
        return {
            "skipped": True,
            "reason": (
                "LINKEDIN_REFRESH_TOKEN/CLIENT_ID/CLIENT_SECRET not configured - your "
                "LinkedIn app may not have refresh-token rotation approved. You'll need "
                "to manually re-run the OAuth flow before the current access token "
                "expires (~60 days)."
            ),
        }

    auth_client = AuthClient(client_id=client_id, client_secret=client_secret)
    response = auth_client.exchange_refresh_token_for_access_token(refresh_token=refresh_token)
    if response.status_code != 200 or not response.access_token:
        raise RuntimeError(f"LinkedIn token refresh failed: {response.status_code} {response.response.text}")

    add_secret_version("LINKEDIN_ACCESS_TOKEN", response.access_token)
    if getattr(response, "refresh_token", None):
        add_secret_version("LINKEDIN_REFRESH_TOKEN", response.refresh_token)
    return {"expires_in_seconds": response.expires_in}


def refresh_all_tokens() -> dict:
    results: dict = {}
    try:
        results["instagram"] = refresh_instagram_token()
    except Exception as exc:  # noqa: BLE001
        results["instagram"] = {"error": str(exc)}

    try:
        results["linkedin"] = refresh_linkedin_token()
    except Exception as exc:  # noqa: BLE001
        results["linkedin"] = {"error": str(exc)}

    return results
