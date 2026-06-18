# Levitate API — Complete AI context & Reference Guide

This document provides a comprehensive context specification of the **Levitate API** project for future AI neural networks, engineers, or agents onboarding to the codebase.

---

## 🚀 Overview & Capabilities
Levitate API is an **OpenAI-compatible proxy gateway** designed to sit between user applications and upstream LLM providers (e.g. Gemini, OpenAI, Anthropic).
- **Core Functionality**: Proxies `/v1/chat/completions` and `/v1/embeddings` requests.
- **Upstream Rotation & Balancing**: Implements priority tiers, load balancing weights, and concurrency limits across upstream credentials.
- **Failover & Cooldowns**: Puts failing upstream accounts into a 5-minute cooldown and immediately tries the next best account in the pool.
- **Virtual Key & Quotas**: Issues user-facing virtual keys (`sk-gateway-...`) with strict monthly token limits and rate limits (RPM).
- **Multi-Google OAuth Connect**: Admins can connect multiple Google Accounts via Google OAuth with one click to use their free/paid quotas (e.g. Gemini models) for proxy routing.
- **Admin Console**: Next.js single-page dashboard with Light/Dark themes (custom iOS 16 Liquid Glass layout) and EN/RU localization support.

---

## 📂 Codebase Directory Structure
The workspace is located at `/Users/kirill-book/My-projects`:

```
/Users/kirill-book/My-projects
├── backend/                  # FastAPI Backend Server & Worker
│   ├── app/
│   │   ├── api/              # HTTP routers & schemas
│   │   │   ├── routers/      # Routers (admin.py, auth.py, v1/chat.py)
│   │   │   ├── schemas/      # Pydantic schemas (credential.py, virtual_key.py)
│   │   │   └── deps.py       # API dependency helpers (get_current_user, get_db)
│   │   ├── core/             # Configuration & constants (constants.py)
│   │   ├── crypto/           # AES secret encryption for credential keys
│   │   ├── db/               # SQLAlchemy ORM models, session setup
│   │   ├── providers/        # Upstream clients (LiteLLM, Custom Antigravity Google OAuth)
│   │   ├── routing/          # Upstream selection algorithm
│   │   ├── security/         # SSRF blocking, header sanitization, secret scanning
│   │   ├── services/         # Layered business logic & DB interactions
│   │   │   ├── auth_service.py
│   │   │   ├── credential_service.py
│   │   │   ├── stats_service.py
│   │   │   ├── usage_service.py
│   │   │   └── virtual_key_service.py
│   │   ├── workers/          # Cooldown resets, health pings, token pre-refresh
│   │   ├── main.py           # FastAPI server entrypoint
│   │   └── redis_client.py   # Redis connection helper
│   ├── dev.db                # Local SQLite DB
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                 # Next.js Frontend Dashboard (App Router)
│   ├── src/
│   │   ├── app/
│   │   │   ├── (dashboard)/  # Grouped authenticated layout & tab pages
│   │   │   │   ├── layout.tsx
│   │   │   │   ├── credentials/page.tsx
│   │   │   │   ├── keys/page.tsx
│   │   │   │   ├── logs/page.tsx
│   │   │   │   └── overview/page.tsx
│   │   │   ├── login/        # Login page route
│   │   │   │   └── page.tsx
│   │   │   ├── globals.css   # Liquid glass CSS rules, Light/Dark theme variable blocks
│   │   │   ├── layout.tsx    # Root layout with <AppBootstrap>
│   │   │   └── page.tsx      # Landing page (redirects to /overview)
│   │   ├── components/       # UI Component views
│   │   │   ├── AppBootstrap.tsx  # Client bootstrapper (theme, url auth token parsing, polling)
│   │   │   ├── CredentialsTab.tsx  # OAuth connections list & upstream parameters
│   │   │   ├── DashboardLayout.tsx # Navigation sidebars, theme/lang controls
│   │   │   ├── LoginScreen.tsx     # Custom Stripe-style login panel
│   │   │   ├── LogsTab.tsx         # Realtime completions audit logs
│   │   │   ├── OverviewTab.tsx     # Metrics, stats charts, provider health table
│   │   │   └── VirtualKeysTab.tsx  # API key generation & quota parameters
│   │   ├── store/
│   │   │   ├── dashboardStore.ts   # Zustand global application state (without activeTab)
│   │   │   └── translations.ts     # Localization dictionary (RU/EN)
│   │   │   middleware.ts           # Server-side auth token cookie redirect gate
│   │   └── Dockerfile
│   ├── package.json
│   └── tsconfig.json
├── docker-compose.yml        # Docker composition (Postgres, Redis, Backend, Frontend)
└── README.md
```

---

## 🗄️ Database Schema (SQLAlchemy ORM)
Declared in `backend/app/db/models.py`:

```python
class User(Base):
    __tablename__ = "users"
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    role = Column(String, default="user") # 'admin' or 'user'

class VirtualKey(Base):
    __tablename__ = "virtual_keys"
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID, ForeignKey("users.id"))
    name = Column(String, nullable=False)
    key = Column(String, unique=True, nullable=False) # 'sk-gateway-...'
    monthly_token_limit = Column(Integer, nullable=True)
    rpm_limit = Column(Integer, nullable=True)
    status = Column(String, default="active") # 'active', 'paused', 'warning'

class Credential(Base):
    __tablename__ = "credentials"
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID, ForeignKey("users.id"))
    type = Column(String, nullable=False) # 'antigravity' or 'byo_upstream'
    name = Column(String, nullable=False)
    provider = Column(String, nullable=False) # 'Gemini', 'OpenAI', 'Anthropic', etc.
    encrypted_secret = Column(String, nullable=False) # AES-encrypted credentials json
    base_url = Column(String, nullable=True)
    models = Column(JSON, nullable=True) # Allowed models list
    quota_total_tokens = Column(Integer, nullable=True)
    quota_used_tokens = Column(Integer, default=0)
    quota_window = Column(Integer, nullable=True)
    reset_at = Column(DateTime(timezone=True), nullable=True)
    rpm_limit = Column(Integer, nullable=True)
    concurrency_limit = Column(Integer, nullable=True)
    priority = Column(Integer, default=1) # Priority tier (Lower is Higher priority)
    weight = Column(Integer, default=5) # load balancing weight inside the tier
    status = Column(String, default="active") # 'active', 'cooldown', 'exhausted', 'error'
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_check_at = Column(DateTime(timezone=True), nullable=True)
    model_quotas = Column(JSON, nullable=True)

class UsageEvent(Base):
    __tablename__ = "usage_events"
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    virtual_key_id = Column(UUID, ForeignKey("virtual_keys.id"))
    credential_id = Column(UUID, ForeignKey("credentials.id"), nullable=True)
    model = Column(String, nullable=False)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    est_cost = Column(Float, default=0.0)
    latency_ms = Column(Integer, default=0)
    status = Column(String, nullable=False) # 'success' or 'error'
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
```

---

## 🔀 Upstream Routing Selection Algorithm
Implemented in `backend/app/routing/selector.py`:
1. Fetches all active credentials belonging to the owner of the virtual key (`Credential.status == "active"`, `Credential.user_id == vkey.user_id`).
2. Filter models: if the requested model is not listed in `Credential.models` (if defined), skip it.
3. Groups upstreams by `priority` (ascending: priority `1` upstreams are evaluated first).
4. Inside the highest priority group, evaluates concurrency limits using Redis (increments current concurrency count, checks if it exceeds `concurrency_limit`).
5. Applies weighted random selection using `Credential.weight` to balance load.
6. If a selected upstream fails during the request:
   - Identifies the exception type (429/Rate Limit -> `"cooldown"` with `reset_at = now + 1 minute`; Quota/Exhausted -> `"exhausted"`; other connection/upstream failures -> `"degraded"`).
   - Updates the status in the database and commits the transaction immediately. This propagates state instantly, ensuring concurrent and subsequent requests bypass the failed credential without retrying or waiting for the health check.
   - Retries the selection flow to grab the next available upstream credential in the pool.
   - If all eligible credentials fail, the actual last exception details are propagated back to the user.

---

## 🛡️ Egress Security Layer
Implemented in `backend/app/security/egress.py`:
1. **SSRF Protection**: Resolves upstream hostnames asynchronously. Blocks requests to private IPs (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopbacks (`127.0.0.0/8`), link-local IPs (`169.254.0.0/16`), and metadata endpoints.
2. **Header Sanitization**: Filters client headers, preserving only standard API content payloads (`Content-Type`, user-agent, etc.) and stripping potential proxies or administrative parameters.
3. **Secrets Leak Scanner**: Inspects outgoing response payloads and headers. Blocks response returns if matching secrets (like API keys, passwords, or database configs) are detected in the body.

---

## 🔄 Async Worker Cycles
Implemented in `backend/app/workers/worker.py`:
- **Cooldown Reset Cycle (every 10 seconds)**: Scans credentials database. Restores `cooldown` credentials back to `active` once `reset_at` is past the current time.
- **Health Ping Cycle (every 60 seconds)**: Sends a lightweight request to all BYO and Antigravity endpoints (active, degraded, cooldown, exhausted, or in error) to measure round-trip latency and verify status. If healthy, restores them back to `active`; if unhealthy, updates to `degraded`.
- **Token Refresh Cycle (every 10 minutes)**: Pre-fetches Google OAuth access tokens using refresh credentials so client requests avoid incurring OAuth negotiation latency.

---

## 🔐 Multi-Google OAuth Upstream Integration
Administrators can register Google Accounts as upstreams inside the gateway pool:
1. In the frontend **Credentials** tab, clicking **"Connect Google"** redirects the admin's browser to `/admin/auth/login?action=add_credential&token=ADMIN_JWT`.
2. The endpoint forces Google's offline consent screen (`access_type=offline&prompt=consent`) to guarantee a `refresh_token` returns. The action and token parameters are passed in Google's `state` parameter.
3. Upon code exchange in `/admin/auth/callback`:
   - Decodes and verifies the admin session `token` from `state`.
   - Obtains the `refresh_token` and the user's `email`.
   - Creates or updates a `Credential` named `Antigravity Gemini (user_email)` of type `antigravity` and provider `Gemini`, associated with the admin's `user_id`.
   - Encrypts the JSON secret `{"refresh_token": "...", "client_id": "...", "client_secret": "..."}` using the server AES cipher.
   - Commits the transaction and automatically invokes `fetch_quota()` to fetch initial model quotas, check validity, and set the real credential state.
   - Redirects the user back to the dashboard with `?google_connect=success`.

> [!NOTE]
> **Method B (Manual SDK Authorization) Removal**: The legacy manual SDK oauth out-of-band flow (which allowed pasting an authorization code from a console log/login flow) has been completely removed from both backend routes and frontend components. Only browser redirect OAuth (Method A) is supported.

---

## 🎨 Frontend Styling & iOS 16 Liquid Glass System
The dashboard UI utilizes custom visual tokens defined in `frontend/src/app/globals.css` that adapt dynamically:

### Light Theme (`data-theme="light"`)
- Background: `#fdfdf5` (warm ivory)
- Card background: `#f7edd3` (warm peach sand)
- Primary Accent: `#ff661a` (vibrant orange)
- Border: `#e6d3a9` (soft sand border)
- Shadow: `0 8px 32px 0 rgba(142, 114, 75, 0.08), inset 0 2px 8px 0 rgba(255, 255, 255, 0.6)`

### Dark Theme (`data-theme="dark"`)
- Background: `#27282a` (charcoal slate)
- Card background: `#18191b` (deep carbon black)
- Primary Accent: `#ff661a` (vibrant orange)
- Border: `#323539` (dark graphite border)
- Shadow: `0 8px 32px 0 rgba(0, 0, 0, 0.45), inset 0 1px 1px 0 rgba(255, 255, 255, 0.08)`

### Design Tokens
- Corners: `1.5rem` (`var(--radius-lg)`).
- Glass elements: `.metric-card`, `.mc-panel`, and Forms use `backdrop-filter: blur(16px) saturate(180%)` along with inner highlight shadows (the `inset` variable in `--card-shadow`).
- Badges and Tags: Use theme-aware variables (`--tag-managed-bg`, `--tag-managed-text`, etc.) to prevent text contrast issues in light mode.
- Table & UI Styling: Unified table formatting using `.mc-panel` container with `.mc-table` table classes. Remaining quotas are displayed with rounded hairline progress bars (`.w-full.h-1.bg-[var(--mc-subtle)]`). Status badges are rendered as `.mc-pill` containing a status dot `.mc-dot` and state classes (`is-active`, `is-cooldown`, `is-exhausted`, `is-error`).
- Exclusions: The `Priority & Weight` column has been removed from the Accounts credentials view, and the `Cost` ("Стоимость") column has been removed from Request History logs view.

---

## 🛡️ Instructions for Future AI Models
When modifying this codebase, you must follow these rules without exception:
1. **TypeScript Rules**: Do not use `any` annotations. All component props and API structures must be defined using explicit type definitions or interfaces.
2. **Styling Rules**: Do not write hardcoded `px` values. Use `rem` or Tailwind spacing tokens.
3. **Code Quality**: Do not leave `console.log` statements or comments behind in your commits.
4. **Imports**: Always use absolute imports via the `@/` alias (e.g. `@/store/...` or `@/components/...`).
5. **Dotenv Variables**: When adding features that read environment variables, always make sure `load_dotenv()` is called at the entry point of the app before modules are imported.
6. **Design & Aesthetics**: Do not alter, override, or downgrade the visual design system, custom warm color palettes, scroll/layout container bounds, or glassmorphism tokens. Keep the layout's signature look intact. Any visual change must align with and preserve the premium iOS 16 Liquid Glass theme.
7. **Routing & Authentication**:
   - The app uses Next.js App Router. Authenticated pages belong to the `(dashboard)` route group.
   - Redirect logic is guarded server-side by `src/middleware.ts` using the `auth_token` cookie.
   - When extracting the `auth_token` cookie on the client side (e.g. in `AppBootstrap.tsx`), always apply `decodeURIComponent` to handle Next.js automatic cookie URL-encoding of token dot segments (`%2E`).
   - Sidebars and page navigation must use Next.js `<Link>` components and reactive routing instead of mutating global store tab variables.
8. **Secrets Management**: Never hardcode Google OAuth Client IDs, Client Secrets, or other credentials in the source code. Always load them from environment variables (e.g. `ANTIGRAVITY_OAUTH_CLIENT_ID` and `ANTIGRAVITY_OAUTH_CLIENT_SECRET`) and define them in the local, gitignored `.env` file.

---

## 🔑 Antigravity Project Resolution, Quotas & Error Fallbacks
For connected Google Accounts of the `antigravity` provider:

### 1. Project ID Resolution Workflow
The gateway dynamically resolves the correct Google Cloud project ID using the following order:
1. **Cached Settings**: Checks if a valid `project_id` already exists within the credential's decrypted secret JSON.
2. **Environment Override**: Attempts calling the `loadCodeAssist` endpoint with the project ID specified in the `GOOGLE_USER_PROJECT` environment variable (defaults to `levitate-api`).
3. **Blank Query fallback**: Calls `loadCodeAssist` with an empty payload. If successful, extracts the returned `cloudaicompanionProject`.
4. **Google One AI Premium (Personal Account)**: If `loadCodeAssist` returns a tier with `userDefinedCloudaicompanionProject: true` (e.g. for personal `g1-pro-tier` accounts), the gateway automatically falls back to using the `GOOGLE_USER_PROJECT` value, persists it in the secret, and continues.
5. **Onboarding Fallback**: If no project is resolved, it triggers Google's `onboardUser` endpoint and polls `loadCodeAssist` up to 5 times (waiting 1 second between polls) until a Google-managed project is provisioned.

### 2. Available Models & Quota Extraction
Once a project ID is resolved:
1. **API Call**: The gateway queries Google's `fetchAvailableModels` endpoint, passing `project` in the JSON request body (note: using `project` rather than `cloudaicompanionProject` to satisfy Google's API contract).
2. **JSON Structures**: Supports parsing both:
   - The newer `"models"` JSON dictionary format where each model ID maps to a `"quotaInfo"` block containing `"remainingFraction"`.
   - The legacy `"groups"` and `"buckets"` array list format containing `"remainingFraction"`.
3. **Overall Quota**: Calculates the overall remaining quota percentage based on the minimum `remainingFraction` across all active models, scaling it to used tokens (where `0` used tokens = `100%` remaining, and `1,000,000` used tokens = `0%` remaining).

### 3. Error State Propagation
- If project resolution fails or model fetching encounters a non-200 response, the gateway:
  - Updates the credential's database record status to `"error"`.
  - Sets both `quota_total_tokens` and `quota_used_tokens` to `1,000,000` (representing 0% remaining quota).
  - Persists the exception message as `load_error` or `quota_error` in the encrypted credential metadata.
- The Next.js dashboard UI identifies credentials with `status === 'error'` and forces both card-level overall quotas and model-level quotas to `0%` while showing a red alert banner with the error details.

