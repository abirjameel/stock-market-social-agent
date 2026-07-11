"""Orchestrates the two halves of the daily pipeline:

  1. `generate_daily_draft` - runs the content agent (which generates the post
     image via Gemini image generation), archives it to Cloud Storage, saves a
     draft in Firestore, and sends it to Telegram for approval. Triggered by
     Cloud Scheduler via `POST /generate`.
  2. `approve_and_publish_draft` / `reject_draft` - triggered by the Telegram
     webhook once a human taps a button. Publishes to Instagram + LinkedIn
     and records the outcome.

Deliberately split into two requests (see README) because a Cloud Run
request cannot stay open for however long it takes a human to check Telegram.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

from agent.agent import generate_post_draft_async
from agent.tools.market_data import get_market_snapshot
from services import firestore_store, gcs_store, instagram_service, linkedin_service, telegram_service
from services.firestore_store import DraftStatus

logger = logging.getLogger(__name__)


async def generate_daily_draft() -> dict:
    content = await generate_post_draft_async()
    # `content.image_path` is set by the agent via the generate_post_image tool.
    # We still fetch the snapshot here solely to archive the raw numbers in Firestore.
    snapshot = json.loads(get_market_snapshot())

    image_path = Path(content.image_path)

    today = dt.date.today().isoformat()
    # Generated up front (rather than letting create_draft mint one) so the
    # Cloud Storage object name can include it - otherwise two drafts
    # generated on the same day (e.g. a manual re-run of /generate) would
    # both upload to the same date-only object name and the second would
    # silently overwrite the first, leaving any older still-pending draft
    # pointing at image bytes that no longer match its captions.
    draft_id = firestore_store.new_draft_id()
    upload = gcs_store.upload_image(image_path, remote_filename=f"{today}-{draft_id}.jpg")

    firestore_store.create_draft(
        {
            "date": today,
            "linkedin_text": content.linkedin_text,
            "instagram_caption": content.instagram_caption,
            "image_headline": content.image_headline,
            "image_subtext": content.image_subtext,
            "image_storage_path": upload.blob_path,
            "image_public_url": upload.public_url,
            "market_snapshot": snapshot,
        },
        draft_id=draft_id,
    )

    message_id = telegram_service.send_approval_request(
        draft_id=draft_id,
        image_path=image_path,
        linkedin_text=content.linkedin_text,
        instagram_caption=content.instagram_caption,
    )
    firestore_store.update_draft(draft_id, {"telegram_message_id": message_id})

    logger.info("Generated draft %s and sent for approval", draft_id)
    return {"draft_id": draft_id, "telegram_message_id": message_id}


def approve_and_publish_draft(draft_id: str) -> dict:
    """Publish an approved draft to Instagram and LinkedIn.

    Guarded by `try_claim_draft` so redelivered Telegram callbacks (Telegram
    retries webhooks that don't ack fast enough) can never cause a duplicate
    post.
    """

    if not firestore_store.try_claim_draft(draft_id, DraftStatus.APPROVED):
        logger.info("Draft %s already claimed/processed, skipping duplicate publish", draft_id)
        return {"skipped": True}

    draft = firestore_store.get_draft(draft_id)
    if not draft:
        raise ValueError(f"Draft {draft_id} not found")

    local_image_path = gcs_store.download_image(draft["image_storage_path"])

    results: dict = {"instagram": None, "linkedin": None, "errors": {}}

    try:
        results["instagram"] = instagram_service.publish_post(
            image_url=draft["image_public_url"], caption=draft["instagram_caption"]
        )
    except Exception as exc:  # noqa: BLE001 - keep going, LinkedIn should still be attempted
        results["errors"]["instagram"] = str(exc)

    try:
        results["linkedin"] = linkedin_service.publish_to_configured_targets(
            local_image_path, draft["linkedin_text"], alt_text=draft["image_headline"]
        )
    except Exception as exc:  # noqa: BLE001
        results["errors"]["linkedin"] = str(exc)

    linkedin_errors = (results.get("linkedin") or {}).get("errors") or {}
    has_errors = bool(results["errors"]) or bool(linkedin_errors)
    final_status = DraftStatus.FAILED if has_errors else DraftStatus.POSTED
    firestore_store.update_draft(draft_id, {"status": final_status.value, "publish_results": results})
    firestore_store.log_history(draft_id, {**draft, "publish_results": results, "status": final_status.value})

    _notify_publish_outcome(draft_id, results, final_status)
    return results


def reject_draft(draft_id: str) -> dict:
    if not firestore_store.try_claim_draft(draft_id, DraftStatus.REJECTED):
        return {"skipped": True}
    telegram_service.send_message(f"Draft `{draft_id}` rejected. Nothing was posted.")
    return {"rejected": True}


def _notify_publish_outcome(draft_id: str, results: dict, status: DraftStatus) -> None:
    lines = [f"Draft `{draft_id}` publish result: *{status.value}*"]
    if results.get("instagram"):
        if results["instagram"].get("skipped"):
            lines.append(f"Instagram: skipped ({results['instagram'].get('reason', 'disabled')})")
        else:
            lines.append(f"Instagram: posted (media id `{results['instagram']['media_id']}`)")
    if results.get("linkedin"):
        li = results["linkedin"]
        if li.get("personal"):
            lines.append(f"LinkedIn (personal): posted (`{li['personal']}`)")
        if li.get("organization"):
            lines.append(f"LinkedIn (org): posted (`{li['organization']}`)")
        for target, error in (li.get("errors") or {}).items():
            lines.append(f"FAILED - LinkedIn ({target}): {error}")
    if results.get("errors"):
        for target, error in results["errors"].items():
            lines.append(f"FAILED - {target}: {error}")
    telegram_service.send_message("\n".join(lines))
