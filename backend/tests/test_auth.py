from unittest.mock import MagicMock, patch
import pytest
from app.services.auth_service import verify_firebase_token

@patch("app.services.auth_service.auth")
@patch("app.services.auth_service.db")
def test_verify_token_admin(mock_db, mock_auth):
    """
    Verify that an email ending with @iitgn.ac.in that exists in the Firestore 
    admins collection is correctly authenticated with the 'admin' role.
    """
    mock_auth.verify_id_token.return_value = {
        "uid": "admin-uid",
        "email": "admin@iitgn.ac.in"
    }
    
    # Mock firestore lookup where the email is in the admin collection
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
    
    result = verify_firebase_token("fake-token")
    
    assert result["uid"] == "admin-uid"
    assert result["email"] == "admin@iitgn.ac.in"
    assert result["role"] == "admin"
    mock_db.collection.assert_called_with("admins")
    mock_db.collection.return_value.document.assert_called_with("admin@iitgn.ac.in")

@patch("app.services.auth_service.auth")
@patch("app.services.auth_service.db")
def test_verify_token_student(mock_db, mock_auth):
    """
    Verify that an email ending with @iitgn.ac.in that does not exist in the 
    Firestore admins collection is authenticated with the 'student' role.
    """
    mock_auth.verify_id_token.return_value = {
        "uid": "student-uid",
        "email": "student@iitgn.ac.in"
    }
    
    # Mock firestore lookup where the email is not in the admin collection
    mock_doc = MagicMock()
    mock_doc.exists = False
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
    
    result = verify_firebase_token("fake-token")
    
    assert result["uid"] == "student-uid"
    assert result["email"] == "student@iitgn.ac.in"
    assert result["role"] == "student"

@patch("app.services.auth_service.auth")
def test_verify_token_invalid_domain(mock_auth):
    """
    Verify that emails from non-IITGN domains are rejected with a ValueError.
    """
    mock_auth.verify_id_token.return_value = {
        "uid": "user-uid",
        "email": "user@gmail.com"
    }
    
    with pytest.raises(ValueError) as exc:
        verify_firebase_token("fake-token")
    assert "Access restricted to @iitgn.ac.in accounts" in str(exc.value)

@patch("app.services.auth_service.auth")
def test_verify_token_invalid_token(mock_auth):
    """
    Verify that expired or invalid Firebase ID tokens raise a ValueError.
    """
    mock_auth.verify_id_token.side_effect = Exception("Expired token")
    
    with pytest.raises(ValueError) as exc:
        verify_firebase_token("invalid-token")
    assert "Invalid Firebase ID token" in str(exc.value)
