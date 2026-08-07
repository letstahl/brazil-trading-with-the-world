"""Monthly ingestion job: pulls the current year's Comex Stat export/import
files, plus the reference (dimension) tables, from MDIC's open-data bucket
and reloads all of it into BigQuery.

Deployed as an HTTP-triggered Cloud Function, invoked on a schedule by Cloud
Scheduler (see ../SETUP.md). The dimension tables barely change month to
month, but re-downloading four small CSVs is cheap, so they're refreshed on
every run too rather than requiring a separate manual step.
"""

import datetime
import decimal
import io
import os
import warnings

import functions_framework
import pandas as pd
import requests
import urllib3
from google.cloud import bigquery

# balanca.economia.gov.br serves an incomplete certificate chain (missing
# intermediate CA): confirmed independently against two different HTTP
# clients, so this isn't a local trust-store issue. Browsers paper over it by
# fetching the missing intermediate automatically; Python's ssl module does
# not. The data itself is public, non-sensitive trade statistics, so
# disabling verification for just this one domain is an acceptable
# trade-off rather than failing every run.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

PROJECT_ID = os.environ.get("GCP_PROJECT", "your-project-id")
DATASET = os.environ.get("BQ_DATASET", "trade_data")
TABLE = f"{PROJECT_ID}.{DATASET}.f_trading"

EXP_URL_TEMPLATE = "https://balanca.economia.gov.br/balanca/bd/comexstat-bd/ncm/EXP_{year}.csv"
IMP_URL_TEMPLATE = "https://balanca.economia.gov.br/balanca/bd/comexstat-bd/ncm/IMP_{year}.csv"

AUX_BASE_URL = "https://balanca.economia.gov.br/balanca/bd/tabelas"

# (source file, dimension table, columns to keep, rename map)
DIMENSION_TABLES = [
    (
        "PAIS.csv",
        "d_country",
        ["CO_PAIS", "NO_PAIS", "NO_PAIS_ING"],
        {"CO_PAIS": "co_pais", "NO_PAIS": "no_pais", "NO_PAIS_ING": "no_pais_ing"},
    ),
    (
        "UF.csv",
        "d_state",
        ["SG_UF", "NO_UF", "NO_REGIAO"],
        {"SG_UF": "sg_uf", "NO_UF": "no_uf", "NO_REGIAO": "no_regiao"},
    ),
    (
        "NCM.csv",
        "d_ncm",
        ["CO_NCM", "CO_SH6", "NO_NCM_POR", "NO_NCM_ING"],
        {
            "CO_NCM": "co_ncm",
            "CO_SH6": "co_sh6",
            "NO_NCM_POR": "no_ncm_por",
            "NO_NCM_ING": "no_ncm_ing",
        },
    ),
    (
        "NCM_SH.csv",
        "d_sh",
        [
            "CO_SH6", "NO_SH6_POR", "NO_SH6_ING",
            "CO_SH4", "NO_SH4_POR", "NO_SH4_ING",
            "CO_SH2", "NO_SH2_POR", "NO_SH2_ING",
        ],
        {
            "CO_SH6": "co_sh6", "NO_SH6_POR": "no_sh6_por", "NO_SH6_ING": "no_sh6_ing",
            "CO_SH4": "co_sh4", "NO_SH4_POR": "no_sh4_por", "NO_SH4_ING": "no_sh4_ing",
            "CO_SH2": "co_sh2", "NO_SH2_POR": "no_sh2_por", "NO_SH2_ING": "no_sh2_ing",
        },
    ),
]


def _download_csv(
    url: str, encoding: str = "utf-8", usecols: list[str] | None = None
) -> pd.DataFrame:
    response = requests.get(url, timeout=120, verify=False)
    response.raise_for_status()
    return pd.read_csv(
        io.BytesIO(response.content), sep=";", encoding=encoding, usecols=usecols
    )


# The raw yearly EXP/IMP files carry ~15 columns (transport mode, customs
# unit, net weight, statistical quantity, etc.) that this pipeline never
# uses. Reading only these 5 up front, instead of the full file, is what
# keeps a full year's worth of NCM-level rows from blowing past a
# reasonably-sized Cloud Run instance's memory during the groupby.
FACT_COLUMNS = ["CO_ANO", "CO_NCM", "SG_UF_NCM", "CO_PAIS", "VL_FOB"]


def refresh_dimensions(client: bigquery.Client) -> dict:
    """Reloads the four reference tables from MDIC's per-file CSV endpoints.

    These are small, slow-changing lookup tables (countries, states, NCM
    product codes, and the NCM->SH product hierarchy); a full overwrite each
    run is simpler and safer than trying to diff them.
    """
    counts = {}
    for filename, table_name, columns, rename_map in DIMENSION_TABLES:
        df = _download_csv(f"{AUX_BASE_URL}/{filename}", encoding="latin1")
        df = df[columns].rename(columns=rename_map)

        if table_name == "d_country":
            # MDIC lists the Netherlands under two different Portuguese names
            # across years ("Países Baixos (Holanda)" vs "Holanda"); align on
            # one so joins against this table don't silently split in two.
            df.loc[df["no_pais"] == "Países Baixos (Holanda)", "no_pais"] = "Holanda"

        table_id = f"{PROJECT_ID}.{DATASET}.{table_name}"
        job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
        client.load_table_from_dataframe(df, table_id, job_config=job_config).result()
        counts[table_name] = len(df)
    return counts


def _aggregate(df: pd.DataFrame, value_col: str, out_col: str) -> pd.DataFrame:
    grouped = (
        df.groupby(["CO_ANO", "CO_NCM", "SG_UF_NCM", "CO_PAIS"])[value_col]
        .sum()
        .reset_index()
        .rename(columns={value_col: out_col, "CO_PAIS": "COD_PAIS"})
    )
    return grouped


def build_fact_table(year: int) -> pd.DataFrame:
    exports = _download_csv(EXP_URL_TEMPLATE.format(year=year), usecols=FACT_COLUMNS)
    exports_agg = _aggregate(exports, "VL_FOB", "VL_FOB_EXPO")
    del exports  # free the raw rows before loading the (usually larger) import file

    imports = _download_csv(IMP_URL_TEMPLATE.format(year=year), usecols=FACT_COLUMNS)
    imports_agg = _aggregate(imports, "VL_FOB", "VL_FOB_IMPO")
    del imports

    merged = pd.merge(
        exports_agg,
        imports_agg,
        on=["CO_ANO", "CO_NCM", "SG_UF_NCM", "COD_PAIS"],
        how="outer",
    )
    # BigQuery's NUMERIC type is a 16-byte decimal; pyarrow's pandas->arrow
    # path for that type chokes on a plain float64 column ("Got bytestring of
    # length 8 (expected 16)"), so convert to Decimal explicitly rather than
    # relying on the implicit float conversion.
    merged["VL_FOB_EXPO"] = merged["VL_FOB_EXPO"].fillna(0).apply(decimal.Decimal)
    merged["VL_FOB_IMPO"] = merged["VL_FOB_IMPO"].fillna(0).apply(decimal.Decimal)

    merged = merged.rename(
        columns={
            "CO_ANO": "co_ano",
            "CO_NCM": "co_ncm",
            "SG_UF_NCM": "sg_uf_ncm",
            "COD_PAIS": "cod_pais",
            "VL_FOB_EXPO": "vl_fob_expo",
            "VL_FOB_IMPO": "vl_fob_impo",
        }
    )
    return merged


def reload_year(client: bigquery.Client, year: int, df: pd.DataFrame) -> None:
    # Delete whatever is currently loaded for this year, then append the fresh
    # pull. Two steps rather than a single overwrite so a failed load never
    # leaves the table in a half-deleted state for other years.
    client.query(
        f"DELETE FROM `{TABLE}` WHERE co_ano = @year",
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("year", "INT64", year)]
        ),
    ).result()

    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
    client.load_table_from_dataframe(df, TABLE, job_config=job_config).result()


@functions_framework.http
def refresh_trade_data(request):
    year = int(request.args.get("year", datetime.date.today().year))
    skip_dimensions = request.args.get("skip_dimensions", "false").lower() == "true"

    client = bigquery.Client(project=PROJECT_ID)

    dimension_counts = {} if skip_dimensions else refresh_dimensions(client)

    df = build_fact_table(year)
    reload_year(client, year, df)

    return {
        "year": year,
        "fact_rows_loaded": len(df),
        "dimension_rows_loaded": dimension_counts,
        "table": TABLE,
    }
