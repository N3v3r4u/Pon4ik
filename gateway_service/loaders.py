from strawberry.dataloader import DataLoader
from clients import fetch_products_batch

async def load_products_batch(product_ids: list[str]) -> list[dict]: #возвращает сырые словари
    products_data = await fetch_products_batch(product_ids)
    by_id = {p["id"]: p for p in products_data}
    return [by_id.get(pid) for pid in product_ids]

def create_product_loader() -> DataLoader:
    return DataLoader(load_fn=load_products_batch)