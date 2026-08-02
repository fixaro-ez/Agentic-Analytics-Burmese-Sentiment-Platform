<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# Frontend architecture notes

- **Design tokens (v3 spec §3)**: all sentiment/alert/entity/pipeline colors live as CSS variables in `src/app/globals.css` (`:root` data tokens + `.dark` surfaces), exposed as Tailwind utilities via `@theme inline` — e.g. `text-sentiment-positive`, `bg-alert-critical`, `border-entity-compare-1`. Never use generic `green-500`/`red-500`/`yellow-400` for sentiment; never reuse sentiment colors for non-sentiment states.
- **Dark mode**: `next-themes`, dark is the default theme (`defaultTheme="dark"`, system sync off). Toggle lives in the header. `<html>` has `suppressHydrationWarning`.
- **Burmese font**: Noto Sans Myanmar is loaded via `next/font/google` (`--font-noto-myanmar`). Elements with `lang="my"` get it automatically via a globals.css rule; use `containsMyanmar()` / `myanmarLangProps()` from `src/lib/myanmar.ts` to decide. Burglish/English must keep the default Geist UI font.
- **Global filter state**: Zustand store in `src/lib/stores/filters.ts` (`entityId`, `days`, `aspect`). `<FilterSync />` (must stay inside `<Suspense>`) mirrors it to URL params `?entity=&days=&aspect=`; `<FilterBar />` is the sticky bar under the header on Dashboard, Analytics, and Data Mining only. Entity comparison is local to the Aspect Health Radar, Analytics Benchmark, and Data Mining. Backend only honors `entity_id`/`days` on `/api/analytics/trends` so far — other endpoints ignore the filters until a backend pass.
- **Server state**: TanStack Query via `<QueryClientProvider>` in `providers.tsx`. All GET fetching goes through `useApi(path, { skip, initialData, refetchInterval })` in `src/hooks/use-api.ts` — keep its `{data, loading, error, refetch}` shape; pass `refetchInterval` for polling (return `false` to stop).
- **shadcn**: components are hand-maintained copies in `src/components/ui/` (new-york style). Only add a component when something actually uses it.
- **No test framework**: verification is `npm run lint` and `npm run build`.
