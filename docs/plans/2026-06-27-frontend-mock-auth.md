# Frontend Integration for Mock Authentication Switch Implementation Plan

> **For Antigravity:** REQUIRED SUB-SKILL: Load executing-plans to implement this plan task-by-task.

**Goal:** Update the frontend to read the `mock_auth_enabled` status from the backend and conditionally render the mock login button.

**Architecture:** Extend the Zustand state `dashboardStore` to hold and fetch the `mockAuthEnabled` flag, and update `LoginScreen` to conditionally render the "Developer Login" button using this state property.

**Tech Stack:** React, Next.js, TypeScript, Zustand

---

### Task 1: Update dashboardStore.ts

**Files:**
- Modify: `C:/Repos/levitate-api/frontend/src/store/dashboardStore.ts`

**Step 1: Write implementation**
Extend `DashboardState` interface, set default value for `mockAuthEnabled` to `true`, and update `fetchConfig` method to cast the API response and set state.

**Step 2: Commit intermediate store changes**
```bash
git add frontend/src/store/dashboardStore.ts
git commit -m "feat(frontend): add mockAuthEnabled to dashboardStore"
```

### Task 2: Update LoginScreen.tsx

**Files:**
- Modify: `C:/Repos/levitate-api/frontend/src/components/LoginScreen.tsx`

**Step 1: Write implementation**
Retrieve `mockAuthEnabled` from `useDashboardStore()` and wrap the developer login button (`btn_mock`) in a conditional rendering block.

**Step 2: Commit screen changes**
```bash
git add frontend/src/components/LoginScreen.tsx
git commit -m "feat(frontend): conditionally render developer login based on backend config"
```

### Task 3: Verify and Build

**Files:**
- None

**Step 1: Run production build**
Run the production build in the `frontend` directory to ensure type safety and no compilation/lint errors.
Run: `npm run build` in `C:/Repos/levitate-api/frontend`
Expected: Successful build without errors.

**Step 2: Run tests if applicable**
Run: `npm run test` or check for linting.
Expected: PASS
