import logging
import json
from datetime import datetime, timezone
from typing import List, Tuple, Dict, Any, Optional
import redis.asyncio as redis
from app.config import settings

logger = logging.getLogger(__name__)

async def update_rolling_summary_async(old_summary: str, evicted_turn: Dict[str, str]) -> str:
    """
    Uses a highly concise and deterministic prompt to merge an evicted turn into the existing summary.
    """
    if not evicted_turn:
        return old_summary
        
    prompt = f"""Update the conversation summary with the evicted turn.
    Summary: {old_summary or "None"}
    Evicted: User: {evicted_turn.get('user', '')} | Assistant: {evicted_turn.get('bot', '')}
    Output a bulleted list of key topics discussed. Max 3 bullets. Keep it extremely brief. No metadata."""
    
    try:
        from app.services.rag_service import get_llm_client
        llm = get_llm_client()
        response = await llm.acomplete(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Error updating rolling summary: {e}")
        fallback = f"- User queried about: {evicted_turn.get('user', '')}"
        if old_summary:
            return f"{old_summary}\n{fallback}"
        return fallback

class SessionService:
    """
    Session history management using standard Redis async client over TLS (Upstash).
    """
    def __init__(self):
        self.max_turns = settings.SESSION_MAX_TURNS
        self.token_limit = settings.SESSION_TOKEN_LIMIT
        self.ttl = settings.SESSION_TTL_SECONDS
        
        redis_url = settings.secure_redis_url
        if not redis_url:
            raise ValueError("REDIS_URL must be configured in environment.")
            
        self.redis = redis.from_url(redis_url)

    def _get_key(self, session_id: str) -> str:
        return f"session:{session_id}"

    async def get_session_data(self, session_id: str) -> Tuple[List[Dict[str, str]], str]:
        if not session_id:
            return [], ""
            
        try:
            key = self._get_key(session_id)
            data_bytes = await self.redis.get(key)
            if not data_bytes:
                return [], ""
            data_str = data_bytes.decode("utf-8")
            data = json.loads(data_str)
            return data.get("history", []), data.get("summary", "")
        except Exception as e:
            logger.error(f"Error fetching session from Redis: {e}")
            return [], ""

    async def add_turn(self, session_id: str, user_msg: str, bot_msg: str):
        if not session_id:
            return
            
        try:
            from llama_index.core.llms import ChatMessage, MessageRole
            from llama_index.core.memory import ChatMemoryBuffer
            
            history, summary = await self.get_session_data(session_id)
            
            chat_messages = []
            for turn in history:
                chat_messages.append(ChatMessage(role=MessageRole.USER, content=turn.get("user", "")))
                chat_messages.append(ChatMessage(role=MessageRole.ASSISTANT, content=turn.get("bot", "")))
                
            chat_messages.append(ChatMessage(role=MessageRole.USER, content=user_msg))
            chat_messages.append(ChatMessage(role=MessageRole.ASSISTANT, content=bot_msg))
            
            # Bound history to a token limit dynamically using ChatMemoryBuffer
            memory = ChatMemoryBuffer.from_defaults(
                chat_history=chat_messages,
                token_limit=self.token_limit
            )
            
            updated_messages = memory.get_all()
            
            # Update summary for any evicted turns
            evicted_turns_count = (len(chat_messages) - len(updated_messages)) // 2
            for i in range(evicted_turns_count):
                evicted_turn = {
                    "user": chat_messages[2*i].content,
                    "bot": chat_messages[2*i+1].content
                }
                summary = await update_rolling_summary_async(summary, evicted_turn)
                
            new_history = []
            for idx in range(0, len(updated_messages), 2):
                if idx + 1 < len(updated_messages):
                    new_history.append({
                        "user": updated_messages[idx].content,
                        "bot": updated_messages[idx+1].content
                    })
            
            key = self._get_key(session_id)
            session_data = {
                "history": new_history,
                "summary": summary,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            await self.redis.set(key, json.dumps(session_data), ex=self.ttl)
        except Exception as e:
            logger.error(f"Error saving session to Redis: {e}")

    async def clear_session(self, session_id: str):
        if not session_id:
            return
        try:
            key = self._get_key(session_id)
            await self.redis.delete(key)
        except Exception as e:
            logger.error(f"Error deleting session from Redis: {e}")
