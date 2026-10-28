from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncio
import socket
from contextlib import asynccontextmanager
import os
import requests

import jwt
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel

INSTANCE_NAME = os.environ.get("INSTANCE_NAME", "auth-1")

CONSUL_HOST = os.environ.get("CONSUL_HOST", "consul")
CONSUL_PORT = os.environ.get("CONSUL_PORT", "8500")
SERVICE_PORT = int(os.environ.get("PORT", "8000"))


def register_in_consul():
    service_id = f"{INSTANCE_NAME}-{socket.gethostname()}"

    payload = {
        "Name": "auth",
        "ID": service_id,
        "Address": socket.gethostbyname(socket.gethostname()),
        "Port": SERVICE_PORT,
        "Check": {
            "HTTP": f"http://{socket.gethostbyname(socket.gethostname())}:{SERVICE_PORT}/health",
            "Interval": "10s",
            "Timeout": "3s",
        },
    }

    url = f"http://{CONSUL_HOST}:{CONSUL_PORT}/v1/agent/service/register"

    for attempt in range(10):
        try:
            response = requests.put(url, json=payload, timeout=3)
            if response.status_code == 200:
                print(f"[consul] Registered {service_id} as 'auth'")
                return
            print(f"[consul] Attempt {attempt + 1}: HTTP {response.status_code}")
        except requests.RequestException as e:
            print(f"[consul] Attempt {attempt + 1}: {e}")
        asyncio.sleep(2)

    print("[consul] Failed to register after 10 attempts — continuing without Consul")

def deregister_from_consul():
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

SECRET_KEY = "change me in production pls"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

users_db: dict[str, dict] = {} # in memory

# --- Хэширование паролей ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Схема извлечения токена из заголовка ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

app = FastAPI(
    title="Auth Service",
    docs_url="/api/auth/docs",
    openapi_url="/api/auth/openapi.json",
    lifespan=lifespan,
)


class UserRegister(BaseModel): # /register
    username: str
    password: str

class Token(BaseModel): # /login
    access_token: str
    token_type: str


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    if username not in users_db:
        raise credentials_exception

    return username

@app.post("/api/auth/register")
def register(user: UserRegister):
    if user.username in users_db:
        raise HTTPException(status_code=400, detail="Username already registered")

    users_db[user.username] = {
        "username": user.username,
        "hashed_password": get_password_hash(user.password),
    }
    return {"message": "User registered successfully"}


@app.post("/api/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = users_db.get(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user["username"]})
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/api/auth/me")
def read_me(current_user: str = Depends(get_current_user)):
    return {"username": current_user, "message": f"Hello, {current_user}!"}

@app.get("/health")
def health():
    return {"status": "ok", "instance_id": INSTANCE_NAME}