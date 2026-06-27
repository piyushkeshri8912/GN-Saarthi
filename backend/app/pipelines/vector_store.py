import logging
from qdrant_client import QdrantClient
from llama_index.vector_stores.qdrant import QdrantVectorStore
from app.config import settings

logger = logging.getLogger(__name__)
_qdrant_client = None
_vector_store = None

def get_qdrant_client() -> QdrantClient:
    """
    Singleton factory for the raw QdrantClient.
    """
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY
        )
    return _qdrant_client

def get_qdrant_vector_store() -> QdrantVectorStore:
    """
    Singleton factory for LlamaIndex QdrantVectorStore.
    """
    global _vector_store
    if _vector_store is None:
        from qdrant_client import AsyncQdrantClient
        aclient = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY
        )
        _vector_store = QdrantVectorStore(
            client=get_qdrant_client(),
            aclient=aclient,
            collection_name=settings.QDRANT_COLLECTION_NAME
        )
    return _vector_store

def delete_by_doc_id(doc_id: str):
    """
    Deletes all vector points associated with the specified doc_id.
    """
    logger.info(f"Deleting documents with doc_id '{doc_id}' from Qdrant.")
    get_qdrant_vector_store().delete(doc_id)

def verify_startup_vector_store():
    """
    Verifies that the Qdrant connection works and vector store collection is ready.
    """
    logger.info("Verifying Qdrant startup connection...")
    get_qdrant_vector_store()
