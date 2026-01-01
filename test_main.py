# test_main.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import app, get_db, Base, Products

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
    """Create fresh database for each test"""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)

@pytest.fixture
def sample_product_data():
    """Sample product data for testing"""
    return {
        "product_name": "Test Laptop",
        "category": "Electronics",
        "SKU": "LAPTEST001",
        "stock": 50,
        "price": 999.99
    }

class TestProductEndpoints:
    """Test basic CRUD operations"""
    
    def test_create_product_success(self, sample_product_data):
        """Test successful product creation"""
        response = client.post("/product", json=sample_product_data)
        assert response.status_code == 201
        data = response.json()
        assert data["product_name"] == "Test Laptop"
        assert data["SKU"] == "LAPTEST001"
        assert data["status"] == "active"
        assert "id" in data
        assert "created_at" in data
        
    def test_create_product_duplicate_sku(self, sample_product_data):
        """Test duplicate SKU rejection"""
        # Create first product
        client.post("/product", json=sample_product_data)
        
        # Try to create duplicate
        response = client.post("/product", json=sample_product_data)
        assert response.status_code == 400
        assert "SKU already exists" in response.json()["detail"]
        
    def test_create_product_missing_fields(self):
        """Test validation for missing required fields"""
        incomplete_data = {
            "product_name": "Test", 
            "stock": 10
        }  # Missing category, SKU, price
        response = client.post("/product", json=incomplete_data)
        assert response.status_code == 422
        
    def test_get_single_product_success(self, sample_product_data):
        """Test retrieve single product by ID"""
        # Create product
        create_response = client.post("/product", json=sample_product_data)
        product_id = create_response.json()["id"]
        
        # Get product
        response = client.get(f"/product/{product_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == product_id
        assert data["product_name"] == "Test Laptop"
        assert data["stock"] == 50
        assert data["price"] == 999.99
        
    def test_get_product_not_found(self):
        """Test 404 for non-existent product"""
        response = client.get("/product/999")
        assert response.status_code == 404
        assert "Product not found" in response.json()["detail"]
        
    def test_get_products_empty(self):
        """Test empty products list"""
        response = client.get("/product")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        assert len(response.json()) == 0
        
    def test_get_products_with_data(self, sample_product_data):
        """Test retrieving list of products"""
        # Create multiple products
        for i in range(3):
            data = sample_product_data.copy()
            data["SKU"] = f"LAPTEST00{i}"
            data["product_name"] = f"Laptop {i}"
            client.post("/product", json=data)
        
        # Get all products
        response = client.get("/product")
        assert response.status_code == 200
        products = response.json()
        assert len(products) == 3
        assert all("id" in p for p in products)
        
    def test_get_products_pagination(self, sample_product_data):
        """Test pagination parameters"""
        # Create 5 products
        for i in range(5):
            data = sample_product_data.copy()
            data["SKU"] = f"LAPTEST00{i}"
            data["product_name"] = f"Laptop {i}"
            client.post("/product", json=data)
        
        # Get first 2
        response = client.get("/product?skip=0&limit=2")
        assert response.status_code == 200
        assert len(response.json()) == 2
        
        # Get next 2
        response = client.get("/product?skip=2&limit=2")
        assert response.status_code == 200
        assert len(response.json()) == 2
        
        # Get remaining 1
        response = client.get("/product?skip=4&limit=2")
        assert response.status_code == 200
        assert len(response.json()) == 1
        
    def test_health_check(self):
        """Test health endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "message" in data


class TestUpdateProduct:
    """Test update operations"""
    
    def test_update_product_success(self, sample_product_data):
        """Test successful full product update"""
        # Create product first
        create_response = client.post("/product", json=sample_product_data)
        product_id = create_response.json()["id"]
        
        # Update product
        update_data = {
            "product_name": "Updated Laptop Pro",
            "category": "Premium Electronics",
            "SKU": "LAPUPD001",  # New SKU
            "stock": 75,
            "price": 1299.99
        }
        
        response = client.put(f"/product/{product_id}", json=update_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["product_name"] == "Updated Laptop Pro"
        assert data["category"] == "Premium Electronics"
        assert data["SKU"] == "LAPUPD001"
        assert data["stock"] == 75
        assert data["price"] == 1299.99
        assert data["id"] == product_id
        
    def test_update_product_sku_conflict(self, sample_product_data):
        """Test update with SKU that already exists on different product"""
        # Create two products with different SKUs
        create_response1 = client.post("/product", json=sample_product_data)
        product_id1 = create_response1.json()["id"]
        
        product_data2 = sample_product_data.copy()
        product_data2["SKU"] = "LAPTEST002"
        product_data2["product_name"] = "Second Laptop"
        create_response2 = client.post("/product", json=product_data2)
        product_id2 = create_response2.json()["id"]
        
        # Try to update product2 to use product1's SKU (should fail)
        update_data = product_data2.copy()
        update_data["SKU"] = "LAPTEST001"  # product1's SKU
        
        response = client.put(f"/product/{product_id2}", json=update_data)
        assert response.status_code == 400
        assert "SKU already exists" in response.json()["detail"]
        
    def test_update_product_same_sku_allowed(self, sample_product_data):
        """Test update with same SKU (should succeed)"""
        # Create product
        create_response = client.post("/product", json=sample_product_data)
        product_id = create_response.json()["id"]
        
        # Update product keeping the same SKU
        update_data = sample_product_data.copy()
        update_data["stock"] = 200  # Change stock but keep same SKU
        
        response = client.put(f"/product/{product_id}", json=update_data)
        assert response.status_code == 200
        assert response.json()["SKU"] == sample_product_data["SKU"]
        assert response.json()["stock"] == 200
        
    def test_update_product_not_found(self, sample_product_data):
        """Test update non-existent product"""
        response = client.put("/product/999", json=sample_product_data)
        assert response.status_code == 404
        assert "Product not found" in response.json()["detail"]
        
    def test_update_product_invalid_data(self, sample_product_data):
        """Test update with invalid data"""
        # Create product
        create_response = client.post("/product", json=sample_product_data)
        product_id = create_response.json()["id"]
        
        # Try to update with missing fields
        invalid_data = {"product_name": "Test"}  # Missing required fields
        response = client.put(f"/product/{product_id}", json=invalid_data)
        assert response.status_code == 422


class TestDeleteProduct:
    """Test delete operations"""
    
    def test_delete_product_success(self, sample_product_data):
        """Test successful product deletion"""
        # Create product
        create_response = client.post("/product", json=sample_product_data)
        product_id = create_response.json()["id"]
        
        # Delete product
        response = client.delete(f"/product/{product_id}")
        assert response.status_code == 204
        assert response.text == ""  # No content
        
        # Verify product is deleted
        get_response = client.get(f"/product/{product_id}")
        assert get_response.status_code == 404
        
    def test_delete_product_not_found(self):
        """Test delete non-existent product"""
        response = client.delete("/product/999")
        assert response.status_code == 404
        assert "Product not found" in response.json()["detail"]


class TestCRUDIntegration:
    """End-to-end CRUD workflow integration tests"""
    
    def test_full_crud_cycle(self, sample_product_data):
        """Test complete CRUD cycle: Create → Read → Update → Delete"""
        
        # 1. CREATE
        create_response = client.post("/product", json=sample_product_data)
        assert create_response.status_code == 201
        product_id = create_response.json()["id"]
        print(f"✅ Created product ID: {product_id}")
        
        # 2. READ (single)
        read_response = client.get(f"/product/{product_id}")
        assert read_response.status_code == 200
        assert read_response.json()["id"] == product_id
        assert read_response.json()["stock"] == 50
        print(f"✅ Read product ID: {product_id}")
        
        # 3. UPDATE
        update_data = sample_product_data.copy()
        update_data["stock"] = 100
        update_data["price"] = 1199.99
        update_response = client.put(f"/product/{product_id}", json=update_data)
        assert update_response.status_code == 200
        assert update_response.json()["stock"] == 100
        assert update_response.json()["price"] == 1199.99
        print(f"✅ Updated product ID: {product_id}")
        
        # 4. LIST (verify in list)
        list_response = client.get("/product")
        assert list_response.status_code == 200
        products = list_response.json()
        assert len(products) >= 1
        found = any(p["id"] == product_id and p["stock"] == 100 for p in products)
        assert found
        print(f"✅ Verified product in list")
        
        # 5. DELETE
        delete_response = client.delete(f"/product/{product_id}")
        assert delete_response.status_code == 204
        print(f"✅ Deleted product ID: {product_id}")
        
        # 6. VERIFY DELETED
        final_read = client.get(f"/product/{product_id}")
        assert final_read.status_code == 404
        print(f"✅ Verified product deleted")
        
    def test_multiple_products_workflow(self, sample_product_data):
        """Test managing multiple products"""
        product_ids = []
        
        # Create 3 products
        for i in range(3):
            data = sample_product_data.copy()
            data["SKU"] = f"MULTI{i:03d}"
            data["product_name"] = f"Product {i}"
            data["stock"] = 10 * (i + 1)
            
            response = client.post("/product", json=data)
            assert response.status_code == 201
            product_ids.append(response.json()["id"])
        
        # Verify all exist
        list_response = client.get("/product")
        assert len(list_response.json()) == 3
        
        # Update middle product
        update_data = sample_product_data.copy()
        update_data["SKU"] = "MULTI001"
        update_data["stock"] = 999
        response = client.put(f"/product/{product_ids[1]}", json=update_data)
        assert response.status_code == 200
        assert response.json()["stock"] == 999
        
        # Delete first product
        response = client.delete(f"/product/{product_ids[0]}")
        assert response.status_code == 204
        
        # Verify count
        list_response = client.get("/product")
        assert len(list_response.json()) == 2


class TestEdgeCases:
    """Test edge cases and error handling"""
    
    def test_negative_stock(self, sample_product_data):
        """Test creating product with negative stock"""
        data = sample_product_data.copy()
        data["stock"] = -10
        
        response = client.post("/product", json=data)
        # Should accept (no validation for negative in current implementation)
        # You may want to add validation in main.py
        assert response.status_code == 201
        
    def test_zero_price(self, sample_product_data):
        """Test creating product with zero price"""
        data = sample_product_data.copy()
        data["price"] = 0.0
        
        response = client.post("/product", json=data)
        assert response.status_code == 201
        
    def test_very_long_product_name(self, sample_product_data):
        """Test product with very long name"""
        data = sample_product_data.copy()
        data["product_name"] = "A" * 255  # Max length
        
        response = client.post("/product", json=data)
        assert response.status_code == 201
        
    def test_special_characters_in_sku(self, sample_product_data):
        """Test SKU with special characters"""
        data = sample_product_data.copy()
        data["SKU"] = "TEST-SKU_001.V2"
        
        response = client.post("/product", json=data)
        assert response.status_code == 201
        assert response.json()["SKU"] == "TEST-SKU_001.V2"
        
    def test_large_pagination_limit(self):
        """Test pagination with very large limit"""
        response = client.get("/product?skip=0&limit=10000")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


# Run specific test classes:
# pytest test_main.py::TestProductEndpoints -v
# pytest test_main.py::TestUpdateProduct -v
# pytest test_main.py::TestDeleteProduct -v
# pytest test_main.py::TestCRUDIntegration -v
# pytest test_main.py::TestEdgeCases -v

# Run all tests:
# pytest test_main.py -v

# Run with coverage:
# pytest test_main.py -v --cov=main --cov-report=html