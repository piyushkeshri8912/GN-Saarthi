from firebase_admin import auth
import logging

from app.config import settings
from app.dependencies import db

logger = logging.getLogger(__name__)

def verify_firebase_token(token: str) -> dict:
    """
    Verify a Firebase ID token, enforce allowed email domain, and assign role.
    Returns:
    {
        "uid": ...,
        "email": ...,
        "role": "admin" | "student"
    }
    """
    try:
        decoded_token = auth.verify_id_token(token)
    except Exception as e:
        logger.warning(f"Firebase token verification failed: {e}")
        raise ValueError(f"Invalid Firebase ID token: {str(e)}")

    email = (decoded_token.get("email") or "").lower()
    if not email:
        raise ValueError("Token does not contain an email address.")

    allowed_domain = settings.ALLOWED_DOMAIN.lower()
    temp_test_email = (settings.TEMP_TEST_EMAIL or "").lower()

    email_domain = email.split("@")[-1]
    if email_domain != allowed_domain and email != temp_test_email:
        raise ValueError(f"Access restricted to @{allowed_domain} accounts.")

    role = "student"
    try:
        if db.collection("admins").document(email).get().exists:
            role = "admin"
            logger.info(f"User {email} authenticated as admin.")
    except Exception as e:
        logger.error(f"Error querying admins collection for {email}: {e}")

    return {
        "uid": decoded_token.get("uid"),
        "email": email,
        "role": role,
}

