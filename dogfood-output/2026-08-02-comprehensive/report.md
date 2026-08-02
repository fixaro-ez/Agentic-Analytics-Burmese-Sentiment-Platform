# Comprehensive E2E and QA audit — 2026-08-02

## Scope

Audited the Next.js frontend, FastAPI backend, Supabase/PostgreSQL schema and permissions, Mongo-backed scraping pipeline, authentication boundaries, primary product flows, validation, error states, accessibility, responsiveness, dependency health, and data integrity.

Primary authenticated flows exercised in Chrome: Dashboard, Entities, entity detail and review focus, Analytics Overview, Analytics Benchmark, Scraping, Chat with Data, Feedback Patterns map/table, and Feedback Patterns deep-linking into an entity review. Unauthenticated login and reset-password screens were exercised at 390 × 844. Destructive production actions were validated through automated tests and request-model checks rather than creating or deleting real user records.

## Issues discovered and fixed

### Critical — anonymous database access

Anonymous Supabase clients had broad CRUD privileges on core analytics tables, three tables had no RLS, and analytics views ran with owner privileges. A direct anonymous REST request could read real analytics rows.

Fix:

- Enabled RLS on brand, brand-branch, and post-classification tables.
- Added authenticated read policies and removed anonymous table, view, and sequence privileges.
- Removed authenticated direct DML privileges from core analytics facts and dimensions.
- Recreated all analytics views with `security_invoker = true`.
- Applied and verified the hardening migration against the live Supabase database.

Evidence: anonymous REST access now returns 401; authenticated read access continues to work; anonymous SELECT/INSERT grants are false.

### High — missing fact-table integrity constraints

The database accepted invalid platforms, aspects, sentiments, confidence ranges, orphan-like null entity references, negative engagement counts, and invalid ratio values.

Fix:

- Added validated constraints for platform and ABSA enums, confidence 0–1, `no_aspect`/null-sentiment consistency, required entity IDs, non-negative engagement counts, and reaction ratios 0–1.
- Audited the existing live rows before applying constraints. No corrupt rows were found.

### High — review metrics counted aspect rows

The long-format ABSA table was counted with `COUNT(*)`, so reviews with multiple aspects appeared more than once. KFC (Sanpya), for example, showed 257 “reviews” for 215 distinct source reviews. Sentiment ratios also included unclassified `no_aspect` rows in their denominator.

Fix:

- Ranked each source review once using its strongest classified result for overview and trend metrics.
- Kept aspect charts aspect-level, where multiple rows per review are intentional.
- Calculated sentiment ratios only over classified reviews.
- Applied the corrected views to the live database and verified KFC (Sanpya) now shows 215 reviews, 30.5% positive, and 56.9% negative.

### High — vulnerable frontend dependencies

`npm audit` initially reported three high-severity findings through transitive `postcss` and `sharp` dependencies.

Fix:

- Pinned secure transitive versions with package overrides and refreshed the lockfile.
- Final `npm audit --audit-level=low`: zero vulnerabilities.

### Medium — invalid cookie upload could replace valid credentials

Facebook cookie uploads were written before semantic validation, so expired or wrong-domain cookies could overwrite a working file. Upload reads were also unbounded.

Fix:

- Added a 1 MiB upload limit with HTTP 413 handling.
- Validate required Facebook cookies, domains, fields, and expiration before writing.
- Use atomic replacement and clean temporary files on failure.
- Invalid uploads now return 422 and preserve the existing cookie file.

### Medium — password-reset flow was incomplete

The login page sent a reset email without an application callback, and no page existed to finish the password change.

Fix:

- Added a PKCE callback route, safe internal redirect handling, reset-password form, session validation, password confirmation, error states, and sign-out after success.
- Added route metadata and made the recovery routes available before authentication.
- Invalid/expired links show an explicit accessible error.

### Medium — malformed filters stayed in the URL/API

Unknown aspects and invalid entity IDs could remain in the browser URL; `days=9999` changed state but left a misleading, non-canonical URL. The backend accepted arbitrary aspect strings.

Fix:

- Added a six-aspect allowlist, positive entity validation, and 1–365 day clamping.
- Canonicalize malformed URLs after hydration (`days=9999&aspect=...&entity=-4` becomes `days=365`).
- Added backend literal validation; unknown aspect filters now return 422.

### Medium — scraping accepted insecure HTTP targets

Allowed-host validation still accepted `http://` URLs, which could expose authenticated Facebook cookies during navigation.

Fix:

- Backend request models and frontend source detection now require complete HTTPS URLs.

### Medium/low — accessibility and route context gaps

Entity table rows used button semantics on `<tr>`, causing visible rows to disappear from the accessibility tree. The app lacked a skip link and route-specific document titles. Login fields were missing form names, password length constraints, and live status semantics.

Fix:

- Replaced clickable table-row behavior with semantic entity links and 44 px targets.
- Added a keyboard-visible “Skip to main content” link and focusable main landmark.
- Added descriptive titles for every route.
- Added names, autocomplete/min-length behavior, and alert/status announcements to authentication forms.
- Login and reset-password axe audits report zero violations at mobile width.

### Low — missing response hardening

Frontend and backend responses lacked basic browser hardening headers and Next.js disclosed `X-Powered-By`.

Fix:

- Added `nosniff`, frame denial, strict referrer policy, and restrictive camera/microphone/geolocation policy to both services.
- Disabled the Next.js powered-by header.

### Low — test and environment hygiene

The default frontend test command omitted helper suites, and Compose emitted an obsolete-version warning.

Fix:

- `npm test` now discovers every `src/lib/*.test.mts` suite.
- Removed obsolete Compose `version` metadata.

## Tests added or strengthened

- Invalid aspect API validation.
- Distinct-review SQL ranking assertions for filtered and entity overview queries.
- Oversized cookie upload rejection.
- Invalid cookie upload preserves the previous file.
- Valid cookie upload atomically replaces the file.
- HTTP scrape URL rejection in frontend and backend.
- URL filter clamping, allowlisting, and invalid entity rejection.
- Email and reset-password validation.
- Backend security-header assertions.

## Final verification

| Check | Result |
|---|---:|
| Backend pytest | 81 passed + 12 subtests |
| Scraper unittest | 46 passed |
| Frontend node tests | 13 passed |
| Frontend ESLint | Passed |
| Next.js production build | Passed; 13 routes generated |
| npm audit, including dev dependencies | 0 vulnerabilities |
| Python `pip-audit` against backend requirements | 0 known vulnerabilities |
| Python `pip check` | No broken requirements |
| Docker Compose config validation | Passed |
| Login axe audit at 390 × 844 | 0 violations |
| Reset-password axe audit at 390 × 844 | 0 violations |
| Browser console during authenticated flow audit | No application errors |
| Invalid-token API sweep | 55 protected routes returned 401; health returned 200 |
| Live anonymous Supabase access | Blocked |

Screenshots:

- `screenshots/login-mobile-fixed.png`
- `screenshots/reset-password-mobile.png`

## Remaining risks and limitations

1. **No role-based authorization inside the authenticated tier.** Any signed-in user can currently invoke brand mutations, classification overrides/backfills, scraping, and ETL operations. This needs an explicit admin/analyst role model before the app is multi-user.
2. **No Content Security Policy.** Basic response headers are present, but a production CSP should be introduced with nonce support and tested against Next.js runtime scripts.
3. **Email delivery was not triggered.** The recovery callback, invalid-link state, and password validation were tested, but a real reset email and final password mutation were intentionally not performed.
4. **Destructive production flows were not executed.** Delete brand, classification changes, scrape launches/cancellation, and schedule mutations were covered by unit/API tests to avoid modifying live user data.
5. **Authenticated mobile coverage is partial.** The authenticated shell was exercised down to an 1121 px desktop window; login and reset screens were fully audited at 390 px. A dedicated Playwright project with seeded auth state should cover every authenticated route at 390, 768, and desktop widths.
6. **No load/soak test.** Query correctness and failure behavior were checked, but production-scale latency, concurrency, scheduler overlap, and connection-pool saturation remain unmeasured.
7. **One dependency warning remains non-failing.** Backend tests emit a Starlette TestClient deprecation warning recommending `httpx2`; it does not affect runtime behavior today.

## Changed implementation areas

- `migrations/20260802_security_and_integrity_hardening.sql`
- `migrations/20260802_review_level_sentiment_views.sql`
- `views.sql`
- Backend analytics, scraping upload validation, request validation, and response middleware.
- Frontend auth recovery, filter synchronization, semantic entity navigation, route metadata, security headers, and test discovery.

The repository had extensive pre-existing uncommitted work. All audit changes were made narrowly without resetting, deleting, staging, or committing unrelated changes.
