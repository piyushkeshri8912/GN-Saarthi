import logging
import json
import re
import asyncio
import time
import contextvars
from threading import Lock
from typing import AsyncGenerator, Optional, List, Dict, Any
from app.config import settings
from app.dependencies import db
from app.services.session_service import SessionService
from app.pipelines.retriever import SmartRetriever
from llama_index.core.schema import NodeWithScore
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.agent import FunctionAgent, AgentStream
from llama_index.core.tools import FunctionTool

logger = logging.getLogger(__name__)

GLOBAL_QUICK_LINKS_KEY = "global:quick_links"

async def get_quick_links(redis_client) -> List[Dict[str, str]]:
    try:
        # 1. Try fetching from Redis
        cached_data = await redis_client.get(GLOBAL_QUICK_LINKS_KEY)
        if cached_data:
            logger.info("Retrieved quick links from Redis cache.")
            return json.loads(cached_data.decode("utf-8"))
    except Exception as e:
        logger.warning(f"Failed to read quick links from Redis: {e}")

    # 2. Cache miss: Fetch from Firestore
    try:
        logger.info("Fetching quick links from Firestore...")
        # Since db.collection.stream() is a synchronous Firestore call, run in executor
        def _fetch_from_firestore():
            links_ref = db.collection("quick_links").order_by("service").stream()
            links = []
            for doc in links_ref:
                data = doc.to_dict()
                service = data.get("service", "").strip()
                link = data.get("link", "").strip()
                purpose = data.get("purpose", "").strip()
                if service and link:
                    links.append({"service": service, "link": link, "purpose": purpose})
            return links

        links = await asyncio.to_thread(_fetch_from_firestore)
        
        # 3. Store in Redis with 1 hour TTL (3600 seconds)
        try:
            await redis_client.set(GLOBAL_QUICK_LINKS_KEY, json.dumps(links), ex=3600)
            logger.info("Successfully cached quick links in Redis.")
        except Exception as e:
            logger.warning(f"Failed to write quick links to Redis: {e}")
            
        return links
    except Exception as e:
        logger.error(f"Failed to fetch quick links from Firestore: {e}")
        return []

async def invalidate_links_cache():
    try:
        from app.dependencies import get_query_service
        query_service = get_query_service()
        
        # 1. Clear key in Redis
        redis_client = query_service.session_service.redis
        await redis_client.delete(GLOBAL_QUICK_LINKS_KEY)
        
        # 2. Reset the cached agent in QueryService singleton to force rebuilding prompt
        query_service.agent = None
        logger.info("Quick links cache invalidated in Redis and QueryService agent reset.")
    except Exception as e:
        logger.error(f"Failed to invalidate quick links cache: {e}")

# ContextVar to track the session key across the task boundary
current_session_key = contextvars.ContextVar("current_session_key", default="")

async def retrieve_documents(query: str) -> str:
    """
    Search official college documents for rules, schedules, academic guidelines, policies, events, and timings at IIT Gandhinagar (IITGN).
    Call this tool when the user's query requires specific policy details, calendar dates, or campus timings.
    """
    from app.dependencies import get_query_service
    query_service = get_query_service()
    
    logger.info(f"[TOOL CALL] retrieve_documents called with query: '{query}'")
    try:
        nodes = await query_service.retriever.retrieve(query)
        logger.info(f"[TOOL CALL] retrieve_documents found {len(nodes)} relevant nodes.")
    except Exception as e:
        logger.error(f"[TOOL CALL] retrieve_documents failed: {e}", exc_info=True)
        nodes = []
        
    session_key = current_session_key.get()
    if session_key:
        query_service.session_nodes[session_key] = nodes
    
    if not nodes:
        return "No relevant college documents found for this query."
        
    # Format chunks with clear [Source N] markers for LLM citation mapping
    formatted = []
    for idx, node in enumerate(nodes):
        meta = node.node.metadata
        source = meta.get("source", "Document")
        page = meta.get("page", 1)
        formatted.append(f"[Source {idx + 1}] (File: {source}, Page: {page})\n{node.node.text}\n")
    return "\n---\n".join(formatted)


class QueryService:
    """
    Orchestrates the agentic RAG conversation flow using FunctionCallingAgentWorker.
    """
    def __init__(self, session_service: SessionService, retriever: SmartRetriever):
        self.session_service = session_service
        self.retriever = retriever
        self.session_nodes = {}
        
        # 1. Wrap the retrieve_documents function into LlamaIndex FunctionTool
        self.retrieval_tool = FunctionTool.from_defaults(fn=retrieve_documents)
        self.agent = None

    async def query_stream(self, query: str, session_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        """
        Executes query pipeline via LlamaIndex Agent Chat and returns an async generator for SSE chunks.
        """
        logger.info(f"Generating streaming RAG answer for query: '{query}' (session: {session_id})")

        # Set session key and reset retrieved nodes for this request
        session_key = session_id or "default"
        current_session_key.set(session_key)
        self.session_nodes[session_key] = []

        # Cache quick links in Redis automatically at the start of each session
        redis_client = self.session_service.redis
        if session_id:
            session_marker = f"session:{session_id}:quick_links_loaded"
            try:
                is_loaded = await redis_client.get(session_marker)
                if not is_loaded:
                    # Session start detected: Warm up/cache links in Redis
                    await get_quick_links(redis_client)
                    await redis_client.set(session_marker, "1", ex=self.session_service.ttl)
                    logger.info(f"Automatically cached quick links in Redis at the start of session: {session_id}")
            except Exception as e:
                logger.warning(f"Failed to automatically cache quick links for session {session_id}: {e}")

        # Lazy load FunctionAgent in production mode
        if self.agent is None:
            from app.services.rag_service import get_llm_client
            self.llm = get_llm_client()
            
            links = await get_quick_links(redis_client)
            links_text = "\n".join([
                f"- Service: {l['service']}\n  Link/Contact: {l['link']}\n  Purpose: {l['purpose']}"
                for l in links
            ])
            
            from app.services.prompts import SYSTEM_PROMPT
            system_prompt = SYSTEM_PROMPT.format(links_text=links_text)
            
            self.agent = FunctionAgent(
                tools=[self.retrieval_tool],
                llm=self.llm,
                system_prompt=system_prompt
            )

        # Fetch Session History
        history = []
        if session_id:
            history, _ = await self.session_service.get_session_data(session_id)

        # Convert history to LlamaIndex ChatMessage format
        llama_history = []
        for turn in history:
            llama_history.append(ChatMessage(role=MessageRole.USER, content=turn.get("user", "")))
            llama_history.append(ChatMessage(role=MessageRole.ASSISTANT, content=turn.get("bot", "")))

        # Stream response
        full_answer = ""
        try:
            handler = self.agent.run(user_msg=query, chat_history=llama_history)
            async for event in handler.stream_events():
                if isinstance(event, AgentStream):
                    token = event.delta
                    if token:
                        full_answer += token
                        yield f"data: {json.dumps({'type': 'text', 'content': token})}\n\n"
            await handler
        except Exception as e:
            logger.error(f"Error in agent run: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': f'Generation error: {str(e)}'})}\n\n"
            return

        # Extract retrieved nodes and format citations
        nodes = self.session_nodes.pop(session_key, [])
        serialized_sources = []
        if nodes and full_answer:
            import re
            # Match formats like [Source 1], [source 1], [1], or Source 1
            matches = re.findall(r"\[(?:Source\s+)?(\d+)\]", full_answer, re.IGNORECASE)
            matches_raw = re.findall(r"\bSource\s+(\d+)\b", full_answer, re.IGNORECASE)
            cited_indices = {int(m) for m in matches + matches_raw}
                
            seen_keys = set()
            for idx, node in enumerate(nodes):
                if (idx + 1) in cited_indices:
                    meta = node.node.metadata
                    source_name = meta.get("source") or "Document"
                    page = meta.get("page", 1)
                    doc_id_key = meta.get("doc_id_key")
                    
                    if doc_id_key:
                        citation_key = doc_id_key
                        if citation_key not in seen_keys:
                            seen_keys.add(citation_key)
                            serialized_sources.append({
                                "doc_id": doc_id_key,
                                "document_id": doc_id_key,
                                "source": source_name,
                                "source_type": meta.get("source_type", "pdf"),
                                "page": page,
                                "page_start": meta.get("page_start", page),
                                "page_end": meta.get("page_end", page),
                                "text_content": node.node.text
                            })
                            
        yield f"data: {json.dumps({'type': 'sources', 'content': serialized_sources})}\n\n"

        # Save turn
        if session_id and full_answer:
            await self.session_service.add_turn(session_id, query, full_answer)