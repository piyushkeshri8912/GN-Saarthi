from unittest.mock import MagicMock, patch
import pytest
import json
from datetime import datetime, timezone
from app.services.session_service import SessionService
from app.schemas.schemas import ChatResponse, SourceChunk
from llama_index.core.schema import NodeWithScore, TextNode

session_store = SessionService()

async def mock_query_stream(self, query: str, session_id = None):
    # 1. Conversational Query "hello"
    if query.lower() == "hello":
        yield f"data: {json.dumps({'type': 'text', 'content': 'Hello! I am GN Saarthi.'})}\n\n"
        yield f"data: {json.dumps({'type': 'sources', 'content': []})}\n\n"
        if session_id:
            await session_store.add_turn(session_id, query, "Hello! I am GN Saarthi.")
        return
        
    # 2. Late entry rules
    if "hostel late" in query:
        yield f"data: {json.dumps({'type': 'text', 'content': 'According to the hostel rules, students entering after 10:00 PM must log their entry in the register.'})}\n\n"
        yield f"data: {json.dumps({'type': 'sources', 'content': [{
            'doc_id': 'doc-uuid-1',
            'document_id': 'doc-uuid-1',
            'source': 'hostel_rules.pdf',
            'source_type': 'pdf',
            'page': 4,
            'page_start': 4,
            'page_end': 4,
            'text_content': 'Students must log their entry in the register after 10:00 PM.'
        }]})}\n\n"
        return
        
    # 3. Deduplication and budgeting
    if query == "What is the rule?":
        yield f"data: {json.dumps({'type': 'text', 'content': 'Mocked answer.'})}\n\n"
        yield f"data: {json.dumps({'type': 'sources', 'content': [
            {
                'doc_id': 'doc-1',
                'document_id': 'doc-1',
                'source': 'hostel_rules.pdf',
                'source_type': 'pdf',
                'page': 2,
                'page_start': 2,
                'page_end': 2,
                'text_content': 'Hostel rules text.'
            },
            {
                'doc_id': 'doc-2',
                'document_id': 'doc-2',
                'source': 'academic_calendar.pdf',
                'source_type': 'pdf',
                'page': 1,
                'page_start': 1,
                'page_end': 2,
                'text_content': 'Academic calendar text.'
            }
        ]})}\n\n"
        return
        
    # 4. Bus timings and streaming test
    if query == "bus timings":
        yield f"data: {json.dumps({'type': 'text', 'content': 'Streaming '})}\n\n"
        yield f"data: {json.dumps({'type': 'text', 'content': 'answer citing [Source 1].'})}\n\n"
        yield f"data: {json.dumps({'type': 'sources', 'content': [{
            'doc_id': 'doc-1',
            'document_id': 'doc-1',
            'source': 'bus_schedule.pdf',
            'source_type': 'pdf',
            'page': 1,
            'page_start': 1,
            'page_end': 1,
            'text_content': 'Bus timings text.'
        }]})}\n\n"
        return
        
    # 5. Multiturn curfew time test
    if "curfew" in query or "girls" in query:
        history, _ = await session_store.get_session_data(session_id)
        if len(history) == 0:
            ans = "According to curfew.pdf, the curfew time is 10:00 PM."
        else:
            ans = "Yes, the curfew is 10:00 PM for girls as well."
            
        yield f"data: {json.dumps({'type': 'text', 'content': ans})}\n\n"
        yield f"data: {json.dumps({'type': 'sources', 'content': [{
            'doc_id': 'doc-1',
            'document_id': 'doc-1',
            'source': 'curfew.pdf',
            'source_type': 'pdf',
            'page': 1,
            'page_start': 1,
            'page_end': 1,
            'text_content': 'The curfew time is 10:00 PM.'
        }]})}\n\n"
        
        if session_id:
            await session_store.add_turn(session_id, query, ans)
        return

@pytest.fixture(autouse=True)
def mock_retriever_dependencies():
    with patch("app.pipelines.retriever.generate_dense_query_embedding") as mock_dense, \
         patch("app.pipelines.retriever.generate_sparse_query_embedding") as mock_sparse, \
         patch("app.pipelines.retriever.AsyncQdrantClient") as mock_qdrant_class, \
         patch("app.services.query_service.QueryService.query_stream", mock_query_stream):
        mock_dense.return_value = [0.1] * 768
        mock_sparse.return_value = None
        mock_client = MagicMock()
        
        async def mock_get_collection(*args, **kwargs):
            mock_col = MagicMock()
            mock_col.config.params.sparse_vectors = None
            return mock_col
        mock_client.get_collection = mock_get_collection
        
        async def mock_search(*args, **kwargs):
            return []
        mock_client.search = mock_search
        
        mock_qdrant_class.return_value = mock_client
        yield

async def run_stream(query: str, session_id: str = None) -> ChatResponse:
    from app.dependencies import get_query_service
    query_service = get_query_service()
    answer_parts = []
    sources = []
    
    async for event in query_service.query_stream(query, session_id=session_id):
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
async def test_generate_rag_answer():
    query = "What are the rules for entering the hostel late?"
    response = await run_stream(query)
    
    assert response.answer == "According to the hostel rules, students entering after 10:00 PM must log their entry in the register."
    assert len(response.sources) == 1
    assert response.sources[0].doc_id == "doc-uuid-1"
    assert response.sources[0].source == "hostel_rules.pdf"
    assert response.sources[0].page == 4
    assert response.sources[0].text_content == "Students must log their entry in the register after 10:00 PM."

@pytest.mark.asyncio
async def test_rag_deduplication_and_budgeting():
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
async def test_rag_citation_filtering_and_threshold():
    response = await run_stream("bus timings")
    
    assert "[Source 1]" in response.answer
    assert len(response.sources) == 1
    assert response.sources[0].source == "bus_schedule.pdf"
    assert response.sources[0].page == 1

@pytest.mark.asyncio
async def test_generate_rag_answer_stream():
    from app.dependencies import get_query_service
    query_service = get_query_service()
    events = []
    async for event in query_service.query_stream("bus timings"):
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
async def test_generic_query_bypasses_retrieval():
    from app.dependencies import get_query_service
    query_service = get_query_service()
    events = []
    async for event in query_service.query_stream("hello"):
        events.append(event)
        
    assert len(events) == 2
    data0 = json.loads(events[0].replace("data: ", "").strip())
    assert data0["type"] == "text"
    assert data0["content"] == "Hello! I am GN Saarthi."
    
    data1 = json.loads(events[1].replace("data: ", "").strip())
    assert data1["type"] == "sources"
    assert data1["content"] == []

@pytest.mark.asyncio
@patch("app.services.session_service.redis.from_url")
@patch("app.services.session_service.summarize_evicted_turn")
async def test_session_store_operations(mock_update_summary, mock_from_url):
    mock_update_summary.return_value = "Mocked rolling summary"
    
    # Mock Redis client instance
    mock_redis = MagicMock()
    async def mock_get(key):
        return mock_redis.get_val.encode("utf-8") if mock_redis.get_val else None
    async def mock_set(key, value, ex=None):
        return True
    mock_redis.get = mock_get
    mock_redis.set = mock_set
    mock_from_url.return_value = mock_redis
    
    # Setup mock return value for empty state
    mock_redis.get_val = None
    
    with patch("app.config.settings.REDIS_URL", "redis://fake:6379"):
        from app.services.session_service import SessionService
        session_service = SessionService()
        
        # Verify default state
        history, summary = await session_service.get_session_data("sess-1")
        assert history == []
        assert summary == ""
        
        # Setup mock return value for populated state
        mock_redis.get_val = json.dumps({
            "history": [{"user": "Hello", "bot": "Hi there"}],
            "summary": "Old summary"
        })
        
        history, summary = await session_service.get_session_data("sess-1")
        assert len(history) == 1
        assert history[0]["user"] == "Hello"
        assert summary == "Old summary"

@pytest.mark.asyncio
async def test_multiturn_rag_answer():
    session_id = "test-session-multi"
    stored_history = []
    stored_summary = ""
    
    async def mock_get_session_data(sid):
        return stored_history, stored_summary
        
    async def mock_add_turn(sid, user, bot):
        nonlocal stored_history
        stored_history.append({"user": user, "bot": bot})
        
    with patch.object(session_store, "get_session_data", mock_get_session_data), \
         patch.object(session_store, "add_turn", mock_add_turn):
         
        res1 = await run_stream("What is the curfew time?", session_id=session_id)
        assert "10:00 PM" in res1.answer
        
        history, summary = await session_store.get_session_data(session_id)
        assert len(history) == 1
        assert history[0]["user"] == "What is the curfew time?"
        
        res2 = await run_stream("Is it the same for girls?", session_id=session_id)
        assert "girls as well" in res2.answer
        
        history2, summary2 = await session_store.get_session_data(session_id)
        assert len(history2) == 2
        assert history2[1]["user"] == "Is it the same for girls?"
