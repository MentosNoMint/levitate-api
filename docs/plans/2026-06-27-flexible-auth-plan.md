# Flexible Authentication (Google OAuth vs Admin Token) Implementation Plan

> **For Antigravity:** REQUIRED SUB-SKILL: Load executing-plans to implement this plan task-by-task.

**Goal:** Add a configurable `AUTH_METHOD` in environment variables to allow switching between Google OAuth, static Admin Token login, or both, with brute force rate limit protection and long-lived session persistence.

**Architecture:**
- Backend configuration manages `AUTH_METHOD` and `ADMIN_TOKEN`.
- New FastAPI route `POST /admin/auth/token-login` validates the token and issues a session token using existing JWT-like signature logic.
- Redis-based (or in-memory fallback) rate limiting restricts login requests by IP to 5 per minute.
- Next.js frontend fetches the configuration and dynamically displays the Google button and/or a token password input.
- Successful token login stores the session token in cookies and local storage to prevent needing to re-login.

**Tech Stack:** FastAPI, Next.js, TypeScript, Tailwind CSS, Redis/FakeRedis, pytest

---

### Task 1: Backend Environment Configuration and Rate Limiter

**Files:**
- Modify: `backend/app/services/auth_service.py`
- Modify: `.env.example`
- Modify: `.env`

**Step 1: Update env examples and locals**
Add default configurations to `.env.example` and current `.env`:
```ini
AUTH_METHOD=both
ADMIN_TOKEN=dev-admin-token-for-local-testing-12345
```

**Step 2: Add variables and validations in `auth_service.py`**
Modify `backend/app/services/auth_service.py` to:
1. Load `AUTH_METHOD` (defaults to `"both"`).
2. Load `ADMIN_TOKEN` (defaults to empty/none).
3. Validate variables (if in production mode, check that `ADMIN_TOKEN` has length >= 16 if token auth is active).
4. Implement `handle_token_login(token, client_ip, db)` with Redis rate limiter.

**Step 3: Verify backend builds**
Manually verify syntax of `auth_service.py`.
Run: `python -m py_compile backend/app/services/auth_service.py`
Expected output: No syntax error.

**Step 4: Commit**
```bash
git add backend/app/services/auth_service.py .env.example
git commit -m "feat(auth): configure AUTH_METHOD and ADMIN_TOKEN with rate limiting support"
```

---

### Task 2: Backend Login Endpoint and Tests

**Files:**
- Modify: `backend/app/api/routers/auth.py`
- Create: `backend/tests/test_flexible_auth.py`

**Step 1: Implement endpoint in `auth.py`**
1. Update `/config` to return `"auth_method"`.
2. Implement `POST /admin/auth/token-login` which handles token validation.

**Step 2: Create unit tests in `backend/tests/test_flexible_auth.py`**
Write a test using FastAPI's `TestClient` to verify:
- `/config` returns correct `auth_method`.
- `POST /admin/auth/token-login` succeeds with correct token, returns `auth_token`.
- `POST /admin/auth/token-login` fails with 401 on incorrect token.
- `POST /admin/auth/token-login` enforces rate limiting (returns 429 after 5 failures).

**Step 3: Run pytest**
Run: `pytest backend/tests/test_flexible_auth.py -v` (or standard tests command in project)
Expected output: Tests PASS.

**Step 4: Commit**
```bash
git add backend/app/api/routers/auth.py backend/tests/test_flexible_auth.py
git commit -m "feat(auth): implement token-login route and test suite"
```

---

### Task 3: Frontend Store and Localizations

**Files:**
- Modify: `frontend/src/store/translations.ts`
- Modify: `frontend/src/store/dashboardStore.ts`

**Step 1: Update Translation Schema and Translations**
Add keys in `translations.ts` for English and Russian in `login` block:
- `token_placeholder`
- `btn_token`
- `error_invalid_token`
- `error_rate_limited`
- `error_generic`

**Step 2: Update Zustand Store State and Actions**
1. Add `authMethod` field to `DashboardState` and set default to `"both"`.
2. Update `fetchConfig` action to read `auth_method` from backend.
3. Implement `loginWithToken(token: string)` action which calls `/admin/auth/token-login` and stores the token.

**Step 3: Verify TypeScript compilation**
Run: `npm run build` in `frontend/` (or verify using `npx tsc --noEmit`)
Expected output: Successful build.

**Step 4: Commit**
```bash
git add frontend/src/store/translations.ts frontend/src/store/dashboardStore.ts
git commit -m "feat(auth): update frontend store and add localizations for token login"
```

---

### Task 4: Frontend UI Implementation

**Files:**
- Modify: `frontend/src/components/LoginScreen.tsx`

**Step 1: Update Login UI Component**
1. Extract `authMethod` and `loginWithToken` from store.
2. Render the token login password input and "Login with Token" button when `authMethod` is `token` or `both`.
3. Align design with the iOS 16 Liquid Glass theme:
   - Floating input style, warm orange focus rings, glass-blurred borders.
   - Show loading spin-indicator when authenticating.
   - Show validation error messages elegantly.

**Step 2: Verify build and test suite**
1. Compile and build frontend.
   Run: `npm run build` inside `frontend/`
   Expected: Build succeeds.
2. Run backend checks if any tests fail.

**Step 3: Commit**
```bash
git add frontend/src/components/LoginScreen.tsx
git commit -m "feat(auth): implement token login form with liquid glass styling"
```

---

### Task 5: Verification & Integration Test

**Step 1: Test switching configurations**
1. Set `AUTH_METHOD=token` in `.env`. Restart backend. Verify only token form is visible.
2. Set `AUTH_METHOD=google` in `.env`. Restart backend. Verify only Google OAuth button is visible.
3. Set `AUTH_METHOD=both` in `.env`. Restart backend. Verify both methods are visible.
4. Try logging in with a valid token, verify session is saved (reloading does not log you out).
5. Attempt brute forcing the token input to verify 429 status code and lock out message.
