import logging
import json
import asyncio
import re
import time
from collections import OrderedDict
from threading import Lock
from typing import AsyncGenerator, Optional
from anyio.to_thread import run_sync
from google.oauth2 import service_account
from langchain_google_vertexai import ChatVertexAI
from app.config import settings
from app.schemas.schemas import ChatResponse, SourceChunk
from app.pipelines.embedder import generate_query_embedding
from app.pipelines.vector_store import search_vectors

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
        response = llm.invoke(prompt)
        return response.content.strip()
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
        response = llm.invoke(prompt)
        reformulated = response.content.strip()
        logger.info(f"Reformulated query from '{query}' to '{reformulated}'")
        return reformulated
    except Exception as e:
        logger.error(f"Error reformulating query: {e}. Using original query.")
        return query



def get_llm_client() -> ChatVertexAI:
    """
    Singleton factory for ChatVertexAI using gemini-2.5-flash.
    """
    global _llm_client
    if _llm_client is None:
        sa_info = settings.firebase_service_account_dict
        gcp_cred = service_account.Credentials.from_service_account_info(
            sa_info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        _llm_client = ChatVertexAI(
            model_name="gemini-2.5-flash",
            project=settings.GCP_PROJECT_ID,
            location=settings.VERTEX_AI_LOCATION,
            credentials=gcp_cred
        )
    return _llm_client



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
Please respond politely to the user, explaining that the answer cannot be found in the uploaded documents.
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
        async for chunk in llm.astream(prompt):
            content = chunk.content
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
        response = llm.invoke(prompt)
        intent = response.content.strip().lower()
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
            async for chunk in llm.astream(prompt):
                content = chunk.content
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
        
    # 4. Embed query (using reformulated query)
    from app.pipelines.embedder import get_embeddings_client, generate_query_embedding
    try:
        embeddings_client = get_embeddings_client()
        query_vector = await embeddings_client.aembed_query(reformulated_query)
    except Exception as e:
        logger.error(f"Error generating query embedding asynchronously: {e}. Falling back to sync.")
        query_vector = await run_sync(generate_query_embedding, reformulated_query)
        
    # 5. Search Qdrant
    hits = await run_sync(search_vectors, query_vector, 20)
    hits = [h for h in hits if h.get("score", 0.0) >= 0.45]
    selected_hits = select_diverse_and_budgeted_chunks(hits, max_chars=25000)
    
    if not selected_hits:
        logger.info("No relevant chunks found in Qdrant search. Returning graceful link fallback answer.")
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
        
    # 6. Build Context
    sources = []
    context_blocks = []
    
    for idx, hit in enumerate(selected_hits):
        sources.append(SourceChunk(
            doc_id=hit["doc_id"],
            source=hit["source"],
            page=hit["page"],
            text_content=hit["text_content"],
            page_start=hit.get("page_start"),
            page_end=hit.get("page_end"),
            source_type=hit.get("source_type"),
            document_id=hit.get("doc_id")
        ))
        
        if hit.get("page_start") and hit.get("page_end") and hit["page_start"] != hit["page_end"]:
            page_info = f"Pages: {hit['page_start']}-{hit['page_end']}"
        else:
            page_info = f"Page: {hit['page']}"
            
        context_blocks.append(
            f"Source {idx + 1} (File: {hit['source']}, {page_info}):\n{hit['text_content']}"
        )
        
    context_text = "\n\n".join(context_blocks)
    
    links = get_quick_links()
    links_text = "\n".join([
        f"- Service: {l['service']}\n  Link/Contact: {l['link']}\n  Purpose: {l['purpose']}"
        for l in links
    ])
    
    # Append history and summary section if present
    history_section = ""
    if history_text or summary_section:
        history_section = f"Conversation Context:\n{summary_section}Recent History:\n{history_text}\n"
        
    # 7. Formulate prompt
    prompt = f"""You are GN Saarthi, a RAG-powered chatbot for IIT Gandhinagar (IITGN).
Your task is to answer the user query based on the provided college document context.

{history_section}Context:
{context_text}

Fallback Quick Links (Use ONLY if the answer is NOT present in the Context):
{links_text}

User Query: {query}

Instructions:
1. First, check if the answer to the query can be found in the provided "Context".
2. If the answer is present in the Context, answer the query accurately and clearly. For every statement sourced from the context, you MUST cite the corresponding source by appending its citation label (e.g. [Source 1], [Source 2]) to the end of the sentence.
3. If the answer is NOT present in the Context, respond politely explaining that the answer cannot be found in the uploaded documents, and refer the user to the most appropriate service/link from the "Fallback Quick Links" list. Keep the response polite, helpful, and provide the exact link and contact information. Do NOT cite any sources in this case.
4. Structure your response beautifully using clean Markdown (e.g. bold text, bulleted lists, subheadings, tables, or numbered steps) with appropriate line breaks and paragraph spacing.
5. Include relevant emojis at the start of key sections, lists, or headers (e.g. 📚, 🏡, 📅, 🚌) to make the response engaging and easy to read.
6. Be helpful, concise, and polite.
"""

    # 8. Stream Response
    llm = get_llm_client()
    full_answer = ""
    try:
        logger.info("Invoking Gemini LLM streaming for answer generation...")
        async for chunk in llm.astream(prompt):
            content = chunk.content
            if content:
                full_answer += content
                yield f"data: {json.dumps({'type': 'text', 'content': content})}\n\n"
                await asyncio.sleep(0.005)
    except Exception as e:
        logger.error(f"Error during streaming: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': 'Error during streaming generation: ' + str(e)})}\n\n"
        return
        
    # 9. Parse Citations
    is_fallback = False
    for l in links:
        url_clean = l["link"].split("?")[0].replace("https://", "").replace("http://", "").strip("/")
        if url_clean in full_answer or l["link"] in full_answer:
            is_fallback = True
            break
            
    if is_fallback:
        final_sources = []
    else:
        cited_indices = set()
        matches = re.findall(r"\[Source\s+(\d+)\]", full_answer)
        for m in matches:
            cited_indices.add(int(m))
            
        cited_sources = []
        for idx, source in enumerate(sources):
            if (idx + 1) in cited_indices:
                cited_sources.append(source)
                
        if not cited_sources:
            cited_sources = sources
            
        final_sources = []
        seen_keys = set()
        for src in cited_sources:
            p_start = src.page_start if src.page_start is not None else src.page
            p_end = src.page_end if src.page_end is not None else src.page
            key = (src.source, p_start, p_end)
            if key not in seen_keys:
                seen_keys.add(key)
                final_sources.append(src)
                
    serialized_sources = [
        (src.model_dump() if hasattr(src, "model_dump") else src.dict())
        for src in final_sources
    ]
    
    if session_id:
        session_cache.add_turn(session_id, query, full_answer)
        
    yield f"data: {json.dumps({'type': 'sources', 'content': serialized_sources})}\n\n"

