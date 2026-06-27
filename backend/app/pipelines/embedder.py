from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from app.config import settings
from typing import List
import os

# Set Vertex AI env configurations required by google-genai SDK
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
os.environ["GOOGLE_CLOUD_PROJECT"] = settings.GCP_PROJECT_ID
os.environ["GOOGLE_CLOUD_LOCATION"] = settings.VERTEX_AI_LOCATION

_embeddings_client = None

def get_embeddings_client() -> GoogleGenAIEmbedding:
    """
    Returns a singleton instance of the GoogleGenAIEmbedding client.
    """
    global _embeddings_client
    if _embeddings_client is None:
        _embeddings_client = GoogleGenAIEmbedding(model_name="text-embedding-004")
    return _embeddings_client

def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Generates embeddings for a list of texts using GoogleGenAIEmbedding.
    """
    if not texts:
        return []
    client = get_embeddings_client()
    return client.get_text_embedding_batch(texts)

def generate_query_embedding(text: str) -> List[float]:
    """
    Generates the embedding representation for a single search query.
    """
    client = get_embeddings_client()
    return client.get_query_embedding(text)

_embedding_dimension = None

def get_embedding_dimension() -> int:
    """
    Dynamically fetches and caches the embedding dimension of the configured model.
    Falls back to 768 on error.
    """
    global _embedding_dimension
    if _embedding_dimension is None:
        try:
            client = get_embeddings_client()
            if hasattr(client, "embed_query"):
                _embedding_dimension = len(client.embed_query("t"))
            else:
                _embedding_dimension = len(client.get_query_embedding("t"))
        except Exception:
            return 768
    return _embedding_dimension
