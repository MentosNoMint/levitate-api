import uuid
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.api.deps import get_db, get_current_user, get_current_admin
from app.db.models import User
from app.api.schemas.credential import CredentialCreate, CredentialUpdate
from app.api.schemas.virtual_key import VirtualKeyCreate, VirtualKeyUpdate
from app.services import credential_service, virtual_key_service, stats_service

router = APIRouter(dependencies=[Depends(get_current_admin)])

@router.get("/credentials")
async def list_credentials(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await credential_service.list_credentials(db, current_user.id)

@router.post("/credentials")
async def create_credential(
    payload: CredentialCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await credential_service.create_credential(db, payload, current_user.id)

@router.put("/credentials/{id}")
async def update_credential(
    id: str,
    payload: CredentialUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        cred_id = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid credential ID format")
    return await credential_service.update_credential(db, cred_id, payload, current_user.id)

@router.delete("/credentials/{id}")
async def delete_credential(
    id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        cred_id = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid credential ID format")
    return await credential_service.delete_credential(db, cred_id, current_user.id)

@router.post("/credentials/{id}/test")
async def test_credential(
    id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        cred_id = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid credential ID format")
    return await credential_service.test_credential(db, cred_id, current_user.id)

@router.get("/virtual-keys")
async def list_virtual_keys(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await virtual_key_service.list_virtual_keys(db, current_user.id)

@router.post("/virtual-keys")
async def create_virtual_key(
    payload: VirtualKeyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await virtual_key_service.create_virtual_key(db, payload, current_user.id)

@router.put("/virtual-keys/{id}")
async def update_virtual_key(id: str, payload: VirtualKeyUpdate, db: AsyncSession = Depends(get_db)):
    try:
        vkey_id = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid virtual key ID format")
    return await virtual_key_service.update_virtual_key(db, vkey_id, payload)

@router.delete("/virtual-keys/{id}")
async def delete_virtual_key(id: str, db: AsyncSession = Depends(get_db)):
    try:
        vkey_id = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid virtual key ID format")
    return await virtual_key_service.delete_virtual_key(db, vkey_id)

@router.get("/stats")
async def get_stats(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await stats_service.get_stats(db, current_user.id)

@router.get("/logs")
async def get_logs(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await stats_service.get_logs(db, current_user.id)

@router.delete("/logs")
async def clear_logs(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await stats_service.clear_logs(db, current_user.id)

class SimulateRequest(BaseModel):
    model: Optional[str] = None
    prompt: Optional[str] = None

@router.post("/logs/simulate")
async def simulate_log(
    payload: Optional[SimulateRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    model = payload.model if payload else None
    prompt = payload.prompt if payload else None
    return await stats_service.simulate_log(db, current_user.id, model=model, prompt=prompt)

@router.post("/credentials/{id}/refresh-quota")
async def refresh_credential_quota(
    id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        cred_id = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid credential ID format")
    return await credential_service.refresh_credential_quota(db, cred_id, current_user.id)

@router.post("/credentials/refresh-all-quotas")
async def refresh_all_quotas(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await credential_service.refresh_all_quotas(db, current_user.id)
