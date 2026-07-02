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
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    client = get_qdrant_client()
    client.delete(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        points_selector=Filter(
            should=[
                FieldCondition(key="doc_id_key", match=MatchValue(value=doc_id)),
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id))
            ]
        )
    )

def verify_startup_vector_store():
    """
    Verifies that the Qdrant connection works and vector store collection is ready.
    Ensures that payload indexes for doc_id and doc_id_key are created to allow deleting vectors.
    """
    logger.info("Verifying Qdrant startup connection...")
    get_qdrant_vector_store()
    
    client = get_qdrant_client()
    collection_name = settings.QDRANT_COLLECTION_NAME
    
    try:
        from qdrant_client.models import PayloadSchemaType
        client.create_payload_index(
            collection_name=collection_name,
            field_name="doc_id_key",
            field_schema=PayloadSchemaType.KEYWORD
        )
        logger.info("Ensured payload index on 'doc_id_key' exists.")
    except Exception as e:
        logger.warning(f"Could not create payload index on 'doc_id_key' (it may already exist): {e}")
        
    try:
        from qdrant_client.models import PayloadSchemaType
        client.create_payload_index(
            collection_name=collection_name,
            field_name="doc_id",
            field_schema=PayloadSchemaType.KEYWORD
        )
        logger.info("Ensured payload index on 'doc_id' exists.")
    except Exception as e:
        logger.warning(f"Could not create payload index on 'doc_id' (it may already exist): {e}")
