from langchain_google_vertexai import VertexAIEmbeddings
from google.oauth2 import service_account
import vertexai
from app.config import settings
from typing import List

_embeddings_client = None

def get_embeddings_client():
    """
    Returns a singleton instance of the VertexAIEmbeddings client.
    Initializes Vertex AI SDK with the appropriate credentials and project configuration.
    """
    global _embeddings_client
    if _embeddings_client is None:
        sa_info = settings.firebase_service_account_dict
        gcp_cred = service_account.Credentials.from_service_account_info(
            sa_info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        
        # Initialize global vertexai settings
        vertexai.init(
            project=settings.GCP_PROJECT_ID,
            location=settings.VERTEX_AI_LOCATION,
            credentials=gcp_cred
        )
        
        _embeddings_client = VertexAIEmbeddings(
            model_name="text-embedding-004",
            project=settings.GCP_PROJECT_ID,
            location=settings.VERTEX_AI_LOCATION,
            credentials=gcp_cred
        )
    return _embeddings_client

def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Generates embeddings for a list of texts using Vertex AI text-embedding-004.
    Processes the inputs in batches of 50 to respect API limit guidelines.
    """
    if not texts:
        return []
        
    client = get_embeddings_client()
    
    embeddings = []
    batch_size = 50
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i : i + batch_size]
        batch_embeddings = client.embed_documents(batch_texts)
        embeddings.extend(batch_embeddings)
        
    return embeddings

def generate_query_embedding(text: str) -> List[float]:
    """
    Generates the embedding representation for a single search query.
    """
    client = get_embeddings_client()
    return client.embed_query(text)

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
            _embedding_dimension = len(client.embed_query("t"))
        except Exception:
            return 768
    return _embedding_dimension
