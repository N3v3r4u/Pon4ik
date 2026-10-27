import os
import asyncio
import socket
from datetime import date
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

import requests

CONSUL_HOST = os.environ.get("CONSUL_HOST", "consul")
CONSUL_PORT = os.environ.get("CONSUL_PORT", "8500")
SERVICE_PORT = int(os.environ.get("PORT", "8000"))

def register_in_consul(): #регистрация
    service_id = f"{INSTANCE_NAME}-{socket.gethostname()}"

    payload = {
        "Name": "catalog",
        "ID": service_id,
        "Address": socket.gethostbyname(socket.gethostname()),
        "Port": SERVICE_PORT,
        "Check": {
            "HTTP": f"http://{socket.gethostbyname(socket.gethostname())}:{SERVICE_PORT}/",
            "Interval": "10s",
            "Timeout": "3s",
        },
    }

    url = f"http://{CONSUL_HOST}:{CONSUL_PORT}/v1/agent/service/register"

    for attempt in range(10):
        try:
            response = requests.put(url, json=payload, timeout=3)
            if response.status_code == 200:
                print(f"[consul] Registered {service_id} as 'catalog'")
                return
            print(f"[consul] Attempt {attempt + 1}: HTTP {response.status_code}")
        except requests.RequestException as e:
            print(f"[consul] Attempt {attempt + 1}: {e}")
        asyncio.sleep(2)

    print("[consul] Failed to register after 10 attempts — continuing without Consul")

def deregister_from_consul(): #дерегистрация
    service_id = f"{INSTANCE_NAME}-{socket.gethostname()}"
    url = f"http://{CONSUL_HOST}:{CONSUL_PORT}/v1/agent/service/deregister/{service_id}"
    try:
        response = requests.put(url, timeout=3)
        if response.status_code == 200:
            print(f"[consul] Deregistered {service_id}")
    except requests.RequestException as e:
        print(f"[consul] Deregistration failed: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # === STARTUP ===
    register_in_consul()
    yield
    # === SHUTDOWN ===
    deregister_from_consul()




app = FastAPI(title="Catalog Service — Goals", lifespan=lifespan)

INSTANCE_NAME = os.environ.get("INSTANCE_NAME", "catalog-unknown")

class GoalCreate(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    description: Optional[str] = None
    target_amount: float = Field(gt=0, description="Сумма цели, больше 0")
    deadline: Optional[date] = None


class GoalUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=100)
    description: Optional[str] = None
    target_amount: Optional[float] = Field(default=None, gt=0)
    deadline: Optional[date] = None
    status: Optional[str] = None


class Goal(BaseModel):
    id: str
    author_id: str
    title: str
    description: Optional[str] = None
    target_amount: float
    collected_amount: float
    deadline: Optional[date] = None
    status: str
    created_at: date

# In-memory хранилище: goal_id -> словарь с данными цели
goals_db: dict[str, dict] = {}

VALID_STATUSES = {"active", "completed", "closed"}


def _now() -> date: # вынесено в функцию для удобства тестирования
    return date.today()


def _new_goal_dict(goal: "GoalCreate", author_id: str) -> dict:
    return {
        "id": str(uuid4()),
        "author_id": author_id,
        "title": goal.title,
        "description": goal.description,
        "target_amount": goal.target_amount,
        "collected_amount": 0.0,
        "deadline": goal.deadline,
        "status": "active",
        "created_at": _now(),
    }

@app.get("/")
def root():
    return {
        "service": "catalog",
        "instance_id": INSTANCE_NAME,
        "status": "ok",
    }

@app.get("/goals")
def list_goals():
    return {
        "instance_id": INSTANCE_NAME,
        "count": len(goals_db),
        "goals": list(goals_db.values()),
    }

@app.post("/goals", response_model=Goal, status_code=201)
def create_goal(goal: GoalCreate, author_id: str):
    new_goal = _new_goal_dict(goal, author_id)
    goals_db[new_goal["id"]] = new_goal
    return new_goal

@app.put("/goals/{goal_id}", response_model=Goal)
def update_goal(goal_id: str, updates: GoalUpdate):
    if goal_id not in goals_db:
        raise HTTPException(status_code=404, detail="Goal not found")

    if updates.status is not None and updates.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Allowed: {sorted(VALID_STATUSES)}",
        )

    goal = goals_db[goal_id]

    if updates.title is not None:
        goal["title"] = updates.title
    if updates.description is not None:
        goal["description"] = updates.description
    if updates.target_amount is not None:
        goal["target_amount"] = updates.target_amount
    if updates.deadline is not None:
        goal["deadline"] = updates.deadline
    if updates.status is not None:
        goal["status"] = updates.status

    return goal

@app.delete("/goals/{goal_id}")
def delete_goal(goal_id: str):
    if goal_id not in goals_db:
        raise HTTPException(status_code=404, detail="Goal not found")

    del goals_db[goal_id]
    return {"message": f"Goal {goal_id} deleted"}

