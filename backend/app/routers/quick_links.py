from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
import logging
from datetime import datetime
import uuid
from app.dependencies import require_admin, verify_token, db
from app.schemas.schemas import User, QuickLinkCreate, QuickLinkResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quick_links", tags=["quick_links"])

@router.get("", response_model=List[QuickLinkResponse])
async def list_quick_links(current_user: User = Depends(verify_token)):
    """
    Endpoint for listing all quick links. Requires authentication.
    """
    try:
        logger.info(f"User {current_user.email} requested quick links list.")
        links_ref = db.collection("quick_links").order_by("service").stream()
        links = []
        for doc in links_ref:
            data = doc.to_dict()
            created_at = data.get("created_at")
            
            # Ensure it is a datetime object
            if not isinstance(created_at, datetime):
                if hasattr(created_at, "to_datetime"):
                    created_at_dt = created_at.to_datetime()
                else:
                    try:
                        created_at_dt = datetime.fromisoformat(str(created_at))
                    except:
                        created_at_dt = datetime.utcnow()
            else:
                created_at_dt = created_at
                    
            links.append(QuickLinkResponse(
                id=doc.id,
                service=data.get("service", ""),
                link=data.get("link", ""),
                purpose=data.get("purpose", ""),
                created_at=created_at_dt
            ))
        return links
    except Exception as e:
        logger.error(f"Failed to list quick links: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve quick links: {str(e)}"
        )

@router.post("", response_model=QuickLinkResponse)
async def create_quick_link(
    payload: QuickLinkCreate,
    current_user: User = Depends(require_admin)
):
    """
    Endpoint for creating a new quick link. Enforces Admin role.
    """
    try:
        logger.info(f"Admin {current_user.email} is creating quick link: {payload.service}")
        link_id = str(uuid.uuid4())
        created_at = datetime.utcnow()
        
        doc_data = {
            "service": payload.service.strip(),
            "link": payload.link.strip(),
            "purpose": payload.purpose.strip() if payload.purpose else "",
            "created_at": created_at
        }
        
        # Save to Firestore
        db.collection("quick_links").document(link_id).set(doc_data)
        
        # Invalidate the memory cache in RAG service when links are modified
        try:
            from app.services.rag_service import invalidate_links_cache
            invalidate_links_cache()
        except Exception as cache_err:
            logger.warning(f"Failed to invalidate quick links cache: {cache_err}")
            
        return QuickLinkResponse(
            id=link_id,
            service=doc_data["service"],
            link=doc_data["link"],
            purpose=doc_data["purpose"],
            created_at=created_at
        )
    except Exception as e:
        logger.error(f"Failed to create quick link: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create quick link: {str(e)}"
        )

@router.put("/{link_id}", response_model=QuickLinkResponse)
async def update_quick_link(
    link_id: str,
    payload: QuickLinkCreate,
    current_user: User = Depends(require_admin)
):
    """
    Endpoint for updating an existing quick link. Enforces Admin role.
    """
    try:
        logger.info(f"Admin {current_user.email} is updating quick link {link_id}")
        doc_ref = db.collection("quick_links").document(link_id)
        doc = doc_ref.get()
        if not doc.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Quick link with ID {link_id} not found."
            )
            
        existing_data = doc.to_dict()
        created_at = existing_data.get("created_at", datetime.utcnow())
        
        doc_data = {
            "service": payload.service.strip(),
            "link": payload.link.strip(),
            "purpose": payload.purpose.strip() if payload.purpose else "",
            "created_at": created_at
        }
        
        # Update Firestore document
        doc_ref.set(doc_data)
        
        # Invalidate cache
        try:
            from app.services.rag_service import invalidate_links_cache
            invalidate_links_cache()
        except Exception as cache_err:
            logger.warning(f"Failed to invalidate quick links cache: {cache_err}")
            
        return QuickLinkResponse(
            id=link_id,
            service=doc_data["service"],
            link=doc_data["link"],
            purpose=doc_data["purpose"],
            created_at=created_at
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Failed to update quick link {link_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update quick link: {str(e)}"
        )

@router.delete("/{link_id}")
async def delete_quick_link(
    link_id: str,
    current_user: User = Depends(require_admin)
):
    """
    Endpoint for deleting a quick link. Enforces Admin role.
    """
    try:
        logger.info(f"Admin {current_user.email} is deleting quick link {link_id}")
        doc_ref = db.collection("quick_links").document(link_id)
        if not doc_ref.get().exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Quick link with ID {link_id} not found."
            )
            
        doc_ref.delete()
        
        # Invalidate cache
        try:
            from app.services.rag_service import invalidate_links_cache
            invalidate_links_cache()
        except Exception as cache_err:
            logger.warning(f"Failed to invalidate quick links cache: {cache_err}")
            
        return {"success": True, "message": f"Quick link {link_id} deleted successfully."}
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Failed to delete quick link {link_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete quick link: {str(e)}"
        )
