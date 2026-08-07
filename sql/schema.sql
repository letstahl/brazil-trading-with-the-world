-- Star schema for Brazilian foreign trade data (Comex Stat / MDIC).
-- Run once to create the dataset and tables before the first Cloud Function run.
-- Replace `your_project.trade_data` with your actual project + dataset id.

CREATE SCHEMA IF NOT EXISTS `your_project.trade_data`
OPTIONS (location = 'US');

-- Fact table: one row per (year, NCM product code, exporting/importing state, partner country).
-- Partitioned by year so the Cloud Function can cheaply truncate-and-reload only the
-- current, still-incomplete year on each monthly run, leaving prior years untouched.
CREATE TABLE IF NOT EXISTS `your_project.trade_data.f_trading` (
  co_ano        INT64      NOT NULL,  -- year, used as the partitioning column
  co_ncm        INT64      NOT NULL,  -- NCM product code (8-digit)
  sg_uf_ncm     STRING     NOT NULL,  -- exporting/importing state (2-letter UF)
  cod_pais      INT64      NOT NULL,  -- partner country code
  vl_fob_expo   NUMERIC    DEFAULT 0,  -- export value, FOB, USD
  vl_fob_impo   NUMERIC    DEFAULT 0   -- import value, FOB, USD
)
PARTITION BY RANGE_BUCKET(co_ano, GENERATE_ARRAY(1997, 2100, 1))
CLUSTER BY sg_uf_ncm, cod_pais;

-- Dimension: country.
CREATE TABLE IF NOT EXISTS `your_project.trade_data.d_country` (
  co_pais     INT64   NOT NULL,
  no_pais     STRING,   -- Portuguese name
  no_pais_ing STRING    -- English name
);

-- Dimension: Brazilian state (UF).
CREATE TABLE IF NOT EXISTS `your_project.trade_data.d_state` (
  sg_uf     STRING  NOT NULL,
  no_uf     STRING,
  no_regiao STRING
);

-- Dimension: NCM product code, linked to its SH6 aggregate.
CREATE TABLE IF NOT EXISTS `your_project.trade_data.d_ncm` (
  co_ncm      INT64   NOT NULL,
  co_sh6      INT64,
  no_ncm_por  STRING,
  no_ncm_ing  STRING
);

-- Dimension: SH6 -> SH4 -> SH2 product hierarchy, for rolling NCM up to readable categories.
CREATE TABLE IF NOT EXISTS `your_project.trade_data.d_sh` (
  co_sh6      INT64   NOT NULL,
  no_sh6_por  STRING,
  no_sh6_ing  STRING,
  co_sh4      INT64,
  no_sh4_por  STRING,
  no_sh4_ing  STRING,
  co_sh2      INT64,
  no_sh2_por  STRING,
  no_sh2_ing  STRING
);
