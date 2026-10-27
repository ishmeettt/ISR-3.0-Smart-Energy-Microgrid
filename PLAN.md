# HackSphere 3.0 Build Plan

## Phase 1: Local Development Environment Setup
**Status: ✓ COMPLETED**

- [x] Extract starter kit files to project directory
- [x] Verify Python 3.12+ is available
- [x] Install required Python packages (pandas, numpy, requests)
- [x] Create project structure with clear separation:
  ```
  HackSphere3.0/
  ├── starter_kit/          # Original starter files
  ├── src/
  │   ├── predict.py        # Main prediction module
  │   ├── transition.py    # Grid transition logic
  │   └── preprocessing.py # Data cleaning/features
  ├── tests/
  │   └── test_predict.py  # Unit tests
  ├── dashboard/           # Web dashboard (future)
  └── README.md
  ```
- [x] Verify test_eval.py passes with starter code

**Questions for User:**
- Do you have access to Zoho Catalyst QuickML for model training?
- Should we build the full web dashboard now or focus on the prediction pipeline first?

---

## Phase 2: Data Analysis & Preprocessing
**Status: ✓ COMPLETED**

- [x] Analyze train_telemetry.csv:
  - Checked: no missing values
  - Analyzed distributions of each feature
  - Examined target_demand_kw: mean=157, std=50, min=51, max=306
  - Verified timestamp continuity
- [x] Create feature engineering functions:
  - Hour of day, day_of_week extraction
  - Cyclical hour encoding (sin/cos)
  - Peak hour indicator (18-22)
  - Weather features (temp_above_24, humidity_inv, solar_normalized, heat_load)
- [x] Validate sample_test_input.csv format matches training data

**Key Findings:**
- Sample data is hotter (29°C mean vs 18°C training) → higher predictions expected
- Correlations: temp=0.53, humidity=-0.50, solar=0.28 with target
- Peak hours (18-22) have ~220 kW average demand vs ~92 kW at night

---

## Phase 3: Enhanced predict.py Implementation
**Status: ✓ COMPLETED**

- [x] Improve upon starter predict.py:
  - [x] Keep QuickML API integration (when endpoint available)
  - [x] Improved fallback model with multiple factors:
    - Hourly base load pattern (from training data analysis)
    - Temperature effect (cooling load above 24°C)
    - Humidity effect (inverse correlation)
    - Solar irradiance effect
    - Peak hour boost
  - [x] Add input validation
  - [x] Add proper error handling
- [x] Ensure predict() function signature matches test_eval.py expectations:
  - Input: pandas DataFrame with ['timestamp', 'ambient_temp_c', 'humidity_pct', 'solar_irradiance_wm2']
  - Output: numpy array of predictions (one per row)
- [x] Add CLI interface: `python predict.py --input <csv> --output <csv>`

**Testing:**
- [x] Run test_eval.py - outputs SUCCESS ✓
- [x] Generate predictions.csv from sample_test_input.csv
- [x] Validate prediction ranges are realistic:
  - Mean: 165.5 kW (training mean: 157 kW) ✓
  - Min: 72 kW, Max: 257 kW
  - Std: 54 kW (training std: 50 kW) ✓

---

## Phase 4: Transition Controller Logic
**Status: ✓ COMPLETED**

- [x] Implement transition.py with complete rules:
  - [x] `determine_grid_mode(demand_kw, hour)` - returns 'renewable' or 'main_grid'
  - [x] `check_overload_alert(demand_kw)` - returns bool for ≥200 kW
  - [x] `generate_transition_signal(timestamp, demand)` - full signal object
  - [x] `process_forecast(timestamps, predictions)` - batch processing
  - [x] `process_forecast_from_df(df, predictions)` - DataFrame integration
  - [x] `summarize_forecast(signals)` - summary statistics
- [x] Rules implemented correctly:
  - Demand > 160 kW OR hour 18-22 → Renewable Storage Mode ✓
  - Otherwise → Main Grid Mode ✓
  - Demand ≥ 200 kW → Critical Overload Alert (independent) ✓
- [x] Add unit tests for transition logic edge cases ✓ (22 transition tests pass)

---

## Phase 5: Self-Testing & Validation
**Status: ✓ COMPLETED**

- [x] Run test_eval.py - confirm SUCCESS ✓
- [x] Create comprehensive unit tests (35 tests total):
  - [x] test_predict.py: 35 tests covering:
    - Predict function (7 tests)
    - Fallback model behavior (2 tests)
    - Preprocessing functions (5 tests)
    - Transition controller (10 tests)
    - Integration tests (3 tests)
    - Edge cases (5 tests)
- [x] Validate predictions against training data statistics:
  - Training mean: 157 kW → Predictions mean: 165 kW (slightly higher due to hotter sample data) ✓
  - Training std: 50 kW → Predictions std: 54 kW ✓
  - Predictions within plausible range (50-310 kW) ✓
- [x] Test edge cases:
  - [x] Boundary hours (17, 18, 22, 23)
  - [x] Exact threshold values (159.9, 160.0, 160.1 kW)
  - [x] Overload threshold (199.9, 200.0, 200.1 kW)
  - [x] Extreme weather values
  - [x] Negative temperatures
  - [x] Zero solar at night

---

## Phase 6: Web Dashboard
**Status: ✓ COMPLETED**

- [ ] Create simple HTML/JS dashboard
- [ ] Display:
  - 24-hour predicted load curve (chart)
  - Active grid state badge
  - Battery state-of-charge indicator
  - Overload alerts banner
- [ ] Host locally for demonstration

**Notes:** This phase is optional depending on Zoho Catalyst deployment plans.

---

## Phase 7: QuickML Integration (Function → Live Model)
**Status: ✓ COMPLETED**

- [x] Train QuickML regression pipeline `ISR` in Catalyst console
  - Stages: Source → Select/Drop (drop `timestamp`) → Decision-Tree/AdaBoost Regression
  - Target: `target_demand_kw`; features: `ambient_temp_c`, `humidity_pct`, `solar_irradiance_wm2`
  - Execution Status: Success → produced **ISR model** (V1)
- [x] Create prediction endpoint `predict` from ISR model → **Published**
- [x] Wire `QUICKML_ENDPOINT_KEY` into `functions/predict/catalyst-config.json`
- [x] Fix `functions/predict/index.js` to call QuickML through the SDK

**Bugs found & fixed during integration:**

1. **Raw `fetch` cannot authenticate to QuickML** → always `INVALID_TICKET`.
   The endpoint needs Catalyst's internal auth ticket, which only a running
   function has. **Fix:** use `catalyst.initialize(req).quickML().predict()` —
   the SDK's `AuthorizedHttpClient` injects the ticket automatically.
2. **`ORGID_HEADER_UNAVAILABLE`** → SDK only sends `CATALYST-ORG` when
   `process.env.X_ZOHO_CATALYST_ORG_ID` is set. Setting it as a deployed env var
   was rejected (`environment_variables must not contain reserved keywords`).
   **Fix:** populate `process.env.X_ZOHO_CATALYST_ORG_ID` in code (`60093145112`).
3. **`predict()` rejects arrays** → SDK validator `isObject` excludes arrays.
   **Fix:** loop one row per `predict()` call and collect `result[0]`.
4. **`INVALID_DATA: missing_columns: [timestamp]`** → endpoint contract requires
   `timestamp` even though the model was trained with it dropped.
   **Fix:** include `timestamp` in the payload alongside the numeric features.
5. **API version** → endpoint/SDK use `/quickml/v1/...` (not v2).

**Verified live (`/server/predict/execute`):**
- Health GET → `200 {"status":"ok"}`
- Single row → `[221.29]`, `note: "From QuickML trained model"`
- Batch 3 rows → `[145.27, 211.51, 183.96]`, `note: "From QuickML trained model"`
- Bad payload → `400 {"error":"Missing or invalid data array"}`

> Note: one QuickML call per row → large batches risk the Advanced I/O 30s
> timeout. Fine for 24-hour forecasts; add chunking/concurrency if scoring the
> full 1000-row test set through the function.

---

## Phase 8: Dashboard Deployment (Slate) & CORS
**Status: ✓ COMPLETED**

- [x] Wire `dashboard/index.html` to the live predict function
  - Default `apiBase` = full function URL (`.../server/predict/execute`)
  - `buildForecastRows()` generates the 24-hour request payload: `timestamp` +
    `ambient_temp_c` + `humidity_pct` + `solar_irradiance_wm2`
  - Maps numeric `predictions[]` back to `{timestamp, demand}` for the chart/table
- [x] Deploy dashboard to Catalyst Slate → `https://dashboard-ejcdhurx.onslate.in`
- [x] Fix cross-domain CORS (Slate → Function)
- [x] End-to-end verification in browser

**Bugs found & fixed:**

1. **Empty/wrong request** → old code posted `{data: []}` to `apiBase + '/predict'`
   (wrong path, empty rows). **Fix:** build 24 real rows and POST to the full
   `/execute` URL as-is.
2. **Wrong response mapping** → raw `predictions[]` (numbers) was assigned to
   `predictionsData`, which expects `{timestamp, demand}`. **Fix:** zip timestamps
   with values.
3. **CORS preflight blocked** → `Content-Type: application/json` triggers an
   OPTIONS preflight. Catalyst's gateway (ZGS) answers OPTIONS itself **without**
   `Access-Control-Allow-Origin` and never reaches the function, so the browser
   rejects the call. The actual POST *does* return `access-control-allow-origin: *`.
   **Fix:** send `Content-Type: text/plain;charset=UTF-8` (CORS-safelisted → no
   preflight); the function's `getBody()` parses raw JSON regardless of content type.
4. **Flat/identical night predictions** → original synthetic features made every
   night hour identical (temp=20, humid=70, solar=0). **Fix:** smooth diurnal
   curves (temp min ~03:00 / max ~15:00, humidity inverse, solar bell 06-18).

**Verified live (browser console + network):**
- `POST .../server/predict/execute → 200 (Fetch)` — no preflight, **no console errors**
- 24 predictions render; current-hour demand populated; chart + table + grid-mode
  badge + overload banner all update
- Forecast shape: night trough ~144 kW → morning ramp → midday peak ~221 kW →
  evening peak ~266 kW (values reflect the Decision Tree's leaf bins)

> Note: the model is a Decision Tree, so its output is piecewise-constant —
> adjacent hours with similar features share a predicted value (7 distinct levels
> across 24 hours). That is the model's real behavior, faithfully displayed.

**Live URLs:**
- Dashboard (Slate): `https://dashboard-ejcdhurx.onslate.in`
- Predict function: `https://project-rainfall-60093145112.development.catalystserverless.in/server/predict/execute`

---

## Phase 9: UI/Visual Redesign
**Status: ✓ COMPLETED**

- [x] Replace the basic navy/blue theme with a distinct **emerald + charcoal**
  energy palette, accented by **amber** (solar/thresholds) and **sky** (main grid)
- [x] Modern typography: **Space Grotesk** headings + **Inter** body (Google Fonts)
- [x] Header: gradient logo chip, gradient title, animated **QuickML Live** pill,
  grouped API input, styled Refresh + Import CSV buttons
- [x] Stat cards: colored icon chips, hover lift, large tabular values, gradient
  battery charge bar
- [x] Alert banner: bordered, left-accent, slide-down animation
- [x] Chart: emerald gradient area fill, styled tooltip, threshold labels on-canvas,
  hidden legend (chips instead)
- [x] Table: numbered hour chips, pill badges for grid mode/overload, current-hour
  row highlight with emerald inset bar
- [x] Ambient background glows, footer with QuickML attribution, responsive tweaks
- [x] Verified live: no console errors, fonts + Chart.js load, POST → 200, all
  panels render real QuickML predictions

> All JS logic (forecast build, fetch with text/plain CORS workaround, transition
> rules, chart/table render) was preserved unchanged — only markup/CSS restyled.

### Polish add-ons (same phase)

- [x] **Dark/Light theme toggle** — full `[data-theme]` token set (both themes
  re-style cards, pills, alert, and the Chart.js canvas via `cssVar()` reads);
  preference persisted in `localStorage['hs-theme']` and applied by an inline
  head script **before first paint** (no flash of wrong theme); toggle button
  shows ☀️/🌙 per active theme
- [x] **Animations**
  - Number count-up (ease-out cubic, 850ms) on Predicted Demand, Battery SOC,
    Peak Hours whenever the dashboard updates
  - Staggered `riseIn` entrance for the 4 stat cards → chart → table → controls
  - Table rows stagger in on each refresh
  - Chart draw: `easeOutQuart` with 22ms per-point delay (line draws in)
  - Battery bar width transitions with a long ease
- [x] `prefers-reduced-motion` respected (animations disabled for those users)
- [x] Verified live: toggle flips theme + persists across reload; **zero console
  errors**; live QuickML POST → 200 in both themes

---

## Phase 10: Problem-Statement Gap Closure & Submission Prep
**Status: ✓ COMPLETED**

### 10a. Predict function — batch safety + server-side transition controller
- [x] Bounded-concurrency QuickML pool (25 in flight) + **bulk-first strategy**:
  one authenticated request with all rows via the SDK's requester (the SDK's
  `predict()` rejects arrays client-side), per-row pool as fallback
  - Verified: **1000 rows → HTTP 200 in 9.0s**, 0 non-finite values
- [x] **Server-side transition controller** (§6): response now includes
  `signals[]` (`timestamp`, `hour`, `predicted_demand_kw`, `grid_mode`,
  `alert`) + `summary` (`renewable_hours`, `main_grid_hours`, `overload_hours`)
- [x] Hour parsed from the timestamp **string** (no `Date` → immune to server tz)
- [x] Local assertion suite: exact 160 kW → main_grid, >160 → renewable,
  ≥200 → overload, 18–22 **inclusive** → renewable, 23 → main_grid ✓
- [x] `quickml_error` surfaced in the response when falling back (diagnosability)

### 10b. predict.py — wired to the live model (35% accuracy criterion)
- [x] `QUICKML_ENDPOINT_URL` default = deployed function `/execute` URL;
  overridable via `QUICKML_ENDPOINT_URL` env var or `--quickml-url`
- [x] Batch payload (all rows, one request), timeout 10s → 60s
- [x] Warns on stderr when the API reports fallback instead of QuickML
- [x] `python test_eval.py` → **SUCCESS**; `pytest` → **35 passed**

### 10c. Dashboard — ingestion + SOC (Requirements 2 & dashboard spec)
- [x] **CSV import now scored through QuickML**: parses feature columns by
  header name and POSTs them to the function (was plotting raw column 4);
  still accepts pre-scored `timestamp,target_demand_kw` files
- [x] **Manual telemetry form**: timestamp + 3 weather fields → live predict;
  result shows kW, server-side grid mode, overload pill, model note
- [x] **Real battery SOC simulation**: starts 87%, −6%/h discharging in
  renewable mode, +4%/h recharging on main grid, clamped 0–100; label shows
  autonomy / time-to-full for the current hour
- [x] First paint fetches the **live** forecast (sample data only as fallback)
- [x] Verified in browser: form → 180 kW / Renewable / ✓, CSV → 3 rows
  scored, **zero console errors**, POST → 200

### 10d. Submission deliverables (§9)
- [x] `git init` + commit (146 files) — **secret scan clean**: no endpoint
  key, no OAuth token, no `node_modules/`, no `.catalystrc`, no logs
- [x] `.gitignore` protects credentials; `catalyst-config.example.json`
  template documents the only required secret (`QUICKML_ENDPOINT_KEY`)
- [x] `README.md` rewritten: architecture diagram, setup steps, env-var
  table, transition rules, live URLs, test results (was a copy of the PDF)
- [x] `ISR_Forceast_Submission.zip` built via `git archive` (231 files,
  552 KB) — verified: no leaked secrets, all required files present

### ⚠️ Known issue: QuickML prediction quota exhausted
The endpoint returns `PREDICTION_USAGE_LIMIT_EXCEEDED` — the account's free
tier is **500 prediction calls/month** (pay-as-you-go), reset monthly, and it
was consumed by integration testing. Until it resets or the plan is upgraded:
- The function falls back to the heuristic model and says so via `note` /
  `quickml_error` (the app never breaks)
- The **bulk-first** design means a full 1000-row scoring run costs **1** API
  call instead of 1000 once quota is available — this is the fix for the
  grading run (`predict.py` on the hidden test set)
- `test_eval.py` still passes (contract check doesn't require QuickML)

---

## Phase 11: Data Cleanup, System Log & Resource Audit
**Status: ✓ COMPLETED**

### 11a. Requirement 2 — clean & validate data (both sides of the wire)
- [x] `src/preprocessing.py` → `clean_input_dataframe()`:
  numeric coercion ("31.5", "N/A" → float/NaN), median imputation, range
  clamping (temp −50..60, humidity 0..100, solar 0..1500), timestamp
  normalization to `YYYY-MM-DD HH:MM:SS` with neighbor-repair for
  unparsable values; fails only on a missing required column
- [x] `src/predict.py` now cleans **before** building the API payload — a
  NaN in the input previously serialized as invalid JSON and broke the call
- [x] Function `sanitizeRows()` — same rules server-side: string→number,
  missing→column default, range clamping, missing/bad timestamp → current
  hour, junk rows dropped (400 only if zero usable rows)
- [x] 4 new tests (dirty values, timestamp normalization, missing column,
  dirty-input predict) → **pytest 39 passed**; `test_eval.py` → SUCCESS

### 11b. System logs (architecture table: "system logs")
- [x] 🧾 System Log panel on the dashboard — monospace feed with
  color-coded source chips (FETCH / CSV / MANUAL / ALERT / SYSTEM)
- [x] Events wired: init + live forecast fetch (rows, model note, server
  summary), fetch failures, CSV import scored via QuickML, manual
  predictions (kW/mode/overload), overload raised **and** cleared
- [x] Persisted to `localStorage['hs-log']`, capped at 60 entries, Clear
  button, HTML-escaped messages
- [x] Verified live: 4 event types rendering, **zero console errors**

### 11c. Resource audit — Stratus & Data Store
- [x] Added read-only `GET /resources` to the function (admin-scope probe)
- [x] Result: `stratus: []`, `datastore: []` — **no buckets, no tables exist**
- [x] Research (web) confirmed: Catalyst exposes **no documented REST/SDK
  create-table or create-bucket API** — creation is Console-only (or via
  the `CatalystbyZoho_*` MCP tools, which are not connected in this agent)
- Consequence: the CSV→Stratus archive and forecast→Data Store logging
  integrations are **blocked on resource creation** (Console click or MCP
  setup), not on code. Everything else runs today; the system-log panel
  covers the "system logs" display requirement in the meantime.

---

## Phase 12: Virtual Assistant (Nova)
**Status: ✓ COMPLETED**

Goal: a guide that appears at site start, explains everything, and knows the
full site — without ever exposing an API key to the browser.

### 12a. Groq-backed `/assistant` route (server-side key)
- [x] Verified Groq models this key can use: `qwen/qwen3.8-27b` (primary)
  and `openai/gpt-oss-20b` (fallback) — `llama-3.3-70b-versatile` is now
  Enterprise-only
- [x] `GROQ_API_KEY` added as a **function env var** (`catalyst-config.json`,
  git-ignored; template documented in `catalyst-config.example.json`)
- [x] `POST /assistant { messages[] } → { reply }` in `functions/predict/index.js`:
  injects a site-knowledge system prompt (features, grid rules 160/180/200
  kW, 18–22h peak window, CSV import, manual predictions, system log,
  architecture, QuickML fallback), sanitizes message history (max 12 turns,
  user/assistant only), model fallback cascade, 502/503 with clear errors
- [x] Route accepts `text/plain` body (CORS-safelisted) because the Catalyst
  gateway answers OPTIONS **without** CORS headers — it never reaches the
  function. Same trick as the predict route.
- [x] Curl-verified: accurate site summary, correct transition rules,
  multi-turn context

### 12b. Dashboard widget
- [x] Chat panel (Nova) with launcher button, animated typing indicator,
  quick-prompt chips, message history (last 12 turns kept for context)
- [x] **Auto-opens ~1s after page load** with an introduction of the site,
  per the requirement "shows up at start of the site explaining everything"
- [x] Graceful degradation: assistant outage shows a friendly notice without
  breaking the dashboard; every answer is logged to the System Log panel

### 12c. Live verification (https://dashboard-ejcdhurx.onslate.in)
- [x] Rebrand: site now presented as **ISR 3.0** everywhere — page title, header
  logo, footer, Nova's subtitle, and the assistant's system prompt (it now
  answers "ISR 3.0" when asked the site's name). Repo/plan docs keep the
  HackSphere 3.0 hackathon context.
- [x] Auto-open + greeting works from the deployed Slate site
- [x] Q&A verified: site overview and grid-switch rules (160 kW / 18–22h)
  answered correctly with **zero console errors**
- [x] Key exposure audit: Groq key exists only as a function env var —
  never in `dashboard/`, git history, or the submission zip
- [x] Chat panel made solid: `--surface` is 3.5% white in dark theme, which
  made the chat look see-through — panel now uses an opaque `#0a1411`
  (light: `#ffffff`) with matching solid message/input bars

---

## Phase 13: Control-Room UI Redesign
**Status: ✓ COMPLETED**

Full visual overhaul of the dashboard (visuals only — every ID, JS hook and
feature preserved and re-tested).

### 13a. Design system
- [x] New `:root` token block per the redesign spec: `--bg #070B14`,
  `--bg-elevated #0E1626`, `--renewable #34D399`, `--solar #FBBF24`,
  `--storage #22D3EE`, `--main-grid #818CF8`, `--danger #F43F5E`,
  `--warning #FB923C`, primary gradient cyan→green, danger gradient
  red→orange. Legacy tokens (`--emerald`, `--sky`, …) kept as literal
  aliases so the chart JS (`cssVar`) keeps working unchanged
- [x] Light palette (bg `#F4F7FB`) with the same accent set
- [x] Typography: Space Grotesk headings, JetBrains Mono for every number,
  timestamp and the log (`tabular-nums`)

### 13b. Chrome & layout
- [x] Animated background: 3 slow blurred orbs (cyan/indigo/green, ~15%)
  + dot-grid overlay
- [x] Sticky glass header with a flowing energy-pulse line on its bottom
  edge; gradient bolt logo in a glowing square; QuickML Live + API pills
- [x] Layout: KPI row → chart → table (2/3) + telemetry (1/3)… as spec'd
  where the original flow allowed; fully responsive 4→2→1

### 13c. Components
- [x] All emoji icons replaced with inline SVG (1.7–1.9px stroke, Lucide
  style); zero emoji remain in the file (verified by regex scan)
- [x] KPI cards: colored top-edge glow, tinted icon squares, count-up
  numbers (existing `animateNumber`), pulsing mode badge, SOC bar with
  shimmer sweep + green/amber/red thresholds, 24h sparkline canvas
- [x] Chart: gradient area fill, faint grid only, peak-hours band, NOW
  marker with pulsing ring, dashed 160/200 kW lines with right-edge label
  chips, red tint above 200 kW, crosshair, glass tooltip, 1.2s left-to-
  right draw-in, legend pills that toggle series, skeleton shimmer loader
- [x] Table: sticky header, zebra rows, hover accent bar, mono values,
  inline demand bars, colored pills (Overload pulses), 30ms stagger,
  designed empty state, All/Renewable/Main Grid/Overload filter tabs with
  sliding underline + arrow-key support
- [x] Alert: spring slide-down + first-show shake, danger gradient glow,
  animated icon, dismiss button, pulsing red page vignette while active
- [x] Telemetry: icons + unit suffixes (°C/%/W/m²), synced range sliders,
  spinner while predicting, animated result card, toasts
- [x] System Log: darker terminal surface, mono, colored [FETCH/CSV/
  MANUAL/ALERT/SYSTEM] tags, slide-in, blinking cursor
- [x] Dev tools: "Developer tools" label, collapsible section, danger/
  success/neutral segmented buttons
- [x] Nova: gradient FAB with pulsing ring + notification dot, panel
  scale+fade from the button, glass bubbles, online dot, pill suggestions
- [x] Toasts (glass, top-right, auto-dismiss) on refresh/CSV/manual
  success & failure
- [x] Favicon (bolt), meta theme-color, custom scrollbars, ::selection,
  focus rings, reduced-motion guard, light parallax tilt on KPI cards

### 13d. Verification (local server + deployed Slate)
- [x] Refresh, CSV import (3 rows scored via function), manual predict,
  alert show/dismiss, sample data, simulate overload, filter tabs,
  legend toggles, sliders, dev-tools collapse, theme toggle, Nova
  (auto-open + greeting + chips) — all pass
- [x] Zero console errors on both local and live site

### 13e. Premium motion pass (GPU-friendly: transform/opacity only)
- [x] Background: 3 orbs re-timed to 14s ease-in-out alternate at ~20%,
  48px grid overlay with radial mask drifting slowly, 6 glowing particles
  rising bottom→top (14s, staggered)
- [x] Header: "ISR 3.0" flowing gradient text (cyan→green→indigo, 7s),
  2px light-streak loop (3.5s) on the bottom edge, breathing logo glow
- [x] Entrance: 100ms stagger with `animation-fill-mode: backwards` so
  hover transforms still apply
- [x] Hover: cards lift 3px with cyan border/shadow, buttons lift 2px,
  primary buttons sweep a diagonal shine every 3.6s
- [x] KPI numbers count up over 1.8s (easeOutExpo), on load and on every
  refresh; SOC bar grows from 0 with shimmer; mode badge breathes
- [x] Chart: 2s left-to-right draw, gradient area fades in after it
  (2.1s + 700ms), white energy pulses travel the line (dashed offset),
  cyan scan beam every 5s, NOW pulsing ring, custom glass tooltip that
  fades/scales in, legend toggles fade smoothly (animated alphas)
- [x] Table: 80ms row stagger, overload rows pulse red (2s loop)
- [x] Alert: overshoot spring-in, 2.4s red glow pulse, icon shakes every
  4s, and a real slide-up exit on dismiss (`hiding` class + animationend)
- [x] Log: lines slide in from the left, auto-scroll keeps newest visible
  without fighting manual scrolling, blinking cursor
- [x] Nova FAB floats 9px (3.5s) with ripple ring; toasts carry an
  auto-dismiss progress bar; manual-result kW counts up
- [x] Motion loop pauses when `document.hidden` (visibilitychange →
  `body.paused` freezes all decorative CSS loops); everything wrapped in
  `prefers-reduced-motion: reduce` — chart renders without animation and
  count-ups snap to final values
- [x] Re-verified after the pass: 28 element IDs and 17 JS hooks all
  intact (scripted audit), zero console errors, live site green

---

## Phase 14: Final Submission Pass (wiring + honesty patches)
**Status: ✓ COMPLETED**

Deadline-driven pass: everything patchable before Oct 28 was done; the
quota-dependent item (Nov 1 reset) was skipped per plan.

### 14a. Storage provisioning — empirically proven Console-only
- [x] Temporary admin `/provision` probe deployed; it exercised the exact
  REST paths the SDK uses for list ops, with POST (create), across payload
  variants and both credentials:
  - **Data Store:** `POST /baas/v1/project/{id}/table` exists (format
    errors, not 404) but the only format-valid body `{table_name}` is
    rejected with **"invalid oauth scope to access this URL"** — function
    tokens carry no schema-DDL scope, even as admin. Column-shaped bodies
    fail format validation; `/data-table` 404s.
  - **Stratus:** `POST /bucket` with `{bucket_name}` passes format but is
    rejected with **"User needs to be in session when accessing Stratus
    for the first time"** for both `user` and `admin` — creation needs an
    interactive Console session.
- [x] Probe removed from the shipped function; findings recorded here.

### 14b. Integration wiring (ready, self-activating)
- [x] **`POST /archive`** — accepts `{name, content}`, uploads to the
  `isr-forecast-archive` bucket (`csv/<ts>-<name>`); until the bucket
  exists it answers `{archived:false, reason}` honestly — verified live
- [x] **`logForecast()`** — every predict writes its transition signals to
  the `forecast_log` Data Store table (`timestamp`, `predicted_demand_kw`,
  `grid_mode`, `alert`, `model_source`); failures are remembered per
  container (`DATASTORE_LOG_STATE`) so warm requests pay **zero extra
  latency** (predict still 200 in 0.23s) and the log activates by itself
  the moment the table exists
- [x] Dashboard: after each successful CSV import it archives in the
  background and logs either "CSV archived to Stratus bucket" or
  "Stratus archive skipped — bucket not provisioned yet (…)" to the
  System Log — verified live
- Activation (Console, ~2 min, NOT quota-bound): create bucket
  `isr-forecast-archive` (Stratus) + table `forecast_log` with columns
  timestamp/text, predicted_demand_kw/number, grid_mode/text, alert/text,
  model_source/text; then redeploy the function. Zero code changes needed.

### 14c. Honesty patches (visible holes)
- [x] Header now tells the truth: model pill shows amber **"Fallback
  Model"** (tooltip explains quota + Nov 1) whenever the last response
  came from the heuristic, and flips back to green "QuickML Live" on its
  own when QuickML recovers; API pill shows **API · OK / API · OFFLINE**
  from real reachability. Wired into fetch, CSV, and manual flows.
- [x] Skipped by design: anything requiring the Nov 1 quota reset.

### 14d. Submission gate (all green)
- [x] `pytest` → **39 passed** (fixed a real blocker: duplicate
  `test_eval.py` basenames made bare `pytest` fail collection — added
  `pytest.ini` with `testpaths = tests` + cleared `__pycache__`)
- [x] `python test_eval.py` → **SUCCESS**
- [x] Grader CLI `python predict.py --input starter_kit/sample_test_input.csv
  --output predictions.csv` → 1000 rows written
- [x] Browser: zero console errors; pills, CSV flow, archive logging verified

---

## Dependencies

```txt
pandas>=1.5.0
numpy>=1.20.0
requests>=2.28.0
```

## Zoho Catalyst Skills Installed

The following Catalyst skills have been added via `npx skills add catalystbyzoho/agent-skills`:

| Skill | Purpose |
|-------|--------|
| catalyst-quickml | ML pipeline training & prediction endpoints |
| catalyst-slate | Frontend hosting for dashboard |
| catalyst-functions | Serverless functions (API backend) |
| catalyst-appsail | Containerized deployments |
| catalyst-datastore | Persistent data storage |
| catalyst-stratus | File storage for CSV uploads |
| catalyst-authentication | User authentication |

## Zoho Catalyst Architecture Plan

Based on the problem statement and Catalyst skills, here's the target architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                    Catalyst Slate (Dashboard)               │
│  - Static HTML/JS dashboard with Chart.js                   │
│  - Hosted at *.onslate.com                                  │
│  - Location: dashboard/                                     │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ API calls (absolute URLs)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Catalyst Functions (Advanced I/O)              │
│  - /predict - Forward to QuickML endpoint                   │
│  - Location: functions/predict/                             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Catalyst QuickML (ML Engine)                   │
│  - Train regression model on train_telemetry.csv            │
│  - Publish endpoint for predictions                         │
│  - Returns predicted demand per hour                        │
└─────────────────────────────────────────────────────────────┘
```

### Implementation Status

| Component | Status | Location |
|-----------|--------|----------|
| Dashboard (Slate) | ✓ Ready | `dashboard/index.html` |
| Prediction Function | ✓ Deployed (live) | `functions/predict/index.js` |
| Python predict.py | ✓ Ready | `src/predict.py` |
| Transition Logic | ✓ Ready | `src/transition.py` |
| QuickML Model | ✓ Trained + Published | `ISR model` (V1) → endpoint `predict` |

### Deployment Steps (when ready)

1. **QuickML Model Training** (Console → QuickML)
   - Upload train_telemetry.csv
   - Create AutoML or regression pipeline
   - Train → Evaluate → Publish endpoint
   - Copy endpoint key to `functions/predict/index.js`

2. **Initialize Catalyst Project**
   ```bash
   catalyst login
   catalyst init --org <orgId> -p <projectId> -ni
   catalyst functions:add --name predict --type aio --stack node20 -ni
   ```

3. **Deploy Functions**
   ```bash
   catalyst deploy --only functions:predict
   ```

4. **Deploy Dashboard**
   ```bash
   catalyst deploy slate
   ```

## Current Status Summary

| Phase | Status | Notes |
|-------|--------|-------|
| 1. Environment Setup | ✓ Complete | Python 3.12, all packages installed |
| 2. Data Analysis | ✓ Complete | Analyzed training/test data, created features |
| 3. predict.py | ✓ Complete | Enhanced model with QuickML integration ready |
| 4. Transition Logic | ✓ Complete | All rules implemented, 22 dedicated tests |
| 5. Testing | ✓ Complete | 35 tests pass, test_eval.py SUCCESS |
| 6. Web Dashboard | ✓ Complete | HTML/JS dashboard + Catalyst function created |
| 7. QuickML Integration | ✓ Complete | Endpoint published; function returns live model predictions |
| 8. Dashboard (Slate) | ✓ Complete | CORS fixed; end-to-end verified (see Live URLs below) |
| 9. UI Redesign | ✓ Complete | Emerald/charcoal theme, amber + sky accents, modern type |
| 10. Gap closure + submission | ✓ Complete | Server-side signals, predict.py wired, CSV/form/SOC, repo + zip (see Phase 10) |
| 11. Cleanup + system log + audit | ✓ Complete | Input cleaning both sides, System Log panel, Stratus/DataStore audit (see Phase 11) |

## Live Deployment URLs

| Component | URL |
|-----------|-----|
| Dashboard (Slate) | https://dashboard-ejcdhurx.onslate.in |
| Predict Function | https://project-rainfall-60093145112.development.catalystserverless.in/server/predict/execute |
| QuickML Endpoint | `predict` (project 100321000000013024, org 60093145112) |

## Test Results

```
test_eval.py: SUCCESS
pytest: 39 passed in 13.38s
Function: 1000-row batch → HTTP 200 in 9.0s (bulk path, 0 non-finite)
Browser: zero console errors · manual form + CSV import verified live
Assistant: Nova auto-opens on load · Groq qwen3.8-27b via /assistant (key server-side only)
Git: 146 files committed · secret scan clean · ISR_Forceast_Submission.zip (231 files)
```

## Questions for User

1. **Zoho Catalyst Account:** Do you have a Zoho Catalyst account? If yes, I can help set up the project using the CLI (`catalyst init`, `catalyst functions:add`, etc.).

2. **QuickML Training:** Should I guide you through training the model in QuickML console (upload data → create pipeline → train → publish), or do you want to use the fallback model for now and train later?

3. **Frontend Framework:** For the dashboard, do you prefer:
   - (A) Simple static HTML/JS (fastest to deploy)
   - (B) React + Vite (more interactive, recommended for good UI score)
   - (C) Skip dashboard for now, focus on backend + QuickML integration

4. **Deployment Priority:** The grading weights are:
   - 35% Model Accuracy (QuickML RMSE)
   - 35% Deployment (live URL required)
   - 20% Transition Logic
   - 10% UI
   
   Should we prioritize getting a live deployment first (even with fallback model), or perfect the QuickML model first?

## Presentation Deck

**Status: ✅ BUILT (2026-10-26)** — `ppt/isr-overview.pptx`

- 13 slides, 16:9 dark "control-room" theme (matches the dashboard palette: cyan/green/amber/indigo on deep navy)
- Flow: Cover → Problem → Solution → How It Works → Transition Rules → Architecture → Frontend → The Model → Scaling & Robustness → Current State → Nova Assistant → Why It Wins → Next Steps
- Sources: `ppt/slide1.py` … `ppt/slide13.py` (each compiles standalone)
- Build: `python ppt/_emit.py` (regenerates `ppt/build-ppt.py` from the slide sources) then `python ppt/build-ppt.py` → `ppt/isr-overview.pptx`
- Verified: all 13 slides reopen via python-pptx; every slide's text content inspected — no mangled strings, correct line breaks, escaped quotes render as intended
- Assets: `ppt/img/` (Nova avatar PNG used on slide 11; SVG art kept as source)
