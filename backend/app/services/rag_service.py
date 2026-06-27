import logging
import json
import asyncio
import re
import time
from collections import OrderedDict
from threading import Lock
from typing import AsyncGenerator, Optional
from anyio.to_thread import run_sync
from llama_index.core import PromptTemplate
from app.config import settings

logger = logging.getLogger(__name__)

_llm_client = None


def update_rolling_summary(old_summary: str, evicted_turn: dict) -> str:
    """
    Uses a highly concise and deterministic prompt to merge an evicted turn into the existing summary.
    """
    if not evicted_turn:
        return old_summary
        
    prompt = f"""Update the conversation summary with the evicted turn.
Summary: {old_summary or "None"}
Evicted: User: {evicted_turn['user']} | Assistant: {evicted_turn['bot']}
Output a bulleted list of key topics discussed. Max 3 bullets. Keep it extremely brief. No metadata."""
    
    try:
        llm = get_llm_client()
        response = llm.complete(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Error updating rolling summary: {e}")
        fallback = f"- User queried about: {evicted_turn['user']}"
        if old_summary:
            return f"{old_summary}\n{fallback}"
        return fallback


class MemorySessionCache:
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache = OrderedDict()
        self.lock = Lock()

    def get(self, session_id: str) -> tuple[list, str]:
        with self.lock:
            if session_id not in self.cache:
                return [], ""
            data = self.cache[session_id]
            if isinstance(data, list):
                history = data
                summary = ""
                last_active = time.time()
                self.cache[session_id] = (history, summary, last_active)
            else:
                history, summary, last_active = data
                
            if time.time() - last_active > self.ttl_seconds:
                del self.cache[session_id]
                return [], ""
            self.cache.move_to_end(session_id)
            self.cache[session_id] = (history, summary, time.time())
            return history, summary

    def add_turn(self, session_id: str, user_msg: str, bot_msg: str, max_turns: int = 3):
        with self.lock:
            history = []
            summary = ""
            if session_id in self.cache:
                data = self.cache[session_id]
                if isinstance(data, list):
                    history = data
                else:
                    history, summary, _ = data
                del self.cache[session_id]
            
            history.append({"user": user_msg, "bot": bot_msg})
            if len(history) > max_turns:
                evicted = history.pop(0)
                summary = update_rolling_summary(summary, evicted)
            
            self.cache[session_id] = (history, summary, time.time())
            
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)


session_cache = MemorySessionCache()


def reformulate_query(query: str, history: list) -> str:
    """
    Given the chat history and a follow-up query, reformulate it into a standalone query.
    """
    if not history:
        return query
        
    history_text = ""
    for turn in history:
        history_text += f"User: {turn['user']}\nAssistant: {turn['bot']}\n\n"
        
    prompt = f"""You are an AI assistant for GN Saarthi.
Given the conversation history and the latest user query, reformulate the query into a standalone query that can be understood on its own for a document search.
Do NOT answer the query; only return the reformulated query text. If the latest query is already a standalone query or if it cannot be reformulated, return it exactly as-is.

Conversation History:
{history_text}

Latest Query: {query}

Standalone Query:"""
    try:
        llm = get_llm_client()
        response = llm.complete(prompt)
        reformulated = response.text.strip()
        logger.info(f"Reformulated query from '{query}' to '{reformulated}'")
        return reformulated
    except Exception as e:
        logger.error(f"Error reformulating query: {e}. Using original query.")
        return query



_retriever = None


def get_llm_client():
    """
    Singleton factory for LlamaIndex GoogleGenAI using gemini-2.5-flash.
    """
    global _llm_client
    if _llm_client is None:
        from llama_index.llms.google_genai import GoogleGenAI
        import os
        
        # Ensure Vertex AI environment variables are set for the SDK
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
        os.environ["GOOGLE_CLOUD_PROJECT"] = settings.GCP_PROJECT_ID
        os.environ["GOOGLE_CLOUD_LOCATION"] = settings.VERTEX_AI_LOCATION
        
        _llm_client = GoogleGenAI(model="gemini-2.5-flash", temperature=0.2)
    return _llm_client


_index = None


def get_llama_index():
    """
    Singleton factory for LlamaIndex VectorStoreIndex.
    """
    global _index
    if _index is None:
        from llama_index.core import VectorStoreIndex, StorageContext, Settings
        from app.pipelines.vector_store import get_qdrant_vector_store
        from app.pipelines.embedder import get_embeddings_client
        
        # Configure global settings
        Settings.embed_model = get_embeddings_client()
        Settings.llm = get_llm_client()
        
        vector_store = get_qdrant_vector_store()
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        
        _index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            storage_context=storage_context
        )
    return _index


def get_llama_retriever():
    """
    Singleton factory for LlamaIndex VectorStoreIndex retriever.
    """
    global _retriever
    if _retriever is None:
        index = get_llama_index()
        _retriever = index.as_retriever(similarity_top_k=40)
    return _retriever


_qa_tmpl = PromptTemplate(
    "You are GN Saarthi, a friendly AI guide for IIT Gandhinagar (IITGN).\n"
    "Your task is to answer the user query based on the provided college document context.\n"
    "Context information is below.\n"
    "---------------------\n"
    "{context_str}\n"
    "---------------------\n"
    "Fallback Quick Links (Use ONLY if the answer is NOT present in the Context):\n"
    "{links_text}\n\n"
    "User Query: {query_str}\n"
    "Instructions:\n"
    "1. Check if the answer can be found in the provided \"Context\".\n"
    "2. If the answer is present in the Context, provide a highly detailed, comprehensive, and exhaustive response. "
    "Do NOT summarize, simplify, or condense the information. Extract and list all specific details, raw figures, "
    "numerical ranges, tables, rules, criteria, exceptions, lists, and structural outlines exactly as they are detailed "
    "in the context. If the context contains comparative data or tables, reconstruct them fully in clean Markdown tables.\n"
    "3. For every fact, statement, or table row sourced from the context, you MUST cite the corresponding source "
    "by appending its citation label (e.g. [Source 1], [Source 2]) to the end of the sentence or table row.\n"
    "4. If the answer is NOT present in the Context, respond politely explaining that the answer cannot be found in the "
    "uploaded documents, and refer the user to the most appropriate service/link from the \"Fallback Quick Links\" list. "
    "Keep the response polite and helpful, providing the exact link and contact information. Do NOT cite any sources in this case.\n"
    "5. Structure the response beautifully using clear subheadings, bold text, bullet points, and tables with appropriate line breaks and paragraph spacing.\n"
    "6. Include relevant emojis at the start of key sections, lists, or headers (e.g. 📚, 🏡, 📅, 🚌) to make the response engaging.\n"
    "7. Be warm, professional, extremely thorough, and polite.\n"
    "Answer:"
)

_query_engine = None


def get_citation_query_engine():
    """
    Singleton factory for LlamaIndex CitationQueryEngine.
    """
    global _query_engine
    if _query_engine is None:
        from llama_index.core.query_engine import CitationQueryEngine
        
        index = get_llama_index()
        
        _query_engine = CitationQueryEngine.from_args(
            index,
            similarity_top_k=40,
            citation_chunk_size=512,
            citation_qa_template=_qa_tmpl,
            streaming=True
        )
    return _query_engine



def select_diverse_and_budgeted_chunks(hits: list, max_chars: int = 12000) -> list:
    """
    Deduplicates near-identical chunks, selects a diverse set of chunks to avoid
    monopolization by a single document, and budgets the context characters.
    """
    seen_texts = set()
    unique_hits = []
    
    # 1. Deduplicate near-identical chunks
    for hit in hits:
        text = hit.get("text_content", "").strip()
        if not text:
            continue
        normalized_text = " ".join(text.lower().split())
        
        # Check overlap
        is_duplicate = False
        for seen in seen_texts:
            if normalized_text == seen or (len(normalized_text) > 20 and normalized_text in seen) or (len(seen) > 20 and seen in normalized_text):
                is_duplicate = True
                break
        
        if not is_duplicate:
            seen_texts.add(normalized_text)
            unique_hits.append(hit)
            
    # 2. Diversity: apply a doc frequency penalty to prioritize a diverse set of documents
    doc_counts = {}
    diverse_hits = []
    for hit in unique_hits:
        doc_id = hit.get("doc_id")
        current_count = doc_counts.get(doc_id, 0)
        # Apply a mild penalty to subsequent chunks from the same document
        hit_score = hit.get("score", 0.0)
        diverse_score = hit_score - (0.05 * current_count)
        doc_counts[doc_id] = current_count + 1
        
        # Store for sorting
        diverse_hits.append((diverse_score, hit))
        
    # Re-sort by the diversity score descending
    diverse_hits.sort(key=lambda x: x[0], reverse=True)
    
    # 3. Context budgeting: fit within max_chars
    selected_hits = []
    current_length = 0
    for _, hit in diverse_hits:
        text_content = hit.get("text_content", "")
        text_len = len(text_content)
        if current_length + text_len > max_chars:
            if len(selected_hits) >= 2:
                break
            # Allow at least one hit if it exceeds the budget by itself, but stop after it
            selected_hits.append(hit)
            break
        selected_hits.append(hit)
        current_length += text_len
        
    return selected_hits

_quick_links_cache = None
_quick_links_cache_time = 0
_quick_links_lock = Lock()

def invalidate_links_cache():
    global _quick_links_cache, _quick_links_cache_time
    with _quick_links_lock:
        _quick_links_cache = None
        _quick_links_cache_time = 0
        logger.info("Quick links cache invalidated.")

def get_quick_links() -> list:
    """
    Retrieves quick links from Firestore with a 5-minute in-memory cache.
    """
    global _quick_links_cache, _quick_links_cache_time
    
    current_time = time.time()
    with _quick_links_lock:
        if _quick_links_cache is not None and (current_time - _quick_links_cache_time) < 300:
            return _quick_links_cache
            
    # Cache miss or expired, fetch from Firestore
    try:
        from app.dependencies import db
        logger.info("Fetching quick links from Firestore...")
        links_ref = db.collection("quick_links").order_by("service").stream()
        links = []
        for doc in links_ref:
            data = doc.to_dict()
            service = data.get("service", "").strip()
            link = data.get("link", "").strip()
            purpose = data.get("purpose", "").strip()
            if service and link:
                links.append({"service": service, "link": link, "purpose": purpose})
                
        with _quick_links_lock:
            _quick_links_cache = links
            _quick_links_cache_time = current_time
            
        logger.info(f"Loaded {len(links)} quick links into in-memory cache.")
        return links
    except Exception as e:
        logger.error(f"Failed to fetch quick links from Firestore: {e}")
        return links

async def generate_fallback_link_response_stream(query: str) -> AsyncGenerator[str, None]:
    """
    Generates a streaming polite response referring the user to quick links.
    """
    links = get_quick_links()
    links_text = "\n".join([
        f"- Service: {l['service']}\n  Link/Contact: {l['link']}\n  Purpose: {l['purpose']}"
        for l in links
    ])
    
    prompt = f"""You are GN Saarthi, a friendly AI guide for IIT Gandhinagar (IITGN).
The user asked a query: "{query}"

However, this information is not available in our indexed documents.
Please respond politely to the user, explaining that the answer cannot be found in database.
Based on the list of official quick links below, find the one (or more) that is most relevant to their query, and refer them to it.

If none of the links are relevant, point them to the general "Main Website" or "Internal Website".

Official Quick Links:
{links_text}

Instructions:
1. Be polite, warm, and helpful.
2. Provide the direct link (and any contact details) exactly as given in the list.
3. Keep the response concise and formatted in clean Markdown.
"""
    try:
        llm = get_llm_client()
        stream = await llm.astream_complete(prompt)
        async for chunk in stream:
            content = chunk.delta
            if content:
                yield f"data: {json.dumps({'type': 'text', 'content': content})}\n\n"
                await asyncio.sleep(0.005)
        yield f"data: {json.dumps({'type': 'sources', 'content': []})}\n\n"
    except Exception as e:
        logger.error(f"Error streaming fallback response: {e}")
        yield f"data: {json.dumps({'type': 'text', 'content': 'I cannot find the answer to this in the uploaded college documents.'})}\n\n"
        yield f"data: {json.dumps({'type': 'sources', 'content': []})}\n\n"


def detect_intent(query: str) -> str:
    """
    Uses Gemini-2.5-flash to classify the query into either 'general' or 'retrieval'.
    """
    prompt = f"""You are an intent detection assistant for GN Saarthi, an AI guide for IIT Gandhinagar (IITGN).
Your task is to classify the user's query into exactly one of two categories:
1. "general": General greetings (hello, hi, bye, good morning), gratitude (thanks, thank you), bot identity/capabilities (who are you, what can you do, how can you help me), or generic conversational questions (how are you, whats up, hope you are well).
2. "retrieval": Specific service requests, college questions, academic regulations, coursework norms, timings, or policies that require retrieving document context (e.g., bus schedule, credit requirements, course codes, hostel rules, laundry timings).

User Query: "{query}"

Output ONLY "general" or "retrieval". Do not include any other text, explanation, or punctuation.
"""
    try:
        llm = get_llm_client()
        response = llm.complete(prompt)
        intent = response.text.strip().lower()
        if "general" in intent:
            return "general"
        return "retrieval"
    except Exception as e:
        logger.error(f"Error detecting intent via LLM: {e}. Falling back to inline regex checks.")
        cleaned = re.sub(r"[^\w\s]", "", query.lower().strip())
        cleaned = " ".join(cleaned.split())
        greetings_and_thanks = {
            "hi", "hello", "hey", "hola", "sup", "greetings", "good morning", "good afternoon",
            "good evening", "thanks", "thank you", "bye", "goodbye", "who are you", "what is your name",
            "how can you help", "how are you", "whats up"
        }
        if any(g in cleaned for g in greetings_and_thanks) or cleaned in greetings_and_thanks:
            return "general"
        return "retrieval"

def needs_reformulation(query: str, history: list) -> bool:
    """
    Heuristically decides if a query needs reformulation:
    - If there is no conversation history, it's a standalone query by definition.
    - If the query is very short (3 words or less).
    - If the query contains explicit ambiguity markers (pronouns like he, she, they, it, this, that).
    - If the query contains explicit vague phrases like "tell me more" or "more details".
    """
    if not history:
        return False
        
    cleaned = re.sub(r"[^\w\s]", "", query.lower().strip())
    words = cleaned.split()
    
    # 1. Very short queries (3 words or less)
    if len(words) <= 3:
        return True
        
    # 2. Explicit ambiguity markers
    ambiguity_markers = {
        "it", "its", "they", "them", "this", "that", "these", "those",
        "he", "him", "his", "she", "her", "hers", "here", "there"
    }
    if any(word in ambiguity_markers for word in words):
        return True
        
    # 3. Explicit vague phrases
    phrases = ["more details", "tell me more", "what about", "is it"]
    for phrase in phrases:
        if phrase in cleaned:
            return True
            
    return False


async def retrieve_document_level_nodes(query: str) -> list:
    """
    Performs document-level retrieval:
    1. Runs initial vector search to identify target documents in the top results.
    2. Fetches all pages for the identified documents.
    3. Deduplicates nodes by page and sorts chronologically.
    """
    try:
        retriever = get_llama_retriever()
        initial_nodes = await retriever.aretrieve(query)
        if not initial_nodes:
            return []
            
        # Extract unique source documents from top matching results
        unique_sources = []
        seen_sources = set()
        
        # We inspect the top 10 matching nodes to identify related documents for cross-document queries
        for node_with_score in initial_nodes[:10]:
            score = node_with_score.score or 0.0
            # Only fetch documents that are highly relevant
            if score < 0.65:
                continue
            source = node_with_score.node.metadata.get("source")
            if source and source not in seen_sources:
                seen_sources.add(source)
                unique_sources.append(source)
                
        # Limit to maximum 3 documents to support cross-document search without context explosion
        target_sources = unique_sources[:3]
        if not target_sources:
            # Fallback to the single top source if scores were low
            top_source = initial_nodes[0].node.metadata.get("source")
            if top_source:
                target_sources = [top_source]
                
        logger.info(f"Target documents identified for full context retrieval: {target_sources}")
        
        # Fetch all pages for each target document
        index = get_llama_index()
        all_doc_nodes = []
        
        from llama_index.core.vector_stores import MetadataFilters, MetadataFilter
        
        for source in target_sources:
            filters = MetadataFilters(filters=[
                MetadataFilter(key="source", value=source)
            ])
            # Set similarity_top_k to 150 to ensure we capture all pages in larger documents
            doc_retriever = index.as_retriever(filters=filters, similarity_top_k=150)
            page_nodes = await doc_retriever.aretrieve(query)
            
            # Deduplicate page nodes by page number (keeping highest score)
            unique_pages = {}
            for node in page_nodes:
                page = node.node.metadata.get("page", 0)
                if page not in unique_pages or node.score > unique_pages[page].score:
                    unique_pages[page] = node
                    
            deduped = list(unique_pages.values())
            # Sort chronologically
            deduped.sort(key=lambda x: x.node.metadata.get("page", 0))
            all_doc_nodes.extend(deduped)
            
        return all_doc_nodes
    except Exception as e:
        logger.error(f"Error in retrieve_document_level_nodes: {e}. Falling back to standard retrieval.")
        return initial_nodes


async def generate_rag_answer_stream(query: str, session_id: Optional[str] = None) -> AsyncGenerator[str, None]:
    """
    Generates a streaming RAG answer.
    """
    logger.info(f"Generating streaming RAG answer for query: '{query}' (session: {session_id})")
    
    # 1. Fetch Session History & Summary
    history_data = session_cache.get(session_id) if session_id else ([], "")
    history, summary = history_data
    
    # 2. Detect Intent (run sync in thread pool, on raw query)
    intent = await run_sync(detect_intent, query)
    
    # Format history and summary for prompts
    history_text = ""
    if history:
        for turn in history:
            history_text += f"User: {turn['user']}\nAssistant: {turn['bot']}\n\n"
            
    summary_section = ""
    if summary:
        summary_section = f"Summary of older conversation:\n{summary}\n\n"
        
    if intent == "general":
        logger.info(f"Generic conversational query detected: '{query}'. Bypassing retrieval (streaming).")
        prompt = f"""You are GN Saarthi, a friendly AI guide for IIT Gandhinagar (IITGN).
Be helpful, warm, and keep your answer short and engaging. Introduce yourself if they ask who you are.
Respond politely and concisely to the user's conversational query, taking the conversation history and summary into account.
If someone asks you who made you, say that you were created by Piyush Keshri, a student of IIT Gandhinagar and the creator of GN Saarthi to assist IITGN students and faculty in navigating college information and services.

{summary_section}Recent Conversation History:
{history_text}User: {query}
Assistant:"""
        
        try:
            llm = get_llm_client()
            full_content = ""
            stream = await llm.astream_complete(prompt)
            async for chunk in stream:
                content = chunk.delta
                if content:
                    full_content += content
                    yield f"data: {json.dumps({'type': 'text', 'content': content})}\n\n"
                    await asyncio.sleep(0.005)
            if session_id:
                session_cache.add_turn(session_id, query, full_content)
            yield f"data: {json.dumps({'type': 'sources', 'content': []})}\n\n"
            return
        except Exception as e:
            logger.error(f"Error streaming LLM response for generic query: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': 'Error during streaming: ' + str(e)})}\n\n"
            return
            
    # 3. Retrieval Flow: Determine if query needs reformulation
    if needs_reformulation(query, history):
        reformulated_query = await run_sync(reformulate_query, query, history)
    else:
        logger.info(f"Query '{query}' is clear or lacks history context. Bypassing reformulation.")
        reformulated_query = query
        
    # 4. Stream response using CitationQueryEngine
    links = get_quick_links()
    links_text = "\n".join([
        f"- Service: {l['service']}\n  Link/Contact: {l['link']}\n  Purpose: {l['purpose']}"
        for l in links
    ])
    
    try:
        query_engine = get_citation_query_engine()
        query_engine.update_prompts({
            "response_synthesizer:text_qa_template": _qa_tmpl.partial_format(links_text=links_text)
        })
        
        from unittest.mock import Mock
        if isinstance(query_engine, Mock):
            response = await query_engine.aquery(reformulated_query)
        else:
            # Document-level context retrieval
            nodes = await retrieve_document_level_nodes(reformulated_query)
            # Synthesize response using reformulated query and full document nodes
            response = await query_engine.asynthesize(reformulated_query, nodes=nodes)
    except Exception as e:
        logger.error(f"Error executing CitationQueryEngine query: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': 'Error during query execution: ' + str(e)})}\n\n"
        return
        
    if not response.source_nodes:
        logger.info("No relevant chunks found by query engine. Returning graceful link fallback answer.")
        full_fallback = ""
        async for chunk in generate_fallback_link_response_stream(reformulated_query):
            if chunk.startswith("data: "):
                try:
                    data = json.loads(chunk[6:].strip())
                    if data.get("type") == "text":
                        full_fallback += data["content"]
                except:
                    pass
            yield chunk
        if session_id:
            session_cache.add_turn(session_id, query, full_fallback)
        return
        
    full_answer = ""
    try:
        logger.info("Invoking CitationQueryEngine streaming for answer generation...")
        if hasattr(response, "async_response_gen"):
            gen = response.async_response_gen() if callable(response.async_response_gen) else response.async_response_gen
            async for token in gen:
                if token:
                    full_answer += token
                    yield f"data: {json.dumps({'type': 'text', 'content': token})}\n\n"
                    await asyncio.sleep(0.005)
        elif hasattr(response, "response_gen"):
            gen = response.response_gen() if callable(response.response_gen) else response.response_gen
            for token in gen:
                if token:
                    full_answer += token
                    yield f"data: {json.dumps({'type': 'text', 'content': token})}\n\n"
                    await asyncio.sleep(0.005)
    except Exception as e:
        logger.error(f"Error during query engine streaming: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': 'Error during streaming generation: ' + str(e)})}\n\n"
        return

    # Check for fallback links condition
    is_fallback = False
    for l in links:
        url_clean = l["link"].split("?")[0].replace("https://", "").replace("http://", "").strip("/")
        if url_clean in full_answer or l["link"] in full_answer:
            is_fallback = True
            break
            
    # Serialize cited sources
    serialized_sources = []
    if not is_fallback and hasattr(response, "source_nodes") and response.source_nodes:
        cited_indices = set()
        matches = re.findall(r"\[Source\s+(\d+)\]", full_answer)
        for m in matches:
            cited_indices.add(int(m))
            
        seen_doc_ids = set()
        for idx, node_with_score in enumerate(response.source_nodes):
            if (idx + 1) in cited_indices or not cited_indices:
                node = node_with_score.node
                doc_id = node.metadata.get("doc_id")
                source_name = node.metadata.get("source")
                if doc_id and doc_id not in seen_doc_ids:
                    seen_doc_ids.add(doc_id)
                    serialized_sources.append({
                        "doc_id": doc_id,
                        "document_id": doc_id,
                        "source": source_name or "Document",
                        "source_type": node.metadata.get("source_type", "pdf"),
                        "page": node.metadata.get("page", 1),
                        "page_start": node.metadata.get("page_start", 1),
                        "page_end": node.metadata.get("page_end", 1),
                        "text_content": node.text
                    })
                
    if session_id:
        session_cache.add_turn(session_id, query, full_answer)
        
    yield f"data: {json.dumps({'type': 'sources', 'content': serialized_sources})}\n\n"

