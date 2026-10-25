# HackSphere 3.0 - Deployment Guide for Zoho Catalyst

This guide walks you through deploying the HackSphere 3.0 application to Zoho Catalyst.

## Prerequisites

1. **Zoho Catalyst Account** - Sign up at https://catalyst.zoho.com/
2. **Create a new project** in the Catalyst Console
3. **Node.js v20+** installed (currently using v26.7.0)
4. **Catalyst CLI** installed (`npm install -g zcatalyst-cli`)

## Deployment Steps

### Step 1: Login to Catalyst

```bash
catalyst login
```

This will open a browser window for authentication. Complete the login, then return to the terminal.

### Step 2: List Your Projects

```bash
catalyst project:list
```

Note the project ID of the project you want to deploy to.

### Step 3: Initialize the Project

```bash
catalyst init --org <YOUR_ORG_ID> -p <YOUR_PROJECT_ID> -ni
```

Replace `<YOUR_ORG_ID>` and `<YOUR_PROJECT_ID>` with your actual values.

This creates a `.catalystrc` file linking your local directory to the Catalyst project.

### Step 4: Add the Prediction Function

```bash
catalyst functions:add --name predict --type aio --stack node20 -ni
```

This creates the function scaffolding. **Note:** This may overwrite our existing `functions/predict/index.js`. If so, restore it from git or recreate it.

### Step 5: Configure the Function

Update `functions/predict/index.js` with your QuickML endpoint key (after training the model):

```javascript
const QUICKML_ENDPOINT_KEY = process.env.QUICKML_ENDPOINT_KEY || 'YOUR_ACTUAL_ENDPOINT_KEY';
```

### Step 6: Deploy the Function

```bash
catalyst deploy --only functions:predict
```

After deployment, note the function URL (it will be shown in the output).

### Step 7: Deploy the Dashboard to Slate

First, update `catalyst.json` with the correct dashboard source path:

```json
{
  "slate": [{
    "name": "dashboard",
    "source": "C:\\Users\\user\\HackSphere3.0\\dashboard"
  }]
}
```

Then deploy:

```bash
catalyst deploy slate
```

### Step 8: Verify Deployment

1. **Function:** Test the deployed function URL with a POST request
2. **Dashboard:** Open the Slate URL in a browser

## QuickML Model Training (Required for Full Functionality)

Before the prediction function can use the actual ML model, you need to train it in QuickML:

1. Go to **Catalyst Console → QuickML**
2. Click **"Start Exploring"** to activate QuickML
3. **Upload Data:** Import `starter_kit/train_telemetry.csv`
4. **Create Pipeline:**
   - Type: Prediction (Regression)
   - Target column: `target_demand_kw`
   - Features: `ambient_temp_c`, `humidity_pct`, `solar_irradiance_wm2`, `timestamp`
5. **Train:** Execute the pipeline
6. **Evaluate:** Check RMSE metric
7. **Publish:** Create an endpoint from the best model version
8. **Copy Endpoint Key:** Use it in `functions/predict/index.js`

## Project Structure for Deployment

```
HackSphere3.0/
├── catalyst.json           # Project config (updates after init)
├── .catalystrc            # Created by catalyst init
├── dashboard/
│   ├── index.html         # Dashboard (deployed to Slate)
│   └── .catalyst/
│       └── slate-config.toml
├── functions/
│   └── predict/
│       ├── index.js       # Prediction API (deployed as function)
│       ├── package.json
│       └── node_modules/
├── src/                   # Python modules (for local testing/submission)
├── tests/                 # Test suite
└── starter_kit/           # Original starter data
```

## Files to Submit

For the hackathon submission, you need to provide:

1. **Public Catalyst App URL** (from Slate deployment)
2. **GitHub Repository URL** OR zipped source folder
3. **Working predict.py** with QuickML endpoint configured
4. **README.md** with setup instructions

## Troubleshooting

### Login Issues
- Ensure you're using the correct Zoho account
- Check browser popup blockers

### Function Deployment Fails
- Check `catalyst.json` has correct function target
- Verify `functions/predict/package.json` exists
- Ensure Node.js dependencies are installed

### Slate Deployment Fails
- Ensure Slate is activated in Console (Slate → Start Exploring)
- Verify `dashboard/.catalyst/slate-config.toml` exists
- Check `catalyst.json` has correct slate source path

### Function Returns 404
- Remember to add `/execute` suffix to the function URL
- Example: `https://project.catalystserverless.com/server/predict/execute`

## Environment Variables (for Production)

After deployment, you can set environment variables in the Catalyst Console:

- `QUICKML_ENDPOINT_KEY` - Your QuickML endpoint key
- `QUICKML_API_HOST` - API host (e.g., https://api.catalyst.zoho.com)

Set these in Console → Functions → predict → Environment Variables
