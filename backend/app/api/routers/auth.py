from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.db.models import User
from app.services import auth_service

router = APIRouter()

@router.get("/config")
async def get_auth_config():
    return {
        "google_oauth_configured": auth_service.get_google_oauth_configured(),
        "mock_auth_enabled": auth_service.ALLOW_MOCK_AUTH
    }

@router.get("/login")
async def auth_login(action: Optional[str] = Query(None), token: Optional[str] = Query(None)):
    url = auth_service.get_login_url(action, token)
    return RedirectResponse(url=url)

@router.get("/callback")
async def auth_callback(
    code: str = Query(...),
    state: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    url = await auth_service.handle_oauth_callback(code, state, db)
    return RedirectResponse(url=url)

@router.get("/mock")
async def auth_mock(db: AsyncSession = Depends(get_db)):
    if not auth_service.ALLOW_MOCK_AUTH:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mock authentication is disabled in this environment"
        )
    url = await auth_service.handle_mock_login(db)
    return RedirectResponse(url=url)

@router.get("/me")
async def auth_me(current_user: User = Depends(get_current_user)):
    return {
        "email": current_user.email,
        "role": current_user.role,
        "id": str(current_user.id)
    }
