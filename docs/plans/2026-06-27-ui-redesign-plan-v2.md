# UI Redesign and True Light Mode Implementation Plan (V2)

> **For Antigravity:** REQUIRED SUB-SKILL: Load executing-plans to implement this plan task-by-task.

**Goal:** Implement a true Light Mode (light background, dark text), refine layout variables, polish buttons, inputs, and tables, and perform a full interactive browser audit of all screens and workflows.

**Architecture:** We will adjust CSS variables in globals.css, making the light theme fully clean and contrasty. We will improve borders, focus states, and button presses. We will verify layout and typography elements, build and deploy inside Docker, and run an automated Chrome session to verify modals, translations, and logs in both themes.

**Tech Stack:** Next.js (next/font/google), Tailwind CSS, Lucide icons, React, Docker.

---

### Task 1: Refactor globals.css for True Light Mode

**Files:**
- Modify: `frontend/src/app/globals.css`

**Step 1: Rewrite Light Theme Variables**

Update variables under `[data-theme="light"]` and `[data-theme="light"] .overview-mc` in `frontend/src/app/globals.css` to use high-contrast light colors.

```css
[data-theme="light"] {
  --background: #f8f9fa;
  --foreground: #121316;
  --bg-app: #f8f9fa;
  --bg-panel: #ffffff;
  --bg-panel-hover: #f1f2f4;
  --bg-subtle: #fafafb;
  
  --border: #e4e5e7;
  --border-active: #ff4f18;
  
  --text-main: #121316;
  --text-muted: #64666e;
  --text-dark: #8e9098;

  --card-shadow: 0 4px 20px 0 rgba(0, 0, 0, 0.04), inset 0 1px 0 0 rgba(255, 255, 255, 0.6);

  --tag-managed-bg: rgba(255, 79, 24, 0.08);
  --tag-managed-text: #ff4f18;
  --tag-byo-bg: rgba(100, 100, 100, 0.08);
  --tag-byo-text: #64666e;
  --code-text: #ff4f18;
  --branding-gradient: linear-gradient(135deg, #ffffff 0%, #ffeae5 50%, #ff4f18 100%);
}
```

Update `[data-theme="light"] .overview-mc`:
```css
[data-theme="light"] .overview-mc {
  --mc-panel: #ffffff;
  --mc-elev: #fafafb;
  --mc-subtle: #f8f9fa;
  --mc-border: #e4e5e7;
  --mc-border-strong: #a1a2a9;
  --mc-text: #121316;
  --mc-muted: #64666e;
  --mc-dim: #8e9098;
  --mc-grid: rgba(0, 0, 0, 0.03);
  --mc-ok: #10b981;
  --mc-warn: #f59e0b;
  --mc-danger: #ef4444;
  --mc-neutral: #71717a;
  --mc-hairline: rgba(0, 0, 0, 0.02);
  --mc-primary: #ff4f18;
  --mc-primary-line: rgba(255, 79, 24, 0.4);
  --mc-shadow: 0 4px 16px -4px rgba(0, 0, 0, 0.05);
}
```

Update `.mc-card:hover` to adapt shadows dynamically to light theme:
```css
.mc-card:hover {
  border-color: var(--mc-border-strong);
  transform: translateY(-0.15rem);
  box-shadow: var(--card-shadow), 0 10px 25px -5px rgba(0, 0, 0, 0.1);
}
```

**Step 2: Commit**

```bash
git add frontend/src/app/globals.css
git commit -m "style: implement high-contrast true Light Mode theme in globals.css"
```

---

### Task 2: Polish Components and Layouts for Theme Consistency

**Files:**
- Modify: `frontend/src/components/DashboardLayout.tsx`
- Modify: `frontend/src/components/Modal.tsx`

**Step 1: Check select text colors in Light Theme**

Make sure dropdown selects and text within DashboardLayout sidebar retain contrast.
In `DashboardLayout.tsx`, change background class of theme/lang switcher from `bg-[var(--bg-subtle)]` to a style that stands out nicely on white panels.

**Step 2: Commit**

```bash
git add frontend/src/components/DashboardLayout.tsx frontend/src/components/Modal.tsx
git commit -m "style: polish layout and modal elements for Light/Dark contrast"
```

---

### Task 3: Build, Run, and Verify via Browser Agent

**Files:**
- Modify: `task.md`

**Step 1: Rebuild and restart application**

Run build: `docker compose up --build -d`.

**Step 2: Run Browser Agent for a complete interactive flow**

Command the browser agent to click through the entire UI:
- Switch theme to Light.
- Switch language to RU and EN on `/overview`, `/keys`, `/credentials`, `/logs`.
- Open Modal on `/keys`.
- Send test request on `/logs` and verify success response is visible.
- Make screenshots of all states.

**Step 3: Commit**

```bash
git add C:\Users\Arem\.gemini\antigravity\brain\a760b701-144b-4743-ae52-99c1323b0fa2\task.md
git commit -m "docs: finalize all tasks and log visual audit results"
```
