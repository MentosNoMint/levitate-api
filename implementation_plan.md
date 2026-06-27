# Broken Object Level Authorization (IDOR) Fix in Virtual Keys Implementation Plan

> **For Antigravity:** REQUIRED SUB-SKILL: Load executing-plans to implement this plan task-by-task.

**Goal:** Prevent users from updating or deleting virtual keys belonging to other users.

**Architecture:**
- Modify the `update_virtual_key` and `delete_virtual_key` services to check user ownership of the virtual key or verify if they are an admin.
- Modify the FastAPI router endpoints to dependency-inject `current_user` and pass their `id` and `role` down to the service layer.

**Tech Stack:** Python, FastAPI, SQLAlchemy

---

### Task 1: Update Service Layer Logic

**Files:**
- Modify: `backend/app/services/virtual_key_service.py`

**Step 1: Modify `update_virtual_key` signature and logic**
Accept `current_user_id: uuid.UUID` and `current_user_role: str`. Check if `vkey.user_id == current_user_id` or `current_user_role == "admin"`. If not, raise `HTTPException(404, detail="Virtual Key not found")`.
```python
async def update_virtual_key(
    db: AsyncSession, 
    vkey_id: uuid.UUID, 
    payload: VirtualKeyUpdate,
    current_user_id: uuid.UUID,
    current_user_role: str
) -> Dict[str, Any]:
    stmt = select(VirtualKey).where(VirtualKey.id == vkey_id)
    result = await db.execute(stmt)
    vkey = result.scalar_one_or_none()
    if not vkey:
        raise HTTPException(status_code=404, detail="Virtual Key not found")

    if vkey.user_id != current_user_id and current_user_role != "admin":
        raise HTTPException(status_code=404, detail="Virtual Key not found")

    for k, v in payload.dict(exclude_unset=True).items():
        if k in ["monthly_token_limit", "rpm_limit"]:
            setattr(vkey, k, v)
        elif v is not None:
            setattr(vkey, k, v)

    await db.commit()
    return {"status": "updated"}
```

**Step 2: Modify `delete_virtual_key` signature and logic**
Accept `current_user_id: uuid.UUID` and `current_user_role: str`. Perform the same validation check.
```python
async def delete_virtual_key(
    db: AsyncSession, 
    vkey_id: uuid.UUID,
    current_user_id: uuid.UUID,
    current_user_role: str
) -> Dict[str, Any]:
    stmt = select(VirtualKey).where(VirtualKey.id == vkey_id)
    result = await db.execute(stmt)
    vkey = result.scalar_one_or_none()
    if not vkey:
        raise HTTPException(status_code=404, detail="Virtual Key not found")

    if vkey.user_id != current_user_id and current_user_role != "admin":
        raise HTTPException(status_code=404, detail="Virtual Key not found")

    await db.delete(vkey)
    await db.commit()
    return {"status": "deleted"}
```

---

### Task 2: Update API Router Endpoints

**Files:**
- Modify: `backend/app/api/routers/admin.py`

**Step 1: Modify `update_virtual_key` and `delete_virtual_key` endpoints**
Add dependency `current_user: User = Depends(get_current_user)` and forward `id` and `role` to the service functions.
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
    return await virtual_key_service.update_virtual_key(
        db, vkey_id, payload, current_user.id, current_user.role
    )

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
    return await virtual_key_service.delete_virtual_key(
        db, vkey_id, current_user.id, current_user.role
    )
```

---

### Task 3: Verification & Compilation Check

**Step 1: Compile files to verify no syntax errors**
Run: `python -m py_compile backend/app/services/virtual_key_service.py`
Run: `python -m py_compile backend/app/api/routers/admin.py`

**Step 2: Commit changes**
Run:
```bash
git add backend/app/services/virtual_key_service.py backend/app/api/routers/admin.py
git commit -m "feat(security): fix IDOR vulnerability in virtual keys update and delete"
```
