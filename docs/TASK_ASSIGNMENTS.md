# Team Task Assignments (5 Members)

Member 1 (Backend + Scheduling) is **DONE**. The remaining work is split among 5 members.
Each member owns their files end-to-end (backend + frontend where applicable).

## How to Run

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### API Testing
All endpoints require Supabase Auth. Login via `/login` page, the JWT is auto-attached
by the frontend API client. For manual testing (Postman/curl):
```
Authorization: Bearer <supabase-jwt-token>
```

### Existing API Endpoints (already implemented)
| Method | Endpoint | Status |
|--------|----------|--------|
| GET | `/api/health` | Done |
| GET | `/api/entities` | Done |
| GET | `/api/entities/{id}` | Done |
| POST | `/api/entities` | Done |
| GET | `/api/analytics/overview` | Done |
| GET | `/api/analytics/entities` | Done |
| GET | `/api/analytics/aspects` | Done |
| GET | `/api/analytics/trends` | Done |
| GET | `/api/analytics/engagement` | Done |
| POST | `/api/etl/run` | Done |
| POST | `/api/etl/clean` | Done |
| POST | `/api/etl/absa` | Done |
| POST | `/api/etl/export` | Done |
| GET | `/api/etl/status` | Done |
| GET | `/api/etl/history` | Done |

### Existing Frontend Pages
| Page | Status |
|------|--------|
| `/login` | Functional (Supabase Auth working) |
| `/dashboard` | Wired with real API (KPIs + charts from backend) |
| `/entities` | Shell (table placeholder) — Member C fills |
| `/analytics` | Shell (chart placeholders) — Member D fills |
| `/chat` | Shell (input + result placeholder) — Member B fills |
| `/alerts` | Shell (list + config placeholder) |
| `/scraping` | Wired with real API (source selector + polling + history) |
| `/mining` | Shell (cards placeholder) |

---

## Member A: Chat Backend (LangChain Text-to-SQL)

You own the Chat with Data backend — the LangChain agent that converts natural language to SQL and returns results.

**Note:** Member B owns the Chat frontend. You only implement the backend API.

### Your Files

| File | Action | Description |
|------|--------|-------------|
| `backend/app/services/chat.py` | **FILL** | Implement LangChain Text-to-SQL agent |
| `backend/app/routers/chat.py` | **FILL** | Wire real queries + history storage |
| `backend/app/models/chat.py` | **EXTEND** | Add `ChatHistoryItem` model |

### Tasks

**1. Implement Text-to-SQL** (`backend/app/services/chat.py`):

Replace the current stub with a real LangChain agent:

```python
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langgraph.prebuilt import create_react_agent

from ..config import settings

READONLY_DSN = settings.pg_dsn  # Use same DSN but add safety checks

_BLOCKED_KEYWORDS = [
    "DROP", "DELETE", "INSERT", "UPDATE", "TRUNCATE",
    "ALTER", "CREATE", "GRANT", "REVOKE",
]

async def query_data(question: str) -> ChatResponse:
    for kw in _BLOCKED_KEYWORDS:
        if kw in question.upper():
            return ChatResponse(
                question=question,
                error=f"Blocked: destructive keyword '{kw}' not allowed",
            )

    llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=settings.OPENAI_API_KEY)
    db = SQLDatabase.from_uri(READONLY_DSN)
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)

    system_prompt = (
        "You are a data analyst for a Burmese sentiment analytics platform. "
        "The database has these tables: dim_entities, fact_social_posts, "
        "fact_review_absa_results. Only write SELECT queries. "
        "The 6 ABSA aspects are: product_or_service_quality, fulfillment_and_speed, "
        "price_and_value, digital_experience, customer_support, variety_and_availability. "
        "Sentiment labels: Positive, Negative, Neutral."
    )

    agent = create_react_agent(llm, toolkit.get_tools(), prompt=system_prompt)
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    # Parse result, extract SQL and data
```

**Security requirements:**
- Block destructive keywords (DROP, DELETE, INSERT, UPDATE, TRUNCATE)
- Add 30-second query timeout
- Limit results to 100 rows
- Wrap in try/except for agent errors

**2. Add chat history** (`backend/app/routers/chat.py`):

Run this SQL migration in Supabase dashboard first:
```sql
CREATE TABLE chat_history (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    question TEXT NOT NULL,
    sql_query TEXT,
    result_count INT DEFAULT 0,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE chat_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own chat history"
  ON chat_history FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "Service role can insert chat history"
  ON chat_history FOR INSERT TO service_role
  WITH CHECK (true);
```

Then in the `chat_query` endpoint, after getting the response, insert into `chat_history`.
In `chat_history` endpoint, query `WHERE user_id = current_user_id ORDER BY created_at DESC LIMIT 50`.

**3. API contract for Member B:**

| Endpoint | Request | Response |
|----------|---------|----------|
| `POST /api/chat` | `{ "question": "..." }` | `{ "question", "sql", "results", "explanation", "error" }` |
| `GET /api/chat/history` | — | `[{ "chat_id", "question", "created_at" }]` |

### Dependencies
```bash
pip install langchain langchain-openai langgraph langchain-community
```

---

## Member B: Chat Frontend (UI)

You own the Chat with Data frontend — the conversational UI that talks to Member A's LangChain backend.

### Your Files

| File | Action | Description |
|------|--------|-------------|
| `frontend/src/app/(app)/chat/page.tsx` | **FILL** | Full chat interface |
| `frontend/src/lib/types.ts` | **EXTEND** | Add `ChatMessage`, `ChatHistoryItem` types |
| `frontend/src/components/chat/` | **CREATE** | Reusable chat components (message bubble, input, history sidebar) |

### Tasks

**1. Add TypeScript types** (`frontend/src/lib/types.ts`):

```typescript
export interface ChatMessage {
  role: "user" | "assistant"
  content: string
  sql?: string           // SQL query if the assistant generated one
  results?: Record<string, unknown>[]  // Query results
  timestamp: string
}

export interface ChatHistoryItem {
  chat_id: string
  question: string
  created_at: string
}
```

**2. Build Chat Page** (`frontend/src/app/(app)/chat/page.tsx`):

Layout: 3-panel design
- Left sidebar: Chat history list (previous questions)
- Center: Message thread (user bubbles right, assistant bubbles left)
- Bottom: Input bar with send button

Steps:
1. Fetch `GET /api/chat/history` on mount → show in left sidebar
2. On send: POST to `/api/chat` with `{ question: "..." }`
3. Show user message immediately, then stream/appear assistant response
4. If response includes `sql` and `results`, render a small data table inline
5. Handle errors gracefully (show error message in chat bubble)

**3. Create Chat Components** (optional, but recommended):

| Component | Purpose |
|-----------|---------|
| `ChatMessageBubble.tsx` | Single message — different styles for user vs assistant |
| `ChatInput.tsx` | Text input + send button, Enter to submit |
| `ChatHistorySidebar.tsx` | List of previous questions, click to reload |

### Backend Dependency

Member A implements the backend:
- `POST /api/chat` → returns `ChatResponse` with `question`, `sql`, `results`, `explanation`, `error`
- `GET /api/chat/history` → returns list of past questions

You build the UI assuming these contracts.

---

## Member C: Dashboard + Entities (Frontend)

You own the main dashboard overview and the entities management page.

### Your Files

| File | Action | Description |
|------|--------|-------------|
| `frontend/src/app/(app)/dashboard/page.tsx` | **FILL** | KPI cards + 2 charts |
| `frontend/src/app/(app)/entities/page.tsx` | **FILL** | Entity data table |
| `frontend/src/components/charts/sentiment-trend-chart.tsx` | **CREATE** | Recharts AreaChart |
| `frontend/src/components/charts/aspect-bar-chart.tsx` | **CREATE** | Recharts BarChart |
| `frontend/src/hooks/use-analytics.ts` | **CREATE** | Typed fetch hooks |

### Tasks

**1. Create Analytics Hooks** (`frontend/src/hooks/use-analytics.ts`):

```tsx
import { useApi } from "@/hooks/use-api"
import type { SentimentOverview, EntitySentimentOverview, AspectBreakdown, SentimentTrendPoint } from "@/lib/types"

export function useSentimentOverview() {
  return useApi<SentimentOverview>("/api/analytics/overview")
}

export function useEntityOverviews() {
  return useApi<EntitySentimentOverview[]>("/api/analytics/entities")
}

export function useAspectBreakdown() {
  return useApi<AspectBreakdown[]>("/api/analytics/aspects")
}

export function useSentimentTrends(entityId?: number, days: number = 30) {
  const params = new URLSearchParams()
  if (entityId) params.set("entity_id", String(entityId))
  params.set("days", String(days))
  return useApi<SentimentTrendPoint[]>(`/api/analytics/trends?${params}`)
}
```

**2. Create Chart Components**:

`sentiment-trend-chart.tsx`:
```tsx
"use client"
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts"
import type { SentimentTrendPoint } from "@/lib/types"

export function SentimentTrendChart({ data }: { data: SentimentTrendPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="date" />
        <YAxis domain={[0, 1]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
        <Tooltip formatter={(v: number) => `${(v * 100).toFixed(1)}%`} />
        <Legend />
        <Area type="monotone" dataKey="positive_ratio" stroke="#10b981" fill="#10b981" fillOpacity={0.2} name="Positive" />
        <Area type="monotone" dataKey="negative_ratio" stroke="#ef4444" fill="#ef4444" fillOpacity={0.2} name="Negative" />
      </AreaChart>
    </ResponsiveContainer>
  )
}
```

`aspect-bar-chart.tsx` — similar pattern but with `BarChart`, `Bar`, grouped by aspect.

**3. Fill Dashboard Page** (`frontend/src/app/(app)/dashboard/page.tsx`):

- KPI cards: Use `useSentimentOverview()` hook, display `total_reviews`, `positive_ratio` (as %), `negative_ratio` (as %)
- Sentiment Trend chart: Use `useSentimentTrends()` hook + `SentimentTrendChart` component
- Aspect Breakdown chart: Use `useAspectBreakdown()` hook + `AspectBarChart` component
- Entity Performance: Use `useEntityOverviews()` hook, display as simple table

**4. Fill Entities Page** (`frontend/src/app/(app)/entities/page.tsx`):

- Fetch `GET /api/entities` for entity list
- Fetch `GET /api/analytics/entities` for sentiment data per entity
- Display as table: entity_name, platform (Badge), total_reviews, positive_ratio, negative_ratio
- Add platform filter buttons: All / Facebook / Foodpanda
- Use the `Badge` component from `@/components/ui/badge`

---

## Member D: Analytics + Engagement (Frontend Charts)

You own the deep-dive analytics page with all chart types.

### Your Files

| File | Action | Description |
|------|--------|-------------|
| `frontend/src/app/(app)/analytics/page.tsx` | **FILL** | 4 chart types + filters |
| `frontend/src/components/charts/engagement-chart.tsx` | **CREATE** | Reactions BarChart |
| `frontend/src/components/charts/entity-radar.tsx` | **CREATE** | RadarChart |

### Tasks

**1. Create Engagement Chart** (`frontend/src/components/charts/engagement-chart.tsx`):

```tsx
"use client"
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts"
import type { FacebookEngagement } from "@/lib/types"

const REACTION_COLORS = {
  like: "#1877f2", love: "#e0245e", care: "#f7b928",
  haha: "#f5a623", wow: "#d4a017", sad: "#497fb5", angry: "#e97109",
}

export function EngagementChart({ data }: { data: FacebookEngagement[] }) {
  // Transform data for stacked bar chart
  // Each bar = one entity, stacked by reaction type
}
```

**2. Create Entity Radar** (`frontend/src/components/charts/entity-radar.tsx`):

```tsx
"use client"
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Legend } from "recharts"
import { ASPECT_LABELS } from "@/lib/types"

export function EntityRadar({ entities }: { entities: EntitySentimentOverview[] }) {
  // Compare entities on sentiment metrics using radar chart
  // Each axis = one metric (positive_ratio, negative_ratio, etc.)
}
```

**3. Fill Analytics Page** (`frontend/src/app/(app)/analytics/page.tsx`):

This page has 4 sections:

**Section 1: Sentiment Over Time**
- Recharts `AreaChart` with positive/neutral/negative areas
- Time range picker: 7 days / 30 days / 90 days (buttons)
- Entity filter dropdown (All entities + each entity by name)
- Fetch `GET /api/analytics/trends?days=30&entity_id=1`

**Section 2: Aspect Sentiment**
- Recharts `BarChart` grouped by aspect, stacked by sentiment (Positive/Neutral/Negative)
- Use `ASPECT_LABELS` from `lib/types.ts` for readable axis labels
- Color: Positive=green, Neutral=gray, Negative=red
- Fetch `GET /api/analytics/aspects`

**Section 3: Facebook Engagement**
- Stacked `BarChart` of reactions (like, love, care, haha, wow, sad, angry)
- One bar per entity
- Fetch `GET /api/analytics/engagement`

**Section 4: Entity Comparison**
- `RadarChart` comparing entities on 6 ABSA aspects
- Entity selector (checkboxes to pick which entities to compare)
- Fetch `GET /api/analytics/entities`

---

## Member E: Polish + Shared Components (Frontend)

You own cross-cutting UI improvements that make the whole app feel polished.

### Your Files

| File | Action | Description |
|------|--------|-------------|
| `frontend/src/app/login/page.tsx` | **POLISH** | Forgot password + validation |
| `frontend/src/components/layout/sidebar.tsx` | **POLISH** | Responsive mobile collapse |
| `frontend/src/components/ui/skeleton.tsx` | **CREATE** | Loading skeleton |
| `frontend/src/components/ui/table.tsx` | **CREATE** | shadcn Table component |
| `frontend/src/components/ui/toast.tsx` | **CREATE** | Toast notifications |
| `frontend/src/lib/api.ts` | **EXTEND** | Better error formatting |

### Tasks

**1. Polish Login Page** (`frontend/src/app/login/page.tsx`):
- Add "Forgot password?" link that calls `supabase.auth.resetPasswordForEmail({ email })`
- Add email format validation (show error if invalid)
- Add minimum password length validation (6 chars)
- Add a subtle branding element (app name + icon)
- Already functional — just improve UX

**2. Create Skeleton Component** (`frontend/src/components/ui/skeleton.tsx`):

```tsx
import { cn } from "@/lib/utils"

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-primary/10", className)}
      {...props}
    />
  )
}

export { Skeleton }
```

Then add skeleton loading states to Dashboard and Analytics pages — while `loading` is true,
show skeleton blocks instead of chart placeholders.

**3. Create Table Component** (`frontend/src/components/ui/table.tsx`):

```tsx
import * as React from "react"
import { cn } from "@/lib/utils"

const Table = React.forwardRef<HTMLTableElement, React.HTMLAttributes<HTMLTableElement>>(
  ({ className, ...props }, ref) => (
    <div className="relative w-full overflow-auto">
      <table ref={ref} className={cn("w-full caption-bottom text-sm", className)} {...props} />
    </div>
  )
)
// + TableHeader, TableBody, TableRow, TableHead, TableCell
// Follow shadcn/ui table pattern
```

This component is used by Members C and D for their data tables.

**4. Create Toast Component** (`frontend/src/components/ui/toast.tsx`):

Simple toast system:
- `useToast()` hook that returns `{ toast, toasts }`
- `toast({ title, description, variant })` where variant = "default" | "destructive" | "success"
- Auto-dismiss after 5 seconds
- Renders at bottom-right of screen

**5. Responsive Sidebar** (`frontend/src/components/layout/sidebar.tsx`):
- On mobile (< 768px), sidebar collapses to a hamburger menu
- Use a Sheet/overlay pattern (slide in from left)
- Add a `Menu` icon button in the Header for mobile toggle

**6. Extend API Client** (`frontend/src/lib/api.ts`):
- Better error formatting: parse FastAPI error responses, show user-friendly messages
- Add a global error handler that shows toasts on API failures

---



---

## Dependency Graph

```
Member A (Chat Backend) ←── needs OPENAI_API_KEY in backend/.env
    │
Member B (Chat Frontend) ←── needs Member A's Chat backend (POST /api/chat, GET /api/chat/history)
    │
Member C (Dashboard + Entities) ←── uses Table/Skeleton from Member E
    │
Member D (Analytics Charts) ←── uses shared chart patterns from Member C
    │
Member E (Polish + Shared Components) ←── independent, can start immediately
    │                                          Table/Skeleton used by C and D
    │
You (Data Mining) ←── LAST, after all features stable
```

**Parallel work recommendation:**
- **Wave 1 (start together):** Member A (Chat Backend), Member E (Polish/Shared) — independent
- **Wave 2 (after A done):** Member B (Chat Frontend) — needs A's backend
- **Wave 3 (after E done):** Member C (Dashboard/Entities), Member D (Analytics) — need E's Table/Skeleton
- **Last:** You (Data Mining) — after everything else works

## Architecture Reference

### Data Flow
```
Facebook/Foodpanda → Playwright → MongoDB → clean → ABSA → export → PostgreSQL → FastAPI → Next.js
```

### PostgreSQL Views Available
| View | Columns |
|------|---------|
| `v_entity_sentiment_overview` | entity_id, entity_name, platform, total_reviews, positive/negative/neutral counts + ratios |
| `v_aspect_breakdown` | aspect_category, sentiment_label, count, avg_confidence |
| `v_entity_aspect_summary` | entity_id, entity_name, platform, aspect_category, sentiment_label, count |
| `v_sentiment_daily_trends` | feedback_date, entity_id, entity_name, platform, daily counts + ratios |
| `v_facebook_engagement` | entity_id, entity_name, total_posts, total_reactions/shares/comments, avg ratios |

### ABSA Aspects
| Key | Display Name |
|-----|-------------|
| `product_or_service_quality` | Product/Service Quality |
| `fulfillment_and_speed` | Fulfillment & Speed |
| `price_and_value` | Price & Value |
| `digital_experience` | Digital Experience |
| `customer_support` | Customer Support |
| `variety_and_availability` | Variety & Availability |

### Supabase Project
- URL: `https://syatpftefackiarujypv.supabase.co`
- Region: ap-northeast-2
- pg_cron: installed, daily ETL + hourly alerts scheduled
- Edge Functions: `trigger-etl`, `check-alerts` deployed
