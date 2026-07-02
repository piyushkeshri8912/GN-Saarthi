import firebase_admin
from firebase_admin import credentials, firestore
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings
from app.schemas.schemas import User

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    sa_dict = settings.firebase_service_account_dict
    if sa_dict:
        # Local development: initialize using service account JSON credentials
        cred = credentials.Certificate(sa_dict)
        firebase_admin.initialize_app(cred)
    else:
        # Production/GCP: initialize using Application Default Credentials (ADC)
        firebase_admin.initialize_app()

db = firestore.client(database_id=settings.FIRESTORE_DATABASE_ID)

security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """
    Dependency to verify Firebase ID token passed in the Authorization header.
    Enforces allowed email domain.
    """
    token = credentials.credentials
    try:
        from app.services.auth_service import verify_firebase_token
        user_data = verify_firebase_token(token)
        return User(**user_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {str(e)}"
        )

async def require_admin(current_user: User = Depends(verify_token)) -> User:
    """
    Dependency that wraps verify_token and additionally checks if the user is an admin.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Admin privileges required."
        )
    return current_user

_query_service = None

def get_query_service():
    global _query_service
    if _query_service is None:
        from app.services.session_service import SessionService
        from app.pipelines.retriever import SmartRetriever
        from app.services.query_service import QueryService
        
        session_svc = SessionService()
        retriever = SmartRetriever()
        _query_service = QueryService(session_svc, retriever)
    return _query_service
