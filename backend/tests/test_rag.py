from unittest.mock import MagicMock, patch
import pytest
import json
from app.services.rag_service import generate_rag_answer_stream, session_cache
from app.schemas.schemas import ChatResponse, SourceChunk
from llama_index.core.schema import NodeWithScore, TextNode

async def run_stream(query: str, session_id: str = None) -> ChatResponse:
    answer_parts = []
    sources = []
    
    async for event in generate_rag_answer_stream(query, session_id=session_id):
        if event.startswith("data: "):
            try:
                data = json.loads(event[6:].strip())
                if data["type"] == "text":
                    answer_parts.append(data["content"])
                elif data["type"] == "sources":
                    sources = [SourceChunk(**src) for src in data["content"]]
            except Exception:
                pass
                
    return ChatResponse(
        answer="".join(answer_parts),
        sources=sources
    )

@pytest.mark.asyncio
@patch("app.services.rag_service.detect_intent")
@patch("app.services.rag_service.get_citation_query_engine")
@patch("app.services.rag_service.get_llm_client")
async def test_generate_rag_answer(mock_get_llm, mock_get_query_engine, mock_detect):
    mock_detect.return_value = "retrieval"
    """
    Verify that generate_rag_answer_stream retrieves nodes from query engine,
    and builds a valid ChatResponse.
    """
    mock_query_engine = MagicMock()
    mock_response = MagicMock()
    
    async def mock_async_response_gen():
        yield "According to the hostel rules, students entering after 10:00 PM must log their entry in the register."
    mock_response.async_response_gen = mock_async_response_gen()
    
    node = TextNode(
        text="Students must log their entry in the register after 10:00 PM.",
        metadata={
            "doc_id": "doc-uuid-1",
            "source": "hostel_rules.pdf",
            "page": 4,
            "page_start": 4,
            "page_end": 4
        }
    )
    mock_response.source_nodes = [NodeWithScore(node=node, score=0.88)]
    
    async def mock_aquery(*args, **kwargs):
        return mock_response
    mock_query_engine.aquery = mock_aquery
    mock_get_query_engine.return_value = mock_query_engine
    
    query = "What are the rules for entering the hostel late?"
    response = await run_stream(query)
    
    assert response.answer == "According to the hostel rules, students entering after 10:00 PM must log their entry in the register."
    assert len(response.sources) == 1
    assert response.sources[0].doc_id == "doc-uuid-1"
    assert response.sources[0].source == "hostel_rules.pdf"
    assert response.sources[0].page == 4
    assert response.sources[0].text_content == "Students must log their entry in the register after 10:00 PM."

@pytest.mark.asyncio
@patch("app.services.rag_service.detect_intent")
@patch("app.services.rag_service.get_citation_query_engine")
@patch("app.services.rag_service.get_llm_client")
async def test_rag_deduplication_and_budgeting(mock_get_llm, mock_get_query_engine, mock_detect):
    mock_detect.return_value = "retrieval"
    """
    Verify that RAG extracts returned source details correctly from the query engine response.
    """
    mock_query_engine = MagicMock()
    mock_response = MagicMock()
    
    async def mock_async_response_gen():
        yield "Mocked answer."
    mock_response.async_response_gen = mock_async_response_gen()
    
    n1 = TextNode(text="Hostel rules text.", metadata={"doc_id": "doc-1", "source": "hostel_rules.pdf", "page": 2, "page_start": 2, "page_end": 2})
    n2 = TextNode(text="Academic calendar text.", metadata={"doc_id": "doc-2", "source": "academic_calendar.pdf", "page": 1, "page_start": 1, "page_end": 2})
    mock_response.source_nodes = [
        NodeWithScore(node=n1, score=0.95),
        NodeWithScore(node=n2, score=0.85)
    ]
    
    async def mock_aquery(*args, **kwargs):
        return mock_response
    mock_query_engine.aquery = mock_aquery
    mock_get_query_engine.return_value = mock_query_engine
    
    response = await run_stream("What is the rule?")
    
    sources = response.sources
    assert len(sources) == 2
    assert sources[0].doc_id == "doc-1"
    assert sources[0].source == "hostel_rules.pdf"
    assert sources[0].page_start == 2
    assert sources[0].page_end == 2
    
    assert sources[1].doc_id == "doc-2"
    assert sources[1].source == "academic_calendar.pdf"
    assert sources[1].page_start == 1
    assert sources[1].page_end == 2

@pytest.mark.asyncio
@patch("app.services.rag_service.detect_intent")
@patch("app.services.rag_service.get_citation_query_engine")
@patch("app.services.rag_service.get_llm_client")
async def test_rag_citation_filtering_and_threshold(mock_get_llm, mock_get_query_engine, mock_detect):
    mock_detect.return_value = "retrieval"
    """
    Verify that RAG filters returned sources based on citation tags [Source X] in the answer.
    """
    mock_query_engine = MagicMock()
    mock_response = MagicMock()
    
    async def mock_async_response_gen():
        yield "The bus leaves at 8:00 AM according to [Source 1]."
    mock_response.async_response_gen = mock_async_response_gen()
    
    n1 = TextNode(text="Bus timings text.", metadata={"doc_id": "doc-1", "source": "bus_schedule.pdf", "page": 1})
    n2 = TextNode(text="Calendar dates text.", metadata={"doc_id": "doc-2", "source": "calendar.pdf", "page": 1})
    mock_response.source_nodes = [
        NodeWithScore(node=n1, score=0.65),
        NodeWithScore(node=n2, score=0.55)
    ]
    
    async def mock_aquery(*args, **kwargs):
        return mock_response
    mock_query_engine.aquery = mock_aquery
    mock_get_query_engine.return_value = mock_query_engine
    
    response = await run_stream("bus timings")
    
    assert "[Source 1]" in response.answer
    assert len(response.sources) == 1
    assert response.sources[0].source == "bus_schedule.pdf"
    assert response.sources[0].page == 1

@pytest.mark.asyncio
@patch("app.services.rag_service.detect_intent")
@patch("app.services.rag_service.get_citation_query_engine")
@patch("app.services.rag_service.get_llm_client")
async def test_generate_rag_answer_stream(mock_get_llm, mock_get_query_engine, mock_detect):
    mock_detect.return_value = "retrieval"
    """
    Verify that generate_rag_answer_stream successfully retrieves and streams tokens.
    """
    mock_query_engine = MagicMock()
    mock_response = MagicMock()
    
    async def mock_async_response_gen():
        yield "Streaming "
        yield "answer citing [Source 1]."
    mock_response.async_response_gen = mock_async_response_gen()
    
    n1 = TextNode(text="Bus timings text.", metadata={"doc_id": "doc-1", "source": "bus_schedule.pdf", "page": 1})
    mock_response.source_nodes = [NodeWithScore(node=n1, score=0.65)]
    
    async def mock_aquery(*args, **kwargs):
        return mock_response
    mock_query_engine.aquery = mock_aquery
    mock_get_query_engine.return_value = mock_query_engine
    
    events = []
    async for event in generate_rag_answer_stream("bus timings"):
        events.append(event)
        
    assert len(events) == 3
    data0 = json.loads(events[0].replace("data: ", "").strip())
    assert data0["type"] == "text"
    assert data0["content"] == "Streaming "
    
    data1 = json.loads(events[1].replace("data: ", "").strip())
    assert data1["type"] == "text"
    assert data1["content"] == "answer citing [Source 1]."
    
    data2 = json.loads(events[2].replace("data: ", "").strip())
    assert data2["type"] == "sources"
    assert len(data2["content"]) == 1
    assert data2["content"][0]["source"] == "bus_schedule.pdf"

@pytest.mark.asyncio
@patch("app.services.rag_service.detect_intent")
@patch("app.services.rag_service.get_llm_client")
async def test_generic_query_bypasses_retrieval(mock_get_llm, mock_detect):
    mock_detect.return_value = "general"
    """
    Verify that a generic query bypasses retrieval and returns conversational responses directly.
    """
    mock_llm = MagicMock()
    async def mock_astream_complete(prompt, *args, **kwargs):
        async def gen():
            chunk = MagicMock()
            chunk.delta = "Hello! I am GN Saarthi."
            yield chunk
        return gen()
    mock_llm.astream_complete = mock_astream_complete
    mock_get_llm.return_value = mock_llm
    
    events = []
    async for event in generate_rag_answer_stream("hello"):
        events.append(event)
        
    assert len(events) == 2
    data0 = json.loads(events[0].replace("data: ", "").strip())
    assert data0["type"] == "text"
    assert data0["content"] == "Hello! I am GN Saarthi."
    
    data1 = json.loads(events[1].replace("data: ", "").strip())
    assert data1["type"] == "sources"
    assert data1["content"] == []

@patch("app.services.rag_service.update_rolling_summary")
def test_session_cache_operations(mock_update_summary):
    mock_update_summary.return_value = "Mocked rolling summary"
    from app.services.rag_service import MemorySessionCache
    import time
    
    cache = MemorySessionCache(max_size=2, ttl_seconds=1)
    assert cache.get("sess-1") == ([], "")
    
    cache.add_turn("sess-1", "Hello", "Hi there", max_turns=2)
    cache.add_turn("sess-1", "How are you?", "I am good", max_turns=2)
    cache.add_turn("sess-1", "What is RAG?", "Retrieval Augmented Generation", max_turns=2)
    
    history, summary = cache.get("sess-1")
    assert len(history) == 2
    assert history[0]["user"] == "How are you?"
    assert history[1]["user"] == "What is RAG?"
    assert summary == "Mocked rolling summary"
    
    cache.add_turn("sess-2", "User2", "Bot2")
    cache.add_turn("sess-3", "User3", "Bot3")
    assert cache.get("sess-1") == ([], "")
    
    h2, _ = cache.get("sess-2")
    assert len(h2) == 1
    h3, _ = cache.get("sess-3")
    assert len(h3) == 1
    
    time.sleep(1.1)
    assert cache.get("sess-2") == ([], "")

@pytest.mark.asyncio
@patch("app.services.rag_service.detect_intent")
@patch("app.services.rag_service.get_citation_query_engine")
@patch("app.services.rag_service.get_llm_client")
async def test_multiturn_rag_answer(mock_get_llm, mock_get_query_engine, mock_detect):
    mock_detect.return_value = "retrieval"
    
    mock_query_engine = MagicMock()
    n1 = TextNode(text="The curfew time is 10:00 PM.", metadata={"doc_id": "doc-1", "source": "curfew.pdf", "page": 1})
    
    call_count = 0
    async def mock_aquery(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        
        mock_response = MagicMock()
        async def mock_async_response_gen():
            if call_count == 1:
                yield "According to curfew.pdf, the curfew time is 10:00 PM."
            else:
                yield "Yes, the curfew is 10:00 PM for girls as well."
        mock_response.async_response_gen = mock_async_response_gen()
        mock_response.source_nodes = [NodeWithScore(node=n1, score=0.90)]
        return mock_response
        
    mock_query_engine.aquery = mock_aquery
    mock_get_query_engine.return_value = mock_query_engine
    
    mock_llm = MagicMock()
    mock_llm_reformulate = MagicMock()
    mock_llm_reformulate.text = "Is the curfew time the same for girls' hostels?"
    mock_llm.complete.return_value = mock_llm_reformulate
    mock_get_llm.return_value = mock_llm
    
    session_id = "test-session-multi"
    if session_id in session_cache.cache:
        del session_cache.cache[session_id]
        
    res1 = await run_stream("What is the curfew time?", session_id=session_id)
    assert "10:00 PM" in res1.answer
    
    history, summary = session_cache.get(session_id)
    assert len(history) == 1
    assert history[0]["user"] == "What is the curfew time?"
    
    res2 = await run_stream("Is it the same for girls?", session_id=session_id)
    assert "girls as well" in res2.answer
    
    history2, summary2 = session_cache.get(session_id)
    assert len(history2) == 2
    assert history2[1]["user"] == "Is it the same for girls?"
    
    if session_id in session_cache.cache:
        del session_cache.cache[session_id]
