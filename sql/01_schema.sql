-- Opioid Crisis Intelligence: schema
DROP SCHEMA IF EXISTS opioid CASCADE;
CREATE SCHEMA opioid;
SET search_path TO opioid;

CREATE TABLE dim_state (
    state_abbr  CHAR(2) PRIMARY KEY,
    state_name  TEXT NOT NULL UNIQUE,
    state_fips  CHAR(2) NOT NULL,
    region      TEXT NOT NULL
);

-- CMS Part D, opioid rows only (filtered from ~25M Provider x Drug rows in prepare.py)
CREATE TABLE stg_cms_opioid (
    npi                 BIGINT,
    state               CHAR(2),
    prescriber_type     TEXT,
    brand_name          TEXT,
    generic_name        TEXT,
    total_claims        NUMERIC,
    total_day_supply    NUMERIC,
    total_drug_cost     NUMERIC,
    total_beneficiaries NUMERIC
);

CREATE TABLE stg_cms_all_claims (
    state           CHAR(2) PRIMARY KEY,
    all_drug_claims NUMERIC
);

CREATE TABLE stg_cdc_overdose (
    state       TEXT,
    state_name  TEXT,
    year        INT,
    month       TEXT,
    period      TEXT,
    indicator   TEXT,
    data_value  NUMERIC
);

CREATE TABLE stg_sdoh_county (
    county_fips      TEXT,
    state_fips       TEXT,
    state_name       TEXT,
    county_name      TEXT,
    population       NUMERIC,
    poverty_pct      NUMERIC,
    unemployment_pct NUMERIC,
    uninsured_pct    NUMERIC,
    gini_index       NUMERIC,
    median_hh_income NUMERIC
);
