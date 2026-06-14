from fastapi import APIRouter, Depends
from app.dependencies import verify_token
from app.schemas.schemas import User

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/verify", response_model=User)
async def verify_auth(current_user: User = Depends(verify_token)):
    """
    Endpoint to verify a Firebase ID token.
    Accepts standard Authorization: Bearer <token> header.
    Returns the user's details and resolved role.
    """
    return current_user
