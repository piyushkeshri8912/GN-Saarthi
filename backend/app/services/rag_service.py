import os
import logging
from app.config import settings

logger = logging.getLogger(__name__)

_llm_client = None
_index = None

def get_llm_client():
    """
    Singleton factory for LlamaIndex GoogleGenAI LLM client configured with Vertex AI.
    """
    global _llm_client
    if _llm_client is None:
        from llama_index.llms.google_genai import GoogleGenAI
        
        # Ensure Vertex AI environment variables are set for the SDK
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
        os.environ["GOOGLE_CLOUD_PROJECT"] = settings.GCP_PROJECT_ID
        os.environ["GOOGLE_CLOUD_LOCATION"] = settings.VERTEX_AI_LOCATION
        
        _llm_client = GoogleGenAI(
            model=settings.LLM_MODEL, 
            temperature=settings.LLM_TEMPERATURE,
            vertexai_config={
                "project": settings.GCP_PROJECT_ID,
                "location": settings.VERTEX_AI_LOCATION
            }
        )
    return _llm_client

def get_llama_index():

    global _index
    if _index is None:
        from llama_index.core import VectorStoreIndex, StorageContext, Settings
        from app.pipelines.vector_store import get_qdrant_vector_store
        from app.pipelines.embedder import get_embeddings_client
        
        # Configure global settings
        Settings.embed_model = get_embeddings_client()
        Settings.llm = get_llm_client()
        
        vector_store = get_qdrant_vector_store()
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        
        _index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            storage_context=storage_context
        )
    return _index
