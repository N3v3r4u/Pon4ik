from dataclasses import dataclass
from typing import Optional
import strawberry
from strawberry.types import Info

#Типы данных

@strawberry.type(description="Товар в каталоге")
@dataclass
class Product:
    id: strawberry.ID
    name: str
    price: float

@strawberry.type(description="Позиция заказа")
class OrderItem:
    productId: str
    quantity: int

    @strawberry.field(description="Данные товара (подгружается из Catalog)")
    async def product(self, info: Info) -> Optional[Product]:
        product_dict = await info.context["product_loader"].load(self.productId)
        if product_dict is None:
            return None
        return Product(id=product_dict["id"], name=product_dict["name"], price=product_dict["price"])

@strawberry.type(description="Заказ пользователя")
@dataclass
class Order:
    id: strawberry.ID
    userId: strawberry.ID
    createdAt: str
    items: list[OrderItem]

#Резолверы

@strawberry.type
class Query:
    @strawberry.field(
        name="ordersByUserId", 
        description="Получить все заказы пользователя с деталями товаров"
    )
    async def orders_by_user(self, userId: strawberry.ID, info: Info) -> list[Order]:
        orders_data = await info.context["fetch_orders"](str(userId))
        
        # Явно собираем объекты из словарей
        result = []
        for o in orders_data:
            items = [OrderItem(productId=i["productId"], quantity=i["quantity"]) for i in o["items"]]
            result.append(Order(id=o["id"], userId=o["userId"], createdAt=o["createdAt"], items=items))
            
        return result

schema = strawberry.Schema(query=Query)