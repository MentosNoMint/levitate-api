import asyncio
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routers.v1.chat import router as v1_router
from app.api.routers.admin import router as admin_router
from app.api.routers.auth import router as auth_router
from app.workers.worker import start_worker
from app.db.models import Base
from app.db.session import engine

import os

app = FastAPI(title="LiteLLM Backend Gateway")

frontend_url = os.getenv("FRONTEND_URL")
origins = ["http://localhost:3000"]
if frontend_url:
    origins.append(frontend_url.strip())

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/v1")
app.include_router(auth_router, prefix="/admin/auth")
app.include_router(admin_router, prefix="/admin")

@app.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    asyncio.create_task(start_worker())

@app.get("/health")
async def health_check():
    return {"status": "ok"}
