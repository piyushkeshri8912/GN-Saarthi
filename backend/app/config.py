from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, Dict, Any
import json
import os

class Settings(BaseSettings):
    GCP_PROJECT_ID: str 
    GCP_REGION: str 
    GCS_BUCKET_NAME: str
    QDRANT_URL: str
    QDRANT_API_KEY: str
    QDRANT_COLLECTION_NAME: str 
    FIREBASE_SERVICE_ACCOUNT_JSON: Optional[str] = None
    VERTEX_AI_LOCATION: str
    ALLOWED_DOMAIN: str 
    TEMP_TEST_EMAIL: Optional[str] = ""
    FIRESTORE_DATABASE_ID: str
    ALLOWED_CORS_ORIGINS: Optional[str] = ""

    # Retrieval tuning
    RETRIEVAL_TOP_K: int = 40
    RERANK_TOP_N: int = 15
    RELEVANCE_THRESHOLD: float = 0.50

    # Hybrid search (BM42 dense + sparse fusion)
    HYBRID_DENSE_TOP_K: int = 40
    HYBRID_SPARSE_TOP_K: int = 75
    HYBRID_FUSION_TOP_K: int = 15
    HYBRID_RRF_K: int = 60

    BM42_MODEL: str = "Qdrant/bm42-all-minilm-l6-v2-attentions"
    QDRANT_DENSE_VECTOR_NAME: Optional[str] = None
    QDRANT_SPARSE_VECTOR_NAME: str = "bm42"

    # Redis
    REDIS_URL: str

    # Session settings
    SESSION_TOKEN_LIMIT: int = 3000
    SESSION_TTL_SECONDS: int = 86400

    # LLM
    LLM_MODEL: str = "gemini-2.5-flash"
    LLM_TEMPERATURE: float = 0.2
    EMBEDDING_MODEL: str = "text-embedding-004"
    EMBEDDING_DIMENSION: int = 768

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


    @property
    def firebase_service_account_dict(self) -> Optional[Dict[str, Any]]:
        if not self.FIREBASE_SERVICE_ACCOUNT_JSON:
            return None
        try:
            # Strip quotes if they exist around the JSON string
            json_str = self.FIREBASE_SERVICE_ACCOUNT_JSON.strip()
            if (json_str.startswith("'") and json_str.endswith("'")) or (json_str.startswith('"') and json_str.endswith('"')):
                json_str = json_str[1:-1]
            return json.loads(json_str)
        except Exception as e:
            # Fallback in case raw parsing is needed
            raise ValueError(f"Failed to parse FIREBASE_SERVICE_ACCOUNT_JSON: {e}")

settings = Settings()

# Configure GOOGLE_APPLICATION_CREDENTIALS dynamically for Google GenAI / LlamaIndex
if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    try:
        sa_dict = settings.firebase_service_account_dict
        if sa_dict:
            import tempfile
            # Create a temp file that survives program runtime
            temp_file = tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".json")
            json.dump(sa_dict, temp_file)
            temp_file.close()
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_file.name
    except Exception as e:
        import sys
        print(f"Warning: Failed to dynamically configure GOOGLE_APPLICATION_CREDENTIALS: {e}", file=sys.stderr)
