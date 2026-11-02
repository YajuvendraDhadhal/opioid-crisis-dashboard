-- Build analysis tables: population-weighted SDOH, prescribing, deaths, 4-CTE master merge
SET search_path TO opioid;

-- 1) State-level SDOH: population-weighted averages of county values
DROP TABLE IF EXISTS state_sdoh;
CREATE TABLE state_sdoh AS
SELECT d.state_abbr,
       SUM(c.population)                                                                       AS population,
       SUM(c.poverty_pct * c.population)      / NULLIF(SUM(c.population) FILTER (WHERE c.poverty_pct IS NOT NULL), 0)      AS poverty_pct,
       SUM(c.unemployment_pct * c.population) / NULLIF(SUM(c.population) FILTER (WHERE c.unemployment_pct IS NOT NULL), 0) AS unemployment_pct,
       SUM(c.uninsured_pct * c.population)    / NULLIF(SUM(c.population) FILTER (WHERE c.uninsured_pct IS NOT NULL), 0)    AS uninsured_pct,
       SUM(c.gini_index * c.population)       / NULLIF(SUM(c.population) FILTER (WHERE c.gini_index IS NOT NULL), 0)       AS gini_index,
       SUM(c.median_hh_income * c.population) / NULLIF(SUM(c.population) FILTER (WHERE c.median_hh_income IS NOT NULL), 0) AS median_hh_income,
       COUNT(*)                                                                                AS counties
FROM stg_sdoh_county c
JOIN dim_state d ON d.state_name = c.state_name
GROUP BY d.state_abbr;

-- 2) Opioid prescribing per state (Medicare Part D 2020)
DROP TABLE IF EXISTS state_rx;
CREATE TABLE state_rx AS
SELECT o.state                              AS state_abbr,
       SUM(o.total_claims)                  AS opioid_claims,
       COUNT(DISTINCT o.npi)                AS opioid_prescribers,
       SUM(o.total_drug_cost)               AS opioid_drug_cost,
       MAX(a.all_drug_claims)               AS all_drug_claims
FROM stg_cms_opioid o
LEFT JOIN stg_cms_all_claims a ON a.state = o.state
GROUP BY o.state;

-- 3) Overdose deaths 2020 (CDC VSRR, 12 months ending December 2020, reported counts)
DROP TABLE IF EXISTS state_deaths;
CREATE TABLE state_deaths AS
SELECT d.state_abbr,
       MAX(c.data_value) FILTER (WHERE c.indicator = 'Opioids (T40.0-T40.4,T40.6)')     AS opioid_deaths,
       MAX(c.data_value) FILTER (WHERE c.indicator = 'Number of Drug Overdose Deaths') AS all_overdose_deaths
FROM stg_cdc_overdose c
JOIN dim_state d ON d.state_abbr = c.state
WHERE c.year = 2020 AND c.month = 'December' AND c.period = '12 month-ending'
GROUP BY d.state_abbr;

-- 4) Master table: 4-CTE merge through the dim_state bridge
DROP TABLE IF EXISTS state_master;
CREATE TABLE state_master AS
WITH s AS (SELECT * FROM state_sdoh),
     r AS (SELECT * FROM state_rx),
     k AS (SELECT * FROM state_deaths),
     base AS (
        SELECT d.state_abbr, d.state_name, d.region,
               s.population, r.opioid_claims, r.opioid_prescribers, r.opioid_drug_cost, r.all_drug_claims,
               k.opioid_deaths, k.all_overdose_deaths,
               s.poverty_pct, s.unemployment_pct, s.uninsured_pct, s.gini_index, s.median_hh_income,
               1000.0   * r.opioid_claims / NULLIF(s.population, 0)   AS rx_rate_per_1k,
               100.0    * r.opioid_claims / NULLIF(r.all_drug_claims, 0) AS opioid_share_pct,
               100000.0 * k.opioid_deaths / NULLIF(s.population, 0)   AS opioid_death_rate_per_100k,
               100000.0 * k.all_overdose_deaths / NULLIF(s.population, 0) AS overdose_death_rate_per_100k
        FROM dim_state d
        LEFT JOIN s ON s.state_abbr = d.state_abbr
        LEFT JOIN r ON r.state_abbr = d.state_abbr
        LEFT JOIN k ON k.state_abbr = d.state_abbr
     )
SELECT base.*,
       NTILE(3) OVER (ORDER BY median_hh_income) AS income_tertile   -- 1 = poorest third
FROM base;

-- 5) EDA tables
DROP TABLE IF EXISTS drug_top;
CREATE TABLE drug_top AS
SELECT generic_name, SUM(total_claims) AS claims, COUNT(DISTINCT npi) AS prescribers
FROM stg_cms_opioid GROUP BY generic_name ORDER BY claims DESC;

DROP TABLE IF EXISTS specialty_top;
CREATE TABLE specialty_top AS
SELECT prescriber_type, SUM(total_claims) AS claims, COUNT(DISTINCT npi) AS prescribers,
       SUM(total_claims) / COUNT(DISTINCT npi) AS claims_per_prescriber
FROM stg_cms_opioid GROUP BY prescriber_type ORDER BY claims DESC;

-- 6) National trend by drug type, 12 months ending December of each year
DROP TABLE IF EXISTS drug_trend_us;
CREATE TABLE drug_trend_us AS
SELECT year, indicator, data_value AS deaths
FROM stg_cdc_overdose
WHERE state = 'US' AND month = 'December' AND period = '12 month-ending'
  AND indicator IN ('Opioids (T40.0-T40.4,T40.6)', 'Heroin (T40.1)', 'Natural & semi-synthetic opioids (T40.2)',
                    'Synthetic opioids, excl. methadone (T40.4)', 'Cocaine (T40.5)',
                    'Psychostimulants with abuse potential (T43.6)', 'Number of Drug Overdose Deaths')
ORDER BY indicator, year;

SELECT COUNT(*) AS states, COUNT(opioid_deaths) AS states_with_opioid_deaths, SUM(opioid_claims) AS total_opioid_claims
FROM state_master;
