import uuid
import logging
import mimetypes
from datetime import datetime
from google.cloud import storage
from google.oauth2 import service_account
from app.config import settings
from app.dependencies import db
from app.pipelines.pdf_parser import extract_text_from_pdf, extract_text_from_image
from app.pipelines.chunker import chunk_document_pages
from app.pipelines.embedder import generate_embeddings
from app.pipelines.vector_store import upsert_chunks, delete_by_doc_id

logger = logging.getLogger(__name__)

def _get_storage_client() -> storage.Client:
    """
    Returns an authenticated Google Cloud Storage client.
    """
    sa_info = settings.firebase_service_account_dict
    gcp_cred = service_account.Credentials.from_service_account_info(
        sa_info,
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    return storage.Client(credentials=gcp_cred, project=settings.GCP_PROJECT_ID)

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

def ingest_document(filename: str, file_bytes: bytes) -> str:
    """
    Runs the full ingestion pipeline:
      1. Upload to GCS
      2. Parse PDF or image to extract text per page
      3. Chunk text into token-based pages
      4. Embed text chunks using Vertex AI
      5. Upsert embeddings & metadata payloads to Qdrant
      6. Save document metadata to Firestore
      
    Returns the generated doc_id.
    """
    ext = "." + filename.lower().split(".")[-1]
    allowed_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif"}
    if ext not in allowed_extensions:
        raise ValueError(f"Unsupported file type '{ext}'. Only PDF and common image types are allowed.")

    doc_id = str(uuid.uuid4())
    gcs_uri = None
    
    try:
        # Step 1: Upload to GCS
        gcs_uri = upload_to_gcs(filename, file_bytes)
        
        # Step 2: Parse PDF or image
        logger.info(f"[{doc_id}] Parsing document text for {filename}...")
        if ext == ".pdf":
            pages_data = extract_text_from_pdf(file_bytes)
        else:
            pages_data = extract_text_from_image(file_bytes, filename)
        
        # Step 3: Chunk text
        logger.info(f"[{doc_id}] Chunking document text...")
        chunks = chunk_document_pages(pages_data, doc_id=doc_id)
        
        if not chunks:
            raise ValueError(f"No text could be extracted or chunked from the uploaded file: {filename}")
            
        # Step 4: Embed chunks
        logger.info(f"[{doc_id}] Generating embeddings for {len(chunks)} chunks...")
        chunk_texts = [c["text"] for c in chunks]
        embeddings = generate_embeddings(chunk_texts)
        
        # Step 5: Upsert to Qdrant
        logger.info(f"[{doc_id}] Upserting to Qdrant...")
        upsert_chunks(
            doc_id=doc_id,
            source=filename,
            chunks=chunks,
            embeddings=embeddings
        )
        
        # Step 6: Save metadata to Firestore
        logger.info(f"[{doc_id}] Writing metadata to Firestore...")
        doc_meta = {
            "doc_id": doc_id,
            "filename": filename,
            "gcs_uri": gcs_uri,
            "size_bytes": len(file_bytes),
            "uploaded_at": datetime.utcnow()
        }
        db.collection("documents").document(doc_id).set(doc_meta)
        
        logger.info(f"[{doc_id}] Ingestion pipeline completed successfully.")
        return doc_id
        
    except Exception as e:
        logger.error(f"[{doc_id}] Ingestion pipeline failed: {e}")
        # Cleanup GCS blob if uploaded
        if gcs_uri:
            logger.info(f"[{doc_id}] Cleaning up GCS blob...")
            try:
                delete_from_gcs(gcs_uri)
            except Exception as ge:
                logger.error(f"[{doc_id}] Cleanup: GCS blob deletion failed: {ge}")
        # Cleanup Qdrant vectors if any were upserted
        try:
            delete_by_doc_id(doc_id)
        except Exception as qe:
            logger.error(f"[{doc_id}] Cleanup: Qdrant vectors deletion failed: {qe}")
        raise

def delete_document(doc_id: str):
    """
    Removes a document entirely:
      1. Fetch metadata from Firestore (best-effort)
      2. Delete blob from GCS (best-effort)
      3. Delete vectors from Qdrant (best-effort)
      4. Delete metadata from Firestore
    """
    logger.info(f"Starting deletion for doc_id: {doc_id}")
    
    # 1. Fetch metadata (best effort)
    gcs_uri = None
    doc_ref = db.collection("documents").document(doc_id)
    try:
        doc_snap = doc_ref.get()
        if doc_snap.exists:
            data = doc_snap.to_dict()
            gcs_uri = data.get("gcs_uri")
    except Exception as e:
        logger.warning(f"Failed to fetch Firestore metadata for doc_id {doc_id}: {e}")
        
    # 2. Delete from GCS (best effort)
    if gcs_uri:
        try:
            delete_from_gcs(gcs_uri)
        except Exception as e:
            logger.error(f"Failed to delete GCS blob {gcs_uri}: {e}")
            
    # 3. Delete from Qdrant (best effort)
    try:
        delete_by_doc_id(doc_id)
    except Exception as e:
        logger.error(f"Failed to delete vectors from Qdrant for doc_id '{doc_id}': {e}")
        
    # 4. Delete from Firestore (always perform, ignore missing docs for idempotency)
    try:
        doc_ref.delete()
    except Exception as e:
        logger.error(f"Failed to delete document from Firestore for doc_id '{doc_id}': {e}")
        raise ValueError(f"Failed to delete document metadata from Firestore: {e}")
        
    logger.info(f"Document {doc_id} deletion completed.")
