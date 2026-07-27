# BI & ABSA Analytics Platform — UI/UX Architecture (v2)

**Stack context:** Next.js · PostgreSQL Star Schema · XLM-RoBERTa two-stage ABSA · Facebook + Foodpanda ETL
**Team size:** 6 engineers · **Theme:** Dark mode primary

---

## 1. Dashboard Layout Structure

### 1.1 Main Dashboard (Overview)

The dashboard is built as a strict grid so panels can be reordered/resized later without a rewrite. Global controls are pinned; everything below scrolls.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ TOPBAR (sticky)                                                               │
│ Logo   Entity: [OMUK ▾]  [+ Compare vs Lotteria]   Date Range: [Last 30d ▾]   │
│                       Sync: ● 12 min ago  [🔥 Crisis · 2]  [Escalation Q · 14]│
├──────────────────────────────────────────────────────────────────────────────┤
│ KPI STRIP — 4–5 cards, horizontal scroll on narrow viewports                  │
│ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐      │
│ │ Review Volume │ │ Sentiment     │ │ Hangry Index  │ │ Escalation    │      │
│ │ 12,480  ▲4.2% │ │ Health 72/100 │ │ 0.34   ▼0.06  │ │ Backlog: 14   │      │
│ │ sparkline     │ │ ▲ vs prev pd  │ │ (dinner-hour) │ │ 3 urgent      │      │
│ └───────────────┘ └───────────────┘ └───────────────┘ └───────────────┘      │
├───────────────────────────────────────┬──────────────────────────────────────┤
│ TIME-SERIES PANEL (~65% width)         │ ASPECT RADAR (~35% width)            │
│ Line: sentiment score over time        │ 6-axis radar, entity A vs B overlay  │
│ Bar overlay: FB engagement spikes      │ Toggle: volume-weighted / raw        │
│ Brush + zoom, event annotations (▲)    │ Hover: n reviews, avg confidence     │
├───────────────────────────────────────┴──────────────────────────────────────┤
│ ASPECT BREAKDOWN — full width                                                │
│ 6 horizontal stacked bars (Positive/Neutral/Negative), sortable by volume,   │
│ negativity %, or trend delta. Click a bar → filters everything below.       │
├─────────────────────────────────┬──────────────────────────────────────────┤
│ SOCIAL ENGAGEMENT (Facebook)     │ TOP DRIVERS                              │
│ Like/Love/Haha reaction mix      │ Keyword chips per aspect (neg-weighted)  │
│ donut + reaction-ratio trend     │ "Recently flagged" review preview list  │
└─────────────────────────────────┴──────────────────────────────────────────┘

                                                            ┌───────────────┐
                                                            │ 💬 Ask Data AI│  ← floating action
                                                            └───────────────┘   button, bottom-right
```

**Interaction notes**
- Every chart is a filter: clicking an aspect bar, radar axis, or time-series segment narrows the whole page (breadcrumb trail shows active filters, one-click clear).
- The Entity Switcher supports single-brand or side-by-side compare mode; compare mode duplicates color-coded series rather than opening a second page.
- KPI cards are clickable and deep-link to the relevant panel already filtered/scrolled into view (progressive disclosure, not a redirect to a separate page).

### 1.2 Global Navigation (updated)

Adding two new primary destinations alongside the Overview and the existing Escalation Queue:

```
Sidebar / top nav order:
1. Overview              (Section 1)
2. Escalation Queue       (Section 4, original doc)
3. Agentic Inbox    🔥2   (Section 5.2 — badge shows open crisis-severity alerts)
4. Data Mining & Insights (Section 5.3)
```

"Chat with Data" is deliberately **not** a nav destination — it's a global overlay (drawer), reachable from every page via `Cmd/Ctrl + K` or the floating action button, so an analyst never has to leave their current filtered context to ask a question.

---

## 2. Component Library Recommendations

Optimized for: fast adoption by a 6-person team, minimal bespoke chart-building, good dark-mode defaults, and a data-grid that can handle a live triage queue.

| Layer | Recommendation | Why |
|---|---|---|
| Styling foundation | **Tailwind CSS** | Team-wide shared vocabulary, no CSS drift across 6 contributors |
| UI primitives | **shadcn/ui** | Copy-in components (not an npm black box) — dialog, dropdown, tabs, drawer, command palette. Fully ownable/editable, which matters once you need custom drawer/keyboard behavior for the queue |
| BI charts & KPI cards | **Tremor** (or Tremor Raw) | Purpose-built for exactly this: KPI cards, area/bar/line charts, spark-lines, category bars — built on Recharts, saves weeks vs. hand-rolling |
| Radar chart | **Recharts** (`RadarChart`) directly, or **Visx** if you need custom confidence-shaded axes | Tremor has no radar primitive; Recharts is already a dependency via Tremor so no extra weight |
| Escalation queue data grid | **TanStack Table (react-table v8)** | Headless — pair with shadcn table primitives for styling. Handles sorting, filtering, row-selection, and virtualization (needed once the queue has thousands of rows) |
| Data fetching / caching | **TanStack Query** | Pairs cleanly with Next.js route handlers hitting Postgres; handles the polling/refetch pattern for "sync: 12 min ago" |
| Global state (filters, entity, date range) | **Zustand** | Lighter than Redux, easy for a small team to reason about; keep filters in URL search params too so views are shareable/bookmarkable |
| Date range picker | **react-day-picker** (shadcn wraps this) | Already integrated with shadcn's popover pattern |
| Micro-interactions (drawer slide, row expand) | **Framer Motion** | Use sparingly — see UX section on restraint |
| Theming | **next-themes** | Simple dark/light persistence if you ever add a light mode later |
| **Command palette / global drawer trigger** | **cmdk** (shadcn's `Command` component wraps it) | Same primitive that powers `Cmd+K` in most modern SaaS tools — already in the shadcn ecosystem, so no new dependency to justify |
| **AI chat streaming** | **Vercel AI SDK (`ai` package)** | `useChat`/`useCompletion` hooks handle token-streaming state, loading, and abort out of the box against a Next.js route handler — avoids hand-rolling SSE parsing for the Text-to-SQL responses |
| **SQL / code syntax highlighting** | **Shiki** (or `react-syntax-highlighter` if bundle size is less of a concern) | Renders the generated SQL block in the chat stream with proper dark-mode-native theming (Shiki ships VS Code themes directly) |
| **Association-rule network graph** | **react-force-graph-2d** (canvas-based) for large rule sets, or **Visx `Graph`** if you want full control over node/edge styling with Tailwind tokens | Recharts has no network/graph primitive; force-graph is the lightest-weight option that still handles physics-based layout without a heavy dependency like Cytoscape |
| **Entity clustering scatter + hulls** | **Recharts `ScatterChart`** for points, **d3-polygon / d3-hierarchy** (already a transitive dependency via Visx/Recharts) for convex-hull cluster boundaries | Keeps the whole clustering view inside the existing charting stack instead of introducing a dedicated plotting library |
| **Burmese Unicode font** | **Noto Sans Myanmar**, loaded via `next/font/google` | Only Google-hosted font family with full Myanmar Unicode block coverage and consistent glyph rendering across OS/browser combinations; critical since system fonts render Burmese inconsistently on Windows vs. macOS |

**Why this stack over alternatives:** Tremor + shadcn/ui is the fastest realistic path for a 6-person team to ship a *good-looking, consistent* BI tool without a dedicated design engineer — Tremor removes chart-building as a bottleneck, shadcn removes "which component library has the right dropdown/drawer" debates, and both are Tailwind-native so there's one styling language across the whole app. Avoid mixing in a second heavy charting library (e.g., full ECharts or Highcharts) unless a specific visualization genuinely can't be done in Recharts — extra charting engines are a common source of dark-mode theming drift. The Section 5 additions (force-graph, Shiki, AI SDK) are each single-purpose and narrow in scope specifically so this principle still holds: everything that *can* stay inside Tremor/Recharts does.

---

## 3. Color Palette & Theming (Dark Mode)

Design goals: sentiment must be distinguishable at a glance, safe for red-green color blindness (roughly 8% of male users), and calm enough for all-day analyst use — no pure black, no saturated red/green pairing.

### 3.1 Surfaces & Text

| Token | Hex | Usage |
|---|---|---|
| `bg-base` | `#0B0F14` | App background — near-black blue-charcoal, not pure black (reduces OLED smear/eye strain) |
| `bg-surface` | `#131A21` | Cards, panels |
| `bg-elevated` | `#1B242C` | Hover states, popovers, drawer |
| `border` | `#232E38` | Dividers, table borders |
| `text-primary` | `#E6EDF3` | Headlines, body |
| `text-muted` | `#8B98A5` | Labels, timestamps, secondary metadata |

### 3.2 Sentiment Encoding (the critical set)

Avoid pure red/green — they're the single most common colorblind-accessibility failure in dashboards. Use a teal/coral pairing instead, which stays distinguishable under deuteranopia/protanopia, and always pair color with a shape or icon (▲/▼/●) so meaning never depends on hue alone.

| Sentiment | Hex | Notes |
|---|---|---|
| Positive | `#2DD4A7` | Cyan-leaning teal, not pure green |
| Negative | `#FF6B5E` | Warm coral-red, not pure red |
| Neutral | `#E8B339` | Amber — deliberately a third hue family, not a gray, so it reads as a real category rather than "no data" |

### 3.3 Accent & Alert Colors

| Token | Hex | Usage |
|---|---|---|
| `accent-primary` | `#5B8DEF` | Interactive elements, active filters, links, selected states |
| `accent-hangry` | `#FF9F5A` | Reserved *only* for the Hangry Index — a distinct warm orange so this custom metric visually stands apart from standard negative-sentiment coral |
| `confidence-ramp` | `#26343F → #5B8DEF` | Single-hue saturation ramp (low→high confidence) — deliberately not red/yellow/green so it's never confused with sentiment |

### 3.4 System & Agentic Tokens (new)

These exist because Section 5 introduces states that are *not* sentiment but still need urgency signaling — reusing the sentiment palette for them would violate the platform's own color-meaning rules below.

| Token | Hex | Usage |
|---|---|---|
| `alert-critical` | `#EF4444` | Crisis banners, topbar badge, agentic inbox unread-critical indicator — a hotter, more saturated red than `Negative` so a genuine crisis visually outranks routine negative sentiment |
| `alert-sarcasm` | `#C77DFF` | `haha_ratio` sarcasm-risk badge — a distinct purple family, so "this looks positive but might be mockery" never gets mistaken for Neutral (amber) or Positive (teal) |
| `badge-incomplete` | `#4B5563` (on `bg-elevated`) | "Data Incomplete" badge — deliberately desaturated/gray so it reads as an *absence of information*, not a data point competing with sentiment colors |
| `tag-burglish` | outline only, `border-color: accent-primary`, transparent fill | `[Burglish]` language tag — outline-only so it doesn't compete visually with sentiment fills inside a dense table row |

### 3.5 Rules of use

- Sentiment colors are reserved exclusively for sentiment. Don't reuse coral or teal for unrelated states (errors, success toasts, crisis alerts) — that overloads the color's meaning. This is precisely why Section 3.4 exists as a separate token set rather than reusing `Negative` for crisis banners.
- Cap saturated color to data only. Chrome (nav, borders, backgrounds) stays neutral gray-blue so the eye goes straight to what changed.
- Every sentiment color pairing in a legend or chart also gets a text label or icon — never rely on a color key alone. The same rule applies to `alert-critical` and `alert-sarcasm`: always pair with an icon (🔥 for crisis, 😏 or a distinct "sarcasm" glyph) and a text label.

---

## 4. UX Best Practices for Daily Analyst Use

**Reduce reorientation cost**
- Keep the entity switcher and date range sticky across every page, including the escalation queue and the new Agentic Inbox / Data Mining tabs — analysts shouldn't have to re-establish context when moving between views.
- Persist filters in the URL (query params), not just client state, so a filtered view is bookmarkable and shareable in Slack/email.

**Progressive disclosure over density**
- KPI cards are entry points, not endpoints — clicking one scrolls/filters into the relevant detail panel rather than dumping every metric on screen at once.
- Default to a summary view; let analysts opt into denser table/raw-data views rather than defaulting to maximum density.

**Make the escalation queue fast, not just usable**
- Full keyboard triage (`j/k`, `A/R/E`) — this is the highest-leverage change for a queue touched daily; mouse-driven triage doesn't scale past a few dozen items a day.
- Optimistic actions with an undo toast instead of confirm dialogs. Confirm dialogs feel safer but they add friction to every single action on a queue whose whole point is throughput.
- Make the confidence threshold (currently 0.60) a configurable slider, not a hardcoded cutoff — thresholds tend to need tuning once real usage patterns emerge.
- Show model version and timestamp on every prediction — this builds analyst trust in the AI layer and matters for auditing corrections over time.

**Give context to spikes, not just data**
- Annotate the time-series chart with event markers (promo launches, viral posts, PR incidents) so an engagement or sentiment spike has a "why" attached instead of requiring the analyst to go dig through raw posts.

**Consistency reduces cognitive load more than any single feature**
- Use one fixed icon per business aspect (Product Quality, Fulfillment & Speed, Price & Value, Digital Experience, Customer Support, Variety & Availability) and reuse it everywhere — radar axis label, table column, filter chip, chart legend, and the new Association Rule Network / Cluster views in Section 5.3. Consistent iconography lets analysts pattern-match instead of re-reading labels.
- Keep action verb labels consistent end-to-end: if a button says "Approve," the resulting toast should say "Approved," not "Saved" or "Updated." This now also applies to the Agentic Inbox — "Draft Sent for Review" is a distinct, consistent status from "Draft Approved" or "Draft Rejected."

**Respect daily-use fatigue**
- Skeleton loaders instead of spinners — reduces perceived wait and layout jump on a page analysts open dozens of times a day. This includes the AI chat drawer: stream tokens in as they arrive (via the AI SDK) rather than showing a spinner until the full answer is ready.
- Write empty and error states in plain, specific language ("No reviews matched these filters — try widening the date range" rather than a generic "No data"), since these states show up often for anyone actively filtering data. Apply the same standard to "Data Incomplete" states (Section 5.4) — explain *why*, not just *that*.
- Consider a saved-view feature per analyst (e.g., "my daily triage view," "weekly exec summary") so people don't have to reconstruct the same filter set every session. Extend this to Chat with Data: let an analyst "Pin to Dashboard" a query result, which is really just saving a named view with a generated-SQL source attached.

---

## 5. Advanced Agentic & Data Mining Extensions

This section specifies the four feature modules previously scoped in discussion but missing from the initial draft. Each follows the same format as Sections 1–4: layout, components (mapped to the Section 2 stack), interaction rules, and states/edge-cases.

### 5.1 "Chat with Data" (Text-to-SQL AI Interface)

**Placement:** Global slide-over drawer (shadcn `Sheet`, right-anchored, ~420–480px wide on desktop, full-screen on mobile). Triggered by `Cmd/Ctrl + K` from anywhere in the app, or the floating action button (`💬 Ask Data AI`) pinned bottom-right on every page. The drawer overlays the current page rather than navigating away — filters and scroll position on the underlying dashboard are preserved when it closes.

```
┌────────────────────────────────────────────┐
│ Ask Data AI                            [×] │
├────────────────────────────────────────────┤
│  ┌──────────────────────────────────────┐  │
│  │ 🧑 Which Foodpanda branch had the     │  │
│  │    worst delivery speed score last    │  │
│  │    Friday?                            │  │
│  └──────────────────────────────────────┘  │
│                                              │
│  ┌──────────────────────────────────────┐  │
│  │ 🤖  Yangon Downtown had the lowest    │  │
│  │     Fulfillment & Speed score (2.1/5) │  │
│  │     last Friday, from 340 reviews.    │  │
│  │                                        │  │
│  │  ▸ View generated SQL                 │  │
│  │                                        │  │
│  │  ┌────────────────────────────────┐   │  │
│  │  │ [mini bar chart: branch ranking]│  │  │
│  │  └────────────────────────────────┘   │  │
│  │                                        │  │
│  │  [ Export to CSV ]  [ 📌 Pin to      │  │
│  │                        Dashboard ]    │  │
│  └──────────────────────────────────────┘  │
│                                              │
├────────────────────────────────────────────┤
│ [ 🇲🇲/EN  Ask about your data...       ➤ ]  │
└────────────────────────────────────────────┘
```

**Components (mapped to Section 2 stack):**
- Drawer shell: shadcn `Sheet` + `Command` (the same `cmdk` primitive doubles as the `Cmd+K` launcher and the in-drawer input).
- Message stream: plain flex-column list; each AI turn is a shadcn `Card` on `bg-elevated`.
- Generated SQL: collapsible `<details>`-style shadcn `Collapsible`, syntax-highlighted with Shiki, monospace, copy-to-clipboard button.
- Inline charts/tables: reuse actual Tremor primitives (`BarChart`, `Table`, KPI `Card`) at a reduced/compact size — **not** a screenshot or a separate mini-chart library, so a pinned result renders identically wherever it lands.
- Streaming: Vercel AI SDK `useChat`, hitting a Next.js route handler that (a) sends the NL query + schema context to the LLM to produce SQL, (b) executes the SQL read-only against Postgres, (c) returns both the SQL and result rows for the client to render.

**Interaction rules:**
- Language: input accepts Burmese or English in the same field (no separate toggle needed for typing) — the toggle shown (`🇲🇲/EN`) only controls the *response* language, defaulting to match the input language.
- Generated SQL is collapsed by default (progressive disclosure — most analysts want the answer, not the query) but always present, so a technical user can audit or copy it.
- "Export to CSV" exports the exact result set behind the rendered chart/table, not a re-query.
- "Pin to Dashboard" opens a lightweight placement picker (which panel row, or a new "Pinned Queries" panel) — this is the same underlying mechanism as the saved-view feature in Section 4.
- Every generated query is read-only (`SELECT`-only execution role at the DB layer) — this is a data-safety requirement, not just a UX one, and should be enforced server-side, not just implied by the UI.
- If the model can't map the question to the star schema confidently, show a clarifying-question turn instead of guessing (e.g., *"Did you mean delivery speed for Foodpanda orders, or the 'Fulfillment & Speed' review aspect?"*) rather than silently returning a wrong-but-plausible chart.

---

### 5.2 Agentic AI Command Center & Autonomous Crisis Alerts

**Placement:** A dedicated **"Agentic Inbox"** nav tab (badge shows count of unresolved critical alerts, using `alert-critical` red) plus a slim, dismissible topbar banner that appears app-wide the moment a new crisis-severity event fires — so an analyst on the Overview page doesn't have to be on the Inbox tab to notice.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ TOPBAR BANNER (appears on any page, dismissible, non-blocking)               │
│ 🔥 Crisis Alert — negativity_ratio 0.08 on OMUK Foodpanda (last 2h)          │
│                                            [ View in Agentic Inbox ]  [×]    │
├──────────────────────────────────────────────────────────────────────────────┤
│ AGENTIC INBOX                                                                 │
│ Filters: [ All ] [ Crisis ] [ Sarcasm Risk ] [ Resolved ]     Sort: Newest ▾ │
├──────────────────────────────────────────────────────────────────────────────┤
│ ┌────────────────────────────────────────────────────────────────────────┐   │
│ │ 🔥 CRISIS · negativity_ratio 0.08 (threshold 0.05)                     │   │
│ │ OMUK Foodpanda · Fulfillment & Speed · last 2h · 46 reviews            │   │
│ │                                                                          │   │
│ │ [ 🇲🇲 Draft AI Response ]   [ View Reviews ]   [ Mark Resolved ]        │   │
│ └────────────────────────────────────────────────────────────────────────┘   │
│ ┌────────────────────────────────────────────────────────────────────────┐   │
│ │ 😏 SARCASM RISK · haha_ratio 34% on FB post #4821                      │   │
│ │ "Wow, 2 hour delivery, amazing service 👏" — posted 18:12               │   │
│ │                                                                          │   │
│ │ [ View Post ]   [ Flag for Review ]                                    │   │
│ └────────────────────────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────────────────────┤
│ AGENT ACTION HISTORY (audit log, chronological, read-only)                    │
│ 18:45  Slack alert → Operations Manager (crisis #219)                        │
│ 18:12  Flagged FB post #4821 for sarcasm review                              │
│ 17:03  Draft response generated, awaiting CS approval (ticket #217)          │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Components (mapped to Section 2 stack):**
- Crisis/sarcasm cards: shadcn `Card` + `Badge` (using `alert-critical` / `alert-sarcasm` tokens from 3.4), laid out in the same `Card` grid pattern as the KPI strip for visual consistency.
- Filter bar: shadcn `Tabs` or `ToggleGroup`, same pattern as the Aspect Breakdown's sort control.
- Action History: TanStack Table in a compact, non-virtualized log view (append-only, low row count relative to the escalation queue — virtualization isn't needed here the way it is in Section 4's queue).
- Response Drafter: opens as a shadcn `Dialog` (not the slide-over drawer — this is a discrete approve/edit/reject action, not an exploratory chat), pre-filled with the AI-drafted Burmese reply, editable textarea, and explicit `[ Send for CS Approval ]` — **never** an auto-send button. A human approval step is a hard requirement for anything customer-facing, not a nice-to-have.
- Topbar banner: a slim, app-wide toast-like bar (Framer Motion slide-down, used sparingly per the restraint principle in Section 2) — auto-persists until dismissed or resolved, doesn't auto-hide on a timer, since a crisis alert shouldn't disappear just because nobody clicked it fast enough.

**Interaction rules / thresholds:**
- Crisis trigger: `negativity_ratio > 0.05` (configurable, same "don't hardcode thresholds" principle as the escalation queue's 0.60 confidence cutoff in Section 4).
- Sarcasm-risk trigger: `haha_ratio > 30%` on a Facebook post — flagged for human review, **never** auto-reclassified as negative; the model surfaces the risk, a person makes the call.
- Every automated action (Slack ping, draft generation, flag) writes one line to Agent Action History with an exact timestamp — this is the audit trail that makes the "autonomous" part of "autonomous crisis alerts" trustworthy rather than opaque.
- "Mark Resolved" requires the analyst to pick a resolution reason from a short fixed list (e.g., *False positive / Addressed operationally / Escalated externally*) rather than a bare button — this turns the inbox into a dataset you can later mine for false-positive rate on the 0.05 threshold itself.

---

### 5.3 Data Mining & Insights Tab

**Placement:** Secondary nav tab, **"Data Mining & Insights"**, positioned after Agentic Inbox. Two sub-views selected via an in-page `Tabs` control (not separate routes, so filters/date-range stay in sync): **Association Rules** and **Entity Clusters**.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ DATA MINING & INSIGHTS        [ Association Rules ]  [ Entity Clusters ]     │
├──────────────────────────────────────────────────────────────────────────────┤
│  ASSOCIATION RULES (Apriori / FP-Growth)                                     │
│                                                                                │
│        [Fulfillment                                                          │
│         & Speed: Neg] ───82%───▶ [Customer Support: Neg]                     │
│              │                          │                                    │
│            65%                        41%                                    │
│              ▼                          ▼                                    │
│        [Price & Value: Neg]      [Digital Experience: Neg]                   │
│                                                                                │
│  Node size = support (frequency) · Edge thickness/label = confidence %       │
│  Hover edge → lift, support count, sample review snippets                    │
│  Sidebar: min-support / min-confidence sliders, aspect icon legend           │
├──────────────────────────────────────────────────────────────────────────────┤
│  ENTITY CLUSTERS (K-Means / Hierarchical)                                    │
│                                                                                │
│      ●High Quality /            ●●●                                          │
│       Slow Delivery      ●   ●●●●●  ← convex hull outline per cluster        │
│         cluster            ●●                                                │
│                                        ●●● Low Price /                       │
│                                       ●●●●● High Risk cluster                │
│                                                                                │
│  X/Y axis selectable (e.g., avg Fulfillment score vs. avg Price score)       │
│  Point = one Foodpanda branch or FB Page · hover → name, n reviews, cluster  │
│  Sidebar: k selector, algorithm toggle (K-Means / Hierarchical), legend      │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Components (mapped to Section 2 stack):**
- Association Rule Network: **react-force-graph-2d**, nodes styled with the fixed per-aspect icon set from Section 4 ("Consistency reduces cognitive load"), edge color on the single-hue `confidence-ramp` token (never sentiment colors — a rule's confidence is a different kind of measurement than a sentiment score, and reusing coral/teal here would visually claim it's sentiment-encoded).
- Alternate/fallback view: for teams that find a force-directed graph too unstable to read at a glance, offer a same-data **heatmap matrix** (aspect × aspect, cell = confidence %) as a Tremor-compatible `Table`-based heatmap — a toggle between "Network" and "Matrix" view of the identical rule set.
- Entity Clusters: Recharts `ScatterChart`, cluster hulls drawn as SVG polygons computed via `d3-polygon` convex hull, colored by cluster with the same accent-family approach (each cluster gets a distinct accent, not a sentiment color, since cluster membership isn't a sentiment measurement).
- Sliders (min-support, min-confidence, k): shadcn `Slider`, same component already used for the escalation queue's confidence threshold in Section 4 — one slider pattern reused everywhere.

**Interaction rules:**
- Both views respect the global entity/date-range filter (Section 4's "reduce reorientation cost") — mining is run against whatever the analyst currently has selected, not a fixed global dataset.
- Clicking a node in the Association Rule view or a point in the Cluster view drills into the underlying review set (same "every chart is a filter" principle from Section 1.1), not a dead-end visualization.
- Clustering is inherently unstable at small sample sizes — show a minimum-sample warning (e.g., *"Fewer than 30 reviews for this entity — cluster assignment may be unreliable"*) rather than silently plotting a misleading point.
- Because this tab is explicitly academic/analytical rather than operational, it's the one place in the app where a denser default view is acceptable — this is the exception to Section 4's "default to summary" rule, flagged here so it doesn't read as an inconsistency.

---

### 5.4 Advanced Reaction Metrics & Burmese Language Context

**Placement:** Expansion of the existing Social Engagement panel (Section 1.1, bottom-left) — not a new panel, so it stays adjacent to the reaction donut/trend it contextualizes.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ SOCIAL ENGAGEMENT (Facebook) — expanded                                      │
│                                                                                │
│  [donut: Like/Love/Haha mix]     Positivity Ratio:   62%                     │
│                                    Negativity Ratio:   18%                     │
│                                    😏 Haha Ratio:      34%  [Sarcasm Risk]     │
│                                                                                │
│  ⚠ Data Incomplete — 3 posts missing reaction breakdown (ratios shown        │
│     as N/A for those posts, not counted as 0%)                               │
│                                                                                │
│  Recent reviews:                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ "hote food ma pyaw bu, ache ma lay bu"  [Burglish]     ● Negative     │   │
│  │ "ဟိုတယ်ဝန်ဆောင်မှုအရမ်းကောင်းတယ်"                        ● Positive     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Components (mapped to Section 2 stack):**
- Ratio display: Tremor `Metric` + `Text` pairs (reusing the KPI card's internal typography scale, not a new component), each ratio's icon/badge using the tokens from Section 3.4 (`alert-sarcasm` purple specifically for the haha-ratio badge).
- "Data Incomplete" badge: shadcn `Badge` in `badge-incomplete` gray, with a tooltip (shadcn `Tooltip`) explaining *why* — reinforcing the Section 4 principle that empty/partial states need plain, specific language, not a bare icon.
- `[Burglish]` tag: outline-only shadcn `Badge` per the `tag-burglish` token — appears next to any review the language-detection step classifies as Romanized Burmese rather than native Unicode script or English.
- Review text rendering: `next/font/google` Noto Sans Myanmar applied conditionally (via a `lang="my"` attribute check) so native Unicode Burmese renders with correct glyph shaping while Burglish/English rows keep the app's default UI font — mixing font families in the same column is intentional here, not a bug, since Noto Sans Myanmar's Latin glyphs look visually inconsistent with the rest of the UI.

**Interaction rules / data rules:**
- `reactions_breakdown_complete = False` → all three ratios render as `N/A` for that post specifically, never `0%`. This is a correctness requirement, not just a display choice: silently coercing missing data to zero would understate both positivity and negativity for that post and skew any aggregate built on top of it.
- The incomplete-data badge should be scoped per-post in any drill-down (so an analyst can see *which* posts are missing data), and aggregated as a count/percentage at the panel level (*"3 of 46 posts"*) — both levels matter for trust in the aggregate ratios shown above.
- `haha_ratio > 30%` here is the same threshold that triggers the Sarcasm Risk card in the Agentic Inbox (Section 5.2) — the panel-level badge and the inbox alert must read the exact same underlying field so an analyst never sees the panel say "34%, flagged" while the inbox shows nothing, or vice versa.
- Burmese text fields should never be truncated with a naive character-count `substring()` — Unicode grapheme clusters in Myanmar script combine multiple codepoints per visual character, so truncation must be grapheme-aware (e.g., `Intl.Segmenter`) or the risk is literally splitting a character in half mid-render.

---

## Suggested Next Steps

1. Lock the token system (colors, spacing scale, type scale) in a shared `tailwind.config` before any team member starts building panels — this is what prevents six people's work from visually drifting apart. This now explicitly includes the Section 3.4 system/agentic tokens, so nobody reaches for `Negative` coral when they mean `alert-critical`.
2. Build the escalation queue drawer + keyboard flow first — it's the highest-risk interaction pattern (React Table + focus management + optimistic updates) and best to de-risk early.
3. Stub the KPI/chart panels with mock data shaped like your real star-schema query output, so swapping in the live PostgreSQL-backed API routes later is a data-layer change only, not a UI rewrite.
4. **New:** Build the "Chat with Data" drawer second, before the Agentic Inbox or Data Mining tab — it shares the read-only SQL execution layer and streaming infrastructure (Vercel AI SDK + route handler) that the Automated Response Drafter in Section 5.2 will also depend on, so building it first avoids duplicating that plumbing later.
5. **New:** Treat the crisis-alert and sarcasm-risk thresholds (0.05, 30%) as config values from day one, not constants — Section 4's escalation-queue threshold already established this pattern; carry it through consistently rather than hardcoding the new thresholds and having to retrofit configurability under pressure once real usage reveals they need tuning.
