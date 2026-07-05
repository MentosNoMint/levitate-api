import asyncio
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from app.api.routers.v1.chat import router as v1_router
from app.api.routers.admin import router as admin_router
from app.api.routers.auth import router as auth_router
from app.workers.worker import start_worker
from app.db.models import Base
from app.db.session import engine

import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    worker_task = asyncio.create_task(start_worker())
    yield
    worker_task.cancel()

app = FastAPI(title="LiteLLM Backend Gateway", lifespan=lifespan)

frontend_url = os.getenv("FRONTEND_URL")
origins = ["http://localhost:3000"]
if frontend_url:
    origins.append(frontend_url.strip())

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/v1")
app.include_router(auth_router, prefix="/admin/auth")
app.include_router(admin_router, prefix="/admin")


@app.get("/health")
async def health_check():
    return {"status": "ok"}


from fastapi.responses import RedirectResponse

@app.get("/version")
async def get_version():
    return {"version": "1.40.0"}


@app.get("/props")
async def get_props():
    return {"props": {}}


@app.get("/api/tags")
async def get_ollama_tags():
    return {"models": []}


@app.post("/api/show")
async def post_ollama_show():
    return {}


@app.get("/api/v1/models")
async def get_api_v1_models():
    return RedirectResponse(url="/v1/models")

