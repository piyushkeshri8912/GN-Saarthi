import uuid
import logging
import mimetypes
import asyncio
from datetime import datetime, timezone
from google.cloud import storage
from google.cloud.firestore_v1.base_query import FieldFilter
from google.oauth2 import service_account
from app.config import settings
from app.dependencies import db
from app.pipelines.pdf_parser import extract_text_from_pdf, extract_text_from_image
from app.pipelines.vector_store import delete_by_doc_id

logger = logging.getLogger(__name__)

# Singleton storage client
_storage_client = None

def _get_storage_client() -> storage.Client:
    """
    Returns an authenticated Google Cloud Storage client (singleton).
    """
    global _storage_client
    if _storage_client is None:
        sa_info = settings.firebase_service_account_dict
        gcp_cred = service_account.Credentials.from_service_account_info(
            sa_info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        _storage_client = storage.Client(credentials=gcp_cred, project=settings.GCP_PROJECT_ID)
    return _storage_client

def upload_to_gcs(filename: str, file_bytes: bytes) -> str:
    """
    Uploads document bytes to the GCS bucket.
    Returns the gs:// URI of the uploaded blob.
    """
    client = _get_storage_client()
    bucket = client.bucket(settings.GCS_BUCKET_NAME)
    
    # Store documents under documents/ folder
    blob_name = f"documents/{uuid.uuid4()}_{filename}"
    blob = bucket.blob(blob_name)
    
    logger.info(f"Uploading {filename} ({len(file_bytes)} bytes) to GCS blob: {blob_name}")
    content_type, _ = mimetypes.guess_type(filename)
    if not content_type:
        ext = filename.lower().split(".")[-1]
        mime_map = {
            "pdf": "application/pdf",
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
            "tiff": "image/tiff",
            "tif": "image/tiff",
        }
        content_type = mime_map.get(ext, "application/octet-stream")
        
    blob.upload_from_string(file_bytes, content_type=content_type)
    return f"gs://{settings.GCS_BUCKET_NAME}/{blob_name}"

def delete_from_gcs(gcs_uri: str):
    """
    Deletes a blob from GCS given its gs:// URI.
    """
    if not gcs_uri or not gcs_uri.startswith("gs://"):
        return
        
    try:
        uri_path = gcs_uri[5:]  # Remove gs://
        parts = uri_path.split("/", 1)
        if len(parts) < 2:
            return
        bucket_name, blob_name = parts
        
        client = _get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        if blob.exists():
            logger.info(f"Deleting GCS blob: {blob_name}")
            blob.delete()
    except Exception as e:
        logger.error(f"Failed to delete GCS blob {gcs_uri}: {e}")

async def ingest_document_async(filename: str, file_bytes: bytes) -> str:
    """
    Runs the full ingestion pipeline asynchronously in thread pools.
    """
    ext = "." + filename.lower().split(".")[-1]
    allowed_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif"}
    if ext not in allowed_extensions:
        raise ValueError(f"Unsupported file type '{ext}'. Only PDF and common image types are allowed.")

    doc_id = str(uuid.uuid4())
    gcs_uri = None
    
    try:
        # Prevent duplicate ingestion of the exact same filename
        try:
            # Firestore calls are sync, wrap in asyncio.to_thread
            existing_docs_snap = await asyncio.to_thread(
                lambda: list(db.collection("documents").where(filter=FieldFilter("filename", "==", filename)).stream())
            )
            for doc in existing_docs_snap:
                old_doc_id = doc.id
                logger.info(f"Duplicate filename detected: '{filename}'. Automatically overwriting old document '{old_doc_id}' first.")
                await delete_document_async(old_doc_id)
        except Exception as e:
            logger.warning(f"Failed to check or delete duplicate document: {e}")

        # Step 1: Upload to GCS
        gcs_uri = await asyncio.to_thread(upload_to_gcs, filename, file_bytes)
        
        # Step 2: Parse PDF or image
        logger.info(f"[{doc_id}] Parsing document text for {filename}...")
        if ext == ".pdf":
            pages_data = await asyncio.to_thread(extract_text_from_pdf, file_bytes)
        else:
            pages_data = await asyncio.to_thread(extract_text_from_image, file_bytes, filename)
        
        # Step 3: Insert documents natively using LlamaIndex
        logger.info(f"[{doc_id}] Indexing pages using LlamaIndex VectorStoreIndex...")
        from llama_index.core import Document
        from app.services.rag_service import get_llama_index
        
        documents = []
        for page_num, text in pages_data:
            text = text.strip()
            if not text:
                continue
            documents.append(Document(
                text=text,
                id_=f"{doc_id}_page_{page_num}",
                metadata={
                    "doc_id_key": doc_id,
                    "doc_id": doc_id,
                    "document_id": doc_id,
                    "source": filename,
                    "source_type": "pdf" if ext == ".pdf" else "image",
                    "page": page_num,
                    "page_start": page_num,
                    "page_end": page_num,
                }
            ))
            
        if not documents:
            raise ValueError(f"No text could be extracted from the uploaded file: {filename}")
            
        # Step 3: Insert documents natively using LlamaIndex (Batch insertion)
        logger.info(f"[{doc_id}] Batch parsing and inserting {len(documents)} pages using LlamaIndex...")
        
        def _insert_sync(docs):
            index = get_llama_index()
            from llama_index.core import Settings
            node_parser = Settings.node_parser
            nodes = node_parser.get_nodes_from_documents(docs)
            index.insert_nodes(nodes)

        await asyncio.to_thread(_insert_sync, documents)
        
        # Step 4: Save metadata to Firestore
        logger.info(f"[{doc_id}] Writing metadata to Firestore...")
        doc_meta = {
            "doc_id": doc_id,
            "filename": filename,
            "gcs_uri": gcs_uri,
            "size_bytes": len(file_bytes),
            "uploaded_at": datetime.now(timezone.utc)
        }
        await asyncio.to_thread(
            lambda: db.collection("documents").document(doc_id).set(doc_meta)
        )
        
        logger.info(f"[{doc_id}] Ingestion pipeline completed successfully.")
        return doc_id
        
    except Exception as e:
        logger.error(f"[{doc_id}] Ingestion pipeline failed: {e}")
        # Cleanup GCS blob if uploaded
        if gcs_uri:
            logger.info(f"[{doc_id}] Cleaning up GCS blob...")
            try:
                await asyncio.to_thread(delete_from_gcs, gcs_uri)
            except Exception as ge:
                logger.error(f"[{doc_id}] Cleanup: GCS blob deletion failed: {ge}")
        # Cleanup Qdrant vectors if any were upserted
        try:
            await asyncio.to_thread(delete_by_doc_id, doc_id)
        except Exception as qe:
            logger.error(f"[{doc_id}] Cleanup: Qdrant vectors deletion failed: {qe}")
        raise

async def delete_document_async(doc_id: str):
    """
    Removes a document entirely asynchronously.
    """
    logger.info(f"Starting deletion for doc_id: {doc_id}")
    
    # 1. Fetch metadata (best effort)
    gcs_uri = None
    doc_ref = db.collection("documents").document(doc_id)
    try:
        doc_snap = await asyncio.to_thread(doc_ref.get)
        if doc_snap.exists:
            data = doc_snap.to_dict()
            gcs_uri = data.get("gcs_uri")
    except Exception as e:
        logger.warning(f"Failed to fetch Firestore metadata for doc_id {doc_id}: {e}")
        
    # 2. Delete from GCS (best effort)
    if gcs_uri:
        try:
            await asyncio.to_thread(delete_from_gcs, gcs_uri)
        except Exception as e:
            logger.error(f"Failed to delete GCS blob {gcs_uri}: {e}")
            
    # 3. Delete from Qdrant (best effort)
    try:
        await asyncio.to_thread(delete_by_doc_id, doc_id)
    except Exception as e:
        logger.error(f"Failed to delete vectors from Qdrant for doc_id '{doc_id}': {e}")
        
    # 4. Delete from Firestore
    try:
        await asyncio.to_thread(doc_ref.delete)
    except Exception as e:
        logger.error(f"Failed to delete document from Firestore for doc_id '{doc_id}': {e}")
        raise ValueError(f"Failed to delete document metadata from Firestore: {e}")
        


    logger.info(f"Document {doc_id} deletion completed.")

# Synchronous compatibility wrapper
def ingest_document(filename: str, file_bytes: bytes) -> str:
    return asyncio.run(ingest_document_async(filename, file_bytes))

def delete_document(doc_id: str):
    return asyncio.run(delete_document_async(doc_id))
