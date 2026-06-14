from unittest.mock import MagicMock, patch
import pytest
import json
from app.services.rag_service import generate_rag_answer_stream, session_cache
from app.schemas.schemas import ChatResponse, SourceChunk

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
@patch("app.pipelines.embedder.get_embeddings_client")
@patch("app.services.rag_service.search_vectors")
@patch("app.services.rag_service.get_llm_client")
async def test_generate_rag_answer(mock_get_llm, mock_search, mock_get_embeddings, mock_detect):
    mock_detect.return_value = "retrieval"
    """
    Verify that generate_rag_answer_stream embeds the query, searches the vector database,
    constructs the context prompt, invokes the LLM, and builds a valid ChatResponse.
    """
    # Mock embedding query
    mock_client = MagicMock()
    async def mock_aembed_query(text):
        return [0.1] * 768
    mock_client.aembed_query = mock_aembed_query
    mock_get_embeddings.return_value = mock_client
    
    # Mock vector search results (1 mock hit)
    mock_search.return_value = [
        {
            "score": 0.88,
            "doc_id": "doc-uuid-1",
            "source": "hostel_rules.pdf",
            "page": 4,
            "text_content": "Students must log their entry in the register after 10:00 PM."
        }
    ]
    
    # Mock LLM and response
    mock_llm = MagicMock()
    async def mock_astream(prompt, *args, **kwargs):
        chunk = MagicMock()
        chunk.content = "According to the hostel rules, students entering after 10:00 PM must log their entry in the register."
        yield chunk
    mock_llm.astream = mock_astream
    mock_get_llm.return_value = mock_llm
    
    # Call generation service
    query = "What are the rules for entering the hostel late?"
    response = await run_stream(query)
    
    # Assert ChatResponse structure and values
    assert response.answer == "According to the hostel rules, students entering after 10:00 PM must log their entry in the register."
    assert len(response.sources) == 1
    assert response.sources[0].doc_id == "doc-uuid-1"
    assert response.sources[0].source == "hostel_rules.pdf"
    assert response.sources[0].page == 4
    assert response.sources[0].text_content == "Students must log their entry in the register after 10:00 PM."
    
    mock_search.assert_called_once_with([0.1] * 768, 20)
    assert mock_get_llm.call_count >= 1

@pytest.mark.asyncio
@patch("app.services.rag_service.detect_intent")
@patch("app.pipelines.embedder.get_embeddings_client")
@patch("app.services.rag_service.search_vectors")
@patch("app.services.rag_service.get_llm_client")
async def test_rag_deduplication_and_budgeting(mock_get_llm, mock_search, mock_get_embeddings, mock_detect):
    mock_detect.return_value = "retrieval"
    """
    Verify that RAG deduplicates identical/similar hits, budgets the context block size,
    and returns correct SourceChunk range fields.
    """
    # Mock embedding query
    mock_client = MagicMock()
    async def mock_aembed_query(text):
        return [0.1] * 768
    mock_client.aembed_query = mock_aembed_query
    mock_get_embeddings.return_value = mock_client
    
    # 1. Mock search results containing duplicate text and large text
    mock_search.return_value = [
        {
            "score": 0.95,
            "doc_id": "doc-1",
            "source": "hostel_rules.pdf",
            "page": 2,
            "page_start": 2,
            "page_end": 2,
            "text_content": "Duplicate hostel rules text."
        },
        {
            "score": 0.90,
            "doc_id": "doc-1",
            "source": "hostel_rules.pdf",
            "page": 3,
            "page_start": 3,
            "page_end": 3,
            "text_content": "Duplicate Hostel Rules Text." # near-identical (different case)
        },
        {
            "score": 0.85,
            "doc_id": "doc-2",
            "source": "academic_calendar.pdf",
            "page": 1,
            "page_start": 1,
            "page_end": 2,
            "text_content": "Very long text that will exceed the context character budget... " * 500
        },
        {
            "score": 0.80,
            "doc_id": "doc-3",
            "source": "bus_schedule.pdf",
            "page": 1,
            "page_start": 1,
            "page_end": 1,
            "text_content": "This chunk should be skipped due to context budgeting limit."
        }
    ]
    
    # Mock LLM and response
    mock_llm = MagicMock()
    async def mock_astream(prompt, *args, **kwargs):
        chunk = MagicMock()
        chunk.content = "Mocked answer."
        yield chunk
    mock_llm.astream = mock_astream
    mock_get_llm.return_value = mock_llm
    
    response = await run_stream("What is the rule?")
    
    sources = response.sources
    
    # Verify deduplication and budgeting
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
@patch("app.pipelines.embedder.get_embeddings_client")
@patch("app.services.rag_service.search_vectors")
@patch("app.services.rag_service.get_llm_client")
async def test_rag_citation_filtering_and_threshold(mock_get_llm, mock_search, mock_get_embeddings, mock_detect):
    mock_detect.return_value = "retrieval"
    """
    Verify that RAG filters out hits below the similarity threshold (0.45)
    and filters returned sources based on citation tags [Source X] in the LLM answer.
    """
    # Mock embedding query
    mock_client = MagicMock()
    async def mock_aembed_query(text):
        return [0.1] * 768
    mock_client.aembed_query = mock_aembed_query
    mock_get_embeddings.return_value = mock_client
    
    # Mock search results:
    # 1. doc-1 Page 1 (Score 0.65) -> Passed to context (Index 1)
    # 2. doc-2 Page 1 (Score 0.55) -> Passed to context (Index 2)
    # 3. doc-3 Page 1 (Score 0.38) -> Filtered out (Score < 0.45)
    mock_search.return_value = [
        {
            "score": 0.65,
            "doc_id": "doc-1",
            "source": "bus_schedule.pdf",
            "page": 1,
            "text_content": "Bus timings text."
        },
        {
            "score": 0.55,
            "doc_id": "doc-2",
            "source": "calendar.pdf",
            "page": 1,
            "text_content": "Calendar dates text."
        },
        {
            "score": 0.38,
            "doc_id": "doc-3",
            "source": "unrelated_doc.pdf",
            "page": 2,
            "text_content": "Completely unrelated content."
        }
    ]
    
    # Mock LLM response citing only Source 1
    mock_llm = MagicMock()
    async def mock_astream(prompt, *args, **kwargs):
        chunk = MagicMock()
        chunk.content = "The bus leaves at 8:00 AM according to [Source 1]."
        yield chunk
    mock_llm.astream = mock_astream
    mock_get_llm.return_value = mock_llm
    
    response = await run_stream("bus timings")
    
    # Assertions
    assert "[Source 1]" in response.answer
    assert "according to" in response.answer
    # doc-3 is filtered out because score < 0.45
    # doc-2 is filtered out because it is not cited in the answer
    # Only doc-1 should be returned in sources
    assert len(response.sources) == 1
    assert response.sources[0].source == "bus_schedule.pdf"
    assert response.sources[0].page == 1

@pytest.mark.asyncio
@patch("app.services.rag_service.detect_intent")
@patch("app.pipelines.embedder.get_embeddings_client")
@patch("app.services.rag_service.search_vectors")
@patch("app.services.rag_service.get_llm_client")
async def test_generate_rag_answer_stream(mock_get_llm, mock_search, mock_get_embeddings, mock_detect):
    mock_detect.return_value = "retrieval"
    """
    Verify that generate_rag_answer_stream successfully embeds query,
    filters by threshold, and streams tokens and final sources correctly.
    """
    # Mock embedding query
    mock_client = MagicMock()
    async def mock_aembed_query(text):
        return [0.1] * 768
    mock_client.aembed_query = mock_aembed_query
    mock_get_embeddings.return_value = mock_client
    
    # Mock search results:
    # 1. doc-1 Page 1 (Score 0.65) -> Passed to context (Index 1)
    # 2. doc-2 Page 1 (Score 0.35) -> Filtered out (Score < 0.45)
    mock_search.return_value = [
        {
            "score": 0.65,
            "doc_id": "doc-1",
            "source": "bus_schedule.pdf",
            "page": 1,
            "text_content": "Bus timings text."
        },
        {
            "score": 0.35,
            "doc_id": "doc-2",
            "source": "unrelated.pdf",
            "page": 1,
            "text_content": "Unrelated."
        }
    ]
    
    # Mock LLM and async stream response
    mock_llm = MagicMock()
    
    async def mock_astream(prompt, *args, **kwargs):
        chunk1 = MagicMock()
        chunk1.content = "Streaming "
        yield chunk1
        chunk2 = MagicMock()
        chunk2.content = "answer citing [Source 1]."
        yield chunk2
        
    mock_llm.astream = mock_astream
    mock_get_llm.return_value = mock_llm
    
    events = []
    async for event in generate_rag_answer_stream("bus timings"):
        events.append(event)
        
    # Check streamed events
    assert len(events) == 3 # 2 text chunks + 1 final sources chunk
    
    # Check text chunks
    data0 = json.loads(events[0].replace("data: ", "").strip())
    assert data0["type"] == "text"
    assert data0["content"] == "Streaming "
    
    data1 = json.loads(events[1].replace("data: ", "").strip())
    assert data1["type"] == "text"
    assert data1["content"] == "answer citing [Source 1]."
    
    # Check final sources chunk
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
    Verify that a generic query does not trigger embedding generation or vector searches,
    and returns conversational responses directly.
    """
    # Mock LLM and async stream response
    mock_llm = MagicMock()
    
    # For streaming call
    async def mock_astream(prompt, *args, **kwargs):
        chunk = MagicMock()
        chunk.content = "Hello! I am GN Saarthi."
        yield chunk
        
    mock_llm.astream = mock_astream
    mock_get_llm.return_value = mock_llm
    
    # Test Stream
    events = []
    async for event in generate_rag_answer_stream("hello"):
        events.append(event)
        
    assert len(events) == 2 # 1 text chunk + 1 final sources chunk
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
    
    # Create a small cache for testing
    cache = MemorySessionCache(max_size=2, ttl_seconds=1)
    
    # Verify empty cache get
    assert cache.get("sess-1") == ([], "")
    
    # Add turns and check limit of max_turns
    cache.add_turn("sess-1", "Hello", "Hi there", max_turns=2)
    cache.add_turn("sess-1", "How are you?", "I am good", max_turns=2)
    cache.add_turn("sess-1", "What is RAG?", "Retrieval Augmented Generation", max_turns=2)
    
    history, summary = cache.get("sess-1")
    assert len(history) == 2
    assert history[0]["user"] == "How are you?"
    assert history[1]["user"] == "What is RAG?"
    assert summary == "Mocked rolling summary"
    
    # Test LRU Eviction
    cache.add_turn("sess-2", "User2", "Bot2")
    cache.add_turn("sess-3", "User3", "Bot3") # Should evict sess-1
    
    assert cache.get("sess-1") == ([], "")
    
    h2, _ = cache.get("sess-2")
    assert len(h2) == 1
    h3, _ = cache.get("sess-3")
    assert len(h3) == 1
    
    # Test TTL Expiration
    time.sleep(1.1)
    assert cache.get("sess-2") == ([], "")

@pytest.mark.asyncio
@patch("app.services.rag_service.detect_intent")
@patch("app.pipelines.embedder.get_embeddings_client")
@patch("app.services.rag_service.search_vectors")
@patch("app.services.rag_service.get_llm_client")
async def test_multiturn_rag_answer(mock_get_llm, mock_search, mock_get_embeddings, mock_detect):
    mock_detect.return_value = "retrieval"
    
    # Mock embedding query
    mock_client = MagicMock()
    async def mock_aembed_query(text):
        return [0.1] * 768
    mock_client.aembed_query = mock_aembed_query
    mock_get_embeddings.return_value = mock_client
    
    mock_search.return_value = [
        {
            "score": 0.90,
            "doc_id": "doc-1",
            "source": "curfew.pdf",
            "page": 1,
            "text_content": "The curfew time is 10:00 PM."
        }
    ]
    
    mock_llm = MagicMock()
    
    call_count = 0
    async def mock_astream(prompt, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            chunk = MagicMock()
            chunk.content = "According to curfew.pdf, the curfew time is 10:00 PM."
            yield chunk
        else:
            chunk = MagicMock()
            chunk.content = "Yes, the curfew is 10:00 PM for girls as well."
            yield chunk
            
    mock_llm.astream = mock_astream
    mock_get_llm.return_value = mock_llm
    
    session_id = "test-session-multi"
    # Ensure cache starts fresh
    if session_id in session_cache.cache:
        del session_cache.cache[session_id]
        
    # First turn: "What is the curfew time?"
    res1 = await run_stream("What is the curfew time?", session_id=session_id)
    assert "10:00 PM" in res1.answer
    
    # Verify session history updated
    history, summary = session_cache.get(session_id)
    assert len(history) == 1
    assert history[0]["user"] == "What is the curfew time?"
    
    # Mock LLM for the second turn (both reformulation call and final generation call)
    mock_llm_reformulate = MagicMock()
    mock_llm_reformulate.content = "Is the curfew time the same for girls' hostels?"
    mock_llm.invoke.return_value = mock_llm_reformulate
    
    # Second turn: "Is it the same for girls?"
    res2 = await run_stream("Is it the same for girls?", session_id=session_id)
    assert "girls as well" in res2.answer
    
    # Verify session history updated with both turns
    history2, summary2 = session_cache.get(session_id)
    assert len(history2) == 2
    assert history2[1]["user"] == "Is it the same for girls?"
    
    # Cleanup
    if session_id in session_cache.cache:
        del session_cache.cache[session_id]
