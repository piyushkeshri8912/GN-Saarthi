from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
import logging
from app.dependencies import verify_token, get_query_service
from app.schemas.schemas import User, ChatRequest
from app.services.query_service import QueryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: User = Depends(verify_token),
    query_service: QueryService = Depends(get_query_service)
):
    """
    Streaming endpoint for querying the RAG chatbot. Requires a valid user token.
    Answers the user query chunk-by-chunk using Server-Sent Events (SSE).
    """
    if not request.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message query cannot be empty."
        )
        
    try:
        logger.info(f"User {current_user.email} sent streaming chat query: '{request.message[:60]}...'")
        return StreamingResponse(
            query_service.query_stream(request.message, session_id=request.session_id),
            media_type="text/event-stream"
        )
    except Exception as e:
        logger.error(f"Error in streaming chat endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred during generation: {str(e)}"
        )
