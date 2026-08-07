# Setup guide: Brazil Trading with the World

Free, no-premium-tier pipeline: Comex Stat (MDIC) raw files, refreshed monthly by a
Cloud Function, land in BigQuery, and Looker Studio reads directly from there.
Nobody has to manually download a CSV again after this is running.

Everything here fits inside Google Cloud's free tier for a dataset this size
(low millions of rows per year): Cloud Functions (2M invocations/month free),
Cloud Scheduler (3 jobs free), BigQuery (1 TB queries + 10 GB storage free per
month).

## 1. Create the GCP project

1. Go to [console.cloud.google.com](https://console.cloud.google.com), create a new project.
2. Enable billing (required even on the free tier; you won't be charged unless you exceed it).
3. Enable these APIs: **BigQuery API**, **Cloud Functions API**, **Cloud Scheduler API**, **Cloud Build API**.

## 2. Create the BigQuery dataset and tables

1. Open **BigQuery** in the console.
2. Open `sql/schema.sql` from this repo, replace `your_project` with your actual project id.
3. Run the whole script in the BigQuery SQL editor. This creates the dataset and five empty tables.
4. Run `sql/sh2_labels.sql` (same project-id replacement): a one-time static lookup of short,
   human-readable names for the 97 HS2 product chapters, used later by `sql/views.sql` to
   avoid showing raw customs nomenclature on charts.

## 3. Deploy the Cloud Function

Cloud Functions 2nd gen runs on Cloud Run under the hood, so this deploys with the
`gcloud run deploy` command, pointed at your function's entry point.

Use **Cloud Shell** (the terminal icon in the console header) rather than a local
machine: it comes with `gcloud` already authenticated, and uploads source directly
without needing git or a local Python environment.

1. Upload this repo's `cloud_function/` folder to Cloud Shell (drag-and-drop onto the
   Cloud Shell terminal, or use its **Upload** button), so you have a folder containing
   `main.py` and `requirements.txt`.
2. From inside that folder, deploy:

```bash
gcloud run deploy refresh-trade-data \
  --source=. \
  --function=refresh_trade_data \
  --region=us-central1 \
  --no-allow-unauthenticated \
  --timeout=3600 \
  --memory=4Gi \
  --cpu=2 \
  --set-env-vars=GCP_PROJECT=your-project-id,BQ_DATASET=trade_data
```

Notes on the flags:
- `--no-allow-unauthenticated` keeps the endpoint private; Cloud Scheduler will call it
  with its own service-account credentials (step 4), nobody else needs access to it.
- `--memory=4Gi --cpu=2` and `--timeout=3600`: a full year's raw NCM-level export/import
  CSVs are large enough (400k+ rows each after aggregation) that the default Cloud Run
  sizing runs out of memory mid-load. This sizing has headroom to spare.
- The build step runs `python3 -m compileall` on your source before deploying, so a
  syntax error fails the build with a clear line number rather than failing silently at
  runtime.

Grant the function's service account permission to read/write BigQuery (the project
number-based default compute service account, unless you've set up a custom one):

```bash
gcloud projects add-iam-policy-binding your-project-id \
  --member="serviceAccount:your-project-id@appspot.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"
```

Test it once manually before scheduling anything:

```bash
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "https://YOUR-SERVICE-URL"
```

A healthy response looks like:

```json
{"dimension_rows_loaded":{"d_country":281,"d_ncm":13745,"d_sh":6620,"d_state":34},"fact_rows_loaded":492718,"table":"your-project-id.trade_data.f_trading","year":2026}
```

## 4. Schedule the monthly run

Comex Stat updates the current year's file roughly monthly. Trigger the function on the
5th of each month, giving MDIC a few days' buffer after month-end close. Each run
refreshes the four dimension tables (country, state, NCM, SH hierarchy) and the current
year's fact data, so there's no separate manual reference-data step:

```bash
gcloud scheduler jobs create http refresh-trade-data-monthly \
  --schedule="0 6 5 * *" \
  --uri="https://YOUR-SERVICE-URL" \
  --http-method=GET \
  --oidc-service-account-email=your-project-id@appspot.gserviceaccount.com \
  --location=us-central1
```

(`--location` needs to match the region you deployed to; the Cloud Scheduler API gets
enabled automatically the first time you run this, if it isn't already.)

## 5. Backfill prior years (one-time)

The scheduled job only ever refreshes the *current* year's fact data (the dimension
tables get reloaded on every call regardless). To load history, call the function once
per past year you want, with `skip_dimensions=true` so you're not re-pulling the same
four small files on every backfill call:

```bash
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "https://YOUR-SERVICE-URL?year=2023&skip_dimensions=true"
```

Repeat for each year back to as far as you want (Comex Stat's NCM-level files go back to
1997, though file size, and the time each call takes, grows the further back you go).
Going back to around 2015-2019 is usually enough to show a meaningful multi-year trend
without a long backfill run.

## 6. Connect Looker Studio

1. In [Looker Studio](https://lookerstudio.google.com), create a new report.
2. Add a data source → **BigQuery** connector → select your project, dataset, and `f_trading`.
3. Add the dimension tables as additional data sources and blend/join them on their key
   columns (`co_pais`, `sg_uf_ncm` / `sg_uf`, `co_ncm`, `co_sh6`), or create BigQuery views
   that pre-join everything if you'd rather blend once at the SQL layer.

## 7. Build the report

Suggested structure, mirroring what this dataset supports:

- **Page 1, Brazil overview**: KPI scorecards (total exports, imports, balance), a
  dropdown filter for state (defaulting to "All Brazil"), top-partner and top-product bar
  charts, all driven by the filter.
- **Geo chart**: Looker Studio's native **Filled Map** chart type supports Brazilian
  states directly, no per-visual category cap and no separate licensing, unlike some
  third-party Power BI map visuals.
- **Page 2, state drill-down**: same filter carried over, more detail once a state is
  selected.

## Adapting this for a different country or dataset

Everything past step 2 is generic: swap the download URLs and column names in
`cloud_function/main.py` for whatever your source publishes, adjust `sql/schema.sql` to
match, and the Cloud Scheduler + Looker Studio wiring stays exactly the same.
