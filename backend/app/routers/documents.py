from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from typing import List
import logging
from app.dependencies import require_admin, verify_token, db
from app.schemas.schemas import User, UploadResponse, DocumentMeta
from app.services.ingestion_service import ingest_document, delete_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin)
):
    """
    Endpoint for uploading a PDF document. Enforces Admin role.
    Processes the document through the ingestion pipeline.
    """
    allowed_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif"}
    ext = "." + file.filename.lower().split(".")[-1]
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Only PDF and common image types (.png, .jpg, .jpeg, .webp, .tiff) are allowed."
        )
        
    try:
        logger.info(f"Admin {current_user.email} is uploading document: {file.filename}")
        file_bytes = await file.read()
        doc_id = ingest_document(file.filename, file_bytes)
        return UploadResponse(
            success=True,
            doc_id=doc_id,
            filename=file.filename,
            message="Document uploaded and indexed successfully."
        )
    except Exception as e:
        logger.error(f"Failed to ingest document {file.filename}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {str(e)}"
        )

@router.get("", response_model=List[DocumentMeta])
async def list_documents(current_user: User = Depends(verify_token)):
    """
    Endpoint for listing all uploaded documents. Requires authentication.
    """
    try:
        logger.info(f"User {current_user.email} requested document list.")
        docs_ref = db.collection("documents").stream()
        docs = []
        for doc in docs_ref:
            data = doc.to_dict()
            # Convert uploaded_at to datetime object if it's a Firestore Timestamp
            uploaded_at = data.get("uploaded_at")
            
            docs.append(DocumentMeta(
                doc_id=data["doc_id"],
                filename=data["filename"],
                gcs_uri=data["gcs_uri"],
                size_bytes=data["size_bytes"],
                uploaded_at=uploaded_at
            ))
            
        # Sort documents by upload date descending
        docs.sort(key=lambda x: x.uploaded_at, reverse=True)
        return docs
    except Exception as e:
        logger.error(f"Failed to fetch documents list: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch documents: {str(e)}"
        )

@router.delete("/{doc_id}", response_model=dict)
async def remove_document(doc_id: str, current_user: User = Depends(require_admin)):
    """
    Endpoint to delete an uploaded document. Enforces Admin role.
    Removes the document from GCS, Qdrant vectors, and Firestore metadata.
    """
    try:
        logger.info(f"Admin {current_user.email} requested deletion of document: {doc_id}")
        delete_document(doc_id)
        return {"message": "Document successfully deleted", "doc_id": doc_id}
    except Exception as e:
        logger.error(f"Failed to delete document {doc_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}"
        )


@router.get("/{doc_id}/download")
async def download_document(doc_id: str, current_user: User = Depends(verify_token)):
    """
    Downloads/views an uploaded document by its doc_id.
    """
    try:
        logger.info(f"User {current_user.email} requested download of document: {doc_id}")
        doc_ref = db.collection("documents").document(doc_id).get()
        if not doc_ref.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found."
            )
            
        data = doc_ref.to_dict()
        gcs_uri = data.get("gcs_uri")
        filename = data.get("filename")
        
        if not gcs_uri or not gcs_uri.startswith("gs://"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document source file URI is invalid."
            )
            
        # Parse gs_uri
        uri_path = gcs_uri[5:]
        parts = uri_path.split("/", 1)
        if len(parts) < 2:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid GCS URI in document metadata."
            )
        bucket_name, blob_name = parts
        
        from app.services.ingestion_service import _get_storage_client
        client = _get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.get_blob(blob_name)
        
        if not blob:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Backing file does not exist in Cloud Storage."
            )
            
        import mimetypes
        content_type = blob.content_type
        if not content_type:
            content_type, _ = mimetypes.guess_type(filename)
        if not content_type:
            content_type = "application/pdf" if filename.lower().endswith(".pdf") else "application/octet-stream"
        
        # Download file bytes
        file_bytes = blob.download_as_bytes()
        
        from io import BytesIO
        return StreamingResponse(
            BytesIO(file_bytes),
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename={filename}"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download document {doc_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve document: {str(e)}"
        )
