# Authentication Security Fixes Implementation Plan

> **For Antigravity:** REQUIRED SUB-SKILL: Load executing-plans to implement this plan task-by-task.

**Goal:** Secure the application's authentication and authorization systems for production deployment.

**Architecture:** 
- Enforce strict environment variables verification (`APP_ENV`, `ENCRYPTION_KEY`, `ALLOW_MOCK_AUTH`, `ALLOWED_ADMIN_EMAILS`).
- Implement true role-based access control (RBAC) on the backend using a new dependency (`get_current_admin`).
- Resolve Broken Object Level Authorization (IDOR) in virtual key management by verifying user ownership.
- Secure the frontend by conditionally rendering developer elements based on backend config.

**Tech Stack:** FastAPI, SQLAlchemy, Next.js, Zustand

---

### Task 1: Environment Safety & Encryption Enforcement

**Files:**
- Create: `backend/app/core/config.py` (optional, or modify `backend/app/crypto/cipher.py` and `backend/app/security/auth.py` directly)
- Modify: [cipher.py](file:///C:/Repos/levitate-api/backend/app/crypto/cipher.py)
- Modify: [auth.py](file:///C:/Repos/levitate-api/backend/app/security/auth.py)
- Modify: [.env.example](file:///C:/Repos/levitate-api/.env.example)

**Step 1: Update .env.example**
Add environment variables for configuration safety:
```ini
APP_ENV=development
ALLOW_MOCK_AUTH=true
ALLOWED_ADMIN_EMAILS=admin@levitate.ai,dev-user@levitate.ai
```

**Step 2: Enforce encryption variables in cipher.py**
Throw a `RuntimeError` on startup if `APP_ENV == "production"` and `ENCRYPTION_KEY` is empty, missing, or uses the static dev fallback.
```python
import os
import base64
from cryptography.fernet import Fernet

app_env = os.getenv("APP_ENV", "development").lower()
_key = os.getenv("ENCRYPTION_KEY")

if app_env == "production":
    if not _key or _key == "vwW6pdYns-N3IpM4slyoaCUl8hwdY01EizkJvvyytz8=":
        raise RuntimeError("ENCRYPTION_KEY must be securely configured in production mode!")
else:
    if not _key:
        _key = base64.urlsafe_b64encode(b"01234567890123456789012345678901")

# Rest of the key processing...
```

**Step 3: Enforce auth signature key in auth.py**
Ensure `AUTH_SECRET` throws an error in production if it's set to the dev default.
```python
app_env = os.getenv("APP_ENV", "development").lower()
AUTH_SECRET = os.getenv("ENCRYPTION_KEY")

if app_env == "production":
    if not AUTH_SECRET or AUTH_SECRET == "vwW6pdYns-N3IpM4slyoaCUl8hwdY01EizkJvvyytz8=":
        raise RuntimeError("ENCRYPTION_KEY must be set to sign user tokens securely in production!")
else:
    if not AUTH_SECRET:
        AUTH_SECRET = "dev-auth-secret-key-32-chars-minimum-for-security"
```

**Step 4: Verify backend fails to start in production mode without ENCRYPTION_KEY**
Write a temporary test or verify startup behavior.
Expected: Starting with `APP_ENV=production` and empty `ENCRYPTION_KEY` crashes immediately with `RuntimeError`.

**Step 5: Commit changes**
Commit with: `feat(security): enforce secure encryption keys in production`

---

### Task 2: Backend Admin Role Verification

**Files:**
- Modify: [auth.py](file:///C:/Repos/levitate-api/backend/app/security/auth.py)
- Modify: [deps.py](file:///C:/Repos/levitate-api/backend/app/api/deps.py)
- Modify: [admin.py](file:///C:/Repos/levitate-api/backend/app/api/routers/admin.py)

**Step 1: Add `get_current_admin` dependency in auth.py**
```python
async def get_current_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user
```

**Step 2: Export `get_current_admin` in deps.py**
```python
from app.db.session import get_db
from app.security.auth import get_current_user, get_current_admin
```

**Step 3: Secure admin router using get_current_admin**
In `backend/app/api/routers/admin.py`, replace:
```python
router = APIRouter(dependencies=[Depends(get_current_user)])
```
with:
```python
router = APIRouter(dependencies=[Depends(get_current_admin)])
```

**Step 4: Verify access control**
Verify that non-admin tokens receive a 403 Forbidden on any `/admin/*` route.

**Step 5: Commit changes**
Commit with: `feat(security): restrict admin routes to users with admin role`

---

### Task 3: Safe Google OAuth Registration & Allowed Emails Config

**Files:**
- Modify: [auth_service.py](file:///C:/Repos/levitate-api/backend/app/services/auth_service.py)

**Step 1: Implement ALLOWED_ADMIN_EMAILS parsing**
In `auth_service.py`, read and split `ALLOWED_ADMIN_EMAILS`:
```python
ALLOWED_ADMIN_EMAILS = [
    email.strip().lower() 
    for email in os.getenv("ALLOWED_ADMIN_EMAILS", "").split(",") 
    if email.strip()
]
```

**Step 2: Assign roles based on white list**
In `handle_oauth_callback`, replace user registration logic:
```python
        if not user:
            role = "admin" if email.lower() in ALLOWED_ADMIN_EMAILS else "user"
            user = User(email=email, role=role)
            db.add(user)
            await db.commit()
            await db.refresh(user)
```
*(If `ALLOWED_ADMIN_EMAILS` is empty, all new registrations default to `"user"`).*

**Step 3: Commit changes**
Commit with: `feat(security): restrict admin creation during OAuth to ALLOWED_ADMIN_EMAILS`

---

### Task 4: Disable Mock Authentication in Production

**Files:**
- Modify: [auth_service.py](file:///C:/Repos/levitate-api/backend/app/services/auth_service.py)
- Modify: [auth.py](file:///C:/Repos/levitate-api/backend/app/api/routers/auth.py)

**Step 1: Define `ALLOW_MOCK_AUTH` config**
In `auth_service.py`:
```python
app_env = os.getenv("APP_ENV", "development").lower()
ALLOW_MOCK_AUTH = os.getenv("ALLOW_MOCK_AUTH", "true").lower() == "true"
if app_env == "production":
    ALLOW_MOCK_AUTH = False
```

**Step 2: Protect `/admin/auth/mock` endpoint**
In `backend/app/api/routers/auth.py`:
```python
@router.get("/mock")
async def auth_mock(db: AsyncSession = Depends(get_db)):
    if not auth_service.ALLOW_MOCK_AUTH:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mock authentication is disabled in this environment"
        )
    url = await auth_service.handle_mock_login(db)
    return RedirectResponse(url=url)
```

**Step 3: Protect URL generation in get_login_url**
In `auth_service.py`, prevent generating mock redirect url if disabled:
```python
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            if not ALLOW_MOCK_AUTH:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="OAuth credentials are not configured"
                )
            return "/admin/auth/mock"
```

**Step 4: Expose mock configuration via config endpoint**
In `backend/app/api/routers/auth.py`:
```python
@router.get("/config")
async def get_auth_config():
    return {
        "google_oauth_configured": auth_service.get_google_oauth_configured(),
        "mock_auth_enabled": auth_service.ALLOW_MOCK_AUTH
    }
```

**Step 5: Commit changes**
Commit with: `feat(security): disable mock authentication in production mode`

---

### Task 5: Broken Object Level Authorization (IDOR) Fix in Virtual Keys

**Files:**
- Modify: [admin.py](file:///C:/Repos/levitate-api/backend/app/api/routers/admin.py)
- Modify: [virtual_key_service.py](file:///C:/Repos/levitate-api/backend/app/services/virtual_key_service.py)

**Step 1: Update API controller parameter signatures**
In `backend/app/api/routers/admin.py`, inject `current_user` and forward it:
```python
@router.put("/virtual-keys/{id}")
async def update_virtual_key(
    id: str, 
    payload: VirtualKeyUpdate, 
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        vkey_id = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid virtual key ID format")
    return await virtual_key_service.update_virtual_key(db, vkey_id, payload, current_user.id)

@router.delete("/virtual-keys/{id}")
async def delete_virtual_key(
    id: str, 
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        vkey_id = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid virtual key ID format")
    return await virtual_key_service.delete_virtual_key(db, vkey_id, current_user.id)
```

**Step 2: Update virtual_key_service logic**
In `backend/app/services/virtual_key_service.py`:
```python
async def update_virtual_key(db: AsyncSession, vkey_id: uuid.UUID, payload: VirtualKeyUpdate, user_id: uuid.UUID) -> Dict[str, Any]:
    stmt = select(VirtualKey).where(VirtualKey.id == vkey_id, VirtualKey.user_id == user_id)
    result = await db.execute(stmt)
    vkey = result.scalar_one_or_none()
    if not vkey:
        raise HTTPException(status_code=404, detail="Virtual Key not found or access denied")
    # ... rest of the code
```
And:
```python
async def delete_virtual_key(db: AsyncSession, vkey_id: uuid.UUID, user_id: uuid.UUID) -> Dict[str, Any]:
    stmt = select(VirtualKey).where(VirtualKey.id == vkey_id, VirtualKey.user_id == user_id)
    result = await db.execute(stmt)
    vkey = result.scalar_one_or_none()
    if not vkey:
        raise HTTPException(status_code=404, detail="Virtual Key not found or access denied")
    await db.delete(vkey)
    await db.commit()
    return {"status": "deleted"}
```

**Step 3: Commit changes**
Commit with: `fix(security): resolve IDOR/BOLA vulnerability in virtual keys update/delete`

---

### Task 6: Frontend Integration for Mock Authentication Switch

**Files:**
- Modify: [dashboardStore.ts](file:///C:/Repos/levitate-api/frontend/src/store/dashboardStore.ts)
- Modify: [LoginScreen.tsx](file:///C:/Repos/levitate-api/frontend/src/components/LoginScreen.tsx)

**Step 1: Update Zustand store state & config fetching**
In `frontend/src/store/dashboardStore.ts`, add `mockAuthEnabled` properties:
```typescript
  // Inside DashboardState interface:
  mockAuthEnabled: boolean;
  
  // Inside store initialization (useDashboardStore):
  mockAuthEnabled: false, // default
  
  // Inside fetchConfig:
  fetchConfig: async () => {
    try {
      const resp = await apiFetch("/admin/auth/config");
      if (resp.ok) {
        const data = await resp.json() as { google_oauth_configured: boolean; mock_auth_enabled: boolean };
        set({ 
          googleOauthConfigured: data.google_oauth_configured,
          mockAuthEnabled: data.mock_auth_enabled
        });
      }
    } catch {
      // Ignored config error fallback
    }
  },
```

**Step 2: Hide Developer Login button in LoginScreen**
In `frontend/src/components/LoginScreen.tsx`, render the mock login button conditionally:
```typescript
  // Load mockAuthEnabled from store:
  const { language, setLanguage, googleOauthConfigured, mockAuthEnabled } = useDashboardStore();
```
Wrap mock login button block:
```tsx
              {/* Developer login option */}
              {mockAuthEnabled && (
                <a
                  href={`${getApiUrl()}/admin/auth/mock`}
                  className="w-full flex items-center justify-between py-3 px-4 bg-[var(--bg-subtle)] hover:bg-[var(--bg-panel-hover)] border border-[var(--border)] text-[var(--text-main)] text-sm font-semibold rounded-[var(--radius-md)] transition-all duration-200 hover:border-[var(--border-active)] active:scale-[0.98] group/btn focus-ring"
                >
                  <span>{t.login.btn_mock}</span>
                  <ArrowRight className="w-4 h-4 text-[var(--text-dark)] group-hover/btn:translate-x-1 group-hover/btn:text-[var(--primary)] transition-all" />
                </a>
              )}
```

**Step 3: Commit changes**
Commit with: `feat(frontend): conditionally render developer login button`

---

### Task 7: Docker Compose Security Cleanup

**Files:**
- Modify: [docker-compose.yml](file:///C:/Repos/levitate-api/docker-compose.yml)

**Step 1: Remove hardcoded secrets from docker-compose.yml**
Remove `ENCRYPTION_KEY` from backend container environments (it is already loaded from `.env` via `env_file`).
```yaml
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://postgres:password@postgres:5432/gateway
      REDIS_URL: redis://redis:6379/0
      # ENCRYPTION_KEY removed (loaded from env_file instead)
    env_file:
      - .env
```

**Step 2: Commit changes**
Commit with: `refactor(security): remove hardcoded encryption key from docker-compose.yml`

---

## Verification Plan

### Automated Tests
- Run `npm run build` inside `frontend` directory to verify Next.js builds successfully.
- Start backend server locally and verify that API runs correctly.

### Manual Verification
1. Run backend with `APP_ENV=production` and empty `ENCRYPTION_KEY`. Ensure it fails to start.
2. Run backend with `APP_ENV=production` and correct keys, check that `/admin/auth/config` returns `mock_auth_enabled: false`.
3. Check the login page: the "Developer Login" button should be hidden.
4. Try to call `/admin/auth/mock` endpoint on backend. Ensure it returns `403 Forbidden`.
5. Create a virtual key under User A. Try to update or delete it via API from User B. Ensure it returns `404 Not Found or access denied`.
