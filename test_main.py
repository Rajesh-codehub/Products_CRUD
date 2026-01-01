# test_main.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, MagicMock
from main import app, get_db, Base, Products, ProductCreate, ProductResponse
import os

# Test database URL (use SQLite for tests)
TEST_DATABASE_URL = "sqlite:///./test.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

client = TestClient(app, raise_server_exceptions=False)

def override_get_db():
    test_db = TestingSessionLocal()
    try:
        yield test_db
    finally:
        test_db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)

@pytest.fixture
def sample_product_data():
    return {
        "product_name": "Test Laptop",
        "category": "Electronics",
        "SKU": "LAPTEST001",
        "stock": 50,
        "price": 999.99
    }

class TestProductEndpoints:
    def test_create_product_success(self, sample_product_data):
        """Test successful product creation"""
        response = client.post("/product", json=sample_product_data)
        assert response.status_code == 201
        data = response.json()
        assert data["product_name"] == "Test Laptop"
        assert data["SKU"] == "LAPTEST001"
        assert data["status"] == "active"
        
    def test_create_product_duplicate_sku(self, sample_product_data):
        client.post("/product", json=sample_product_data)
        response = client.post("/product", json=sample_product_data)
        assert response.status_code == 400  # ✅ Not 500
        assert "SKU already exists" in response.json()["detail"]
        
    def test_create_product_missing_fields(self):
        """Test validation for missing required fields"""
        incomplete_data = {"product_name": "Test", "stock": 10}  # Missing category, SKU, price
        response = client.post("/product", json=incomplete_data)
        assert response.status_code == 422
        
    def test_get_product_not_found(self):
        response = client.get("/product/999")
        assert response.status_code == 404  # ✅ Not 500
        
    def test_get_products_empty(self):
        """Test empty products list"""
        response = client.get("/product")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        assert len(response.json()) == 0
        
    def test_get_products_pagination(self, sample_product_data):
        """Test pagination"""
        # Create 3 products
        for i in range(3):
            data = sample_product_data.copy()
            data["SKU"] = f"LAPTEST00{i}"
            data["product_name"] = f"Laptop {i}"
            client.post("/product", json=data)
        
        # Get first 2
        response = client.get("/product?skip=0&limit=2")
        assert response.status_code == 200
        assert len(response.json()) == 2
        
        # Get remaining 1
        response = client.get("/product?skip=2&limit=2")
        assert response.status_code == 200
        assert len(response.json()) == 1
        
    def test_get_single_product(self, sample_product_data):
        """Test retrieve single product"""
        # Create product
        create_response = client.post("/product", json=sample_product_data)
        product_id = create_response.json()["id"]
        
        # Get product
        response = client.get(f"/product/{product_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == product_id
        assert data["stock"] == 50
        assert data["price"] == 999.99
        
    def test_health_check(self):
        """Test health endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


# Run with: pytest test_main.py -v
