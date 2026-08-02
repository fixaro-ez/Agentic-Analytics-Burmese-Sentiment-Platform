# Marketing vs. Operations Impact — Presentation-Ready Overhaul

## Context

The current "Marketing vs. Operations Impact" feature is mathematically rigorous but unusable in presentations: raw campaign strength numbers reach 10 million, every card shows "Insufficient reviews", the chart is a "dark void", and academic terminology (pp deltas, fractional attribution) confuses stakeholders. The goal is to make this feature intuitive, visually clear, and demo-ready — without losing the analytical backbone.

---

## Phase 1 — Backend: Tier Classification + Thresholds

### 1a. Add tier helper
**File:** `backend/app/services/benchmark.py` (after line 150)

```python
def _campaign_strength_tier(strength: float) -> str:
    if strength < 1_000:
        return "low"
    if strength < 10_000:
        return "medium"
    if strength < 100_000:
        return "high"
    return "viral"
```

### 1b. Update constants (lines 27-34)
```python
IMPACT_MIN_CAMPAIGNS = 3              # was 5
IMPACT_MIN_OPERATION_REVIEWS = 3      # was 10
```

### 1c. Update response models
**File:** `backend/app/models/benchmark.py`

- `CampaignImpactPoint` (line 85): add `campaign_strength_tier: Literal["low", "medium", "high", "viral"] = "low"` after `campaign_strength`
- `OperationalDisconnect` (line 112): add `campaign_strength_tier: str = "low"`, `baseline_available: bool = True`; make `normal_campaign_strength: float | None = None` and `strength_ratio: float | None = None`

### 1d. Populate tier in `build_campaign_impact_response`
**File:** `backend/app/services/benchmark.py`, lines 564-588

Add `campaign_strength_tier=_campaign_strength_tier(campaign["strength"])` to the `CampaignImpactPoint(...)` construction.

---

## Phase 2 — Backend: Query Parameter + Relaxed Disconnects

### 2a. Accept `min_operation_reviews` parameter
- **`build_campaign_impact_response`** (line 444): add `min_operation_reviews: int = IMPACT_MIN_OPERATION_REVIEWS` kwarg; use it instead of the constant for `reliable` check (line 563)
- **`get_campaign_impact`** (line 663): add `min_operation_reviews: int = IMPACT_MIN_OPERATION_REVIEWS` kwarg; pass through
- **API endpoint** `backend/app/routers/analytics.py` (line 204): add `min_operation_reviews: int = Query(default=3, ge=1, le=50)`; pass to service

Echo the parameter in `CampaignImpactMeta.minimum_operation_reviews` (line 650) instead of the constant.

### 2b. Relax disconnect detection (remove baseline requirement)
**File:** `backend/app/services/benchmark.py`, lines 605-630

Replace current condition:
```python
baseline_available = normal_strength is not None
strong = (
    strength_ratio is not None and strength_ratio >= IMPACT_STRONG_CAMPAIGN_MULTIPLIER
) if baseline_available else True

if reliable and drops and strong:
    # ... build disconnect with appropriate message
```

When `baseline_available=False`, message becomes:
> "A campaign coincided with Foodpanda net sentiment falling X% across N post-campaign reviews (no historical baseline for comparison)."

---

## Phase 3 — Frontend: Types Update

**File:** `frontend/src/lib/types.ts` (lines 367-437)

Add to `CampaignImpactPoint`:
```typescript
campaign_strength_tier: "low" | "medium" | "high" | "viral"
```

Update `OperationalDisconnect`:
```typescript
campaign_strength_tier: "low" | "medium" | "high" | "viral"
baseline_available: boolean
normal_campaign_strength: number | null
strength_ratio: number | null
```

---

## Phase 4 — Frontend: Simplified Card Metrics

**File:** `frontend/src/components/analytics/impact-panel.tsx`

### 4a. Add tier badge helper (inline in file)
```typescript
const TIER_LABELS: Record<string, { label: string; className: string }> = {
  low:    { label: "Low Reach",    className: "bg-muted text-muted-foreground" },
  medium: { label: "Medium Reach", className: "bg-blue-500/20 text-blue-400" },
  high:   { label: "High Reach",   className: "bg-orange-500/20 text-orange-400" },
  viral:  { label: "Viral",        className: "bg-purple-500/20 text-purple-400" },
}
```

### 4b. Replace card metrics (lines 266-270)
Replace the 4 `<Metric>` items:

| Current | New |
|---------|-----|
| `Campaign strength: 10,074,027.2` | Tier badge: `[High Reach]` with color |
| `Raw post reviews: 0` | Keep as `Post reviews: {count}` |
| `Attributed reviews: 0.33` | `Reviews analyzed: {Math.round(count)}` |
| `Before → after: -11.1pp → -33.3pp` | `Before: 65% → After: 42% (▼ 23%)` |

Replace the `net()` helper (lines 369-372):
```typescript
function sentimentChange(before: number | null, after: number | null) {
  if (before == null || after == null) return "—"
  const b = Math.round(before * 100)
  const a = Math.round(after * 100)
  const diff = a - b
  if (diff === 0) return `${b}% (no change)`
  const arrow = diff < 0 ? "▼" : "▲"
  return `${b}% → ${a}% (${arrow} ${Math.abs(diff)}%)`
}
```

### 4c. Change "Insufficient reviews" badge
Replace with softer warning: `Low review count` instead of `Insufficient reviews` (line 255).

---

## Phase 5 — Frontend: Chart Redesign

**File:** `frontend/src/components/charts/campaign-impact-chart.tsx`

Replace the dual-axis ComposedChart with a simpler LineChart:

- **Single Y-axis:** Net sentiment -100% to +100%
- **Line:** Connect before → after sentiment points per campaign, sorted by time
- **Vertical ReferenceLines** at each campaign's `post_timestamp` with dashed style, labeled with the campaign's tier badge text
- **Remove:** Bar (campaign strength), dual Y-axis, ReferenceArea shaded boxes

Data transform stays in `benchmark-helpers.ts` but simplify to only emit before/after sentiment points (drop the `campaignStrength` field from chart data). The `campaignTimelineData` function becomes simpler — just before/after pairs.

Recharts imports needed: `LineChart`, `Line`, `XAxis`, `YAxis`, `CartesianGrid`, `ReferenceLine`, `Tooltip`, `ResponsiveContainer`. (`ReferenceLine` is available from `recharts`.)

---

## Phase 6 — Frontend: Demo Data Toggle

### 6a. Create demo fixture
**New file:** `frontend/src/lib/demo-impact.ts`

Hardcoded `CampaignImpactResponse` with 3 campaigns:
1. **Disconnect campaign:** high tier, sentiment drops from +0.42 to -0.18
2. **Successful campaign:** viral tier, sentiment rises from +0.38 to +0.61
3. **Neutral campaign:** low tier, sentiment stays stable +0.55 to +0.53

Meta: `correlation: -0.68`, `correlation_strength: "strong"`, `sufficient_for_correlation: true`, 1 disconnect present.

All sentiment values in decimal [-1, 1] range (matching actual API format).

### 6b. Add toggle to `impact-panel.tsx`
Add state: `const [demo, setDemo] = useState(false)`

Render a button group near the top of the panel:
```
[Live Data] [Demo Case Study]
```

When `demo=true`:
- Pass `skip: true` to `useCampaignImpact`
- Use `DEMO_IMPACT_RESPONSE` as the data source
- Hide brand/branch selectors (demo uses its own fixed data)

---

## Phase 7 — Frontend: Threshold Control

### 7a. Add state + UI
In `impact-panel.tsx`, add `const [minReviews, setMinReviews] = useState(3)`.

Use existing `Dialog` + `Select` components (no new shadcn components needed):
- A `Settings2` icon button (from `lucide-react`) opens a `Dialog`
- Dialog contains a `Select` with options: `[1, 2, 3, 5, 10]` for min operation reviews

### 7b. Pass to hook
**File:** `frontend/src/hooks/use-analytics.ts` (lines 191-203)

Update `useCampaignImpact` signature to accept `minOperationReviews?: number` in options, append as query param:
```typescript
params.set("min_operation_reviews", String(options.minOperationReviews ?? 3))
```

The gear control only affects live data mode (demo mode ignores it).

---

## Phase 8 — Update Tests

### 8a. Backend tests
**File:** `backend/tests/test_benchmark_impact.py`

- Add `test_campaign_strength_tier_boundaries` — test all 4 tier thresholds
- Add `test_disconnect_without_baseline` — campaign with no prior baseline still triggers disconnect with `baseline_available=False`
- Update `test_seven_day_before_after_and_disconnect` — verify new fields (`campaign_strength_tier`, `baseline_available`)
- Update threshold assertions: `minimum_operation_reviews` from 10 to 3, `minimum_campaign_for_correlation` from 5 to 3
- Add `test_min_operation_reviews_parameter` — pass `min_operation_reviews=5`, verify `reliable` flips correctly

### 8b. Frontend tests
**File:** `frontend/src/lib/benchmark-helpers.test.mts`

- Add `campaign_strength_tier: "high"` to mock campaign data (required field)
- Update assertions for simplified timeline data

---

## Files Changed Summary

| File | Action |
|------|--------|
| `backend/app/services/benchmark.py` | Modify: tier helper, constants, query param, disconnect logic |
| `backend/app/models/benchmark.py` | Modify: add tier + baseline_available fields |
| `backend/app/routers/analytics.py` | Modify: add query parameter |
| `backend/tests/test_benchmark_impact.py` | Modify: new + updated tests |
| `frontend/src/lib/types.ts` | Modify: add tier + baseline_available types |
| `frontend/src/components/analytics/impact-panel.tsx` | Modify: tier badges, simplified metrics, demo toggle, threshold control |
| `frontend/src/components/charts/campaign-impact-chart.tsx` | Rewrite: single-axis line chart with campaign flag pins |
| `frontend/src/lib/benchmark-helpers.ts` | Modify: simplify timeline data |
| `frontend/src/lib/benchmark-helpers.test.mts` | Modify: updated test fixtures |
| `frontend/src/hooks/use-analytics.ts` | Modify: add minOperationReviews param |
| `frontend/src/lib/demo-impact.ts` | **New file:** hardcoded demo dataset |

---

## Verification

1. **Backend tests:** `cd backend && python -m pytest tests/test_benchmark_impact.py -v`
2. **Frontend tests:** `cd frontend && node --test src/lib/benchmark-helpers.test.mts`
3. **Lint + build:** `cd frontend && npm run lint && npm run build`
4. **Manual verification:** Start both servers, open Analytics > Marketing vs. Operations Impact, toggle to "Demo Case Study" to see populated cards, tier badges, the redesigned chart with flag pins, and the correlation badge showing "r=-0.68"
