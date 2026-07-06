import json
import logging
from typing import List
from llama_index.core.schema import NodeWithScore, TextNode
from qdrant_client import AsyncQdrantClient, models

from app.config import settings
from app.pipelines.embedder import generate_dense_query_embedding, generate_sparse_query_embedding

logger = logging.getLogger(__name__)


class SmartRetriever:
    """Hybrid retriever using Qdrant native FusionQuery (dense + BM42 sparse, server-side RRF)."""

    def __init__(self):
        self.client = AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)

        self.collection_name = settings.QDRANT_COLLECTION_NAME
        self.dense_vector_name = getattr(settings, "QDRANT_DENSE_VECTOR_NAME")
        self.sparse_vector_name = getattr(settings, "QDRANT_SPARSE_VECTOR_NAME")

        self.sparse_top_k = getattr(settings, "HYBRID_SPARSE_TOP_K")
        self.dense_top_k = getattr(settings, "HYBRID_DENSE_TOP_K")
        self.fusion_top_k = getattr(settings, "HYBRID_FUSION_TOP_K")

    async def retrieve(self, query: str) -> List[NodeWithScore]:
        try:
            dense_vector = generate_dense_query_embedding(query)
            if not dense_vector:
                logger.warning("Empty query embedding")
                return []

            sparse_vector = generate_sparse_query_embedding(query)
            if sparse_vector is None:
                logger.warning("Empty sparse embedding")
                return []

            response = await self.client.query_points(
                collection_name=self.collection_name,
                limit=self.fusion_top_k,
                with_payload=True,
                with_vectors=False,
                prefetch=[
                    models.Prefetch(
                        using=self.dense_vector_name,
                        query=dense_vector,
                        limit=self.dense_top_k,
                    ),
                    models.Prefetch(
                        using=self.sparse_vector_name,
                        query=sparse_vector,
                        limit=self.sparse_top_k,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
            )

            nodes = []
            for point in response.points:
                node = point_to_node(point)
                if node is not None:
                    nodes.append(node)

            return nodes

        except Exception as exc:
            logger.error("Retrieval failed: %s", exc, exc_info=True)
            return []

def point_to_node(point: models.ScoredPoint) -> NodeWithScore | None:
    payload = point.payload or {}
    try:
        node_content = payload.get("_node_content")
        if not node_content:
            return None
        node_data = json.loads(node_content)
        text = node_data.get("text", "") or ""
        metadata = {
            k: payload.get(k) for k in ("doc_id", "source", "source_type", "page", "page_start", "page_end")
        }

        if not text:
            return None
        return NodeWithScore(node=TextNode(text=text, metadata=metadata), score=point.score or 0.0)

    except Exception as exc:
        logger.error("Point conversion error: %s", exc, exc_info=True)
        return None