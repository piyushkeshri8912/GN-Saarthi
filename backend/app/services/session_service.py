import logging
import json
from datetime import datetime, timezone
from typing import List, Tuple, Dict
import redis.asyncio as redis
from app.config import settings
from app.services.llm import llm_client
logger = logging.getLogger(__name__)

CHARS_PER_TOKEN = 4

def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def turn_tokens(turn: Dict[str, str]) -> int:
    return estimate_tokens(turn.get("user", "")) + estimate_tokens(turn.get("bot", ""))


async def summarize_evicted_turn(old_summary: str, evicted_turn: Dict[str, str]) -> str:
    """Fold one evicted turn into the rolling summary using an LLM."""
    prompt = (
        f"Update the conversation summary with the evicted turn.\n"
        f"Summary: {old_summary or 'None'}\n"
        f"Evicted: User: {evicted_turn.get('user', '')} | Assistant: {evicted_turn.get('bot', '')}\n"
        f"Output a bulleted list of key topics discussed. Keep it extremely brief. No metadata."
    )
    try:
        response = await llm_client.acomplete(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Error updating rolling summary: {e}")
        fallback = f"- User queried about: {evicted_turn.get('user', '')}"
        return f"{old_summary}\n{fallback}" if old_summary else fallback


class SessionService:
    """Session history management using Redis."""

    def __init__(self):
        self.token_limit = settings.SESSION_TOKEN_LIMIT
        self.ttl = settings.SESSION_TTL_SECONDS
        self.redis = redis.from_url(settings.REDIS_URL)

    def _key(self, session_id: str) -> str:
        return f"session:{session_id}"

    async def get_session_data(self, session_id: str) -> Tuple[List[Dict[str, str]], str]:
        if not session_id:
            return [], ""
        try:
            raw = await self.redis.get(self._key(session_id))
            if not raw:
                return [], ""
            data = json.loads(raw)
            return data.get("history", []), data.get("summary", "")
        except Exception as e:
            logger.error(f"Error fetching session from Redis: {e}")
            return [], ""

    async def add_turn(self, session_id: str, user_msg: str, bot_msg: str):
        if not session_id:
            return

        try:
            history, summary = await self.get_session_data(session_id)
            history.append({"user": user_msg, "bot": bot_msg})

            # Keep the most recent turns that fit in the token budget.
            # Walk from the newest turn backwards; anything that doesn't
            # fit gets evicted (oldest first) and folded into the summary.
            kept: List[Dict[str, str]] = []
            budget = self.token_limit
            for turn in reversed(history):
                cost = turn_tokens(turn)
                if cost > budget and kept:
                    break
                kept.append(turn)
                budget -= cost
            kept.reverse()

            evicted = history[: len(history) - len(kept)]
            for turn in evicted:
                summary = await summarize_evicted_turn(summary, turn)

            session_data = {
                "history": kept,
                "summary": summary,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            await self.redis.set(self._key(session_id), json.dumps(session_data), ex=self.ttl)

        except Exception as e:
            logger.error(f"Error saving session to Redis: {e}")

    async def clear_session(self, session_id: str):
        if not session_id:
            return
        try:
            await self.redis.delete(self._key(session_id))
        except Exception as e:
            logger.error(f"Error deleting session from Redis: {e}")