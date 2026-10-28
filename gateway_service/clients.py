import httpx

ORDER_SERVICE_URL = "http://order:8000"
CATALOG_SERVICE_URL = "http://catalog-1:8000"


async def fetch_orders_by_user(user_id: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(
            f"{ORDER_SERVICE_URL}/api/orders",
            params={"userId": user_id},
        )
        response.raise_for_status()
        return response.json()


async def fetch_products_batch(product_ids: list[str]) -> list[dict]:
    if not product_ids:
        return []
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(
            f"{CATALOG_SERVICE_URL}/api/catalog/products/batch",
            params={"ids": ",".join(product_ids)},
        )
        response.raise_for_status()
        return response.json()