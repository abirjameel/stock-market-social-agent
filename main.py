"""FastAPI entrypoint deployed to Cloud Run.

Routes:
  POST /generate                   - triggered daily by Cloud Scheduler (shared-secret protected).
  POST /telegram/webhook           - triggered by Telegram when a button is tapped.
  POST /maintenance/expire-drafts  - triggered periodically by Cloud Scheduler.
  POST /maintenance/refresh-tokens - triggered weekly by Cloud Scheduler.
  GET  /healthz                    - trivial liveness check.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Header, HTTPException, Request

import pipeline
from services import firestore_store, telegram_service, token_refresh
from services.config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="market-social-agent")


def _require_scheduler_secret(x_scheduler_secret: str | None) -> None:
    """The Cloud Run service must be deployed publicly (`--allow-unauthenticated`)
    so Telegram's webhook can reach `/telegram/webhook`. That means IAM alone
    can't protect `/generate` and `/maintenance/expire-drafts`, so we instead
    require a shared secret header that only Cloud Scheduler is configured to
    send (see deploy/scheduler_setup.sh). If `SCHEDULER_SECRET` isn't set at
    all, this is a no-op (fine for early local testing only).
    """

    expected = config.scheduler_secret()
    if expected and x_scheduler_secret != expected:
        raise HTTPException(status_code=401, detail="missing or invalid scheduler secret")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/generate")
async def generate(x_scheduler_secret: str | None = Header(default=None)):
    """Runs the content pipeline and sends the result to Telegram for approval.
    Triggered daily by Cloud Scheduler."""

    _require_scheduler_secret(x_scheduler_secret)
    try:
        result = await pipeline.generate_daily_draft()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to generate daily draft")
        try:
            telegram_service.send_message(f"Daily market post generation FAILED: {exc}")
        except Exception:  # noqa: BLE001 - don't let a notification failure mask the real error
            logger.exception("Also failed to notify Telegram about the generation failure")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if not telegram_service.verify_webhook_secret(x_telegram_bot_api_secret_token):
        raise HTTPException(status_code=401, detail="invalid webhook secret")

    update = await request.json()
    callback_query = update.get("callback_query")
    if not callback_query:
        # Ignore any other update types (e.g. plain messages) - this bot is
        # approval-only, not conversational.
        return {"ignored": True}

    callback_id = callback_query["id"]
    data = callback_query.get("data", "")
    action, _, draft_id = data.partition(":")

    if action not in ("approve", "reject") or not draft_id:
        telegram_service.answer_callback_query(callback_id, "Unrecognized action")
        return {"ignored": True}

    telegram_service.answer_callback_query(callback_id, "Got it, processing…")

    message_id = callback_query.get("message", {}).get("message_id")
    if message_id:
        try:
            telegram_service.edit_message_reply_markup(message_id)
        except Exception:  # noqa: BLE001 - cosmetic only, don't fail the request over it
            logger.warning("Could not clear inline keyboard for message %s", message_id)

    if action == "approve":
        result = pipeline.approve_and_publish_draft(draft_id)
    else:
        result = pipeline.reject_draft(draft_id)

    return {"draft_id": draft_id, "action": action, "result": result}


@app.post("/maintenance/expire-drafts")
def expire_drafts(x_scheduler_secret: str | None = Header(default=None)):
    """Marks pending drafts older than DRAFT_EXPIRY_HOURS as expired so a
    forgotten approval never results in a stale post going out later.
    Intended to be called by a periodic Cloud Scheduler job (e.g. hourly).
    """

    _require_scheduler_secret(x_scheduler_secret)
    expired = firestore_store.expire_stale_drafts()
    if expired:
        telegram_service.send_message(
            f"Expired {len(expired)} unapproved draft(s) without posting: {', '.join(expired)}"
        )
    return {"expired": expired}


@app.post("/maintenance/refresh-tokens")
def refresh_tokens(x_scheduler_secret: str | None = Header(default=None)):
    """Refreshes the Instagram (and, if approved, LinkedIn) access tokens
    before they expire. Intended to run weekly via Cloud Scheduler."""

    _require_scheduler_secret(x_scheduler_secret)
    results = token_refresh.refresh_all_tokens()
    errors = {k: v for k, v in results.items() if isinstance(v, dict) and v.get("error")}
    if errors:
        telegram_service.send_message(f"Token refresh had errors: {errors}")
    return results
