"""Instagram Graph API publishing (2-step container -> publish flow).

Prerequisites (see docs/ACCESS_SETUP_CHECKLIST.md):
  - Instagram Business/Creator account linked to a Facebook Page.
  - Meta Developer App with the Instagram Graph API product and
    `instagram_basic` + `instagram_content_publish` permissions approved via
    App Review for production use.
  - `INSTAGRAM_BUSINESS_ACCOUNT_ID` (the IG user id, not the FB Page id) and
    `INSTAGRAM_ACCESS_TOKEN` (long-lived, ~60 days) configured.
"""

from __future__ import annotations

import time

import requests

from services.config import config

GRAPH_API_BASE = "https://graph.facebook.com/{version}"


class InstagramPublishError(RuntimeError):
    pass


def _base_url() -> str:
    return GRAPH_API_BASE.format(version=config.instagram_graph_api_version)


def _create_container(image_url: str, caption: str) -> str:
    url = f"{_base_url()}/{config.instagram_business_account_id}/media"
    response = requests.post(
        url,
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": config.instagram_access_token(),
        },
        timeout=30,
    )
    body = response.json()
    if response.status_code != 200 or "id" not in body:
        raise InstagramPublishError(f"Failed to create media container: {body}")
    return body["id"]


def _wait_for_container_ready(creation_id: str) -> None:
    url = f"{_base_url()}/{creation_id}"
    for _ in range(config.instagram_container_poll_attempts):
        response = requests.get(
            url,
            params={"fields": "status_code", "access_token": config.instagram_access_token()},
            timeout=15,
        )
        body = response.json()
        status = body.get("status_code")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise InstagramPublishError(f"Instagram failed to process media container: {body}")
        time.sleep(config.instagram_container_poll_delay_seconds)
    raise InstagramPublishError(f"Timed out waiting for media container {creation_id} to finish processing")


def _publish_container(creation_id: str) -> str:
    url = f"{_base_url()}/{config.instagram_business_account_id}/media_publish"
    response = requests.post(
        url,
        data={"creation_id": creation_id, "access_token": config.instagram_access_token()},
        timeout=30,
    )
    body = response.json()
    if response.status_code != 200 or "id" not in body:
        raise InstagramPublishError(f"Failed to publish media container: {body}")
    return body["id"]


def publish_post(image_url: str, caption: str) -> dict:
    """Publish a single-image post to the configured Instagram Business account.

    Returns `{"media_id": str}` on success, or `{"skipped": True, "reason": ...}`
    if Instagram posting is disabled via `POST_TO_INSTAGRAM=false` (e.g. while
    waiting on Meta App Review/API access - in that case `INSTAGRAM_ACCESS_TOKEN`
    and `INSTAGRAM_BUSINESS_ACCOUNT_ID` never need to be configured at all).
    Raises `InstagramPublishError` on any failure so callers can surface a
    clear error back via Telegram.
    """

    if not config.post_to_instagram:
        return {"skipped": True, "reason": "Instagram posting disabled via POST_TO_INSTAGRAM"}

    creation_id = _create_container(image_url, caption)
    _wait_for_container_ready(creation_id)
    media_id = _publish_container(creation_id)
    return {"media_id": media_id}
