-- Reporting views for Looker Studio. Run once after schema.sql and after the
-- first Cloud Function run has populated the fact/dimension tables.
-- Replace `your_project.trade_data` with your actual project + dataset id.

-- One flattened, pre-joined row per (year, state, country, SH2 category).
-- Looker Studio reads this directly as a single BigQuery data source, instead
-- of blending four tables at query time on every chart.
--
-- Product names: the raw NCM/SH catalog is official customs nomenclature,
-- long and clause-heavy, not something you'd want on a chart axis. Two fixes:
--   - SH2 (97 stable international chapters): joined against the curated
--     short labels in sh2_labels.sql (run that script once, before this one).
--   - SH6 (5,000+ Brazil-specific codes): hand-curating every one doesn't
--     scale, so this just takes the text before the first comma/semicolon,
--     which is usually where the official description's technical
--     exceptions/qualifiers start (e.g. "Cafe em grao, cru, exceto para
--     semente" -> "Cafe em grao"). Good enough for chart labels, not a
--     substitute for the real description if you need the exact legal text.
CREATE OR REPLACE VIEW `your_project.trade_data.v_trading_enriched` AS
SELECT
  f.co_ano,
  DATE(f.co_ano, 1, 1)     AS dt_ano,       -- synthetic year-start date, so Looker Studio's
                                             -- built-in date-range comparison works on an
                                             -- otherwise integer-only year column
  s.sg_uf,
  CONCAT('BR-', s.sg_uf) AS geo_uf,          -- ISO 3166-2 code (e.g. "BR-SP"), for the Geo
                                              -- Chart's Region field: a bare 2-letter code
                                              -- risks mismatching against non-Brazilian
                                              -- regions in Google's geocoding
  s.no_uf,
  s.no_regiao,
  c.no_pais,
  c.no_pais_ing,
  sh.co_sh2,
  COALESCE(l.no_sh2_curto_por, sh.no_sh2_por) AS no_sh2_por,
  COALESCE(l.no_sh2_curto_ing, sh.no_sh2_ing) AS no_sh2_ing,
  sh.no_sh2_por AS no_sh2_por_oficial,      -- original official name, kept for reference/tooltips
  TRIM(SPLIT(sh.no_sh6_por, ',')[SAFE_OFFSET(0)]) AS no_sh6_por,
  TRIM(SPLIT(sh.no_sh6_ing, ',')[SAFE_OFFSET(0)]) AS no_sh6_ing,
  sh.no_sh6_por AS no_sh6_por_oficial,      -- original official name, kept for reference/tooltips
  f.vl_fob_expo,
  f.vl_fob_impo,
  (f.vl_fob_expo - f.vl_fob_impo) AS vl_saldo
FROM `your_project.trade_data.f_trading` f
LEFT JOIN `your_project.trade_data.d_state`   s  ON f.sg_uf_ncm = s.sg_uf
LEFT JOIN `your_project.trade_data.d_country` c  ON f.cod_pais  = c.co_pais
LEFT JOIN `your_project.trade_data.d_ncm`     n  ON f.co_ncm    = n.co_ncm
LEFT JOIN `your_project.trade_data.d_sh`      sh ON n.co_sh6    = sh.co_sh6
LEFT JOIN `your_project.trade_data.sh2_labels` l ON sh.co_sh2   = l.co_sh2;

-- Herfindahl-Hirschman Index of export-partner concentration, per year.
-- Looker Studio has no native "sum of squared shares" aggregation, so this is
-- computed here instead of as a calculated field in the report.
CREATE OR REPLACE VIEW `your_project.trade_data.v_country_concentration` AS
WITH by_country AS (
  SELECT co_ano, cod_pais, SUM(vl_fob_expo) AS expo
  FROM `your_project.trade_data.f_trading`
  GROUP BY co_ano, cod_pais
),
totals AS (
  SELECT co_ano, SUM(expo) AS total_expo FROM by_country GROUP BY co_ano
)
SELECT
  b.co_ano,
  ROUND(SUM(POW(SAFE_DIVIDE(b.expo, t.total_expo) * 100, 2))) AS hhi
FROM by_country b
JOIN totals t USING (co_ano)
GROUP BY b.co_ano;

-- The single largest export partner for each year, with its share of that
-- year's total exports. Feeds the "Maior parceiro" scorecard on Page 1.
CREATE OR REPLACE VIEW `your_project.trade_data.v_top_partner_by_year` AS
WITH by_country AS (
  SELECT
    f.co_ano,
    c.no_pais,
    SUM(f.vl_fob_expo) AS expo
  FROM `your_project.trade_data.f_trading` f
  LEFT JOIN `your_project.trade_data.d_country` c ON f.cod_pais = c.co_pais
  GROUP BY f.co_ano, c.no_pais
),
totals AS (
  SELECT co_ano, SUM(expo) AS total_expo FROM by_country GROUP BY co_ano
),
ranked AS (
  SELECT
    b.co_ano,
    b.no_pais,
    b.expo,
    SAFE_DIVIDE(b.expo, t.total_expo) AS share,
    ROW_NUMBER() OVER (PARTITION BY b.co_ano ORDER BY b.expo DESC) AS rk
  FROM by_country b
  JOIN totals t USING (co_ano)
)
SELECT co_ano, no_pais, expo, share
FROM ranked
WHERE rk = 1;
