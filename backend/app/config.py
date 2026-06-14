from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, Dict, Any
import json
import os

class Settings(BaseSettings):
    GCP_PROJECT_ID: str = "gn-saarthi"
    GCP_REGION: str = "us-central1"
    GCS_BUCKET_NAME: str
    QDRANT_URL: str
    QDRANT_API_KEY: str
    QDRANT_COLLECTION_NAME: str = "college_docs"
    FIREBASE_SERVICE_ACCOUNT_JSON: str
    VERTEX_AI_LOCATION: str = "us-central1"
    ALLOWED_DOMAIN: str = "iitgn.ac.in"
    TEMP_TEST_EMAIL: Optional[str] = ""
    FIRESTORE_DATABASE_ID: str = "(default)"
    ALLOWED_CORS_ORIGINS: Optional[str] = ""

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def firebase_service_account_dict(self) -> Dict[str, Any]:
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
