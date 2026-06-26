# UI Redesign - Soft Dark Mode Implementation Plan

> **For Antigravity:** REQUIRED SUB-SKILL: Load executing-plans to implement this plan task-by-task.

**Goal:** Modify the core dark theme variables to reduce visual fatigue (lower contrast, slightly lighter background, softer white text).

**Architecture:** We will adjust CSS variables for the root `:root, [data-theme="dark"]` and default `.overview-mc` selectors in globals.css. We will leave the light theme untouched. We will then rebuild and deploy.

**Tech Stack:** Next.js, Tailwind CSS, React, Docker.

---

### Task 1: Refactor globals.css for Soft Dark Mode

**Files:**
- Modify: `frontend/src/app/globals.css`

**Step 1: Rewrite Dark Theme Variables**

Update variables under `:root, [data-theme="dark"]` and `.overview-mc` in `frontend/src/app/globals.css` to use relaxed dark colors.

```css
:root, [data-theme="dark"] {
  --background: #18191b;
  --foreground: #e3e4e8;
  --bg-app: #18191b;
  --bg-panel: #212327;
  --bg-panel-hover: #2b2d32;
  --bg-subtle: #212327;
  
  --border: #2a2c31;
  --border-active: #ff4f18;
  
  --primary: #ff4f18;
  --primary-dim: rgba(255, 79, 24, 0.1);
  --primary-hover: #d83a0f;
  
  --text-main: #e3e4e8;
  --text-muted: #94969f;
  --text-dark: #62646a;
  
  --color-success: #10b981;
  --color-warning: #f59e0b;
  --color-exhausted: #9ca3af;
  --color-danger: #ef4444;
  
  --radius-sm: 0.375rem;
  --radius-md: 0.75rem;
  --radius-lg: 1.5rem;

  --card-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.4), inset 0 1px 1px 0 rgba(255, 255, 255, 0.03);

  --tag-managed-bg: rgba(255, 79, 24, 0.1);
  --tag-managed-text: #ff4f18;
  --tag-byo-bg: rgba(100, 100, 100, 0.12);
  --tag-byo-text: #94969f;
  --code-text: #ff4f18;
  --branding-gradient: linear-gradient(135deg, #18191b 0%, #c10801 35%, #ff4f18 70%, #d9c3ab 100%);
}
```

Update `.overview-mc`:
```css
.overview-mc {
  --mc-panel: #212327;
  --mc-elev: #2b2d32;
  --mc-subtle: #18191b;
  --mc-border: #2a2c31;
  --mc-border-strong: #5a5c62;
  --mc-text: #e3e4e8;
  --mc-muted: #94969f;
  --mc-dim: #62646a;
  --mc-grid: rgba(255, 255, 255, 0.035);
  --mc-ok: #34d399;
  --mc-warn: #fbbf24;
  --mc-danger: #f87171;
  --mc-neutral: #7b8494;
  --mc-hairline: rgba(255, 255, 255, 0.04);
  --mc-primary: #e85002;
  --mc-primary-line: rgba(232, 80, 20, 0.45);
  --mc-shadow: inset 0 0.0625rem 0 0 var(--mc-hairline), 0 0.5rem 1.5rem -0.75rem rgba(0, 0, 0, 0.7);

  display: flex;
  flex-direction: column;
  gap: 1rem;
}
```

**Step 2: Commit**

```bash
git add frontend/src/app/globals.css
git commit -m "style: soften dark theme contrast to reduce eye strain"
```

---

### Task 2: Build and Verify via Browser Agent

**Files:**
- None

**Step 1: Rebuild and restart application**

Run build: `docker compose up --build -d`.

**Step 2: Verify visually via Browser Agent**

Confirm the dark theme is softer, text remains highly readable, and the layout looks premium. Take screenshots.
