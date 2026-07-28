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

### Existing Frontend Pages (shell with TODOs)
| Page | Status |
|------|--------|
| `/login` | Functional (Supabase Auth working) |
| `/dashboard` | Shell (KPI cards + chart placeholders) |
| `/entities` | Shell (table placeholder) |
| `/analytics` | Shell (chart placeholders) |
| `/chat` | Shell (input + result placeholder) |
| `/alerts` | Shell (list + config placeholder) |
| `/mining` | Shell (cards placeholder) |

---

## Member A: Chat with Data (Backend + Frontend)

You own the entire "Chat with Data" feature — from LangChain agent to the chat UI.

### Your Files

| File | Action | Description |
|------|--------|-------------|
| `backend/app/services/chat.py` | **FILL** | Implement LangChain Text-to-SQL agent |
| `backend/app/routers/chat.py` | **FILL** | Wire real queries + history storage |
| `backend/app/models/chat.py` | **EXTEND** | Add `ChatHistoryItem` model |
| `frontend/src/app/(app)/chat/page.tsx` | **FILL** | Full chat interface |
| `frontend/src/lib/types.ts` | **EXTEND** | Add `ChatHistoryItem` type |

### Backend Tasks

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

### Frontend Tasks

**Fill Chat Page** (`frontend/src/app/(app)/chat/page.tsx`):

1. Wire the input + Send button to `api.post("/api/chat/query", { question })`
2. Display the response:
   - SQL query in `<pre><code>` with monospace font
   - Results in a simple HTML table
   - Explanation text
   - Error message (red) if present
3. Add a message history list (each message shows question + SQL + results)
4. Add example questions as clickable buttons:
   - "Which entity has the most negative reviews?"
   - "Show me sentiment trends for the last 7 days"
   - "What are the top 3 aspects with negative sentiment?"
5. Add a loading spinner while the query runs
6. Add a sidebar showing chat history (fetch `GET /api/chat/history`)

### Dependencies
```bash
pip install langchain langchain-openai langgraph langchain-community
```

---

## Member B: Alerts System (Backend + Frontend)

You own the entire Alerts feature — sentiment monitoring backend + alerts UI.

### Your Files

| File | Action | Description |
|------|--------|-------------|
| `backend/app/services/alerts.py` | **CREATE** | Alert detection + CRUD service |
| `backend/app/routers/alerts.py` | **FILL** | Replace stubs with real queries |
| `backend/app/models/chat.py` | **EXTEND** | Add `AlertSummary` model if needed |
| `frontend/src/app/(app)/alerts/page.tsx` | **FILL** | Alert list + config form |

### Backend Tasks

**1. Create SQL tables** (run in Supabase dashboard):
```sql
CREATE TABLE alerts (
    alert_id SERIAL PRIMARY KEY,
    entity_id INT REFERENCES dim_entities(entity_id),
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'medium',
    message TEXT NOT NULL,
    metadata JSONB,
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE alert_config (
    id SERIAL PRIMARY KEY DEFAULT 1,
    negative_threshold DECIMAL(5,4) DEFAULT 0.3,
    spike_window_hours INT DEFAULT 24,
    spike_zscore DECIMAL(5,2) DEFAULT 2.0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO alert_config (negative_threshold, spike_window_hours, spike_zscore)
VALUES (0.3, 24, 2.0);

ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert_config ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated can read alerts"
  ON alerts FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role can manage alerts"
  ON alerts FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Authenticated can read config"
  ON alert_config FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role can manage config"
  ON alert_config FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_alerts_created ON alerts(created_at DESC);
CREATE INDEX idx_alerts_ack ON alerts(acknowledged);
```

**2. Create Alert Service** (`backend/app/services/alerts.py`):

```python
async def get_alerts(pool, acknowledged: bool | None = None) -> list[dict]:
    # SELECT from alerts ORDER BY created_at DESC
    # Filter by acknowledged if provided

async def acknowledge_alert(pool, alert_id: int) -> bool:
    # UPDATE alerts SET acknowledged = TRUE WHERE alert_id = $1

async def get_config(pool) -> dict:
    # SELECT from alert_config WHERE id = 1

async def update_config(pool, config: AlertConfig) -> dict:
    # UPDATE alert_config SET ... WHERE id = 1

async def check_for_anomalies(pool) -> list[dict]:
    # 1. Read config thresholds
    # 2. Query v_sentiment_daily_trends for last N hours
    # 3. For each entity, calculate:
    #    - Current negative_ratio
    #    - Z-score = (current - mean) / stddev over the window
    # 4. If negative_ratio > threshold OR zscore > spike_zscore:
    #    - INSERT into alerts
    #    - Return newly created alerts
```

**3. Fill Alert Router** (`backend/app/routers/alerts.py`):

Replace the existing stubs:
- `GET /api/alerts` → query alerts with optional `?acknowledged=true|false` filter
- `POST /api/alerts/config` → update alert config
- `POST /api/alerts/check` → run anomaly detection, return new alerts
- Add `PATCH /api/alerts/{id}/acknowledge` → mark alert as acknowledged

### Frontend Tasks

**Fill Alerts Page** (`frontend/src/app/(app)/alerts/page.tsx`):

1. Fetch `GET /api/alerts` and display in a list
2. Each alert shows:
   - Severity as Badge: `critical` = red, `high` = orange, `medium` = yellow, `low` = blue
   - Entity name, alert type, message, timestamp
   - "Acknowledge" button (calls `PATCH /api/alerts/{id}/acknowledge`)
3. Filter toggle: All / Unacknowledged
4. Config section:
   - Sliders or number inputs for `negative_threshold`, `spike_window_hours`, `spike_zscore`
   - "Save Config" button (calls `POST /api/alerts/config`)

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

## You (Last): Data Scientist (Mining Algorithms)

Implement after all other features are stable. See original `docs/TASK_ASSIGNMENTS.md` Member 3 section.

---

## Dependency Graph

```
Member A (Chat) ←── needs OPENAI_API_KEY in backend/.env
    │
Member B (Alerts) ←── needs alerts + alert_config tables (you create them)
    │
Member C (Dashboard) ←── uses Table from Member E, charts are self-contained
    │
Member D (Analytics) ←── uses charts from Member C (shared components)
    │
Member E (Polish) ←── independent, can start immediately
    │                    Table/Skeleton components used by C and D
    │
You (Mining) ←── LAST, after everything else works
```

**Recommended parallel work:**
- Week 1: Members A, B, E work in parallel (no dependencies between them)
- Week 2: Members C, D start (E's Table/Skeleton ready by now)
- Week 3: Integration testing + You start Mining

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
