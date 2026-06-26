# UI Redesign and Layout Stability Implementation Plan

> **For Antigravity:** REQUIRED SUB-SKILL: Load executing-plans to implement this plan task-by-task.

**Goal:** Redesign the Levitate Console with premium typography (Plus Jakarta Sans + JetBrains Mono), fix component shifts on language switch, and remove duplicate headers.

**Architecture:** We will replace the Next.js Google font imports in the root layout, update Tailwind's font-family mappings, and refactor CSS variables. The duplicate global header will be removed from DashboardLayout, making all tab headers strictly local. Tables will receive fixed layouts to secure column widths against text width variations.

**Tech Stack:** Next.js (next/font/google), Tailwind CSS, Lucide icons, React.

---

### Task 1: Setup Fonts in Layout

**Files:**
- Modify: `frontend/src/app/layout.tsx`

**Step 1: Replace font imports and initializations**

Modify `frontend/src/app/layout.tsx` to load `Plus_Jakarta_Sans` and `JetBrains_Mono` instead of `Inter` and `Geist_Mono`.

```typescript
import { Plus_Jakarta_Sans, JetBrains_Mono } from "next/font/google";

const plusJakarta = Plus_Jakarta_Sans({
  variable: "--font-plus-jakarta",
  subsets: ["latin", "cyrillic"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin", "cyrillic"],
});
```

Update the HTML class attribute to use:
```typescript
className={`${plusJakarta.variable} ${jetbrainsMono.variable}`}
```

**Step 2: Commit**

```bash
git add frontend/src/app/layout.tsx
git commit -m "style: configure Plus Jakarta Sans and JetBrains Mono fonts in root layout"
```

---

### Task 2: Configure Tailwind and CSS variables

**Files:**
- Modify: `frontend/tailwind.config.ts`
- Modify: `frontend/src/app/globals.css`

**Step 1: Update Tailwind Config fonts**

Change the custom font-family mappings in `frontend/tailwind.config.ts`:
```typescript
      fontFamily: {
        sans: ["var(--font-plus-jakarta)", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "monospace"],
      },
```

**Step 2: Update CSS Variables in globals.css**

Modify `frontend/src/app/globals.css` to bind `body` and `.mc-mono` to the new font variables:
```css
body {
  font-family: var(--font-plus-jakarta), system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  /* ... */
}

.mc-mono {
  font-family: var(--font-jetbrains-mono), ui-monospace, SFMono-Regular, Menlo, "JetBrains Mono", monospace;
  /* ... */
}
```

Add the ambient background mesh gradient to `body`:
```css
body {
  color: var(--text-main);
  background-color: var(--bg-app);
  font-family: var(--font-plus-jakarta), system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  background-image: 
    radial-gradient(at 0% 0%, rgba(232, 80, 2, 0.06) 0px, transparent 50%),
    radial-gradient(at 100% 100%, rgba(193, 8, 1, 0.04) 0px, transparent 50%);
  background-attachment: fixed;
}
```

Add `table-layout: fixed` and transition rules:
```css
.mc-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 0.8125rem;
  table-layout: fixed;
}

.mc-card, .mc-panel, .primary-action-btn, .premium-input, .premium-select, .mc-pill, button {
  transition: all 0.5s cubic-bezier(0.16, 1, 0.3, 1);
}
```

**Step 3: Commit**

```bash
git add frontend/tailwind.config.ts frontend/src/app/globals.css
git commit -m "style: map theme variables and Tailwind fonts to Plus Jakarta and JetBrains Mono"
```

---

### Task 3: Refactor DashboardLayout Header and Sidebar

**Files:**
- Modify: `frontend/src/components/DashboardLayout.tsx`

**Step 1: Remove duplicate header**

Delete the `<header className="p-6 md:p-8 pb-3 md:pb-4 flex flex-col gap-1 shrink-0">...</header>` block from the `main` layout area (lines 217-224).

**Step 2: Stabilize buttons widths**

Ensure language and theme switch containers have a fixed width or minimum width to prevent shifts. E.g. add `min-w-[120px]` or specific sizing.

**Step 3: Commit**

```bash
git add frontend/src/components/DashboardLayout.tsx
git commit -m "refactor: remove global header and stabilize sidebar layout widths"
```

---

### Task 4: Add Overview Header and Cleanup Tab

**Files:**
- Modify: `frontend/src/components/OverviewTab.tsx`

**Step 1: Add Local Header to OverviewTab**

Insert local header wrapper right inside the root div of `OverviewTab.tsx` (before the `.mc-strip` element):
```tsx
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-2">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-[var(--text-main)]">
            {t.layout.overview_title}
          </h2>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            {language === "en" ? "System overview, active pools and keys performance." : "Общая сводка системы, состояние аккаунтов и лимитов."}
          </p>
        </div>
      </div>
```

**Step 2: Remove duplicate weekly quota block**

Delete the duplicate `{cW !== null && ...}` code snippet from lines 318-326.

**Step 3: Commit**

```bash
git add frontend/src/components/OverviewTab.tsx
git commit -m "refactor: add local header to overview tab and remove duplicate weekly quota JSX"
```

---

### Task 5: Build and Verify Redesign

**Files:**
- None

**Step 1: Verify typescript compilation and build**

Run build: `docker compose exec frontend npm run build` or `npm run build` locally within `frontend/` directory.

**Step 2: Verify UI via Browser Agent**

Analyze the updated pages `/overview`, `/keys`, `/credentials` using the browser subagent in Russian and English. Ensure layout holds perfectly.
