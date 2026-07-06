import logging
import json
import re
import asyncio
import contextvars
from typing import AsyncGenerator, Optional

from app.dependencies import db
from app.dependencies import get_query_service
from app.services.session_service import SessionService
from app.pipelines.retriever import SmartRetriever
from app.services.llm import llm_client, SYSTEM_PROMPT

from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.agent import FunctionAgent, AgentStream
from llama_index.core.tools import FunctionTool

logger = logging.getLogger(__name__)

# ContextVar to track the session key across the task boundary
current_session_key = contextvars.ContextVar("current_session_key", default="")


async def retrieve_documents(query: str) -> str:
    """
    Search official college documents for rules, schedules, academic guidelines, policies, events, and timings at IIT Gandhinagar (IITGN).
    Call this tool when the user's query requires specific policy details, calendar dates, or campus timings.
    """
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

    formatted = []
    for idx, node in enumerate(nodes):
        meta = node.node.metadata
        source = meta.get("source", "Document")
        page = meta.get("page", 1)
        formatted.append(
            f"[Source {idx + 1}] (File: {source}, Page: {page})\n{node.node.text}\n"
        )

    return "\n---\n".join(formatted)


async def get_quick_links() -> str:
    """
    Get official IIT Gandhinagar service links, contact details, departmental websites, and support portals.
    Call this tool when the user asks for email addresses, contact numbers, website URLs, or support links.
    """
    try:
        logger.info("Fetching quick links from Firestore...")

        def _fetch_from_firestore():
            links_ref = db.collection("quick_links").order_by("service").stream()
            links = []
            for doc in links_ref:
                data = doc.to_dict()
                service = data.get("service", "").strip()
                link = data.get("link", "").strip()
                purpose = data.get("purpose", "").strip()
                if service and link:
                    links.append(f"- {service}: {link}" + (f" — {purpose}" if purpose else ""))
            return links

        links = await asyncio.to_thread(_fetch_from_firestore)
        if not links:
            return "No official quick links or contact details are available currently."

        return "Official IIT Gandhinagar Quick Links and Contacts:\n" + "\n".join(links)

    except Exception as e:
        logger.error(f"Failed to fetch quick links from Firestore: {e}", exc_info=True)
        return "Failed to fetch quick links."


def build_retrieval_tool() -> FunctionTool:
    return FunctionTool.from_defaults(
        fn=retrieve_documents,
        name="retrieve_documents",
        description=retrieve_documents.__doc__,
    )


def build_quick_links_tool() -> FunctionTool:
    return FunctionTool.from_defaults(
        fn=get_quick_links,
        name="get_quick_links",
        description=get_quick_links.__doc__,
    )


class QueryService:
    """
    Orchestrates the agentic RAG conversation flow using FunctionAgent.
    """
    def __init__(self, session_service: SessionService, retriever: SmartRetriever):
        self.session_service = session_service
        self.retriever = retriever
        self.session_nodes = {}

        self.retrieval_tool = build_retrieval_tool()
        self.quick_links_tool = build_quick_links_tool()
        self.agent = None
        self.llm = None

    async def query_stream(self, query: str, session_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        """
        Executes query pipeline via LlamaIndex Agent Chat and returns an async generator for SSE chunks.
        """
        logger.info(f"Generating streaming RAG answer for query: '{query}' (session: {session_id})")

        session_key = session_id or "default"
        current_session_key.set(session_key)
        self.session_nodes[session_key] = []

        if self.agent is None:
            self.llm = llm_client
            self.agent = FunctionAgent(
                tools=[self.retrieval_tool, self.quick_links_tool],
                llm=self.llm,
                system_prompt=SYSTEM_PROMPT,
            )

        history = []
        if session_id:
            history, _ = await self.session_service.get_session_data(session_id)

        llama_history = []
        for turn in history:
            llama_history.append(ChatMessage(role=MessageRole.USER, content=turn.get("user", "")))
            llama_history.append(ChatMessage(role=MessageRole.ASSISTANT, content=turn.get("bot", "")))

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

        nodes = self.session_nodes.pop(session_key, [])
        serialized_sources = []

        if nodes and full_answer:
            matches = re.findall(r"\[(?:Source\s+)?(\d+)\]", full_answer, re.IGNORECASE)
            matches_raw = re.findall(r"\bSource\s+(\d+)\b", full_answer, re.IGNORECASE)
            cited_indices = {int(m) for m in matches + matches_raw}

            seen_keys = set()
            for idx, node in enumerate(nodes):
                if (idx + 1) in cited_indices:
                    meta = node.node.metadata
                    source_name = meta.get("source") or "Document"
                    page = meta.get("page", 1)
                    doc_id = meta.get("doc_id")

                    if doc_id and doc_id not in seen_keys:
                        seen_keys.add(doc_id)
                        serialized_sources.append({
                            "doc_id": doc_id,
                            "document_id": doc_id,
                            "source": source_name,
                            "source_type": meta.get("source_type", "pdf"),
                            "page": page,
                            "page_start": meta.get("page_start", page),
                            "page_end": meta.get("page_end", page),
                            "text_content": node.node.text,
                        })

        yield f"data: {json.dumps({'type': 'sources', 'content': serialized_sources})}\n\n"

        if session_id and full_answer:
            await self.session_service.add_turn(session_id, query, full_answer)