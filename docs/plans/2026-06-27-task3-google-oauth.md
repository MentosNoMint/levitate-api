# Safe Google OAuth Registration & Allowed Emails Config Implementation Plan

> **For Antigravity:** REQUIRED SUB-SKILL: Load executing-plans to implement this plan task-by-task.

**Goal:** Restrict new admin registrations via Google OAuth to emails specified in a whitelist environment variable.

**Architecture:** Retrieve `ALLOWED_ADMIN_EMAILS` from environment variables, parse it into a set/list of case-insensitive email addresses, and assign the `"admin"` role to new OAuth users only if their email is in that list; otherwise, assign the `"user"` role.

**Tech Stack:** Python, FastAPI, SQLAlchemy

---

### Task 1: Safe Google OAuth Registration & Allowed Emails Config

**Files:**
- Modify: `backend/app/services/auth_service.py`

**Step 1: Write the changes in auth_service.py**
Retrieve and parse `ALLOWED_ADMIN_EMAILS` at the module level in `auth_service.py` and modify the registration logic inside `handle_oauth_callback`.

**Step 2: Run a basic import/syntax check to verify code validity**
Run: `python -m py_compile backend/app/services/auth_service.py`
Expected: Successful compilation without output.

**Step 3: Commit**
Run: `git add backend/app/services/auth_service.py`
Run: `git commit -m "feat(security): restrict admin creation during OAuth to ALLOWED_ADMIN_EMAILS"`
