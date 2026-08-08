# BI & ABSA Analytics Platform — UI/UX Architecture (v3)

**Stack context:** Next.js · PostgreSQL Star Schema · XLM-RoBERTa two-stage ABSA · Facebook + Foodpanda ETL
**Team size:** 6 engineers · **Theme:** Dark mode primary

**v3 changelog:** Adds Section 5.5 (Competitor Share of Voice & Benchmarking), 5.6 (Data Pipeline & ETL Lineage Health Monitor), and 5.7 (Scrape Management & Entity Configuration) — plus the supporting design tokens they require in Sections 3.6–3.7. Also formalizes Section 5.1's AI Response Card into its four-layer anatomy (summary → interactive chart/table → collapsible SQL → actions), adding dynamic Chart/Table view switching and a "View Raw Reviews" action alongside Pin to Dashboard and Export CSV. Everything else in Sections 1–5.4 is unchanged except two short cross-reference additions (§1.2, §"Suggested Next Steps") pointing at the new material.

---

## 1. Dashboard Layout Structure

### 1.1 Main Dashboard (Overview)

The dashboard is built as a strict grid so panels can be reordered/resized later without a rewrite. Global controls are pinned; everything below scrolls.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ TOPBAR (sticky)                                                               │
│ Logo   Entity: [OMUK ▾]                       Date Range: [Last 30d ▾]          │
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
- The Entity Switcher controls the primary scope. Side-by-side comparison is configured locally inside the Aspect Radar, Competitor Benchmark, and Data Mining views.
- KPI cards are clickable and deep-link to the relevant panel already filtered/scrolled into view (progressive disclosure, not a redirect to a separate page).

### 1.2 Global Navigation (updated)

Adding one new primary destination alongside the Overview and the existing Escalation Queue:

```
Sidebar / top nav order:
1. Overview              (Section 1)
2. Escalation Queue       (Section 4, original doc)
3. Data Mining & Insights (Section 5.3)
```

"Chat with Data" is deliberately **not** a nav destination — it's a global overlay (drawer), reachable from every page via `Cmd/Ctrl + K` or the floating action button, so an analyst never has to leave their current filtered context to ask a question.

The same principle holds for the v3 additions: **Competitor Benchmark** is a page-level toggle on the Overview with its own head-to-head selectors, and **ETL Pipeline Health** opens from the existing topbar sync badge. Neither earns another sidebar item — each reuses an existing entry point.

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

### 3.4 System & Risk Tokens (new)

These exist because Section 5 introduces states that are *not* sentiment but still need urgency signaling — reusing the sentiment palette for them would violate the platform's own color-meaning rules below.

| Token | Hex | Usage |
|---|---|---|
| `alert-critical` | `#EF4444` | Pipeline failures and operational-disconnect warnings — a hotter, more saturated red than `Negative` so system urgency stays distinct from routine negative sentiment |
| `alert-sarcasm` | `#C77DFF` | `haha_ratio` sarcasm-risk badge — a distinct purple family, so "this looks positive but might be mockery" never gets mistaken for Neutral (amber) or Positive (teal) |
| `badge-incomplete` | `#4B5563` (on `bg-elevated`) | "Data Incomplete" badge — deliberately desaturated/gray so it reads as an *absence of information*, not a data point competing with sentiment colors |
| `tag-burglish` | outline only, `border-color: accent-primary`, transparent fill | `[Burglish]` language tag — outline-only so it doesn't compete visually with sentiment fills inside a dense table row |

### 3.5 Rules of use

- Sentiment colors are reserved exclusively for sentiment. Don't reuse coral or teal for unrelated states such as errors or success toasts — that overloads the color's meaning. This is why Section 3.4 keeps system urgency separate from sentiment.
- Cap saturated color to data only. Chrome (nav, borders, backgrounds) stays neutral gray-blue so the eye goes straight to what changed.
- Every sentiment color pairing in a legend or chart also gets a text label or icon — never rely on a color key alone. The same rule applies to `alert-critical` and `alert-sarcasm`: always pair them with an icon and a text label.

### 3.6 Competitive Benchmarking Tokens (new, v3)

Share of Voice and head-to-head comparisons (Section 5.5) need to encode *which entity* a data point belongs to — a dimension nothing above covers, since §3.2–3.4 encode sentiment, confidence, and system/agentic state, not brand identity. These are additive, not a fourth "meaning system" competing with sentiment — they're strictly for series/entity identity in places where sentiment is already handled separately (e.g., the matrix's cell shading below).

| Token | Hex | Usage |
|---|---|---|
| `entity-self` | `#5B8DEF` (reuses `accent-primary`) | The home brand (e.g., OMUK) across every benchmarking chart — reusing `accent-primary` ties "our brand" to the same hue already meaning "active/selected" elsewhere, so analysts don't have to learn a new association |
| `entity-compare-1` | `#38BDF8` | First competitor series (e.g., Lotteria) — a blue-family hue chosen specifically to sit outside both the sentiment family (teal/coral/amber) and the alert family (red/purple/gray), so it can never be misread as a sentiment or urgency signal |
| `entity-compare-2` | `#F472B6` | Second competitor series (e.g., Marrybrown) — pink family, same non-sentiment/non-alert constraint |
| `sentiment-diverging` | `#FF6B5E → #E8B339 → #2DD4A7` | Not a new hue — a continuous interpolation across the *existing* `Negative → Neutral → Positive` tokens (§3.2), formalized as its own name because Section 5.5 is the first place it's used as a continuous gradient (matrix cell shading) rather than three discrete swatches |

**Rule of use (extension of §3.5):** entity-series tokens answer "whose data point is this" (SoV slice, matrix column header, legend swatch). `sentiment-diverging` answers "how positive/negative is this value." A single visual element should never be styled by both at once — a SoV donut slice is colored by entity; the percentage written inside a matrix cell is shaded by sentiment. Keeping those two questions on separate tokens is the whole point of this table.

### 3.7 System & Pipeline Status Tokens (new roles, reused hex, v3)

The ETL Health Monitor (Section 5.6) needs an Active / Idle / Error vocabulary that is explicitly **not** sentiment — even though "healthy" invites reaching for `Positive` teal. Per §3.5, sentiment colors are reserved exclusively for sentiment, so this table assigns *existing, non-sentiment* tokens a new role rather than minting new hex values.

| Token | Hex (existing) | New role |
|---|---|---|
| `accent-primary` | `#5B8DEF` | Pipeline node status = Active/Healthy — reuses the existing "interactive/active" meaning instead of introducing a health-specific green that would collide with `Positive` |
| `badge-incomplete` | `#4B5563` | Pipeline node status = Idle/Paused — the same desaturated gray already used for "absence of information" (§3.4) fits "not currently doing anything" |
| `alert-critical` | `#EF4444` | Pipeline node status = Error/Degraded — the same hot red reserved for crisis-severity states, since a broken pipeline node is operationally urgent in the same register as a crisis alert |

---

## 4. UX Best Practices for Daily Analyst Use

**Reduce reorientation cost**
- Keep the entity switcher and date range sticky on analysis surfaces that consume them: Dashboard, Analytics, and Data Mining. Hide them on Entities, Scraping, and Chat with Data so page-level controls remain relevant to the task at hand.
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
- Use one fixed icon per business aspect (Product Quality, Fulfillment & Speed, Price & Value, Staff & Service, Variety & Availability) and reuse it everywhere — radar axis label, table column, filter chip, chart legend, and the new Association Rule Network / Cluster views in Section 5.3. Consistent iconography lets analysts pattern-match instead of re-reading labels.
- Keep action verb labels consistent end-to-end: if a button says "Approve," the resulting toast should say "Approved," not "Saved" or "Updated."

**Respect daily-use fatigue**
- Skeleton loaders instead of spinners — reduces perceived wait and layout jump on a page analysts open dozens of times a day. This includes the AI chat drawer: stream tokens in as they arrive (via the AI SDK) rather than showing a spinner until the full answer is ready.
- Write empty and error states in plain, specific language ("No reviews matched these filters — try widening the date range" rather than a generic "No data"), since these states show up often for anyone actively filtering data. Apply the same standard to "Data Incomplete" states (Section 5.4) — explain *why*, not just *that*.
- Consider a saved-view feature per analyst (e.g., "my daily triage view," "weekly exec summary") so people don't have to reconstruct the same filter set every session. Extend this to Chat with Data: let an analyst "Pin to Dashboard" a query result, which is really just saving a named view with a generated-SQL source attached.

---

## 5. Advanced Analytics, Data Mining & Platform Extensions

This section specifies feature modules previously scoped in discussion but missing from earlier drafts: four introduced in v2 (5.1–5.4), plus **5.5 Competitor Share of Voice & Benchmarking** and **5.6 Data Pipeline & ETL Lineage Health Monitor** in v3. Each follows the same format as Sections 1–4: layout, components (mapped to the Section 2 stack), interaction rules, and states/edge-cases.

### 5.1 "Chat with Data" (Text-to-SQL AI Interface)

**Placement:** Global slide-over drawer (shadcn `Sheet`, right-anchored, ~420–480px wide on desktop, full-screen on mobile). Triggered by `Cmd/Ctrl + K` from anywhere in the app, or the floating action button (`💬 Ask Data AI`) pinned bottom-right on every page. The drawer overlays the current page rather than navigating away — filters and scroll position on the underlying dashboard are preserved when it closes.

**The AI Response Card — four layers, not raw rows:** every AI turn renders as a single structured card, never a bare SQL result dump. Non-technical analysts are the primary audience for this drawer, and a wall of database rows (or a code block) forces them to translate the answer themselves; the card does that translation once, consistently, for everyone. The four layers below are always present in this order — a turn is never missing a layer, only collapsing one (the SQL is always there, just closed by default):

1. **Natural language summary** (Burmese or English, matching the input language) — the headline finding in plain prose, not a caption under a chart.
2. **Interactive chart or table** — a live Tremor component, not a static image, so hover/tooltip behavior works identically to its full-size counterpart on the dashboard.
3. **Collapsible SQL audit** — closed by default, always present, for the technical minority who want to verify or copy the query.
4. **Action controls** — Pin to Dashboard, Export CSV, and View Raw Reviews, so the answer can be acted on without leaving the drawer.

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
│  ┌── 🤖 AI RESPONSE CARD ─────────────────┐ │
│  │                                        │ │
│  │ ① Yangon Downtown had the lowest       │ │
│  │   Fulfillment & Speed score (2.1/5)    │ │
│  │   last Friday, driven by 340 delivery  │ │
│  │   delay complaints.                    │ │
│  │                                        │ │
│  │ ②                       [Chart│Table▾] │ │
│  │   ┌──────────────────────────────┐     │ │
│  │   │ Lotteria    ▇▇ 2.1            │     │ │
│  │   │ OMUK        ▇▇▇▇▇ 4.2         │     │ │
│  │   │ Marrybrown  ▇▇▇▇ 3.8          │     │ │
│  │   │  ↑ hover → n reviews, date,   │     │ │
│  │   │    avg confidence             │     │ │
│  │   └──────────────────────────────┘     │ │
│  │                                        │ │
│  │ ③ ▸ View generated SQL                 │ │
│  │                                        │ │
│  │ ④ [📌 Pin to Dashboard] [📥 Export CSV]│ │
│  │    [🔍 View Raw Reviews]               │ │
│  └────────────────────────────────────────┘ │
│                                              │
├────────────────────────────────────────────┤
│ [ 🇲🇲/EN  Ask about your data...       ➤ ]  │
└────────────────────────────────────────────┘
```

**Components (mapped to Section 2 stack):**
- Drawer shell: shadcn `Sheet` + `Command` (the same `cmdk` primitive doubles as the `Cmd+K` launcher and the in-drawer input).
- Message stream: plain flex-column list; each AI turn is a shadcn `Card` on `bg-elevated`, structured internally as the four layers above — never a single unstructured text blob.
- Layer ② dynamic view switching: shadcn `Tabs`/`ToggleGroup` — the same control pattern already reused for the Overview/Competitor Benchmark toggle in §5.5 — flipping between a compact Tremor `BarChart`/`LineChart` and a compact Tremor `Table` for the identical result set.
- Layer ③ generated SQL: collapsible `<details>`-style shadcn `Collapsible`, syntax-highlighted with Shiki, monospace, copy-to-clipboard button.
- Layer ② chart/table: reuse actual Tremor primitives (`BarChart`, `Table`, KPI `Card`) at a reduced/compact size — **not** a screenshot or a separate mini-chart library, so a pinned result renders identically wherever it lands.
- Layer ④ action row: three shadcn `Button`s (`ghost`/`outline` variant to stay visually secondary to the summary and chart above them).
- Streaming: Vercel AI SDK `useChat`, hitting a Next.js route handler that (a) sends the NL query + schema context to the LLM to produce SQL, (b) executes the SQL read-only against Postgres, (c) returns both the SQL and result rows for the client to render.

**Interaction rules:**
- Language: input accepts Burmese or English in the same field (no separate toggle needed for typing) — the toggle shown (`🇲🇲/EN`) only controls the *response* language, defaulting to match the input language.
- Layer ③ generated SQL is collapsed by default (progressive disclosure — most analysts want the answer, not the query) but always present, so a technical user can audit or copy it.
- Layer ② view switching only appears once the result set crosses a configurable row threshold (default >10 rows) — below that, the chart is the sole view, since a toggle control adds clutter for a result small enough to read at a glance either way. When shown, **Chart** is the default tab; the analyst's last-chosen view persists for the rest of the session, not just the one turn.
- Every inline chart in the card carries the same hover-tooltip behavior (exact review count, date, confidence score) as its full-size counterpart on the dashboard — this is a live Tremor component instance, not a stripped-down preview, so nothing about interactivity is lost by rendering it small.
- **Export CSV** exports the exact result set behind the rendered chart/table, not a re-query.
- **Pin to Dashboard** opens a lightweight placement picker (which panel row, or a new "Pinned Queries" panel) and, once placed, saves the chart as a literal new widget on the Overview grid using the same Tremor component instance — this is the same underlying mechanism as the saved-view feature in §4, just materialized as a dashboard widget instead of a bookmark.
- **View Raw Reviews** closes or minimizes the drawer and deep-links into the main dashboard, pre-filtered to exactly the underlying review rows behind the SQL result — not a re-query, same "exact result set" guarantee as Export CSV, and consistent with the "every chart is a filter" principle from §1.1 rather than opening a separate raw-data view.
- Every generated query is read-only (`SELECT`-only execution role at the DB layer) — this is a data-safety requirement, not just a UX one, and should be enforced server-side, not just implied by the UI.
- If the model can't map the question to the star schema confidently, show a clarifying-question turn instead of guessing (e.g., *"Did you mean delivery speed for Foodpanda orders, or the 'Fulfillment & Speed' review aspect?"*) rather than silently returning a wrong-but-plausible chart. A clarifying-question turn renders as plain text only — layers ②–④ don't apply until there's an actual result to structure.

---

### 5.3 Data Mining & Insights Tab

**Placement:** Secondary nav tab, **"Data Mining & Insights"**. Two sub-views selected via an in-page `Tabs` control (not separate routes, so filters/date-range stay in sync): **Association Rules** and **Entity Clusters**.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ DATA MINING & INSIGHTS        [ Association Rules ]  [ Entity Clusters ]     │
├──────────────────────────────────────────────────────────────────────────────┤
│  ASSOCIATION RULES (Apriori / FP-Growth)                                     │
│                                                                                │
│        [Fulfillment                                                          │
│         & Speed: Neg] ───82%───▶ [Staff & Service: Neg]                      │
│              │                          │                                    │
│            65%                        41%                                    │
│              ▼                          ▼                                    │
│        [Price & Value: Neg]      [Product Quality: Neg]                      │
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
- `haha_ratio > 30%` displays the local Sarcasm Risk badge for human interpretation; it never automatically reclassifies the post's sentiment.
- Burmese text fields should never be truncated with a naive character-count `substring()` — Unicode grapheme clusters in Myanmar script combine multiple codepoints per visual character, so truncation must be grapheme-aware (e.g., `Intl.Segmenter`) or the risk is literally splitting a character in half mid-render.

---

### 5.5 Competitor Share of Voice (SoV) & Benchmarking View

**Placement:** An **"Overview / Competitor Benchmark"** toggle (shadcn `Tabs`/`ToggleGroup`, same control pattern as the sub-view switcher in Section 5.3) in the header row above the KPI strip. The Benchmark view owns its brand, branch, competitor, and date controls so its scope is explicit and does not depend on the global filter bar.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [ Overview ]  [ Competitor Benchmark ● ]      Comparing: OMUK vs Lotteria    │
│                                                 vs Marrybrown       [Edit ▾]  │
├───────────────────────────────────────┬──────────────────────────────────────┤
│ SHARE OF VOICE (SoV)                   │ ASPECT SENTIMENT MATRIX (Head-to-Head)│
│                                         │                                      │
│        ╭───────╮   ● OMUK       42%   │             OMUK   Lotteria  Marrybrn│
│      ╱           ╲  ● Lotteria   38%   │ Product Qty  +62%    +48%     +55%   │
│     │   donut    │  ● Marrybrown 20%   │ Fulfillment  +12%    +34%     +28%   │
│      ╲           ╱                     │ Price/Value  +30%    +22%     +40%   │
│        ╰───────╯                       │ Digital Exp  +45%    +38%     +20%   │
│  Legend colored via §3.6 entity-series │ Cust Support +50%    +41%     +33%   │
│  tokens (entity-self / -compare-1/-2)  │ Variety       +8%    +15%      +5%   │
│                                         │ Cell shade = §3.6 sentiment-diverging│
│  [ Toggle: Donut ↔ Stacked Bar ]        │ ramp; % text always shown, never     │
│  (stacked bar = share by aspect)       │ color-only (§3.5)                    │
├───────────────────────────────────────┴──────────────────────────────────────┤
│ COMPETITIVE ADVANTAGE / VULNERABILITY CARDS                                   │
│ ┌──────────────────────────────────┐  ┌──────────────────────────────────┐   │
│ │ ✅ WINNING ASPECT                 │  │ ⚠ VULNERABILITY ALERT            │   │
│ │ OMUK leads Lotteria on            │  │ Lotteria outperforms OMUK on      │   │
│ │ Product & Service Quality  +14%   │  │ Fulfillment & Speed  −22%         │   │
│ │                                    │  │ on Foodpanda                      │   │
│ │ [ View Supporting Reviews ]       │  │ [ View Supporting Reviews ]       │   │
│ └──────────────────────────────────┘  └──────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Components (mapped to Section 2 stack):**
- SoV chart: Tremor `DonutChart` as default, with a toggle to Tremor `BarChart` (stacked, per-aspect share) — both colored with the §3.6 `entity-series` tokens, never sentiment colors, since SoV encodes *volume share*, not sentiment.
- Aspect Sentiment Matrix: a Tremor-compatible `Table`-based heatmap — the identical pattern already established for the Association Rule "Matrix" alternate view in Section 5.3 — with cell backgrounds interpolated along `sentiment-diverging` (§3.6) and the exact percentage always rendered as text inside the cell (color alone never carries the value, per §3.5).
- Advantage/Vulnerability cards: shadcn `Card` + `Badge`, using the base `Positive`/`Negative` tokens (§3.2) with ✅/⚠ icon pairing. Reusing sentiment tokens here — rather than minting yet another pair — is intentional: a "winning aspect" *is* a positive sentiment delta between two entities, not an unrelated system state, so it stays inside the rule that sentiment color = sentiment measurement.
- "Edit" competitor picker: reuses the existing Entity Switcher component (Section 1.1) in a popover, rather than a bespoke new multi-select.
- "View Supporting Reviews" drill-down reuses the review-list component and — where snippets are in Burmese or Burglish — the exact rendering rules from Section 5.4 (Noto Sans Myanmar for native Unicode, `[Burglish]` tag, grapheme-aware truncation).

**Interaction rules:**
- Respects the global date-range filter (§4's "reduce reorientation cost") — benchmarking always runs over whatever range the analyst currently has selected, same as the Data Mining tab in §5.3.
- Clicking a matrix cell drills into the underlying head-to-head review set for that aspect/entity pair — consistent with the "every chart is a filter" rule from §1.1.
- Compare Mode supports up to 3 entities (self + 2 competitors) on the donut/matrix before an explicit "+N more" overflow state kicks in — a 4th+ column starts to defeat the "compare at a glance" purpose of a head-to-head matrix.
- Advantage/Vulnerability cards surface only when `|net sentiment delta| ≥ 10 percentage points` (configurable, per §4's "don't hardcode thresholds" rule) — deltas inside that margin aren't flagged, to avoid noise from differences that aren't meaningfully outside normal variance.
- Card copy uses exactly two fixed labels — "Winning Aspect" and "Vulnerability Alert" — never a varied phrasing per card, per §4's consistent-verb-labeling rule.
- Reused from Section 5.3's clustering pattern: if any compared entity has fewer than 30 reviews in the selected range, that entity's matrix column shows an inline minimum-sample warning rather than a silently unreliable comparison.

---

### 5.6 Data Pipeline & ETL Lineage Health Monitor


**Placement:** Opens from the existing sticky topbar badge (`Sync: ● 12 min ago`, already specified in §1.1) as a full-width shadcn `Dialog` titled **"System & ETL Health."** This makes a previously static timestamp into a genuine, clickable health signal; the badge itself needs no visual change beyond a hover/clickable state.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ SYSTEM & ETL HEALTH                                                    [×]   │
├──────────────────────────────────────────────────────────────────────────────┤
│ [Scrapers: FB & Foodpanda]──►[MongoDB Data Lake]──►[XLM-R NLP Queue]──►[PG DWH]│
│      ● Active                  ● 12,480 docs          ● 842 queued   ● Synced │
│      98% success               cleaned_contents:       GPU batch:     2 min   │
│      Proxy: Healthy            8,210                   340/min         ago    │
│                                 cleaned_feedbacks:                             │
│                                 4,270                                          │
├──────────────────────────────────────────────────────────────────────────────┤
│ NODE DETAIL (selected: XLM-RoBERTa NLP Queue)                                 │
│  Status: ● Active            Unprocessed items: 842                          │
│  GPU batch throughput: 340 items/min          Est. drain time: ~2.5 min       │
│  Last error: none in past 24h                                                │
├──────────────────────────────────────────────────────────────────────────────┤
│ POSTGRES STAR SCHEMA — LOAD STATUS                                            │
│  fact_review_absa_results     last load 2 min ago      +1,204 rows           │
│  fact_social_posts            last load 4 min ago         +86 rows           │
├──────────────────────────────────────────────────────────────────────────────┤
│ [ 🔄 Force Refresh ]                            Auto-refresh: every 60s ●    │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Components (mapped to Section 2 stack):**
- Shell: shadcn `Dialog` (large/full-width variant) — chosen over a `Sheet` because this is a discrete "check and return" diagnostic task with no underlying filtered context to preserve, unlike the exploratory drawer in §5.1.
- Pipeline node flow: a plain flex-row layout of shadcn `Card`s joined by simple SVG/CSS connector arrows — not a chart-library graph, since these are fixed sequential pipeline stages, not a variable dataset.
- Per-node metrics: Tremor `Metric` + `Text` pairs, reusing the same internal typography scale already established for ratio displays in §5.4.
- Status pills: shadcn `Badge` using the §3.7 token reuse — `accent-primary` (Active), `badge-incomplete` (Idle), `alert-critical` (Error) — deliberately never `Positive` teal, per §3.5.
- Node Detail panel: appears on clicking a node. This is a **select**, not a **filter** — the one other explicit exception to §1.1's "every chart is a filter" rule, alongside the Data Mining tab's density exception already flagged in §5.3, so it doesn't read as an inconsistency.
- Postgres load-status table: TanStack Table, compact and non-virtualized for this low-row-count diagnostic view.
- Force Refresh: TanStack Query manual refetch, with the numbers updating via a skeleton-loader micro-state rather than a full-dialog spinner, per §4's daily-use-fatigue principle.

**Interaction rules:**
- The topbar sync badge itself adopts the §3.7 status tokens: `text-muted` gray by default, switching to `alert-critical` red once time-since-last-sync exceeds a configurable staleness threshold (e.g., >30 min) — turning the existing ambient timestamp into an actual health signal rather than a raw number nobody re-reads.
- Auto-refresh interval (default 60s) is configurable, not hardcoded, per §4's standing rule.
- Any node in Error/Degraded state shows a plain-language reason inline (e.g., *"Foodpanda scraper: 3 consecutive failures, proxy pool exhausted"*) rather than a bare red dot — directly reusing §4's plain-language error-state rule.
- This view is strictly read-only diagnostics. No control here should mutate pipeline state beyond triggering a status re-poll — restarting a scraper or re-queuing a failed NLP batch is out of scope for this UI and routes to the engineering team's existing ops tooling. Stated explicitly so this surface doesn't creep into becoming a pipeline control plane.
- Because this view is checked on-demand rather than being a daily-driver page, it's the second explicit, intentional exception to §4's "default to summary" rule — the density shown above is appropriate here for the same reason §5.3 flagged its own exception.
- The NLP Queue's unprocessed-item count spans both native Unicode Burmese and Burglish input, tagged by the same language-detection step referenced in §5.4 — noted here only because it explains why queue throughput can vary by batch, not because this view renders any Burmese text itself.

---

### 5.7 Scrape Management & Entity Configuration

**Placement:** Opens from a **"[⚙ Scrape Manager]"** button in the topbar, adjacent to the existing sync badge — or as a keyboard shortcut (`Cmd/Ctrl + Shift + S`). Renders as a full-width shadcn `Sheet` drawer (reusing the drawer shell from §5.1) so the analyst never leaves their current dashboard context. This replaces the current CLI-only workflow (`python -m burmese_absa`) with a guided, interactive UI that eliminates manual URL pasting and parameter typing.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ SCRAPE MANAGER                                                         [×]   │
├──────────────────────────────────────────────────────────────────────────────┤
│ [ Saved Entities ]  [ New Scrape ]  [ Scrape History ]                       │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│ ┌─ SAVED ENTITIES ──────────────────────────────────────────────────────┐    │
│ │                                                                        │    │
│ │  ┌─────────────────────────────────────────────────────────────────┐  │    │
│ │  │ 📘 OMUK (CW)                          Facebook Page             │  │    │
│ │  │ https://www.facebook.com/ReviewsOMUK                            │  │    │
│ │  │ Last scraped: 2h ago (12 posts)        Status: ● Healthy        │  │    │
│ │  │ [ Scrape Now ]  [ Edit ]  [ Schedule ▾ ]  [ Delete ]            │  │    │
│ │  └─────────────────────────────────────────────────────────────────┘  │    │
│ │  ┌─────────────────────────────────────────────────────────────────┐  │    │
│ │  │ 🛵 Pizza Company (South Oakkala)         Foodpanda Shop         │  │    │
│ │  │ foodpanda.com.mm/restaurant/jito/pizza-hut-ocean-...             │  │    │
│ │  │ Last scraped: 1d ago (38 reviews)        Status: ● Healthy      │  │    │
│ │  │ [ Scrape Now ]  [ Edit ]  [ Schedule ▾ ]  [ Delete ]            │  │    │
│ │  └─────────────────────────────────────────────────────────────────┘  │    │
│ │  ┌─────────────────────────────────────────────────────────────────┐  │    │
│ │  │ 📘 Lotteria Myanmar                     Facebook Page           │  │    │
│ │  │ https://www.facebook.com/LotteriaMyanmar                        │  │    │
│ │  │ Last scraped: 3d ago (10 posts)          Status: ⚠ Stale       │  │    │
│ │  │ [ Scrape Now ]  [ Edit ]  [ Schedule ▾ ]  [ Delete ]            │  │    │
│ │  └─────────────────────────────────────────────────────────────────┘  │    │
│ │                                                                        │    │
│ │  [+ Add Entity]                                                         │    │
│ └────────────────────────────────────────────────────────────────────────┘    │
│                                                                                │
│ ┌─ NEW SCRAPE (wizard, shown when "+ Add Entity" or "New Scrape" clicked) ┐  │
│ │                                                                        │    │
│ │  Step 1: Source                                                        │    │
│ │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │    │
│ │  │ 📘 Facebook  │  │ 🛵 Foodpanda │  │ 📝 Blog      │                 │    │
│ │  │   Page       │  │   Shop       │  │              │                 │    │
│ │  └──────────────┘  └──────────────┘  └──────────────┘                 │    │
│ │                                                                        │    │
│ │  Step 2: URL & Details  (shown after source selection)                 │    │
│ │  ┌──────────────────────────────────────────────────────────────────┐  │    │
│ │  │ Paste URL:  [ https://www.foodpanda.com.mm/restaurant/...    ]   │  │    │
│ │  │                                                                  │  │    │
│ │  │ Entity Name: [ Pizza Company (South Oakkala)          ]  (auto) │  │    │
│ │  │                                                                  │  │    │
│ │  │ ── Facebook only ──                                              │  │    │
│ │  │ Max Posts:   [ 10 ]  ▾  (5 / 10 / 20 / 50 / Custom)            │  │    │
│ │  │                                                                  │  │    │
│ │  │ ☐ Save this entity for future scrapes (recommended)             │  │    │
│ │  └──────────────────────────────────────────────────────────────────┘  │    │
│ │                                                                        │    │
│ │  Step 3: Run Options                                                   │    │
│ │  ┌──────────────────────────────────────────────────────────────────┐  │    │
│ │  │ ☑ Headless mode (faster, no browser window)                     │  │    │
│ │  │ ☐ Run full pipeline after scrape (Clean → ABSA → Postgres)      │  │    │
│ │  └──────────────────────────────────────────────────────────────────┘  │    │
│ │                                                                        │    │
│ │  [ Back ]                                              [ ▶ Start Scrape ]│    │
│ └────────────────────────────────────────────────────────────────────────┘    │
│                                                                                │
│ ┌─ SCRAPE HISTORY ──────────────────────────────────────────────────────┐    │
│ │  When           Entity              Source    Result       Duration     │    │
│ │  ─────────────  ──────────────────  ────────  ──────────  ─────────   │    │
│ │  14:32 today    OMUK (CW)           FB        12 posts     45s         │    │
│ │  14:32 today    OMUK (CW)           FB        46 comments  (included)  │    │
│ │  Yesterday      Pizza Company       FP        38 reviews   2m 12s      │    │
│ │  2 days ago     Lotteria Myanmar    FB        10 posts     38s         │    │
│ │  2 days ago     Lotteria Myanmar    FB        24 comments  (included)  │    │
│ │                                                                        │    │
│ │  Click any row → expand: posts found, reactions captured, errors,      │    │
│ │  MongoDB write stats, link to raw data                                 │    │
│ └────────────────────────────────────────────────────────────────────────┘    │
├──────────────────────────────────────────────────────────────────────────────┤
│ LIVE SCRAPE PROGRESS (shown during active scrape, replaces wizard)           │
│ ┌────────────────────────────────────────────────────────────────────────┐   │
│ │ Scraping: OMUK (CW) — Facebook                                         │   │
│ │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━░░░░░░░░░  12/20 posts scanned         │   │
│ │ Posts captured: 8  ·  Reactions extracted: 6/8  ·  Comments: 46       │   │
│ │ Status: Extracting reaction breakdown for post #12...                   │   │
│ │                                                                        │   │
│ │ [ Cancel Scrape ]                                                       │   │
│ └────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Components (mapped to Section 2 stack):**
- Shell: shadcn `Sheet` (same drawer pattern as §5.1) — preserves the underlying dashboard context.
- Saved Entities list: TanStack Table, compact rows with per-row action buttons (shadcn `Button` ghost variant). Status pill uses §3.7 tokens — `accent-primary` for healthy, `badge-incomplete` gray for stale (>24h since last scrape, configurable).
- New Scrape wizard: shadcn `Dialog` (stepped, ~600px wide) with source selection as large card buttons (not a dropdown — three options, always visible), URL input with live validation (detects Facebook vs Foodpanda and auto-selects source if user pastes before choosing), and entity name auto-derived via the same logic as the current CLI `derive_foodpanda_entity_name` / `_resolved_entity_name` — user can override before saving.
- Facebook max-posts control: shadcn `Select` with preset values (5/10/20/50) plus a "Custom" option that reveals a numeric input — eliminates the current CLI free-text step.
- Scrape History: TanStack Table with expandable rows (shadcn `Collapsible` per row) showing per-scrape diagnostics. Not virtualized — history is append-only and low-row-count in normal use.
- Live Progress: a real-time section that appears at the bottom of the drawer when a scrape is running. Progress bar via Tremor `ProgressBar` or a plain shadcn `Progress` component. Status text updates pushed via Server-Sent Events (SSE) or WebSocket from the FastAPI backend — same streaming approach established for the AI chat drawer in §5.1.
- Schedule popover: shadcn `Popover` with a simple cron-like picker (Daily / Every 6h / Weekly / Custom cron) — stored as a config value in Supabase, executed by a Supabase Edge Function or pg_cron job.

**Interaction rules:**
- **One-click scrape for saved entities:** the `[ Scrape Now ]` button on a saved entity card immediately starts a scrape with the entity's stored URL and last-used parameters — no wizard, no URL re-entry. This is the single highest-leverage improvement over the current CLI flow for entities you scrape repeatedly.
- **URL auto-detection:** when a URL is pasted in the New Scrape wizard, the source type (Facebook/Foodpanda/Blog) is auto-selected based on domain matching (`facebook.com` → Facebook, `foodpanda.*` → Foodpanda, anything else → Blog). The user can override, but the happy path requires zero clicks after paste.
- **Entity name auto-fill:** for Foodpanda, the entity name is derived the same way as the CLI (stripped Burmese "ဝေဖန်သုံးသပ်ချက်များ" prefix, §5.7 fix). For Facebook, it's extracted from the page URL slug or the user's previous entry. The name field is always editable before confirming.
- **Validation before launch:** the wizard validates the URL format and (for Facebook) checks that `cookies.json` is present and non-expired on the server before enabling the Start button — a pre-flight check that mirrors the existing CLI `_validate_facebook_cookies` step, surfacing the result in the UI (`✓ Cookies valid (127 found)` or `⚠ Cookies expired — re-export from browser`) instead of failing mid-scrape.
- **Pipeline chaining:** the optional "Run full pipeline after scrape" checkbox triggers the cleaning → ABSA → PostgreSQL export steps automatically after the scrape completes — replacing the current three-command sequence (`clean_feedbacks` → `run_absa_pipeline` → `export_to_postgres`). Default is off for safety; once the team trusts the automation, it can become a saved preference per entity.
- **Schedule persistence:** schedules are stored in a new `scrape_schedules` table in Supabase (entity_id, source, cron_expression, params_jsonb, active boolean, last_run, next_run). A Supabase Edge Function or pg_cron job polls due schedules and triggers scrapes via the backend API.
- **Scrape cancellation:** the live progress view includes a `[ Cancel Scrape ]` button that sends a cancellation signal to the backend. For Facebook (async Playwright), this closes the browser context; for Foodpanda (sync Playwright), it sets a cancellation flag checked between scroll iterations.
- **No concurrent scrapes for the same entity:** if a scrape is already running for an entity, the `[ Scrape Now ]` button is disabled with a tooltip showing elapsed time — prevents duplicate MongoDB writes and engagement_history bloat. Different entities can be scraped in parallel.
- **History links to data:** clicking a completed scrape row expands to show captured data, with a "View in Dashboard" link that deep-links to the Overview filtered to that entity and time range — consistent with the "every chart is a filter" rule from §1.1.

**Data model (new Supabase tables):**

```sql
-- Saved entities for quick re-scrape (extends dim_entities with scrape config)
CREATE TABLE scrape_entities (
    id SERIAL PRIMARY KEY,
    dim_entity_id INT REFERENCES dim_entities(entity_id),
    source VARCHAR(50) NOT NULL,           -- 'facebook', 'foodpanda', 'blog'
    source_url TEXT NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    max_posts INT DEFAULT 10,              -- Facebook only
    headless BOOLEAN DEFAULT TRUE,
    auto_pipeline BOOLEAN DEFAULT FALSE,   -- run clean → ABSA → PG after scrape
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_scraped_at TIMESTAMPTZ,
    last_scrape_status VARCHAR(20),        -- 'success', 'error', 'cancelled'
    last_scrape_error TEXT,
    UNIQUE (source_url)
);

-- Schedule configuration
CREATE TABLE scrape_schedules (
    id SERIAL PRIMARY KEY,
    entity_id INT REFERENCES scrape_entities(id),
    cron_expression TEXT NOT NULL,          -- '0 */6 * * *' = every 6h
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    next_run TIMESTAMPTZ
);

-- Audit log of every scrape run
CREATE TABLE scrape_runs (
    id SERIAL PRIMARY KEY,
    entity_id INT REFERENCES scrape_entities(id),
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status VARCHAR(20),                     -- 'running', 'success', 'error', 'cancelled'
    posts_scraped INT,
    feedbacks_scraped INT,
    contents_written INT,
    feedbacks_written INT,
    duration_seconds INT,
    error_message TEXT,
    triggered_by VARCHAR(20) DEFAULT 'manual' -- 'manual', 'schedule'
);
```

**Edge Functions integration (scheduled scraping architecture):**

The scheduled scraping workflow uses Supabase Edge Functions as the orchestration layer between `pg_cron` (the scheduler) and the FastAPI backend (the worker that runs Playwright). This separation is necessary because Edge Functions (Deno-based, lightweight) cannot run Playwright or PyTorch directly, but can coordinate API calls, database writes, and pipeline chaining.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SCHEDULED SCRAPE FLOW                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. pg_cron (Supabase built-in extension)                           │
│     Runs every minute, queries:                                     │
│     SELECT * FROM scrape_schedules                                  │
│     WHERE active = TRUE AND next_run <= NOW()                       │
│     ↓ finds due schedule, triggers                                │
│  2. Edge Function: trigger_scrape()                                 │
│     Reads entity config from scrape_entities table                  │
│     Writes initial row to scrape_runs (status = 'running')         │
│     Calls FastAPI backend: POST /api/scrape { entity_id, params }  │
│     ↓                                                           │
│  3. FastAPI Backend (Member 5)                                      │
│     Launches Playwright → scrapes Facebook/Foodpanda               │
│     Writes to MongoDB (contents + feedbacks)                        │
│     Returns: { status, posts_scraped, feedbacks_scraped, duration } │
│     ↓                                                           │
│  4. Edge Function (callback)                                        │
│     Updates scrape_runs with result                                 │
│     Updates scrape_entities.last_scraped_at                         │
│     If auto_pipeline = TRUE:                                       │
│       Calls FastAPI: POST /api/pipeline { entity_id }              │
│       ↓                                                         │
│     5. FastAPI Backend                                              │
│        Runs: clean_feedbacks → run_absa_pipeline → export_to_pg    │
│        Returns: { cleaned, absa_processed, exported }               │
│     ↓                                                           │
│  6. Edge Function (final)                                           │
│     Computes next_run timestamp from cron_expression                │
│     Updates scrape_schedules.next_run                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Edge Function responsibilities:**
- **Orchestration** — reads schedule config, calls FastAPI, logs results, chains steps
- **Audit logging** — writes to `scrape_runs` table, updates entity timestamps
- **Schedule management** — computes next run time from cron expression
- **Pipeline chaining** — conditionally triggers post-scrape pipeline based on entity config

**What Edge Functions do NOT do:**
- Run Playwright (too heavy — browser automation requires FastAPI server)
- Store secrets like `cookies.json` (those live on FastAPI server's filesystem)
- Run PyTorch models (ABSA pipeline runs via FastAPI)

**FastAPI backend responsibilities:**
- Runs Playwright scrapers (actual browser automation)
- Runs NLP pipeline (PyTorch ABSA models)
- Writes to MongoDB
- Exports to Supabase PostgreSQL
- Exposes `/api/scrape` and `/api/pipeline` endpoints for Edge Functions to call

**Data flow summary:**
- **Frontend** → Supabase (read queries via Supabase client, direct access to star schema)
- **Frontend** → FastAPI (actions: scrape, pipeline, chat with data)
- **Edge Functions** → FastAPI (scheduled orchestration)
- **FastAPI** → MongoDB (write scraped data)
- **FastAPI** → Supabase (write processed data to star schema, update run status)

**Implementation order:** Build FastAPI endpoints first (they work manually from the Scrape Manager UI), then add Edge Functions + pg_cron for scheduling on top. The Edge Functions layer is additive — manual scrapes from the UI bypass Edge Functions and call FastAPI directly.

---

## Suggested Next Steps

1. Lock the token system (colors, spacing scale, type scale) in a shared `tailwind.config` before any team member starts building panels — this is what prevents six people's work from visually drifting apart. This now explicitly includes the Section 3.4 system/agentic tokens, so nobody reaches for `Negative` coral when they mean `alert-critical`.
2. Build the escalation queue drawer + keyboard flow first — it's the highest-risk interaction pattern (React Table + focus management + optimistic updates) and best to de-risk early.
3. Stub the KPI/chart panels with mock data shaped like your real star-schema query output, so swapping in the live PostgreSQL-backed API routes later is a data-layer change only, not a UI rewrite.
4. **New:** Build the "Chat with Data" drawer before the Data Mining tab so its read-only SQL execution layer and streaming infrastructure are established early.
5. **New (v3):** Lock the Section 3.6 entity-series tokens (`entity-self`, `entity-compare-1`, `entity-compare-2`) before anyone builds the SoV chart or Aspect Sentiment Matrix — a benchmarking view where brand colors drift between analysts isn't just visually inconsistent, it's actively misleading about which entity is which.
6. **New (v3):** Build the Scrape Manager's entity-save and one-click scrape flow (Section 5.7) before the scheduling feature — the `scrape_entities` table and the saved-entity card pattern are prerequisites for scheduling, and the one-click scrape alone eliminates the current CLI friction for repeated scrapes. The `scrape_runs` audit table should be created alongside it from day one so history is available immediately.
