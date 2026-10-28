import os
import socket
import asyncio
from contextlib import asynccontextmanager
from datetime import date
from typing import Optional
from uuid import uuid4

import requests
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

INSTANCE_NAME = os.environ.get("INSTANCE_NAME", "catalog-unknown")
CONSUL_HOST = os.environ.get("CONSUL_HOST", "consul")
CONSUL_PORT = os.environ.get("CONSUL_PORT", "8500")
SERVICE_PORT = int(os.environ.get("PORT", "8000"))

#Модели

class ProductCreate(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    price: float = Field(gt=0)
    description: Optional[str] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=100)
    price: Optional[float] = Field(default=None, gt=0)
    description: Optional[str] = None


class Product(BaseModel):
    id: str
    name: str
    price: float
    description: Optional[str] = None


class PaginatedProducts(BaseModel):
    instance_id: str
    page: int
    page_size: int
    total: int
    total_pages: int
    items: list[Product]

products_db: dict[str, dict] = {}

#Сид

SEED_PRODUCTS = {
    "prod-1": {"id": "prod-1", "name": "Микрофон", "price": 15000.0, "description": "Для стримов"},
    "prod-2": {"id": "prod-2", "name": "Кольцевая лампа", "price": 3000.0, "description": "Освещение"},
    "prod-3": {"id": "prod-3", "name": "Звуковая карта", "price": 8000.0, "description": "Для записи"},
}


def _seed_products():
    for pid, product in SEED_PRODUCTS.items():
        if pid not in products_db:
            products_db[pid] = product.copy()

#Работа с Consul

def register_in_consul():
    service_id = f"{INSTANCE_NAME}-{socket.gethostname()}"
    ip = socket.gethostbyname(socket.gethostname())
    payload = {
        "Name": "catalog",
        "ID": service_id,
        "Address": ip,
        "Port": SERVICE_PORT,
        "Check": {
            "HTTP": f"http://{ip}:{SERVICE_PORT}/health",
            "Interval": "10s",
            "Timeout": "3s",
        },
    }
    url = f"http://{CONSUL_HOST}:{CONSUL_PORT}/v1/agent/service/register"
    for attempt in range(10):
        try:
            r = requests.put(url, json=payload, timeout=3)
            if r.status_code == 200:
                print(f"[consul] Registered {service_id} as 'catalog'")
                return
        except requests.RequestException as e:
            print(f"[consul] Attempt {attempt + 1}: {e}")
        asyncio.sleep(2)


def deregister_from_consul():
    service_id = f"{INSTANCE_NAME}-{socket.gethostname()}"
    url = f"http://{CONSUL_HOST}:{CONSUL_PORT}/v1/agent/service/deregister/{service_id}"
    try:
        requests.put(url, timeout=3)
        print(f"[consul] Deregistered {service_id}")
    except requests.RequestException as e:
        print(f"[consul] Deregistration failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _seed_products()
    register_in_consul()
    yield
    deregister_from_consul()


app = FastAPI(
    title="Catalog Service",
    description="Каталог товаров (целей сбора)",
    version="1.0.0",
    docs_url="/api/catalog/docs",
    openapi_url="/api/catalog/openapi.json",
    lifespan=lifespan,
)

#Эндпоинты

@app.get("/health")
def health():
    return {"status": "ok", "instance_id": INSTANCE_NAME}


@app.get("/api/catalog/products", response_model=PaginatedProducts)
def list_products(
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(10, ge=1, le=100, description="Размер страницы"),
):
    all_products = list(products_db.values())
    total = len(all_products)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "instance_id": INSTANCE_NAME,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "items": all_products[start:end],
    }

@app.get("/api/catalog/products/batch", response_model=list[Product])
def get_products_batch(ids: str = Query(..., description="Comma-separated product IDs")):
    id_list = [pid.strip() for pid in ids.split(",") if pid.strip()]
    return [products_db[pid] for pid in id_list if pid in products_db]

@app.get("/api/catalog/products/{product_id}", response_model=Product)
def get_product(product_id: str):
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Product not found")
    return products_db[product_id]


@app.post("/api/catalog/products", response_model=Product, status_code=201)
def create_product(product: ProductCreate):
    new_id = str(uuid4())
    new_product = {
        "id": new_id,
        "name": product.name,
        "price": product.price,
        "description": product.description,
    }
    products_db[new_id] = new_product
    return new_product


@app.put("/api/catalog/products/{product_id}", response_model=Product)
def update_product(product_id: str, updates: ProductUpdate):
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Product not found")
    product = products_db[product_id]
    if updates.name is not None:
        product["name"] = updates.name
    if updates.price is not None:
        product["price"] = updates.price
    if updates.description is not None:
        product["description"] = updates.description
    return product


@app.delete("/api/catalog/products/{product_id}")
def delete_product(product_id: str):
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Product not found")
    del products_db[product_id]
    return {"message": f"Product {product_id} deleted"}

