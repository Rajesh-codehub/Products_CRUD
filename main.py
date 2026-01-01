# OM NAMAH SHIVAYYA
# OM NAMO VENKATESHAYA

import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status, Depends, Request
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, func, select, exc
from sqlalchemy.orm import Session, sessionmaker, DeclarativeBase
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from dotenv import load_dotenv
import mysql.connector


load_dotenv()

# Setup logging - writes to app.log + console
LOG_FILE = Path("app.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logger.error("DATABASE_URL not found in .env")
    raise ValueError("DATABASE_URL required")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = DeclarativeBase()

class Base(DeclarativeBase):  # ✅ Subclass the class
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class Products(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, autoincrement=True)
    product_name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    SKU = Column(String(100), unique=True, nullable=False)
    stock = Column(Integer, default=0, nullable=False)
    price = Column(Float(precision=2), nullable=False)
    status = Column(String(50), default='active', nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

Base.metadata.create_all(bind=engine)
logger.info("Database tables created")

# Pydantic models
class ProductCreate(BaseModel):
    product_name: str
    category: str
    SKU: str
    stock: int
    price: float

class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_name: str
    category: str
    SKU: str
    stock: int
    price: float
    status: str
    created_at: datetime
    updated_at: datetime

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting...")
    yield
    logger.info("Application shutting down...")

app = FastAPI(lifespan=lifespan)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response

@app.post("/product", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    logger.info(f"Creating product: {product.SKU} - {product.product_name}")
    # Check SKU uniqueness
    existing = db.execute(select(Products).where(Products.SKU == product.SKU)).scalar_one_or_none()
    if existing:
        logger.warning(f"SKU already exists: {product.SKU}")
        raise HTTPException(status_code=400, detail="SKU already exists")
    try:
        
        db_product = Products(**product.model_dump())
        db.add(db_product)
        db.commit()
        db.refresh(db_product)
        logger.info(f"Product created successfully: ID={db_product.id}, SKU={db_product.SKU}")
        return db_product
    except exc.IntegrityError as e:
        logger.error(f"Database integrity error: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=400, detail="Database constraint violation")
    except Exception as e:
        logger.error(f"Unexpected error creating product: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/product/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    logger.info(f"Fetching product ID: {product_id}")
    product = db.get(Products, product_id)
    if not product:
        logger.warning(f"Product not found: ID={product_id}")
        raise HTTPException(status_code=404, detail="Product not found")
    logger.info(f"Product retrieved: ID={product.id}")
    return product


@app.get("/product", response_model=list[ProductResponse])
def get_products(db: Session = Depends(get_db), skip: int = 0, limit: int = 100):
    logger.info(f"Fetching products: skip={skip}, limit={limit}")
    try:
        products = db.execute(select(Products).offset(skip).limit(limit)).scalars().all()
        logger.info(f"Retrieved {len(products)} products")
        return products
    except Exception as e:
        logger.error(f"Error fetching products list: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    
@app.put("/product/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int, 
    product_update: ProductCreate,  # Reuse or create ProductUpdate
    db: Session = Depends(get_db)
):
    logger.info(f"Updating product ID: {product_id}")
    
    # Get existing product
    db_product = db.get(Products, product_id)
    if not db_product:
        logger.warning(f"Product not found for update: {product_id}")
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Check SKU conflict (if changed)
    if product_update.SKU != db_product.SKU:
        existing_sku = db.execute(
            select(Products).where(Products.SKU == product_update.SKU)
        ).scalar_one_or_none()
        if existing_sku:
            raise HTTPException(status_code=400, detail="SKU already exists")
    
    # Update fields
    update_data = product_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_product, field, value)
    
    db.commit()
    db.refresh(db_product)
    logger.info(f"Product updated successfully: ID={db_product.id}")
    return db_product

@app.delete("/product/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    logger.info(f"Deleting product ID: {product_id}")
    
    db_product = db.get(Products, product_id)
    if not db_product:
        logger.warning(f"Product not found for delete: {product_id}")
        raise HTTPException(status_code=404, detail="Product not found")
    
    db.delete(db_product)
    db.commit()
    logger.info(f"Product deleted successfully: ID={product_id}")
    return None  # 204 No Content

@app.get("/health")
def health_check():
    logger.info("Health check requested")
    return {"status": "healthy", "message": "Product API running"}
