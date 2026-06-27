# Flexible Authentication (Google OAuth vs Admin Token) Design

This document specifies the design for introducing configurable authentication methods in Levitate API, allowing administrators to choose between Google OAuth, static Admin Token login, or both, controlled via environment variables.

---

## 1. Requirements

- **Configurable Auth Methods**: The admin should be able to toggle auth options using the `AUTH_METHOD` environment variable.
  - `google`: Only Google OAuth login is enabled.
  - `token`: Only static Admin Token login is enabled.
  - `both`: Both methods are available (default behavior).
- **Admin Token**: A secret key defined in the `.env` file under the name `ADMIN_TOKEN`.
- **Brute Force Protection**: Implementation of a rate limiter on the token login endpoint.
- **Session Persistence**: When logging in via token, the session must be persisted in client-side cookies and local storage (for 7 days, identical to the Google OAuth session).
- **Production Guardrails**: In production (`APP_ENV=production`), if `token` authentication is enabled, `ADMIN_TOKEN` must be securely configured and meet length requirements (minimum 16 characters).

---

## 2. Backend Design (FastAPI)

### Environment Configurations
Update `app/services/auth_service.py`:
- `AUTH_METHOD`: string environment variable, lowercase, defaults to `"both"`. Allowed values: `"google"`, `"token"`, `"both"`.
- `ADMIN_TOKEN`: string environment variable. If `AUTH_METHOD` in `("token", "both")`, it must be present. If `APP_ENV == "production"`, it must be at least 16 characters long.

### Login Rate Limiting
Implemented in `app/services/auth_service.py` using `redis_client`:
- Key: `rate_limit:login:{ip_address}`
- Limit: Maximum 5 login attempts within a 60-second window.
- Action: On overshoot, raise `HTTPException(429, "Too many login attempts. Please try again later.")`.

### API Routes
Modify `app/api/routers/auth.py`:
- Update `/config` to return:
  ```json
  {
    "google_oauth_configured": true,
    "mock_auth_enabled": false,
    "auth_method": "both"
  }
  ```
- Add a new route `POST /admin/auth/token-login`:
  - Request body: `{ "token": "string" }`
  - Retrieves caller IP via `request.client.host` for rate limiting.
  - Verifies token against `ADMIN_TOKEN`.
  - On success, resolves/creates user `admin@levitate.ai` (default admin account) with role `"admin"`.
  - Signs a user session token and returns:
    ```json
    {
      "auth_token": "signed_session_token"
    }
    ```

---

## 3. Frontend Design (Next.js)

### State Management (`src/store/dashboardStore.ts`)
- Add `authMethod: "google" | "token" | "both"` to the store state.
- Update `fetchConfig` to extract `auth_method` from backend response and update state.
- Add `loginWithToken(token: string)` action:
  - Dispatches `POST /admin/auth/token-login`.
  - On success, invokes `setToken(data.auth_token)` which registers the cookie and updates global store.
  - Invokes `fetchUser()` to redirect user to dashboard.

### Localization (`src/store/translations.ts`)
- Add RU/EN translation keys for:
  - Token input placeholder ("Enter Admin Token" / "Введите токен администратора")
  - Login button ("Login with Token" / "Войти по токену")
  - Error messages (invalid token, rate limited, loading states)

### Login Component (`src/components/LoginScreen.tsx`)
- Adapt design to render elements based on `authMethod`:
  - If `google` or `both` and Google OAuth is configured: render Google Login button.
  - If `token` or `both`: render a text input field (type `password`) and a submit button.
  - Style the input field using the signature Light/Dark iOS 16 Liquid Glass aesthetics.
  - Show inline error messages and loading animations when authenticating.

---

## 4. Verification Plan

### Automated Tests
- Test rate-limiting logic on `/admin/auth/token-login`.
- Test configuration parsing and validation checks.
- Verify user token generation and signature validation.

### Manual Verification
- Test switching `AUTH_METHOD` in `.env` to verify UI updates.
- Test entering incorrect tokens to trigger rate limiting error.
- Verify session persistence after logging in by token and reloading the page.
