"""ADK content-writer agent.

Defines the root Gemini agent used to turn raw market data + news into
ready-to-review social copy. The agent is given two tools (market snapshot,
market news) and a Pydantic `output_schema` so the pipeline always gets back
well-formed JSON instead of having to parse free text.
"""

from __future__ import annotations

import asyncio
import uuid

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

from agent.tools.market_data import get_market_snapshot
from agent.tools.news import get_market_news
from services.config import config

APP_NAME = "market_social_agent"


class PostDraftContent(BaseModel):
    """Structured output the content-writer agent must produce."""

    linkedin_text: str = Field(
        description=(
            "Professional LinkedIn post (roughly 50-90 words) summarizing today's US "
            "stock market action: index moves, notable gainers/losers from the MAG10 "
            "watchlist, and the likely driver from the news headlines. You may refer to "
            "the tracked watchlist as \"the MAG10\" (our curated list of 10 large-cap "
            "stocks). Be concise - every sentence should earn its place. No hashtags in "
            "the body; end with 2-4 relevant hashtags on their own line."
        )
    )
    instagram_caption: str = Field(
        description=(
            "Punchy, concise Instagram caption (roughly 25-40 words) covering the same "
            "market recap in a more casual tone, tasteful emoji use, ending with 5-8 hashtags."
        )
    )
    image_headline: str = Field(
        description="Very short (max 5 words, hard limit) headline stat for the post image, e.g. 'S&P 500 +1.2% Today'."
    )
    image_subtext: str = Field(
        description="One short supporting line (max 8 words, hard limit) for the post image, e.g. the standout mover."
    )


INSTRUCTION = """
You are a financial social-media copywriter for Wonder Trading Research (WTR),
writing a daily US stock market recap. Our 10-stock watchlist is branded "the
MAG10" - you may reference it by that name (e.g. "today's MAG10 movers").

Steps you MUST follow on every run:
1. Call `get_market_snapshot` to get real index and watchlist (MAG10) numbers.
2. Call `get_market_news` to get today's headlines for context (if headlines
   are empty, just describe price action without inventing a cause).
3. Write the post copy using ONLY the real numbers returned by the tools -
   never invent index levels or percentages.
4. Keep tone factual and non-promotional: this is a news recap, not investment
   advice. Do not tell readers to buy or sell anything.
5. Finish by calling `set_model_response` with the structured result.
"""


def build_content_agent() -> Agent:
    return Agent(
        name="market_content_writer",
        model=config.content_model,
        instruction=INSTRUCTION,
        tools=[get_market_snapshot, get_market_news],
        output_schema=PostDraftContent,
    )


async def generate_post_draft_async() -> PostDraftContent:
    """Run the content-writer agent end-to-end and return the structured draft."""

    agent = build_content_agent()
    session_service = InMemorySessionService()
    user_id = "scheduler"
    session_id = str(uuid.uuid4())
    await session_service.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)

    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)
    trigger = types.Content(
        role="user",
        parts=[types.Part(text="Generate today's US stock market recap post.")],
    )

    final_json: str | None = None
    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=trigger):
        if event.is_final_response() and event.content and event.content.parts:
            for part in event.content.parts:
                if getattr(part, "text", None):
                    final_json = part.text

    if not final_json:
        raise RuntimeError("Content agent did not return a final response")

    return PostDraftContent.model_validate_json(final_json)


def generate_post_draft() -> PostDraftContent:
    """Sync wrapper around `generate_post_draft_async` for non-async callers."""

    return asyncio.run(generate_post_draft_async())
