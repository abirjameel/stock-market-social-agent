"""Telegram bot integration: sends the pre-posting approval request (photo +
captions + Approve/Reject inline buttons) and exposes helpers used by the
webhook handler in `main.py`.

Uses raw HTTP calls to the Telegram Bot API instead of a heavier SDK - the
surface we need (sendPhoto, answerCallbackQuery, sendMessage, editMessage
caption) is small enough that it's not worth the extra dependency.
"""

from __future__ import annotations

import hmac
from pathlib import Path
from typing import Any

import requests

from services.config import config

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"


def _call(method: str, *, data: dict[str, Any] | None = None, files: dict[str, Any] | None = None) -> dict:
    url = TELEGRAM_API_BASE.format(token=config.telegram_bot_token(), method=method)
    response = requests.post(url, data=data, files=files, timeout=20)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API error calling {method}: {payload}")
    return payload["result"]


def _approval_keyboard(draft_id: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Approve & Post", "callback_data": f"approve:{draft_id}"},
                {"text": "Reject", "callback_data": f"reject:{draft_id}"},
            ]
        ]
    }


def send_approval_request(draft_id: str, image_path: Path, linkedin_text: str, instagram_caption: str) -> int:
    """Send the daily draft to Telegram for human approval.

    Returns the sent message_id (useful if you later want to edit it in place
    once a decision is made).
    """

    caption = (
        f"*Daily market post ready for review* (id `{draft_id}`)\n\n"
        f"*LinkedIn:*\n{linkedin_text}\n\n"
        f"*Instagram:*\n{instagram_caption}"
    )
    # Telegram captions are capped at 1024 characters.
    if len(caption) > 1024:
        caption = caption[:1000] + "…"

    with open(image_path, "rb") as image_file:
        result = _call(
            "sendPhoto",
            data={
                "chat_id": config.telegram_chat_id,
                "caption": caption,
                "parse_mode": "Markdown",
                "reply_markup": _keyboard_json(draft_id),
            },
            files={"photo": image_file},
        )
    return result["message_id"]


def _keyboard_json(draft_id: str) -> str:
    import json

    return json.dumps(_approval_keyboard(draft_id))


def answer_callback_query(callback_query_id: str, text: str) -> None:
    _call("answerCallbackQuery", data={"callback_query_id": callback_query_id, "text": text})


def send_message(text: str) -> None:
    _call("sendMessage", data={"chat_id": config.telegram_chat_id, "text": text, "parse_mode": "Markdown"})


def edit_message_reply_markup(message_id: int, keyboard: dict | None = None) -> None:
    import json

    _call(
        "editMessageReplyMarkup",
        data={
            "chat_id": config.telegram_chat_id,
            "message_id": message_id,
            "reply_markup": json.dumps(keyboard or {"inline_keyboard": []}),
        },
    )


def verify_webhook_secret(provided_secret: str | None) -> bool:
    """Compare the `X-Telegram-Bot-Api-Secret-Token` header against our
    configured secret using a constant-time comparison.

    If no secret is configured (`TELEGRAM_WEBHOOK_SECRET` unset), this is a
    no-op that always returns True - fine for local testing, but you should
    always set a webhook secret in production so random internet traffic
    can't trigger real posts.
    """

    expected = config.telegram_webhook_secret()
    if not expected:
        return True
    if not provided_secret:
        return False
    return hmac.compare_digest(expected, provided_secret)
