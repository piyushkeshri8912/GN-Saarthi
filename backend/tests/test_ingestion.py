from app.config import settings

def test_settings_loaded():
    """
    Verify that application configuration is correctly loaded.
    """
    assert settings.ALLOWED_DOMAIN == "iitgn.ac.in"
    assert settings.GCP_REGION == "us-central1"
    assert settings.QDRANT_COLLECTION_NAME == "college_docs"

def test_split_text_by_page():
    """
    Verify text chunking splits text using LlamaIndex SentenceSplitter.
    """
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.core import Document
    
    splitter = SentenceSplitter(chunk_size=512, chunk_overlap=64)
    doc = Document(text="This is page one text. " * 300)
    nodes = splitter.get_nodes_from_documents([doc])
    
    # Assertions
    assert len(nodes) >= 2
    assert "This is page one text" in nodes[0].text

from unittest.mock import MagicMock, patch
from app.services.ingestion_service import ingest_document, delete_document

@patch("app.services.ingestion_service.upload_to_gcs")
@patch("app.services.ingestion_service.extract_text_from_image")
@patch("app.services.rag_service.get_llama_index")
@patch("app.services.ingestion_service.db")
def test_ingest_image(mock_db, mock_get_index, mock_extract, mock_upload):
    """
    Verify that ingest_document routes image files correctly to extract_text_from_image,
    calls LlamaIndex index.insert, and saves metadata to Firestore.
    """
    mock_upload.return_value = "gs://test-bucket/documents/uuid_test_image.png"
    mock_extract.return_value = [(1, "Extracted text from image")]
    
    mock_index = MagicMock()
    mock_get_index.return_value = mock_index
    
    doc_id = ingest_document("test_image.png", b"fake_png_bytes")
    
    assert doc_id is not None
    mock_upload.assert_called_once_with("test_image.png", b"fake_png_bytes")
    mock_extract.assert_called_once_with(b"fake_png_bytes", "test_image.png")
    mock_index.insert.assert_called_once()
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
from app.pipelines.vector_store import verify_startup_vector_store

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

@patch("app.pipelines.vector_store.get_qdrant_vector_store")
def test_verify_startup_vector_store(mock_get_store):
    """
    Verify that verify_startup_vector_store successfully triggers vector store initialization.
    """
    verify_startup_vector_store()
    mock_get_store.assert_called_once()
