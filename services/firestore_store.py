"""Firestore-backed draft store.

A "draft" is the unit of work that flows through the whole pipeline: created
by `/generate`, read/mutated by the Telegram webhook when the user approves
or rejects it, and finally archived into a history collection once posted.

Firestore (rather than in-memory state) is required here because the two
requests that touch a draft (`/generate` and `/telegram/webhook`) can be
minutes to hours apart and may hit different Cloud Run instances.
"""

from __future__ import annotations

import datetime as dt
import uuid
from enum import StrEnum
from typing import Any

from google.cloud import firestore

from services.config import config

_client: firestore.Client | None = None


class DraftStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    POSTED = "posted"
    FAILED = "failed"
    EXPIRED = "expired"


def _get_client() -> firestore.Client:
    global _client
    if _client is None:
        _client = firestore.Client(project=config.gcp_project or None)
    return _client


def _drafts():
    return _get_client().collection(config.firestore_collection_drafts)


def _history():
    return _get_client().collection(config.firestore_collection_history)


def create_draft(payload: dict[str, Any]) -> str:
    draft_id = str(uuid.uuid4())[:8]
    record = {
        **payload,
        "status": DraftStatus.PENDING.value,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    _drafts().document(draft_id).set(record)
    return draft_id


def get_draft(draft_id: str) -> dict[str, Any] | None:
    snapshot = _drafts().document(draft_id).get()
    if not snapshot.exists:
        return None
    data = snapshot.to_dict()
    data["id"] = draft_id
    return data


def update_draft(draft_id: str, updates: dict[str, Any]) -> None:
    updates = {**updates, "updated_at": firestore.SERVER_TIMESTAMP}
    _drafts().document(draft_id).update(updates)


def try_claim_draft(draft_id: str, new_status: DraftStatus, expected_status: DraftStatus = DraftStatus.PENDING) -> bool:
    """Atomically move a draft from `expected_status` to `new_status`.

    Used to make the Telegram webhook idempotent: Telegram may redeliver the
    same callback_query, and we must only ever publish once per draft.
    Returns True if this call performed the transition, False if the draft
    was already claimed (or in some other state) by a previous delivery.
    """

    client = _get_client()
    doc_ref = _drafts().document(draft_id)

    @firestore.transactional
    def _claim(transaction: firestore.Transaction) -> bool:
        snapshot = doc_ref.get(transaction=transaction)
        if not snapshot.exists:
            return False
        current_status = snapshot.to_dict().get("status")
        if current_status != expected_status.value:
            return False
        transaction.update(doc_ref, {"status": new_status.value, "updated_at": firestore.SERVER_TIMESTAMP})
        return True

    return _claim(client.transaction())


def expire_stale_drafts(max_age_hours: int | None = None) -> list[str]:
    """Mark pending drafts older than `max_age_hours` as expired.

    Meant to be called from a periodic Cloud Scheduler job so a forgotten
    approval never results in a days-old recap being posted unexpectedly.
    Returns the list of draft ids that were expired.
    """

    max_age_hours = max_age_hours or config.draft_expiry_hours
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=max_age_hours)

    expired_ids: list[str] = []
    query = _drafts().where("status", "==", DraftStatus.PENDING.value)
    for doc in query.stream():
        data = doc.to_dict()
        created_at = data.get("created_at")
        if created_at and created_at < cutoff:
            doc.reference.update({"status": DraftStatus.EXPIRED.value, "updated_at": firestore.SERVER_TIMESTAMP})
            expired_ids.append(doc.id)
    return expired_ids


def log_history(draft_id: str, result: dict[str, Any]) -> None:
    _history().document(draft_id).set({**result, "logged_at": firestore.SERVER_TIMESTAMP})
