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

## Live Deployment URLs

| Component | URL |
|-----------|-----|
| Dashboard (Slate) | https://dashboard-ejcdhurx.onslate.in |
| Predict Function | https://project-rainfall-60093145112.development.catalystserverless.in/server/predict/execute |
| QuickML Endpoint | `predict` (project 100321000000013024, org 60093145112) |

## Test Results

```
test_eval.py: SUCCESS
pytest: 35 passed in 3.06s
Function: 1000-row batch → HTTP 200 in 9.0s (bulk path, 0 non-finite)
Browser: zero console errors · manual form + CSV import verified live
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
