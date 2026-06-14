from qdrant_client import QdrantClient
from qdrant_client.http import models
import uuid
import logging
from app.config import settings
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

_qdrant_client = None

def get_qdrant_client() -> QdrantClient:
    """
    Singleton factory for Qdrant client.
    """
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY
        )
    return _qdrant_client

def ensure_collection(vector_size: int = None):
    """
    Ensures that the target collection exists in Qdrant with correct configuration.
    If collection size mismatches target embedding size, deletes and recreates collection.
    """
    if vector_size is None:
        from app.pipelines.embedder import get_embedding_dimension
        vector_size = get_embedding_dimension()
        
    client = get_qdrant_client()
    collection_name = settings.QDRANT_COLLECTION_NAME
    
    recreate = False
    try:
        collection_info = client.get_collection(collection_name)
        vectors_config = collection_info.config.params.vectors
        
        current_size = None
        if hasattr(vectors_config, "size"):
            current_size = vectors_config.size
        elif isinstance(vectors_config, dict):
            current_size = vectors_config.get("size")
        else:
            try:
                current_size = getattr(vectors_config, "size", None)
            except Exception:
                pass
                
        if current_size is not None and current_size != vector_size:
            logger.warning(
                f"Collection '{collection_name}' has vector size {current_size}, "
                f"but target size is {vector_size}. Deleting and recreating."
            )
            recreate = True
    except Exception:
        # Collection does not exist
        recreate = True
        
    if recreate:
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass
            
        try:
            logger.info(f"Creating collection '{collection_name}' with size {vector_size}.")
            client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE
                )
            )
            logger.info(f"Collection '{collection_name}' successfully created.")
        except Exception as e:
            logger.error(f"Failed to create Qdrant collection '{collection_name}': {e}")
            raise

    # Always ensure the payload index exists for doc_id to avoid filter deletion errors
    try:
        client.create_payload_index(
            collection_name=collection_name,
            field_name="doc_id",
            field_schema=models.PayloadSchemaType.KEYWORD
        )
        logger.info(f"Payload index on 'doc_id' successfully ensured.")
    except Exception as e:
        logger.warning(f"Failed to ensure payload index on 'doc_id': {e}")

def upsert_chunks(doc_id: str, source: str, chunks: List[Dict[str, Any]], embeddings: List[List[float]]):
    """
    Upserts document chunks and their corresponding embeddings into Qdrant.
    Raises errors if chunk and embedding counts, emptiness checks, or vector dimensions do not match.
    """
    if not chunks or not embeddings:
        raise ValueError(
            f"Ingestion Error: Chunks and embeddings cannot be empty. "
            f"Chunks empty: {not chunks}, Embeddings empty: {not embeddings} for document '{doc_id}'."
        )

    if len(chunks) != len(embeddings):
        raise ValueError(
            f"Ingestion Error: Mismatched chunk and embedding counts for document '{doc_id}'. "
            f"Chunks: {len(chunks)}, Embeddings: {len(embeddings)}."
        )
        
    from app.pipelines.embedder import get_embedding_dimension
    target_dim = get_embedding_dimension()
    
    # Log details as requested
    logger.info(
        f"Upsert details - document_id: {doc_id}, chunk_count: {len(chunks)}, "
        f"embedding_count: {len(embeddings)}, embedding_dimension: {target_dim}"
    )
    
    # Validate embedding dimensionality
    for idx, vector in enumerate(embeddings):
        if not vector or len(vector) != target_dim:
            raise ValueError(
                f"Ingestion Error: Embedding dimension mismatch or empty vector at index {idx}. "
                f"Expected {target_dim}, but got {len(vector) if vector else 0}."
            )
            
    ensure_collection(vector_size=target_dim)
    client = get_qdrant_client()
    collection_name = settings.QDRANT_COLLECTION_NAME
    
    # Determine source type
    ext = source.lower().split(".")[-1]
    source_type = "pdf" if ext == "pdf" else "image"
    
    points = []
    for idx, (chunk, vector) in enumerate(zip(chunks, embeddings)):
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}_{idx}"))
        
        payload = {
            "doc_id": doc_id,
            "document_id": doc_id,
            "source": source,
            "source_type": source_type,
            "page": chunk.get("page", 1),
            "page_start": chunk.get("page_start", 1),
            "page_end": chunk.get("page_end", 1),
            "chunk_index": chunk.get("chunk_index", idx),
            "text_content": chunk.get("text", "")
        }
        
        points.append(models.PointStruct(
            id=point_id,
            vector=vector,
            payload=payload
        ))
        
    try:
        client.upsert(
            collection_name=collection_name,
            points=points
        )
        logger.info(f"Successfully upserted {len(points)} points to Qdrant collection '{collection_name}'.")
    except Exception as e:
        logger.error(f"Failed to upsert points to Qdrant collection '{collection_name}': {e}")
        raise

def search_vectors(query_vector: List[float], limit: int = 5) -> List[Dict[str, Any]]:
    """
    Searches Qdrant for vectors closest to the query_vector.
    Returns payloads containing source document, page ranges, and extended metadata.
    """
    from app.pipelines.embedder import get_embedding_dimension
    target_dim = get_embedding_dimension()
    
    if len(query_vector) != target_dim:
        logger.warning(f"Query vector dimension {len(query_vector)} mismatches target dimension {target_dim}. Re-padding or raising.")
        
    ensure_collection(vector_size=target_dim)
    client = get_qdrant_client()
    collection_name = settings.QDRANT_COLLECTION_NAME
    
    try:
        results = client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=limit
        )
        
        hits = []
        for point in results.points:
            hits.append({
                "score": point.score,
                "doc_id": point.payload.get("doc_id"),
                "document_id": point.payload.get("doc_id"),
                "source": point.payload.get("source"),
                "source_type": point.payload.get("source_type", "pdf"),
                "page": point.payload.get("page"),
                "page_start": point.payload.get("page_start", point.payload.get("page", 1)),
                "page_end": point.payload.get("page_end", point.payload.get("page", 1)),
                "chunk_index": point.payload.get("chunk_index"),
                "text_content": point.payload.get("text_content")
            })
        return hits
    except Exception as e:
        logger.error(f"Qdrant vector search failed: {e}")
        raise

def delete_by_doc_id(doc_id: str):
    """
    Deletes all vector points matching the specified doc_id.
    """
    ensure_collection()
    client = get_qdrant_client()
    collection_name = settings.QDRANT_COLLECTION_NAME
    
    try:
        logger.info(f"Deleting vectors with doc_id '{doc_id}' from Qdrant.")
        client.delete(
            collection_name=collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="doc_id",
                            match=models.MatchValue(value=doc_id)
                        )
                    ]
                )
            )
        )
        logger.info(f"Vectors for doc_id '{doc_id}' deleted successfully.")
    except Exception as e:
        logger.error(f"Failed to delete vectors from Qdrant for doc_id '{doc_id}': {e}")
        raise

def verify_startup_vector_store():
    """
    Startup validation: verifies that the model embedding dimension equals the Qdrant collection dimension.
    """
    from app.pipelines.embedder import get_embedding_dimension
    dim = get_embedding_dimension()
    logger.info(f"Startup validation: Verifying Qdrant vector store collection has dimension {dim}...")
    ensure_collection(dim)
