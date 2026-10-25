/**
 * HackSphere 3.0 - QuickML Prediction Function
 *
 * Uses Catalyst QuickML when QUICKML_ENDPOINT_KEY is set via environment variable.
 * Falls back to a built-in heuristic model otherwise, so the app keeps working before
 * the QuickML model is trained and published.
 *
 * Response contract:
 *   {
 *     predictions: number[],            // one per input row (backward compatible)
 *     signals: [{                       // server-side transition controller output
 *       timestamp, hour, predicted_demand_kw,
 *       grid_mode: 'renewable_storage' | 'main_grid',
 *       alert: 'critical_overload' | 'normal'
 *     }],
 *     summary: { renewable_hours, main_grid_hours, overload_hours },
 *     status, note
 *   }
 */
'use strict';

const catalyst = require('zcatalyst-sdk-node');
const constants = require('zcatalyst-sdk-node/lib/utils/constants').default;

// Concurrency for QuickML per-row calls: the Advanced I/O timeout is 30s and
// the SDK's predict() accepts one row per call, so rows are dispatched in
// parallel windows instead of one-by-one (1000 sequential calls would blow
// the timeout AND burn 1000x the prediction quota).
const QUICKML_CONCURRENCY = 25;

function sendJson(res, statusCode, data) {
    res.writeHead(statusCode, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(data));
}

function getBody(req) {
    return new Promise((resolve, reject) => {
        if (req.body && typeof req.body === 'object') return resolve(req.body);
        if (req.body && typeof req.body === 'string') {
            try { return resolve(JSON.parse(req.body)); } catch (e) { return resolve({}); }
        }
        let data = '';
        req.on('data', (chunk) => { data += chunk; });
        req.on('end', () => {
            try { resolve(data ? JSON.parse(data) : {}); } catch (e) { resolve({}); }
        });
        req.on('error', reject);
    });
}

const QUICKML_ENDPOINT_KEY = process.env.QUICKML_ENDPOINT_KEY || '';

/** Run fn over items with at most `limit` in flight, preserving order. */
async function mapWithConcurrency(items, limit, fn) {
    const results = new Array(items.length);
    let next = 0;
    async function worker() {
        while (next < items.length) {
            const i = next++;
            results[i] = await fn(items[i], i);
        }
    }
    const workers = [];
    const pool = Math.min(limit, items.length);
    for (let w = 0; w < pool; w++) workers.push(worker());
    await Promise.all(workers);
    return results;
}

/**
 * Extract the hour from a timestamp string WITHOUT Date parsing, so the hour
 * comes from the written timestamp itself rather than the server's timezone.
 * Accepts "YYYY-MM-DD HH:MM:SS", ISO "YYYY-MM-DDTHH:MM:SS...", "HH:MM".
 */
function hourFromTimestamp(ts) {
    if (typeof ts !== 'string') return null;
    const m = ts.match(/(\d{1,2}):(\d{2})/);
    if (m) return parseInt(m[1], 10);
    const d = new Date(ts);
    if (!Number.isNaN(d.getTime())) return d.getHours();
    return null;
}

/**
 * Transition controller rules (problem statement §6):
 *  - Demand > 160 kW OR hour 18-22 inclusive  -> Renewable Storage Mode
 *  - Otherwise                                 -> Main Grid Mode
 *  - Demand >= 200 kW                          -> Critical Overload Alert (independent)
 */
function buildTransitionSignals(rows, predictions) {
    let renewableHours = 0;
    let mainGridHours = 0;
    let overloadHours = 0;

    const signals = rows.map((row, i) => {
        const demand = Math.round(Number(predictions[i]) * 100) / 100;
        const hour = hourFromTimestamp(row.timestamp);
        const inPeakWindow = hour !== null && hour >= 18 && hour <= 22;
        const gridMode = (demand > 160 || inPeakWindow) ? 'renewable_storage' : 'main_grid';
        const alert = demand >= 200 ? 'critical_overload' : 'normal';

        if (gridMode === 'renewable_storage') renewableHours++;
        else mainGridHours++;
        if (alert === 'critical_overload') overloadHours++;

        return {
            timestamp: row.timestamp,
            hour: hour,
            predicted_demand_kw: demand,
            grid_mode: gridMode,
            alert: alert
        };
    });

    return {
        signals,
        summary: {
            renewable_hours: renewableHours,
            main_grid_hours: mainGridHours,
            overload_hours: overloadHours
        }
    };
}

/**
 * Call the Catalyst QuickML prediction model for one or more rows.
 *
 * Uses the Catalyst Node.js SDK's QuickML client (catalystApp.quickML()):
 * the SDK authenticates with the function's internal Catalyst credentials and
 * adds X-QUICKML-ENDPOINT-KEY. A raw fetch cannot produce that internal ticket
 * (QuickML rejects it with INVALID_TICKET).
 *
 * The SDK's predict() takes ONE row object per call (arrays fail its validator),
 * so rows run through a bounded-concurrency pool and each response's first
 * result value is collected in order.
 *
 * Returns an array of predicted target_demand_kw values, or null when no
 * endpoint key is configured (caller falls back to the heuristic).
 */
async function callQuickMl(req, rows) {
    if (!QUICKML_ENDPOINT_KEY) {
        return null; // signal that we should fall back
    }

    // The model was trained with the timestamp column dropped, but the
    // endpoint's request contract still requires timestamp as an input column,
    // so we include it alongside the numeric feature columns.
    const features = rows.map((row) => ({
        timestamp: row.timestamp,
        ambient_temp_c: row.ambient_temp_c,
        humidity_pct: row.humidity_pct,
        solar_irradiance_wm2: row.solar_irradiance_wm2
    }));

    // Initialize the SDK from the incoming Advanced I/O request so the call
    // carries the function's internal admin credentials, then run prediction.
    const catalystApp = catalyst.initialize(req);
    const quickMl = catalystApp.quickML();

    // The SDK only attaches the CATALYST-ORG header when
    // process.env.X_ZOHO_CATALYST_ORG_ID is set. It is a reserved keyword in
    // Catalyst's env_variables, so we provide it here from the project's org
    // instead of deploying it as an environment variable.
    if (!process.env.X_ZOHO_CATALYST_ORG_ID) {
        process.env.X_ZOHO_CATALYST_ORG_ID = process.env.CATALYST_ORG_ID || '60093145112';
    }

    const startedAt = Date.now();

    // STRATEGY 1: one bulk request with ALL rows. The SDK's predict() rejects
    // arrays client-side, so we go through the SDK's authenticated requester
    // directly (same ticket/org/endpoint-key headers, same path) but pass the
    // full row array. If the API accepts it, N rows cost ONE prediction call —
    // critical because the free QuickML tier counts every prediction request.
    try {
        const resp = await quickMl.requester.send({
            method: constants.REQ_METHOD.post,
            path: `/${constants.PRODUCT_NAME.quickml}/${constants.API_VERSION}/project/${quickMl.projectId}/endpoints/predict`,
            data: { data: features },
            type: 'json',
            headers: { 'X-QUICKML-ENDPOINT-KEY': QUICKML_ENDPOINT_KEY },
            catalyst: false,
            track: true,
            user: constants.CREDENTIAL_USER.admin
        });
        const bulk = normalizeBulkResult(resp.data, features.length);
        if (bulk) {
            console.log(`QuickML bulk: ${features.length} rows in 1 request, ${Date.now() - startedAt}ms`);
            return bulk;
        }
        console.warn('QuickML bulk: unexpected result shape, falling back to per-row calls');
    } catch (bulkErr) {
        // Shape/contract rejections fall through to per-row; usage-limit
        // errors would fail there too, so bail immediately with the real error.
        // NOTE: SDK rejections are often plain objects {code, message}, not Errors.
        const desc = String((bulkErr && bulkErr.message) || bulkErr);
        const code = String((bulkErr && bulkErr.code) || '');
        if (/USAGE_LIMIT/i.test(desc + ' ' + code)) {
            throw bulkErr;
        }
        console.warn('QuickML bulk request rejected, falling back to per-row calls:', desc);
    }

    // STRATEGY 2: one authenticated call per row, bounded concurrency.
    const predictions = await mapWithConcurrency(features, QUICKML_CONCURRENCY, async (feature) => {
        const response = await quickMl.predict(QUICKML_ENDPOINT_KEY, feature);
        if (response && Array.isArray(response.result) && response.result.length > 0) {
            return response.result[0];
        }
        if (response && typeof response.result === 'number') {
            return response.result;
        }
        throw new Error('Unexpected QuickML response shape: ' + JSON.stringify(response));
    });
    console.log(`QuickML per-row: ${features.length} rows in ${Date.now() - startedAt}ms (concurrency ${QUICKML_CONCURRENCY})`);
    return predictions;
}

/**
 * Coerce a bulk QuickML response into a flat prediction array, or null when
 * the shape doesn't match the row count (caller falls back to per-row).
 * Handles both flat `result: [v1, v2, ...]` and nested `[[v1], [v2], ...]`.
 */
function normalizeBulkResult(data, expectedCount) {
    if (!data || !Array.isArray(data.result)) return null;
    const raw = data.result;
    if (raw.length !== expectedCount) return null;
    const flat = raw.map((v) => Array.isArray(v) ? v[0] : v);
    if (!flat.every((v) => typeof v === 'number' && isFinite(v))) return null;
    return flat;
}

/** Heuristic fallback used only when QuickML is unavailable/misconfigured. */
function fallbackPredictions(rows) {
    return rows.map((row) => {
        const hour = hourFromTimestamp(row.timestamp);
        let baseLoad;
        if (hour === null) baseLoad = 140;
        else if (hour >= 6 && hour <= 9) baseLoad = 170;
        else if (hour >= 18 && hour <= 22) baseLoad = 210;
        else if (hour >= 10 && hour <= 17) baseLoad = 160;
        else baseLoad = 95;

        const tempEffect = Math.max(0, (row.ambient_temp_c || 25) - 24) * 5;
        return Math.round((baseLoad + tempEffect) * 100) / 100;
    });
}

// Column defaults for sanitation: training-data medians / physically valid
// midpoints, used only when an incoming value is missing or non-numeric.
const COLUMN_DEFAULTS = {
    ambient_temp_c: 20.0,
    humidity_pct: 60.0,
    solar_irradiance_wm2: 0.0
};

/**
 * Requirement 2 (Data Ingestion & Cleanup): coerce incoming rows to the
 * training schema before QuickML sees them — numeric fields become finite
 * numbers (missing/bad -> column default, clamped to valid ranges), and a
 * missing/unparsable timestamp falls back to the current hour. Rows without
 * any usable structure at all are dropped.
 */
function sanitizeRows(rawRows) {
    const cleaned = [];
    for (const r of rawRows) {
        if (!r || typeof r !== 'object') continue;

        const num = (v, key) => {
            const n = typeof v === 'number' ? v : parseFloat(v);
            const val = Number.isFinite(n) ? n : COLUMN_DEFAULTS[key];
            if (key === 'ambient_temp_c') return Math.max(-50, Math.min(60, val));
            if (key === 'humidity_pct') return Math.max(0, Math.min(100, val));
            return Math.max(0, Math.min(1500, val)); // solar W/m²
        };

        let timestamp = typeof r.timestamp === 'string' && r.timestamp.trim()
            ? r.timestamp.trim()
            : null;
        if (timestamp === null || hourFromTimestamp(timestamp) === null) {
            const d = new Date();
            const p = (x) => String(x).padStart(2, '0');
            timestamp = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ` +
                `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
        }

        cleaned.push({
            timestamp,
            ambient_temp_c: num(r.ambient_temp_c, 'ambient_temp_c'),
            humidity_pct: num(r.humidity_pct, 'humidity_pct'),
            solar_irradiance_wm2: num(r.solar_irradiance_wm2, 'solar_irradiance_wm2')
        });
    }
    return cleaned;
}

module.exports = async (req, res) => {
    try {
        console.log('Prediction function invoked');
        const method = req.method;
        const url = new URL(req.url, `https://${req.headers.host}`);
        let path = url.pathname;

        // Catalyst serve prefixes /server/<functionName>/; production adds /execute
        // Normalize both forms to the same internal path
        if (path.startsWith('/server/')) {
            const match = path.match(/^\/server\/[^\/]+\/(.*)$/);
            if (match) path = '/' + match[1];
            else path = '/';
        }
        if (path.startsWith('/execute')) {
            path = path.replace(/^\/execute/, '') || '/';
        }

        if (method === 'OPTIONS') {
            res.writeHead(204, {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            });
            res.end();
            return;
        }

        res.setHeader('Access-Control-Allow-Origin', '*');

        if (method === 'GET' && path === '/') {
            sendJson(res, 200, { status: 'ok', service: 'hacksphere-predict' });
            return;
        }

        // Diagnostics: what storage resources exist in this project?
        // (Stratus buckets + Data Store tables — used to wire CSV archiving
        // and forecast logging.) Read-only.
        if (method === 'GET' && path === '/resources') {
            const out = { stratus: null, datastore: null };
            try {
                const app = catalyst.initialize(req, { scope: 'admin' });
                try {
                    out.stratus = await app.stratus().listBuckets();
                } catch (e) {
                    out.stratus = { error: String(e && e.message || e) };
                }
                try {
                    out.datastore = await app.datastore().getAllTables();
                } catch (e) {
                    out.datastore = { error: String(e && e.message || e) };
                }
                sendJson(res, 200, out);
            } catch (e) {
                sendJson(res, 200, { stratus: { error: e.message }, datastore: { error: e.message } });
            }
            return;
        }

        if (method === 'POST' && path === '/') {
            const body = await getBody(req);

            if (!body.data || !Array.isArray(body.data) || body.data.length === 0) {
                sendJson(res, 400, { error: 'Missing or invalid data array' });
                return;
            }

            // Clean/validate before anything else sees the rows (requirement 2).
            const rows = sanitizeRows(body.data);
            if (rows.length === 0) {
                sendJson(res, 400, { error: 'No usable rows after cleaning input data' });
                return;
            }

            let predictions;
            let note;
            let quickmlErrorDetail;

            try {
                const quickmlResult = await callQuickMl(req, rows);
                if (quickmlResult !== null) {
                    predictions = quickmlResult;
                    note = 'From QuickML trained model';
                } else {
                    throw new Error('No QuickML endpoint key configured');
                }
            } catch (quickmlError) {
                console.warn('QuickML call failed, using fallback model:', quickmlError.message);
                quickmlErrorDetail = quickmlError.message;
                predictions = fallbackPredictions(rows);
                note = 'Using fallback model';
            }

            // Server-side transition controller (grid mode + overload per hour)
            const { signals, summary } = buildTransitionSignals(rows, predictions);

            const payload = {
                predictions: predictions,
                signals: signals,
                summary: summary,
                status: 'success',
                note: note
            };
            // Surface the QuickML failure reason when we fell back, so the
            // client (and logs) can diagnose instead of guessing.
            if (quickmlErrorDetail) payload.quickml_error = quickmlErrorDetail;
            sendJson(res, 200, payload);
            return;
        }

        sendJson(res, 404, { error: 'Not found' });
    } catch (error) {
        console.error('Error:', error);
        sendJson(res, 500, { error: error.message });
    }
};
