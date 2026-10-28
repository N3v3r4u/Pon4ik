import os
import socket
import asyncio
from contextlib import asynccontextmanager

import requests
import strawberry
from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

from clients import fetch_orders_by_user
from loaders import create_product_loader
from schema import schema


INSTANCE_NAME = os.environ.get("INSTANCE_NAME", "gateway-1")
CONSUL_HOST = os.environ.get("CONSUL_HOST", "consul")
CONSUL_PORT = os.environ.get("CONSUL_PORT", "8500")
SERVICE_PORT = int(os.environ.get("PORT", "8000"))


async def get_context():
    return {
        "fetch_orders": fetch_orders_by_user,
        "product_loader": create_product_loader(),
    }


graphql_app = GraphQLRouter(schema, context_getter=get_context)


def register_in_consul():
    service_id = f"{INSTANCE_NAME}-{socket.gethostname()}"
    ip = socket.gethostbyname(socket.gethostname())
    payload = {
        "Name": "gateway",
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
                print(f"[consul] Registered {service_id} as 'gateway'")
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
    title="GraphQL Gateway",
    description="Агрегация Order + Catalog через GraphQL",
    docs_url="/api/gateway/docs",
    openapi_url="/api/gateway/openapi.json",
    lifespan=lifespan,
)

app.include_router(graphql_app, prefix="/graphql")


@app.get("/health")
def health():
    return {"status": "ok", "instance_id": INSTANCE_NAME}