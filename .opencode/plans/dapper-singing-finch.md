# Frontend Skills Review & Fix Plan

## Scope
- **Pages**: All 10 UI files (toast, entities list, entity detail, analytics, dashboard, login, sidebar, 3 charts, providers)
- **Reviews**: Impeccable (context + critique + audit), Vercel guidelines, Frontend design principles
- **Fixes**: All P0 through P3 issues

---

## Phase 1: Impeccable Setup

Run `node .agents/skills/impeccable/scripts/context.mjs` to establish project context.

Expected outcome: Script will note missing PRODUCT.md and DESIGN.md. We'll create minimal versions if needed, or skip and proceed with critiques directly.

---

## Phase 2: Impeccable Critique (per page)

Run `$impeccable critique` on each of these targets:

| # | Target | File |
|---|--------|------|
| 1 | Toast component | `frontend/src/components/ui/toast.tsx` |
| 2 | Entities list | `frontend/src/app/(app)/entities/page.tsx` |
| 3 | Entity detail | `frontend/src/app/(app)/entities/[id]/page.tsx` |
| 4 | Analytics | `frontend/src/app/(app)/analytics/page.tsx` |
| 5 | Dashboard | `frontend/src/app/(app)/dashboard/page.tsx` |
| 6 | Login | `frontend/src/app/login/page.tsx` |
| 7 | Sidebar | `frontend/src/components/layout/sidebar.tsx` |
| 8 | Engagement chart | `frontend/src/components/charts/engagement-chart.tsx` |
| 9 | Aspect bar chart | `frontend/src/components/charts/aspect-bar-chart.tsx` |
| 10 | Entity radar | `frontend/src/components/charts/entity-radar.tsx` |

Output per page: Nielsen's 10 heuristic scores, design-specificity verdict, P0-P3 issues, persona red flags.

---

## Phase 3: Impeccable Audit (per page)

Run `$impeccable audit` on each target. Scores across 5 dimensions:

1. Accessibility (A11y)
2. Performance
3. Theming
4. Responsive Design
5. Implementation Integrity

---

## Phase 4: Vercel Guidelines Check

Run `web-design-guidelines` skill on all UI files:
- `frontend/src/**/*.tsx`

Output: `file:line` findings format.

---

## Phase 5: Design Principles Review (Frontend Design)

Evaluate all pages against 6 principles:
1. Ground it in the subject
2. Hero as thesis
3. Typography carries personality
4. Structure encodes meaning
5. Motion with purpose
6. Restraint and self-critique

---

## Phase 6: Fix All Issues

### P0 — Critical (must fix)

| Issue | File | Fix |
|-------|------|-----|
| Toast auto-dismiss kills wrong toast | toast.tsx | Add per-toast timer with `useEffect` per toast `id` |
| Entity detail NaN ID guard | entities/[id]/page.tsx | Add `isNaN(entityId)` check, show 404 |

### P1 — High (should fix)

| Issue | File | Fix |
|-------|------|-----|
| No ARIA labels on charts | engagement-chart, aspect-bar-chart, entity-radar | Add `role="img"` + `aria-label` on SVG containers |
| Tables lack horizontal scroll | entities/page.tsx, dashboard/page.tsx | Wrap in `overflow-x-auto` div |
| Dark mode: hardcoded colors | toast, engagement-chart, entity-detail | Use CSS variables or `dark:` Tailwind variants |
| Login: no autoFocus/autoComplete | login/page.tsx | Add `autoFocus` + `autoComplete` attributes |
| Analytics: duplicate entity API calls | analytics/page.tsx | Remove `useApi("/api/entities")`, reuse `entitiesData` |
| Analytics: select lacks label | analytics/page.tsx | Add `<label>` or `aria-label` |

### P2 — Medium (should fix)

| Issue | File | Fix |
|-------|------|-----|
| Entity table rows not keyboard accessible | entities/page.tsx | Add `role="button"`, `tabIndex={0}`, `onKeyDown` |
| Sidebar: no aria-label on nav | sidebar.tsx | Add `aria-label="Main navigation"` |
| Sidebar: no Escape key to close | sidebar.tsx | Add `useEffect` for Escape key listener |
| Radar: only 5 colors | entity-radar.tsx | Expand color palette or use dynamic generation |
| Dashboard: bar width formula misleading | dashboard/page.tsx | Normalize relative to max aspect count, not total reviews |

### P3 — Low (nice to fix)

| Issue | File | Fix |
|-------|------|-----|
| Login: forgot-password button raw HTML | login/page.tsx | Use `<Button variant="ghost">` component |
| Sidebar: supabase client per render | sidebar.tsx | Wrap in `useMemo` or move to top |
| No global error boundary | layout.tsx | Add React Error Boundary wrapper |
| Login: validateEmail recreated per render | login/page.tsx | Move outside component or wrap in useCallback |
| Toast: ID collision risk | toast.tsx | Use `crypto.randomUUID()` or counter |

---

## Phase 7: Polish

Run `$impeccable polish` on each target page. This does the final quality pass:
- Verify loading/empty/error/success states
- Check responsive behavior at all breakpoints
- Verify keyboard navigation
- Check dark mode
- Clean up dead code and unused imports

---

## Phase 8: Verify

Re-run `$impeccable critique` and `$impeccable audit` on the most complex pages (entities, analytics, dashboard) to confirm improvement.

---

## Execution Order

```
Phase 1: context.mjs (setup)
Phase 2: critique × 10 pages (evaluation)
Phase 3: audit × 10 pages (evaluation)
Phase 4: web-design-guidelines scan (evaluation)
Phase 5: design principles review (evaluation)
Phase 6: fix P0 → P1 → P2 → P3 (implementation)
Phase 7: polish × 10 pages (final pass)
Phase 8: re-critique + re-audit (verification)
```

Estimated: ~45-60 minutes of agent work across all phases.
