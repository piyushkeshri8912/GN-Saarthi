import logging
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, PayloadSchemaType
from llama_index.vector_stores.qdrant import QdrantVectorStore
from app.config import settings

logger = logging.getLogger(__name__)


qdrant_client = None
qdrant_vector_store = None

def get_qdrant_client() -> QdrantClient:
    global qdrant_client
    if qdrant_client is None:
        qdrant_client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY
        )
    return qdrant_client    


def get_qdrant_vector_store() -> QdrantVectorStore:
    global qdrant_vector_store
    if qdrant_vector_store is None:
        client = get_qdrant_client()
        qdrant_vector_store = QdrantVectorStore(
            client=client,
            collection_name=settings.QDRANT_COLLECTION_NAME,
            embedding_dim=settings.EMBEDDING_DIMENSION,
            enable_hybrid=True,
            fastembed_sparse_model=settings.BM42_MODEL,
            sparse_vector_name=settings.QDRANT_SPARSE_VECTOR_NAME,
            text_key="text",
            metadata_key="metadata",
            payload_key="payload"
        )
    return qdrant_vector_store

def delete_from_qdrant(doc_id: str):
    client = get_qdrant_client()
    client.delete(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        points_selector=Filter(
            must=[
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id))
            ]
        )
    )

# def create_payload_index():
#     try:
#         get_qdrant_vector_store()
#         client = get_qdrant_client()
#         client.create_payload_index(
#             collection_name=settings.QDRANT_COLLECTION_NAME,
#             field_name="doc_id",
#             field_schema=PayloadSchemaType.KEYWORD
#         )
#         logger.debug("Qdrant vector store and payload index created successfully.")
#     except Exception as e:
#         logger.warning(f"Failed to create Qdrant vector store index: {e}")
