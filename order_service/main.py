import os
import socket
import asyncio
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI, Query
from pydantic import BaseModel

INSTANCE_NAME = os.environ.get("INSTANCE_NAME", "order-1")
CONSUL_HOST = os.environ.get("CONSUL_HOST", "consul")
CONSUL_PORT = os.environ.get("CONSUL_PORT", "8500")
SERVICE_PORT = int(os.environ.get("PORT", "8000"))

#Модели

class OrderItem(BaseModel):
    productId: str
    quantity: int


class Order(BaseModel):
    id: str
    userId: str
    createdAt: str
    items: list[OrderItem]


#Сид

orders_db: dict[str, dict] = {
    "order-1": {
        "id": "order-1",
        "userId": "user-123",
        "createdAt": "2026-10-28T14:32:00Z",
        "items": [
            {"productId": "prod-1", "quantity": 2},
            {"productId": "prod-2", "quantity": 1},
        ],
    },
    "order-2": {
        "id": "order-2",
        "userId": "user-456",
        "createdAt": "2026-10-27T10:15:00Z",
        "items": [
            {"productId": "prod-3", "quantity": 5},
        ],
    },
    "order-3": {
        "id": "order-3",
        "userId": "user-123",
        "createdAt": "2026-10-26T18:00:00Z",
        "items": [
            {"productId": "prod-2", "quantity": 3},
        ],
    },
}

#Работа с Consul

def register_in_consul():
    service_id = f"{INSTANCE_NAME}-{socket.gethostname()}"
    ip = socket.gethostbyname(socket.gethostname())
    payload = {
        "Name": "order",
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
                print(f"[consul] Registered {service_id} as 'order'")
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
    register_in_consul()
    yield
    deregister_from_consul()

app = FastAPI(
    title="Order Service",
    description="Сервис заказов (донатов)",
    version="1.0.0",
    lifespan=lifespan,
)

#Эндпоинты

@app.get("/health")
def health():
    return {"status": "ok", "instance_id": INSTANCE_NAME}


@app.get("/api/orders", response_model=list[Order])
def list_orders(userId: str = Query(..., description="ID пользователя")):
    result = [o for o in orders_db.values() if o["userId"] == userId]
    return result