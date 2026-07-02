"""LinkedIn Posts API publishing, for both a personal profile and/or a
Company Page depending on `POST_TO_LINKEDIN_PERSONAL` /
`POST_TO_LINKEDIN_ORGANIZATION`.

Uses LinkedIn's official `linkedin-api-client` (`RestliClient`) rather than
raw `requests` calls for the JSON Rest.li calls (`/posts`, `/images`
initializeUpload). It correctly handles Rest.li's "reduced encoding" for
entity ids returned in the `x-restli-id` header, which a hand-rolled
`response.headers.get("x-restli-id")` would not decode.

Two things `RestliClient` does NOT do, so we still handle them ourselves:
  - It never raises on non-2xx responses (confirmed by reading its source) -
    every call here still checks `response.status_code` explicitly.
  - It has no helper for the raw binary image upload PUT (that's not a
    Rest.li call, just a plain PUT to a pre-signed upload URL), so that step
    still uses `requests` directly (reusing the client's session).

Note: LinkedIn's own README marks this library "beta ... use at your own
risk" and it hasn't been released since 0.3.0 (2023). If it ever breaks in a
way that blocks posting, reverting to raw `requests` calls against
`https://api.linkedin.com/rest/posts` and `/images` is a straightforward
fallback - see git history for the previous implementation.

Prerequisites (see docs/ACCESS_SETUP_CHECKLIST.md):
  - Personal profile posting: `w_member_social` scope, `LINKEDIN_PERSON_URN`
    (e.g. `urn:li:person:abcdef`).
  - Company Page posting: `w_organization_social` scope granted via LinkedIn's
    gated Community Management API approval, `LINKEDIN_ORGANIZATION_URN`
    (e.g. `urn:li:organization:12345678`), and the authenticated member must
    be an admin of that page.
  - `LINKEDIN_ACCESS_TOKEN` with the relevant scope(s) above.

Images are uploaded via LinkedIn's own direct-binary-upload flow, so unlike
Instagram we do NOT need a public image URL here - the Dropbox link is not
involved in this integration at all.
"""

from __future__ import annotations

from pathlib import Path

from linkedin_api.clients.restli.client import RestliClient

from services.config import config

_client = RestliClient()


class LinkedInPublishError(RuntimeError):
    pass


def _access_token() -> str:
    return config.linkedin_access_token()


def _initialize_image_upload(owner_urn: str) -> tuple[str, str]:
    response = _client.action(
        resource_path="/images",
        action_name="initializeUpload",
        action_params={"initializeUploadRequest": {"owner": owner_urn}},
        access_token=_access_token(),
        version_string=config.linkedin_api_version,
    )
    if response.status_code != 200 or not response.value:
        raise LinkedInPublishError(f"Failed to initialize LinkedIn image upload: {response.status_code} {response.value}")
    value = response.value
    return value["uploadUrl"], value["image"]


def _upload_image_bytes(upload_url: str, image_path: Path) -> None:
    with open(image_path, "rb") as f:
        response = _client.session.put(
            upload_url,
            data=f.read(),
            headers={"Authorization": f"Bearer {_access_token()}"},
            timeout=60,
        )
    if response.status_code not in (200, 201):
        raise LinkedInPublishError(f"Failed to upload image bytes to LinkedIn: {response.status_code} {response.text}")


def upload_image(image_path: Path, owner_urn: str) -> str:
    """Upload an image for the given owner (person or organization URN) and
    return the resulting `urn:li:image:...` asset id."""

    upload_url, image_urn = _initialize_image_upload(owner_urn)
    _upload_image_bytes(upload_url, image_path)
    return image_urn


def create_post(author_urn: str, commentary: str, image_urn: str | None, alt_text: str = "") -> str:
    entity: dict = {
        "author": author_urn,
        "commentary": commentary,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    if image_urn:
        entity["content"] = {"media": {"altText": alt_text, "id": image_urn}}

    response = _client.create(
        resource_path="/posts",
        entity=entity,
        access_token=_access_token(),
        version_string=config.linkedin_api_version,
    )
    if response.status_code != 201:
        raise LinkedInPublishError(f"Failed to create LinkedIn post for {author_urn}: {response.status_code} {response.entity}")

    post_id = response.decoded_entity_id or response.entity_id
    if not post_id:
        raise LinkedInPublishError(f"LinkedIn post created but no id returned in headers: {dict(response.headers)}")
    return post_id


def publish_to_configured_targets(image_path: Path, commentary: str, alt_text: str = "") -> dict:
    """Publish to whichever of personal profile / Company Page are enabled in
    config. Returns `{"personal": post_id_or_None, "organization": post_id_or_None,
    "errors": {...}}` - partial failures (e.g. org approved but personal
    fails) do not stop the other target from being attempted.
    """

    results: dict = {"personal": None, "organization": None, "errors": {}}

    if config.post_to_linkedin_personal and config.linkedin_person_urn:
        try:
            image_urn = upload_image(image_path, config.linkedin_person_urn)
            results["personal"] = create_post(config.linkedin_person_urn, commentary, image_urn, alt_text)
        except Exception as exc:  # noqa: BLE001 - collect and continue
            results["errors"]["personal"] = str(exc)

    if config.post_to_linkedin_organization and config.linkedin_organization_urn:
        try:
            image_urn = upload_image(image_path, config.linkedin_organization_urn)
            results["organization"] = create_post(config.linkedin_organization_urn, commentary, image_urn, alt_text)
        except Exception as exc:  # noqa: BLE001 - collect and continue
            results["errors"]["organization"] = str(exc)

    return results
