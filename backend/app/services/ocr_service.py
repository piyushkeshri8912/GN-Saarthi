import time
import logging
from abc import ABC, abstractmethod
from typing import List, Tuple
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from google.oauth2 import service_account
from app.config import settings

logger = logging.getLogger(__name__)

class BaseOCRProvider(ABC):
    @abstractmethod
    def extract_text(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
        """
        Extracts text from raw image bytes.
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        pass


class GeminiOCRProvider(BaseOCRProvider):
    def __init__(self):
        self._model = None

    def get_provider_name(self) -> str:
        return "Gemini"

    def _get_model(self) -> GenerativeModel:
        if self._model is None:
            try:
                sa_info = settings.firebase_service_account_dict
                gcp_cred = service_account.Credentials.from_service_account_info(
                    sa_info,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
                vertexai.init(
                    project=settings.GCP_PROJECT_ID,
                    location=settings.VERTEX_AI_LOCATION,
                    credentials=gcp_cred
                )
                self._model = GenerativeModel("gemini-2.5-flash")
            except Exception as e:
                logger.error(f"Failed to initialize GenerativeModel for OCR provider: {e}")
                raise
        return self._model

    def extract_text(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
        model = self._get_model()
        image_part = Part.from_data(data=image_bytes, mime_type=mime_type)
        prompt = (
            "Extract all text from this image exactly. Do not add any preamble, explanation, or commentary. "
            "If the image contains tables, timetables, schedules, side-by-side columns, or structured lists, "
            "format them as clean Markdown tables or structured lists to preserve the column alignment and layout."
        )
        response = model.generate_content([image_part, prompt])
        return response.text.strip() if response.text else ""


class OCRService:
    """
    OCR abstraction layer to separate ingestion logic from specific providers.
    """
    _default_provider = None

    def __init__(self, provider: BaseOCRProvider = None):
        if provider is None:
            if OCRService._default_provider is None:
                OCRService._default_provider = GeminiOCRProvider()
            provider = OCRService._default_provider
        self.provider = provider

    def perform_ocr(self, image_bytes: bytes, filename: str, mime_type: str = "image/jpeg") -> str:
        provider_name = self.provider.get_provider_name()
        logger.info(f"Initiating OCR via provider: {provider_name} for file: {filename}")
        
        start_time = time.time()
        try:
            text = self.provider.extract_text(image_bytes, mime_type=mime_type)
            duration = time.time() - start_time
            logger.info(f"OCR SUCCESS: Provider {provider_name} processed {filename} in {duration:.2f}s (extracted {len(text)} chars)")
            return text
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"OCR FAILURE: Provider {provider_name} failed for {filename} after {duration:.2f}s. Error: {e}")
            raise RuntimeError(f"OCR processing failed using provider {provider_name}: {e}")
