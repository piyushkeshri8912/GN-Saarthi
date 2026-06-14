from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.dependencies import verify_token, require_admin
from app.schemas.schemas import User

client = TestClient(app)

@pytest.fixture(autouse=True)
def cleanup_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()

@pytest.fixture
def mock_db():
    with patch("app.routers.quick_links.db") as mock:
        yield mock

def test_list_quick_links(mock_db):
    # Set override for verify_token
    student_user = User(uid="student-uid", email="student@iitgn.ac.in", role="student")
    app.dependency_overrides[verify_token] = lambda: student_user
    
    # Mock Firestore stream results
    mock_doc = MagicMock()
    mock_doc.id = "link-1"
    mock_doc.to_dict.return_value = {
        "service": "Test Service",
        "link": "https://test.com",
        "purpose": "Testing links",
        "created_at": "2026-06-14T10:00:00"
    }
    
    mock_stream = [mock_doc]
    mock_db.collection.return_value.order_by.return_value.stream.return_value = mock_stream
    
    response = client.get("/quick_links", headers={"Authorization": "Bearer fake-token"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "link-1"
    assert data[0]["service"] == "Test Service"
    assert data[0]["link"] == "https://test.com"

def test_create_quick_link_admin(mock_db):
    admin_user = User(uid="admin-uid", email="admin@iitgn.ac.in", role="admin")
    app.dependency_overrides[verify_token] = lambda: admin_user
    app.dependency_overrides[require_admin] = lambda: admin_user
    
    response = client.post(
        "/quick_links",
        json={"service": "New Service", "link": "https://new.com", "purpose": "New link description"},
        headers={"Authorization": "Bearer fake-token"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "New Service"
    assert data["link"] == "https://new.com"
    assert "id" in data

def test_create_quick_link_forbidden_student(mock_db):
    student_user = User(uid="student-uid", email="student@iitgn.ac.in", role="student")
    app.dependency_overrides[verify_token] = lambda: student_user
    
    def mock_require_admin():
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Forbidden: Admin privileges required.")
        
    app.dependency_overrides[require_admin] = mock_require_admin
    
    response = client.post(
        "/quick_links",
        json={"service": "New Service", "link": "https://new.com", "purpose": "New link description"},
        headers={"Authorization": "Bearer fake-token"}
    )
    assert response.status_code == 403
