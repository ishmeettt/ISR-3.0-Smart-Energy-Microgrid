# HackSphere 3.0 — Smart Energy Microgrid & Demand Forecasting Engine

End-to-end web application on **Zoho Catalyst** that forecasts hourly energy demand
for the next 24 hours using a **QuickML** regression model, then triggers automated
power-source transition signals between Main Grid and Renewable Battery Storage.

**Live app:** https://dashboard-ejcdhurx.onslate.in

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Catalyst Slate (static dashboard)                              │
│  https://dashboard-ejcdhurx.onslate.in                          │
│  - 24h load curve, grid-mode badges, battery SOC, alerts        │
│  - CSV import + manual telemetry form (runs through QuickML)    │
└────────────────────────────┬─────────────────────────────────────┘
                             │ POST {data:[…]} (text/plain, CORS-safe)
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  Catalyst Function — predict (Advanced I/O, Node.js 20)         │
│  /server/predict/execute                                        │
│  - Calls QuickML via zcatalyst-sdk-node (bulk → per-row)        │
│  - Transition controller: grid mode + overload per hour (§6)     │
│  - Returns { predictions[], signals[], summary, note }          │
└────────────────────────────┬─────────────────────────────────────┘
                             │ X-QUICKML-ENDPOINT-KEY (server-side only)
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  Zoho Catalyst QuickML — ISR model (V1), endpoint "predict"     │
│  Decision-Tree regression, target: target_demand_kw             │
│  Features: ambient_temp_c, humidity_pct, solar_irradiance_wm2   │
└──────────────────────────────────────────────────────────────────┘
```

Local Python pipeline (`src/`) mirrors the same contract for training-side
validation and the mandatory self-test:

| File | Purpose |
|------|---------|
| `predict.py` | Submission entry point — batches all rows to the live function, falls back locally |
| `src/predict.py` | Prediction logic + heuristic fallback |
| `src/transition.py` | Grid-mode / overload rules (unit-tested) |
| `src/preprocessing.py` | Validation & feature preparation |
| `tests/test_predict.py` | 35 unit tests |

---

## Setup Steps

### Prerequisites
- Node.js 20+ and Catalyst CLI (`npm install -g zcatalyst-cli`), `catalyst login`
- Python 3.12+ with `pip install pandas numpy requests`

### 1. Clone & install
```bash
git clone <YOUR_REPO_URL>
cd <repo>
cd functions/predict && npm install   # zcatalyst-sdk-node
```

### 2. Configure the function's QuickML endpoint key
Copy the template and paste your endpoint key from
**Console → QuickML → Endpoints → (endpoint) → Required Headers → X-QUICKML-ENDPOINT-KEY**:
```bash
cp functions/predict/catalyst-config.example.json functions/predict/catalyst-config.json
```
Edit `functions/predict/catalyst-config.json` and replace `<YOUR_QUICKML_ENDPOINT_KEY>`.

> ⚠️ **Keep credentials secure:** `catalyst-config.json` is git-ignored and must
> never be committed or shared. The key is only read server-side by the function.

### 3. Deploy
```bash
catalyst deploy --only functions:predict   # API + transition controller
catalyst deploy slate                      # dashboard
```

### 4. Run the local pipeline
```bash
python test_eval.py                                            # must print SUCCESS
python predict.py --input sample_test_input.csv --output predictions.csv
python -m pytest tests/ -q                                     # 35 tests
```

### Environment variables

| Variable | Where | Purpose |
|----------|-------|---------|
| `QUICKML_ENDPOINT_KEY` | Function env (`catalyst-config.json` → `deployment.env_variables`) | Auth key for the published QuickML endpoint |
| `QUICKML_ENDPOINT_URL` | Optional, shell env for `predict.py` | Overrides the default live function URL |
| `CATALYST_ORG_ID` | Function code (fallback `60093145112`) | Org header for the QuickML SDK call |

---

## Transition Controller Rules (problem statement §6)

| Condition | Grid Mode / Alert |
|-----------|-------------------|
| Demand **> 160 kW** OR hour **18:00–22:00 inclusive** | Renewable Storage Mode |
| Otherwise (≤ 160 kW and outside the window) | Main Grid Mode |
| Demand **≥ 200 kW** | Critical Overload Alert (independent of mode) |

Enforced **server-side** in the function response (`signals[]` + `summary`) and
mirrored in the dashboard UI and `src/transition.py`.

---

## Dataset Schema

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | String `YYYY-MM-DD HH:MM:SS` | Reading or forecast hour |
| `ambient_temp_c` | Float | Outdoor temperature (°C) |
| `humidity_pct` | Float | Relative humidity (%) |
| `solar_irradiance_wm2` | Float | Solar potential (W/m²) |
| `target_demand_kw` | Float | Actual demand — **training only, omitted from test inputs** |

---

## Live URLs

| Component | URL |
|-----------|-----|
| Dashboard (Slate) | https://dashboard-ejcdhurx.onslate.in |
| Predict function | `https://project-rainfall-60093145112.development.catalystserverless.in/server/predict/execute` |
| QuickML endpoint | `predict` (project `100321000000013024`, IN data center) |

## Testing

```bash
test_eval.py      → SUCCESS
pytest            → 35 passed
```

## Submission Notes

- Public repo or `TeamName_Submission.zip` should be created **excluding**
  git-ignored files (credentials, `node_modules/`, `.build/`, logs).
- `predict.py` is pre-wired to the live function — graders can run
  `python predict.py --input <hidden>.csv --output predictions.csv` as-is.
