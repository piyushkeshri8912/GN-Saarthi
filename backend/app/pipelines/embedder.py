from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from app.config import settings
from typing import List
from fastembed import SparseTextEmbedding
from qdrant_client import models
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
os.environ["GOOGLE_CLOUD_PROJECT"] = settings.GCP_PROJECT_ID
os.environ["GOOGLE_CLOUD_LOCATION"] = settings.VERTEX_AI_LOCATION


class PatchedGoogleGenAIEmbedding(GoogleGenAIEmbedding):
    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        with ThreadPoolExecutor(max_workers=min(8, len(texts))) as executor:
            return list(executor.map(self._get_text_embedding, texts))

    async def _aget_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        tasks = [self._aget_text_embedding(text) for text in texts]
        return await asyncio.gather(*tasks)


embedding_client = PatchedGoogleGenAIEmbedding(
    model_name=settings.EMBEDDING_MODEL,
)

sparse_embedder = SparseTextEmbedding(
    model_name=settings.BM42_MODEL,
)

def generate_dense_embeddings(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    return embedding_client.get_text_embedding_batch(texts)

def generate_dense_query_embedding(text: str) -> List[float]:
    return embedding_client.get_query_embedding(text)

def generate_sparse_query_embedding(text: str) -> models.SparseVector | None:
    sparse_embedding = next(sparse_embedder.query_embed(text), None)
    if sparse_embedding is None:
        return None
    return sparse_embedding.as_object()