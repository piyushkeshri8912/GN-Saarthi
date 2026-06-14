from app.config import settings
from app.pipelines.chunker import split_text_by_page

def test_settings_loaded():
    """
    Verify that application configuration is correctly loaded.
    """
    assert settings.ALLOWED_DOMAIN == "iitgn.ac.in"
    assert settings.GCP_REGION == "us-central1"
    assert settings.QDRANT_COLLECTION_NAME == "college_docs"

def test_split_text_by_page():
    """
    Verify text chunking splits text while preserving page number metadata.
    """
    pages_data = [
        {"page_num": 1, "text": "This is a short notice on page one."},
        {"page_num": 2, "text": "This is a longer notice on page two. " * 250}
    ]
    
    chunks = split_text_by_page(pages_data)
    
    # Assertions
    assert len(chunks) >= 2
    assert chunks[0]["page"] == 1
    assert "page one" in chunks[0]["text"]
    assert chunks[-1]["page"] == 2
    assert "page two" in chunks[-1]["text"]

from unittest.mock import MagicMock, patch
from app.services.ingestion_service import ingest_document, delete_document

@patch("app.services.ingestion_service.upload_to_gcs")
@patch("app.services.ingestion_service.extract_text_from_image")
@patch("app.services.ingestion_service.chunk_document_pages")
@patch("app.services.ingestion_service.generate_embeddings")
@patch("app.services.ingestion_service.upsert_chunks")
@patch("app.services.ingestion_service.db")
def test_ingest_image(mock_db, mock_upsert, mock_embed, mock_chunk, mock_extract, mock_upload):
    """
    Verify that ingest_document routes image files correctly to extract_text_from_image,
    calls chunker, embedder, and vector store, and saves metadata to Firestore.
    """
    mock_upload.return_value = "gs://test-bucket/documents/uuid_test_image.png"
    mock_extract.return_value = [(1, "Extracted text from image")]
    mock_chunk.return_value = [{"text": "Extracted text from image", "page": 1, "page_start": 1, "page_end": 1}]
    mock_embed.return_value = [[0.1] * 768]
    
    doc_id = ingest_document("test_image.png", b"fake_png_bytes")
    
    assert doc_id is not None
    mock_upload.assert_called_once_with("test_image.png", b"fake_png_bytes")
    mock_extract.assert_called_once_with(b"fake_png_bytes", "test_image.png")
    mock_chunk.assert_called_once_with([(1, "Extracted text from image")], doc_id=doc_id)
    mock_upsert.assert_called_once()
    mock_db.collection.assert_called_once_with("documents")

@patch("app.services.ingestion_service.db")
@patch("app.services.ingestion_service.delete_from_gcs")
@patch("app.services.ingestion_service.delete_by_doc_id")
def test_delete_document_idempotent(mock_delete_qdrant, mock_delete_gcs, mock_db):
    """
    Verify that delete_document runs idempotently and cleans up GCS, Qdrant,
    and Firestore resources even if the Firestore document doesn't exist.
    """
    # Case 1: Document exists
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"gcs_uri": "gs://test-bucket/documents/test.pdf"}
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
    
    delete_document("existing-doc-id")
    
    mock_delete_gcs.assert_called_once_with("gs://test-bucket/documents/test.pdf")
    mock_delete_qdrant.assert_called_once_with("existing-doc-id")
    mock_db.collection.return_value.document.return_value.delete.assert_called_once()
    
    # Reset mocks
    mock_delete_gcs.reset_mock()
    mock_delete_qdrant.reset_mock()
    mock_db.collection.return_value.document.return_value.delete.reset_mock()
    
    # Case 2: Document does not exist in Firestore
    mock_doc.exists = False
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
    
    delete_document("missing-doc-id")
    
    mock_delete_gcs.assert_not_called()
    mock_delete_qdrant.assert_called_once_with("missing-doc-id")
    mock_db.collection.return_value.document.return_value.delete.assert_called_once()

import pytest
from app.services.ocr_service import BaseOCRProvider, OCRService
from app.pipelines.vector_store import upsert_chunks, verify_startup_vector_store

class DummyOCRProvider(BaseOCRProvider):
    def get_provider_name(self) -> str:
        return "DummyProvider"

    def extract_text(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
        if image_bytes == b"fail":
            raise ValueError("Extraction error")
        return "dummy text extraction"

def test_ocr_service_provider_abstraction():
    """
    Verify that OCRService isolates providers behind BaseOCRProvider interface,
    correctly tracks duration/logging, and throws RuntimeErrors on provider failures.
    """
    # Success Case
    service = OCRService(provider=DummyOCRProvider())
    text = service.perform_ocr(b"fake_image_bytes", "test.jpg", "image/jpeg")
    assert text == "dummy text extraction"

    # Failure Case
    with pytest.raises(RuntimeError) as exc_info:
        service.perform_ocr(b"fail", "test_fail.jpg", "image/jpeg")
    assert "OCR processing failed using provider DummyProvider" in str(exc_info.value)

@patch("app.pipelines.embedder.get_embedding_dimension")
@patch("app.pipelines.vector_store.ensure_collection")
@patch("app.pipelines.vector_store.get_qdrant_client")
def test_upsert_chunks_strict_validation(mock_client, mock_ensure, mock_dim):
    """
    Verify that upsert_chunks raises ValueError under strict validation for:
      - count mismatch between chunks and embeddings
      - empty chunks or empty embeddings
      - dimension mismatches in embeddings
    """
    mock_dim.return_value = 768
    
    # 1. Count mismatch
    chunks = [{"text": "Hello", "page": 1, "page_start": 1, "page_end": 1}]
    embeddings = []
    with pytest.raises(ValueError) as exc:
        upsert_chunks("doc-1", "doc.pdf", chunks, embeddings)
    assert "cannot be empty" in str(exc.value)

    embeddings = [[0.1]*768, [0.2]*768]
    with pytest.raises(ValueError) as exc:
        upsert_chunks("doc-1", "doc.pdf", chunks, embeddings)
    assert "Mismatched chunk and embedding counts" in str(exc.value)

    # 2. Empty inputs
    with pytest.raises(ValueError) as exc:
        upsert_chunks("doc-1", "doc.pdf", [], [])
    assert "cannot be empty" in str(exc.value)

    # 3. Dimension mismatch
    chunks = [{"text": "Hello", "page": 1, "page_start": 1, "page_end": 1}]
    embeddings = [[0.1] * 512] # expected 768, got 512
    with pytest.raises(ValueError) as exc:
        upsert_chunks("doc-1", "doc.pdf", chunks, embeddings)
    assert "Embedding dimension mismatch" in str(exc.value)

@patch("app.pipelines.vector_store.ensure_collection")
@patch("app.pipelines.embedder.get_embeddings_client")
def test_verify_startup_vector_store(mock_embed_client, mock_ensure):
    """
    Verify that verify_startup_vector_store successfully invokes embedding client
    to get dimension and validates collection creation.
    """
    mock_client = MagicMock()
    mock_client.embed_query.return_value = [0.1] * 1536
    mock_embed_client.return_value = mock_client
    
    verify_startup_vector_store()
    mock_ensure.assert_called_once_with(1536)
