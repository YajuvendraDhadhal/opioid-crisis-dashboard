-- Load staging files (run with psql from the repository root)
SET search_path TO opioid;
\copy dim_state          FROM 'sql/dim_state.csv'                         CSV HEADER
\copy stg_cms_opioid     FROM 'data/staging/cms_opioid_rows.csv'          CSV HEADER
\copy stg_cms_all_claims FROM 'data/staging/cms_all_claims_by_state.csv'  CSV HEADER
\copy stg_cdc_overdose   FROM 'data/staging/cdc_overdose.csv'             CSV HEADER
\copy stg_sdoh_county    FROM 'data/staging/sdoh_county.csv'              CSV HEADER

CREATE INDEX ON stg_cms_opioid (state);
CREATE INDEX ON stg_cdc_overdose (state, year, month, indicator);
ANALYZE;

SELECT 'stg_cms_opioid' AS table_name, COUNT(*) AS rows FROM stg_cms_opioid
UNION ALL SELECT 'stg_cdc_overdose', COUNT(*) FROM stg_cdc_overdose
UNION ALL SELECT 'stg_sdoh_county', COUNT(*) FROM stg_sdoh_county;
