from firebase_admin import auth
import logging
from app.config import settings
from app.dependencies import db

logger = logging.getLogger(__name__)

def verify_firebase_token(token: str) -> dict:
    """
    Decodes and verifies a Firebase ID token.
    Enforces the allowed email domain and checks if the email is in the admins collection.
    
    Returns a dictionary with:
      - uid: Firebase User ID
      - email: User's email
      - role: "admin" or "student"
    """
    try:
        decoded_token = auth.verify_id_token(token)
    except Exception as e:
        err_msg = str(e)
        if "Token used too early" in err_msg:
            import re
            import time
            matches = re.findall(r"\d+", err_msg)
            if len(matches) >= 2:
                current_time = int(matches[0])
                iat_time = int(matches[1])
                skew = iat_time - current_time
                if 0 < skew <= 300:
                    logger.warning(f"Firebase token used too early due to clock skew. Sleeping for {skew + 1}s before retrying.")
                    time.sleep(skew + 1)
                    try:
                        decoded_token = auth.verify_id_token(token)
                    except Exception as retry_e:
                        logger.warning(f"Firebase token verification failed on retry: {retry_e}")
                        raise ValueError(f"Invalid Firebase ID token: {str(retry_e)}")
                else:
                    raise ValueError(f"Invalid Firebase ID token: {err_msg}")
            else:
                logger.warning("Token used too early. Sleeping for 5s and retrying.")
                time.sleep(5)
                try:
                    decoded_token = auth.verify_id_token(token)
                except Exception as retry_e:
                    raise ValueError(f"Invalid Firebase ID token: {str(retry_e)}")
        else:
            logger.warning(f"Firebase token verification failed: {e}")
            raise ValueError(f"Invalid Firebase ID token: {str(e)}")
        
    email = decoded_token.get("email")
    if not email:
        raise ValueError("Token does not contain an email address.")
        
    email = email.lower()
    
    # Validate domain
    allowed_domain = settings.ALLOWED_DOMAIN.lower()
    email_domain = email.split("@")[-1]
    
    # Check if this matches allowed domain or a temp test email
    is_allowed = (email_domain == allowed_domain)
    if settings.TEMP_TEST_EMAIL and email == settings.TEMP_TEST_EMAIL.lower():
        is_allowed = True
        
    if not is_allowed:
        raise ValueError(f"Access restricted to @{allowed_domain} accounts.")
        
    # Check admin role in Firestore
    # Document keys in "admins" are assumed to be lowercased email addresses
    role = "student"
    try:
        admin_doc = db.collection("admins").document(email).get()
        if admin_doc.exists:
            role = "admin"
            logger.info(f"User {email} authenticated as admin.")
        else:
            logger.info(f"User {email} authenticated as student.")
    except Exception as e:
        logger.error(f"Error querying admins collection for {email}: {e}")
        # Default to student if firestore fails
        role = "student"
        
    return {
        "uid": decoded_token.get("uid"),
        "email": email,
        "role": role
    }
