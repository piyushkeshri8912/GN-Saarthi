import uuid 
import re
import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Optional
from google.cloud import storage
from google.cloud.firestore_v1.base_query import FieldFilter
from app.config import settings
from app.dependencies import db
from app.pipelines.pdf_parser import extract_text_from_pdf, extract_text_from_image
from app.pipelines.vector_store import delete_from_qdrant, get_qdrant_vector_store
from llama_index.core import VectorStoreIndex, StorageContext, Settings
from app.pipelines.embedder import embedding_client

logger = logging.getLogger(__name__)

storage_client = storage.Client(project=settings.GCP_PROJECT_ID)

# Single source of truth for what we accept and how we label it in GCS.
EXTENSION_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}

EXTENSION_PATTERN = re.compile(r"(\.(?:pdf|jpe?g|png|webp|tiff?))$", re.IGNORECASE)

def get_extension(filename: str) -> str:
    match = EXTENSION_PATTERN.search(filename)
    return match.group(1).lower() if match else ""


def upload_to_gcs(filename: str, file_bytes: bytes) -> str:
    """Uploads document bytes to the GCS bucket. Returns the gs:// URI of the uploaded blob."""
    bucket = storage_client.bucket(settings.GCS_BUCKET_NAME)
    blob_name = f"documents/{uuid.uuid4()}_{filename}"
    blob = bucket.blob(blob_name)

    content_type = EXTENSION_CONTENT_TYPES.get(get_extension(filename), "application/octet-stream")
    logger.info(f"Uploading {filename} to GCS blob: {blob_name}")
    blob.upload_from_string(file_bytes, content_type=content_type)

    return f"gs://{settings.GCS_BUCKET_NAME}/{blob_name}"


def delete_from_gcs(gcs_uri: str):
    """Deletes a blob from GCS given its gs:// URI."""
    if not gcs_uri or not gcs_uri.startswith("gs://"):
        return
    try:
        bucket_name, blob_name = gcs_uri[len("gs://"):].split("/", 1)
        blob = storage_client.bucket(bucket_name).blob(blob_name)
        if blob.exists():
            logger.info(f"Deleting GCS blob: {blob_name}")
            blob.delete()
    except Exception as e:
        logger.error(f"Failed to delete GCS blob {gcs_uri}: {e}")


def delete_from_firestore(doc_id: str):
    """Deletes a document record from Firestore given its doc_id."""
    try:
        doc_ref = db.collection("documents").document(doc_id)
        logger.info(f"Deleting Firestore document: {doc_id}")
        doc_ref.delete()
    except Exception as e:
        logger.error(f"Failed to delete Firestore document {doc_id}: {e}")


async def delete_document_async(doc_id: str, gcs_uri: str = None, filename: str = None):

    logger.info(f"Deleting document: {doc_id or '(by filename)'}")

    if filename:
        try:
            query = db.collection("documents").where(filter=FieldFilter("filename", "==", filename))
            duplicates = await asyncio.to_thread(lambda: list(query.stream()))
            for doc in duplicates:
                if doc.id != doc_id:
                    logger.info(f"Deleting duplicate '{filename}': {doc.id}")
                    await delete_document_async(doc.id)
        except Exception as e:
            logger.warning(f"Duplicate cleanup failed for '{filename}': {e}")

    if not doc_id:
        return

    if not gcs_uri:
        try:
            doc_snap = await asyncio.to_thread(
                db.collection("documents").document(doc_id).get
            )
            if doc_snap.exists:
                gcs_uri = doc_snap.to_dict().get("gcs_uri")
        except Exception as e:
            logger.warning(f"Failed to fetch metadata for {doc_id}: {e}")

    if gcs_uri:
        await asyncio.to_thread(delete_from_gcs, gcs_uri)
    await asyncio.to_thread(delete_from_qdrant, doc_id)

    await asyncio.to_thread(delete_from_firestore, doc_id)

index = None

def get_llama_index():
    """Returns a LlamaIndex VectorStoreIndex instance connected to Qdrant."""
    global index
    if index is None:
        from llama_index.core.node_parser import SentenceSplitter
        Settings.embed_model = embedding_client
        Settings.node_parser = SentenceSplitter(chunk_size=768, chunk_overlap=50)
        
        vector_store = get_qdrant_vector_store()
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        
        index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            storage_context=storage_context
        )
    return index



def build_combined_text(pages_data) -> tuple[str, List[Dict]]:
    """Joins per-page text into one blob, tracking each page's character range for later lookup."""
    combined_text = ""
    page_offsets = []

    for page_num, text in pages_data:
        text = text.strip()
        if not text:
            continue
        if combined_text:
            combined_text += "\n\n"

        start_idx = len(combined_text)
        combined_text += text
        page_offsets.append({"page_num": page_num, "start_char": start_idx, "end_char": len(combined_text)})

    return combined_text, page_offsets


def page_for_char(char_idx: int, page_offsets: List[Dict]) -> int:
    """Finds which page a character index falls in, falling back to the nearest preceding page."""
    if not page_offsets:
        return 1
    for offset in page_offsets:
        if offset["start_char"] <= char_idx <= offset["end_char"]:
            return offset["page_num"]
    preceding = [o["page_num"] for o in page_offsets if o["start_char"] <= char_idx]
    return preceding[-1] if preceding else page_offsets[0]["page_num"]


def index_nodes_sync(document, page_offsets: List[Dict], filename: str, source_type: str):
    """Chunks the document into nodes, tags each with page info, and inserts into the vector index."""
    from llama_index.core import Settings
    nodes = Settings.node_parser.get_nodes_from_documents([document])

    for node in nodes:
        start, end = node.start_char_idx, node.end_char_idx
        if start is None or end is None:
            page_start = page_end = page_offsets[0]["page_num"] if page_offsets else 1
        else:
            page_start = page_for_char(start, page_offsets)
            page_end = page_for_char(end, page_offsets)

        node.metadata = {
            "source": filename,
            "source_type": source_type,
            "page": page_start,
            "page_start": page_start,
            "page_end": page_end,
        }

    get_llama_index().insert_nodes(nodes)


async def ingest_document_async(filename: str, file_bytes: bytes) -> str:
    """Runs the full ingestion pipeline asynchronously in thread pools."""
    ext = get_extension(filename)
    if ext not in EXTENSION_CONTENT_TYPES:
        raise ValueError(f"Unsupported file type '{ext}'. Only PDF and common image types are allowed.")

    doc_id = str(uuid.uuid4())
    gcs_uri = None

    try:
        # Prevent duplicate ingestion of the exact same filename
        await delete_document_async(doc_id="", filename=filename)

        # Step 1: Upload to GCS
        gcs_uri = await asyncio.to_thread(upload_to_gcs, filename, file_bytes)

        # Step 2: Parse PDF or image into per-page text
        logger.info(f"[{doc_id}] Parsing document text for {filename}...")
        extractor = extract_text_from_pdf if ext == ".pdf" else extract_text_from_image
        args = (file_bytes,) if ext == ".pdf" else (file_bytes, filename)
        pages_data = await asyncio.to_thread(extractor, *args)

        combined_text, page_offsets = build_combined_text(pages_data)
        if not combined_text:
            raise ValueError(f"No text could be extracted from the uploaded file: {filename}")

        # Step 3: Chunk and index using LlamaIndex
        logger.info(f"[{doc_id}] Indexing pages using LlamaIndex VectorStoreIndex...")
        from llama_index.core import Document

        document = Document(text=combined_text, id_=doc_id)
        source_type = "pdf" if ext == ".pdf" else "image"
        await asyncio.to_thread(index_nodes_sync, document, page_offsets, filename, source_type)

        # Step 4: Save metadata to Firestore
        logger.info(f"[{doc_id}] Writing metadata to Firestore...")
        doc_meta = {
            "doc_id": doc_id,
            "filename": filename,
            "gcs_uri": gcs_uri,
            "size_bytes": len(file_bytes),
            "uploaded_at": datetime.now(timezone.utc),
        }
        await asyncio.to_thread(lambda: db.collection("documents").document(doc_id).set(doc_meta))

        logger.info(f"[{doc_id}] Ingestion pipeline completed successfully.")
        return doc_id

    except Exception as e:
        logger.error(f"[{doc_id}] Ingestion pipeline failed: {e}")
        await delete_document_async(doc_id, gcs_uri)
        raise


# Synchronous compatibility wrappers
def ingest_document(filename: str, file_bytes: bytes) -> str:
    return asyncio.run(ingest_document_async(filename, file_bytes))


def delete_document(doc_id: str):
    return asyncio.run(delete_document_async(doc_id))