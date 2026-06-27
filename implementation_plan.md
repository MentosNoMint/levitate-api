# Docker Compose Security Cleanup Implementation Plan

> **For Antigravity:** REQUIRED SUB-SKILL: Load executing-plans to implement this plan task-by-task.

**Goal:** Remove hardcoded secrets from `docker-compose.yml` to prevent exposure of sensitive variables in version control.

**Architecture:**
- Locate the `backend` service in `docker-compose.yml`.
- Remove the hardcoded `ENCRYPTION_KEY` from the `environment` section of the `backend` service.
- The `ENCRYPTION_KEY` is already safely loaded from `.env` via `env_file`.

**Tech Stack:** Docker Compose, YAML

---

### Task 1: Docker Compose Security Cleanup

**Files:**
- Modify: `docker-compose.yml:32-49`

**Step 1: Remove hardcoded encryption key**
Modify `docker-compose.yml` to remove the line `ENCRYPTION_KEY: vwW6pdYns-N3IpM4slyoaCUl8hwdY01EizkJvvyytz8=` under the `backend` service's `environment` section.

**Step 2: Verify docker-compose syntax**
Verify that the `docker-compose.yml` file has valid syntax.
Run: `docker compose config` (if docker is available) or manually verify the indentation and structure.

**Step 3: Run frontend build and test checks**
Run build commands to ensure project integrity:
- Run `npm run build` in `frontend/` directory.

**Step 4: Commit changes**
Commit changes with the exact message:
```bash
git add docker-compose.yml
git commit -m "refactor(security): remove hardcoded encryption key from docker-compose.yml"
```
