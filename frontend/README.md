# Burmese ABSA Analytics — Frontend

Next.js 16 (React 19) dashboard for the Agentic Analytics & Burmese Sentiment Platform. Dark-first theme with semantic design tokens, Supabase Auth, and real-time data visualization.

## Getting Started

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Login with Supabase credentials.

## Scripts

| Command | Description |
|---|---|
| `npm run dev` | Development server |
| `npm run build` | Production build |
| `npm run start` | Production server |
| `npm run lint` | ESLint |
| `npm run test:mining` | Mining visualization tests |
| `npm run test:analytics` | Analytics helper tests |
| `npm run test:scraping` | Scrape helper tests |

## Stack

- **Next.js 16** with App Router
- **React 19**
- **Tailwind CSS 4** with `@theme inline` design tokens
- **shadcn/ui** (new-york style) in `src/components/ui/`
- **Recharts** for all chart visualizations
- **Zustand** for global filter state (entity, days, aspect); comparison is controlled within the relevant analysis panel
- **TanStack Query** for server state with `useApi()` wrapper
- **next-themes** for dark/light mode (dark default)
- **Supabase Auth** (`@supabase/supabase-js` + `@supabase/ssr`)

## Architecture

See `AGENTS.md` in this directory for frontend-specific agent instructions.

- **Design tokens**: all sentiment/alert/entity/pipeline colors are CSS variables in `src/app/globals.css`, exposed as Tailwind utilities (`text-sentiment-positive`, `bg-alert-critical`, etc.)
- **Dark mode**: `next-themes`, dark default, toggle in header. `<html>` has `suppressHydrationWarning`
- **Burmese font**: Noto Sans Myanmar via `next/font/google`, auto-applied to `lang="my"` elements via `containsMyanmar()` / `myanmarLangProps()` from `src/lib/myanmar.ts`
- **Global filters**: Zustand store in `src/lib/stores/filters.ts`, synced to URL params via `<FilterSync />`
- **Server state**: TanStack Query, all fetching through `useApi()` in `src/hooks/use-api.ts`

## Pages

| Route | Description |
|---|---|
| `/dashboard` | KPI strip, sentiment trends, aspect radar, aspect breakdown, social engagement, top drivers |
| `/entities` | Entity list with platform filter, brand mapping settings |
| `/entities/[id]` | Entity detail (KPIs, aspect breakdown, recent reviews) |
| `/analytics` | Overview (trends, aspects, engagement) + Benchmark tab |
| `/chat` | Chat with Data (streaming AI, inline charts, pinning, export) |
| `/mining` | Association rules + entity clusters |
| `/scraping` | Scrape control center (wizard, active jobs, history) |
| `/login` | Supabase auth (sign in/up/forgot) |

## Component Structure

```
src/components/
├── analytics/    # Brand mapping and benchmark panels
├── charts/       # Recharts: sentiment trends, aspect bars, engagement, radar, donuts
├── chat/         # AI chat workspace (streaming, inline viz, pinning)
├── dashboard/    # KPI strip, aspect radar, top drivers, social engagement
├── etl/          # ETL health dialog
├── layout/       # Sidebar, header, filter bar, filter sync
├── mining/       # Association rules + entity clusters panels
├── scraping/     # Scrape manager drawer
├── ui/           # shadcn primitives (button, card, dialog, tabs, etc.)
├── providers.tsx # TanStack Query + next-themes + toast providers
├── data-error.tsx
└── error-boundary.tsx
```

## Verification

```bash
npm run lint
npm run build
```
