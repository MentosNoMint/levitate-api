# Virtual Keys IDOR Code Quality Improvements Implementation Plan

> **For Antigravity:** REQUIRED SUB-SKILL: Load executing-plans to implement this plan task-by-task.

**Goal:** Apply code quality improvements and PEP8 formatting to virtual keys IDOR check code in services and routers.

**Architecture:** Refactor service function definitions in `virtual_key_service.py` to wrap long lines and separate them with exactly two blank lines, and upgrade Pydantic `.dict()` to `.model_dump()`. Refactor `admin.py` route parameters to use `uuid.UUID` and add return/response type annotations, cleaning up manual UUID verification blocks.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy, Python PEP8.

---

### Task 1: Refactor `virtual_key_service.py`

**Files:**
- Modify: `backend/app/services/virtual_key_service.py`

**Step 1: Update code formatting, function signatures, and model dump method**
Update `update_virtual_key` and `delete_virtual_key` signatures, separate top-level functions with exactly two blank lines, and replace `payload.dict` with `payload.model_dump`.

**Step 2: Verify syntax**
Compile check or run syntax verification on the service module.

---

### Task 2: Refactor `admin.py`

**Files:**
- Modify: `backend/app/api/routers/admin.py`

**Step 1: Update route handlers for virtual keys**
Change `id` parameter from `str` to `uuid.UUID` in `update_virtual_key` and `delete_virtual_key` endpoints. Add `response_model=Dict[str, Any]` and return type annotation `-> Dict[str, Any]`. Remove try-except validation blocks. Format the entire file with exactly two blank lines between top-level functions/classes.

**Step 2: Verify syntax**
Verify syntax of the router module.

---

### Task 3: Build & Verification

**Step 1: Build the application**
Run `npm run build` or the Python equivalent (e.g., verifying backend service starts or compiles).
We will run `pytest` or any available build commands.

**Step 2: Commit changes**
Commit changes using:
```bash
git add backend/app/services/virtual_key_service.py backend/app/api/routers/admin.py
git commit -m "refactor(security): apply code quality fixes to virtual keys IDOR check"
```
