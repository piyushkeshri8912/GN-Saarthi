from __future__ import annotations

import json
import logging
from typing import List, Optional

from fastembed import SparseTextEmbedding
from llama_index.core.schema import NodeWithScore, TextNode
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.models import ScoredPoint

from app.config import settings
from app.pipelines.embedder import generate_query_embedding

logger = logging.getLogger(__name__)

DEFAULT_BM42_MODEL = "Qdrant/bm42-all-minilm-l6-v2-attentions"


class SmartRetriever:
    """Hybrid retriever using Qdrant native FusionQuery (dense + BM42 sparse, server-side RRF)."""

    def __init__(self, base_retriever=None):
        self.client = AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)

        self.collection_name = settings.QDRANT_COLLECTION_NAME
        self.dense_vector_name = getattr(settings, "QDRANT_DENSE_VECTOR_NAME", None)
        self.sparse_vector_name = getattr(settings, "QDRANT_SPARSE_VECTOR_NAME", "bm42")

        self.retrieval_top_k = getattr(settings, "RETRIEVAL_TOP_K", 10)
        self.sparse_top_k = getattr(settings, "HYBRID_SPARSE_TOP_K", 20)
        self.fusion_top_k = getattr(settings, "HYBRID_FUSION_TOP_K", 10)

        self.hybrid_enabled = bool(getattr(settings, "HYBRID_SEARCH_ENABLED", True))
        self.sparse_embedder: Optional[SparseTextEmbedding] = None

        if self.hybrid_enabled:
            try:
                model_name = getattr(settings, "BM42_MODEL_NAME", DEFAULT_BM42_MODEL)
                self.sparse_embedder = SparseTextEmbedding(model_name=model_name)
            except Exception as exc:
                logger.warning("BM42 embedder init failed; falling back to dense-only search: %s", exc)
                self.hybrid_enabled = False

    async def retrieve(self, query: str) -> List[NodeWithScore]:
        try:
            dense_vector = generate_query_embedding(query)
            if not dense_vector:
                logger.warning("Empty query embedding")
                return []

            query_kwargs = self._build_query(query, dense_vector)

            response = await self.client.query_points(
                collection_name=self.collection_name,
                limit=self.fusion_top_k,
                with_payload=True,
                with_vectors=False,
                **query_kwargs,
            )
            return [n for p in response.points if (n := self._point_to_node(p)) is not None]

        except Exception as exc:
            logger.error("Retrieval failed: %s", exc, exc_info=True)
            return []

    def _build_query(self, query: str, dense_vector) -> dict:
        """Return kwargs for query_points: hybrid fusion if possible, else dense-only."""
        if self.hybrid_enabled and self.sparse_embedder is not None:
            sparse_embeddings = list(self.sparse_embedder.query_embed(query))
            if sparse_embeddings:
                return {
                    "prefetch": [
                        self._dense_prefetch(dense_vector),
                        self._sparse_prefetch(sparse_embeddings[0].as_object()),
                    ],
                    "query": models.FusionQuery(fusion=models.Fusion.RRF),
                }
            logger.warning("Empty sparse embedding; using dense-only search")

        kwargs = {"query": dense_vector}
        if self.dense_vector_name:
            kwargs["using"] = self.dense_vector_name
        return kwargs

    def _dense_prefetch(self, dense_vector):
        kwargs = {"query": dense_vector, "limit": self.retrieval_top_k}
        if self.dense_vector_name:
            kwargs["using"] = self.dense_vector_name
        return models.Prefetch(**kwargs)

    def _sparse_prefetch(self, sparse_query):
        kwargs = {"query": sparse_query, "limit": self.sparse_top_k}
        if self.sparse_vector_name:
            kwargs["using"] = self.sparse_vector_name
        return models.Prefetch(**kwargs)

    async def close(self):
        try:
            await self.client.close()
        except Exception as exc:
            logger.warning("Error closing Qdrant client: %s", exc)

    @staticmethod
    def _point_to_node(point: ScoredPoint) -> NodeWithScore | None:
        payload = point.payload or {}
        try:
            node_content = payload.get("_node_content")
            if isinstance(node_content, str) and node_content:
                node_data = json.loads(node_content)
                text = node_data.get("text", "") or ""
                metadata = node_data.get("metadata", {}) or {}
            else:
                text = payload.get("text", "") or ""
                metadata = {
                    k: payload.get(k)
                    for k in ("doc_id", "doc_id_key", "source", "source_type", "page", "page_start", "page_end")
                }

            if not text:
                return None
            return NodeWithScore(node=TextNode(text=text, metadata=metadata), score=point.score or 0.0)

        except Exception as exc:
            logger.error("Point conversion error: %s", exc)
            return None