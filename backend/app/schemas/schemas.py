from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from datetime import datetime

class User(BaseModel):
    uid: str
    email: str
    role: str  # "admin" or "student"

class SourceChunk(BaseModel):
    doc_id: str
    source: str
    page: int
    text_content: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    source_type: Optional[str] = None
    document_id: Optional[str] = None

class ChatRequest(BaseModel):
    message: str = Field(..., description="The user query for RAG chatbot")
    session_id: Optional[str] = Field(None, description="Optional session ID for multi-turn chat memory")

class ChatResponse(BaseModel):
    answer: str = Field(..., description="The answer from Gemini grounded in PDF context")
    sources: List[SourceChunk] = Field(default_factory=list, description="Source chunks cited in the answer")

class UploadResponse(BaseModel):
    success: bool
    doc_id: str
    filename: str
    message: str

class DocumentMeta(BaseModel):
    doc_id: str
    filename: str
    gcs_uri: str
    size_bytes: int
    uploaded_at: datetime

class NoticeResponse(BaseModel):
    id: str
    title: str
    body: str
    category: str
    source_email: str
    date: datetime
    created_at: datetime

class EventResponse(BaseModel):
    id: str
    title: str
    description: str
    date: datetime
    location: str
    category: str
    created_at: datetime


class QuickLinkCreate(BaseModel):
    service: str = Field(..., min_length=1, max_length=100, description="Service name")
    link: str = Field(..., min_length=1, description="URL or contact details")
    purpose: Optional[str] = Field("", description="Purpose or description of the link")


class QuickLinkResponse(BaseModel):
    id: str = Field(..., description="Unique ID of the quick link")
    service: str = Field(..., description="Service name")
    link: str = Field(..., description="URL or contact details")
    purpose: str = Field(..., description="Purpose or description of the link")
    created_at: datetime = Field(..., description="Datetime of creation")


