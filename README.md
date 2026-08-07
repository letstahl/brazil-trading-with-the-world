English &nbsp;·&nbsp; [Português](README.pt-BR.md)

# Brazil Trading with the World

*An analytics engineering case study: an automated, zero-cost pipeline for Brazil's
foreign trade data, from raw government files to a governed BigQuery model and a live
dashboard.*

[**Live dashboard**](https://lookerstudio.google.com/reporting/2f914270-3b2c-4ff2-b403-bb4942022449) &nbsp;·&nbsp; [Setup guide](SETUP.md) &nbsp;·&nbsp; [MIT](LICENSE)

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Cloud Run](https://img.shields.io/badge/Cloud%20Run-functions-4285F4?logo=googlecloud&logoColor=white)
![Cloud Scheduler](https://img.shields.io/badge/Cloud%20Scheduler-monthly-4285F4?logo=googlecloud&logoColor=white)
![BigQuery](https://img.shields.io/badge/BigQuery-star%20schema-4285F4?logo=googlebigquery&logoColor=white)
![Looker Studio](https://img.shields.io/badge/Looker%20Studio-reporting-4285F4?logo=looker&logoColor=white)
[![Project Status: WIP](https://www.repostatus.org/badges/latest/wip.svg)](https://www.repostatus.org/#wip)

## Overview

Most trade-data dashboards are built the same way: someone downloads a CSV by hand, runs a
cleaning script locally, re-uploads it to a BI tool, and repeats the whole thing next
month. This project automates that away.

A scheduled job pulls Brazil's official foreign trade data (Comex Stat / MDIC) every
month, loads it into a partitioned BigQuery star schema, and a Looker Studio report reads
directly from the warehouse. Nobody re-runs a script or re-uploads a file. The dashboard
is the demonstration layer; the pipeline underneath it is the actual subject of this repo.

Built as a replicable reference: the [setup guide](SETUP.md) is written so the same
pattern, ingestion, orchestration, warehousing, and reporting, can be adapted to any
other recurring public dataset, entirely on Google Cloud's free tier.

## Architecture

```
Comex Stat (MDIC)  →  Cloud Run function (monthly)  →  BigQuery  →  Looker Studio
   raw CSVs             download, clean, load           star schema    live report
                              ↑
                       Cloud Scheduler
```

- **Ingestion**: an HTTP-triggered Cloud Run function (Python), invoked monthly by Cloud
  Scheduler. It downloads the current year's export/import files plus four reference
  tables (country, state, NCM product code, SH product hierarchy) and reloads them on
  every run.
- **Storage**: BigQuery, partitioned by year and clustered by state/country, so a monthly
  refresh only touches the current, still-incomplete year, never a full-table rewrite.
- **Modeling**: a set of SQL views sit between the raw tables and the report, pre-joining
  dimensions, computing derived metrics (market concentration via HHI), and shortening
  raw customs nomenclature into human-readable product labels.
- **Reporting**: Looker Studio, connected directly to the BigQuery views. No blending
  logic lives in the report itself.

## Data model

Star schema: one fact table, four dimensions, three reporting views on top.

| Table | Grain | Notes |
|---|---|---|
| `f_trading` | year × NCM code × state × partner country | Partitioned by year, clustered by state/country |
| `d_country`, `d_state`, `d_ncm`, `d_sh` | one row per entity | Reference data, reloaded in full on every run |
| `v_trading_enriched` | pre-joined fact + all dimensions | What the report actually queries |
| `v_country_concentration` | one row per year | Herfindahl-Hirschman Index of export-partner concentration |
| `v_top_partner_by_year` | one row per year | Largest export partner and its share |

Full DDL in `sql/schema.sql`, `sql/sh2_labels.sql`, and `sql/views.sql`.

## Tech stack

| Layer | Tool | Why |
|---|---|---|
| Source | Comex Stat (MDIC) | Official, public, updated monthly, no auth required |
| Compute | Cloud Run functions (Python) | Serverless, free tier covers this workload entirely |
| Orchestration | Cloud Scheduler | Cron-based monthly trigger |
| Warehouse | BigQuery | Partitioned star schema, SQL views for reporting logic |
| Reporting | Looker Studio | Free tier, no per-visual licensing caps |

## Repository structure

```
sql/
  schema.sql        star schema DDL
  sh2_labels.sql    curated short labels for the 97 HS2 product chapters
  views.sql         reporting views (enrichment, HHI, top partner)
cloud_function/
  main.py           ingestion job: download, clean, load
  requirements.txt
design/
  backgrounds/      report and landing page background images
SETUP.md            step-by-step deployment guide
LICENSE             MIT
```

## Getting started

See [SETUP.md](SETUP.md) for the full walkthrough: creating the GCP project, deploying
the Cloud Run function, scheduling the monthly run, backfilling history, and connecting
Looker Studio.

## Data

Source: [Comex Stat](https://www.gov.br/mdic/pt-br/assuntos/comercio-exterior/estatisticas/base-de-dados-bruta),
Brazil's Ministry of Development, Industry, Trade and Services (MDIC). Public, open data,
updated monthly, no authentication required.

## License

[MIT](LICENSE)

---

**Status**: v0.1, active development. The pipeline is deployed and running on schedule;
the Looker Studio report is still being refined (styling, additional metrics). Expect
breaking changes to the dashboard layout before a first stable release.
