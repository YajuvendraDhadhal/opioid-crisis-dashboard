"""Prepare staging files for PostgreSQL.

- CMS: stream the 25M-row Provider x Drug file and keep only opioid rows
  (opioid = Opioid_Drug_Flag 'Y' in the CMS Geography x Drug file).
- CDC: rename columns, keep as is.
- AHRQ: read the county sheet and keep the SDOH variables used in the analysis.
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, STAGE = ROOT / "data" / "raw", ROOT / "data" / "staging"
STAGE.mkdir(parents=True, exist_ok=True)

STATES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH "
             "NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())


def opioid_generics() -> set[str]:
    geo = pd.read_csv(RAW / "cms_partd_geo_drug_2020.csv", dtype=str)
    print("geo x drug columns:", geo.columns.tolist())
    flag = geo["Opioid_Drug_Flag"].str.upper().eq("Y")
    names = set(geo.loc[flag, "Gnrc_Name"].str.strip().str.upper())
    print(f"opioid generic names (CMS flag): {len(names)}")
    print("flagged names:", sorted(names))
    print(geo[geo["Gnrc_Name"].str.upper().str.contains("TOPIRAMATE", na=False)]
          [["Prscrbr_Geo_Lvl", "Brnd_Name", "Gnrc_Name", "Opioid_Drug_Flag"]].drop_duplicates().head(20).to_string())
    return names


def prepare_cms(opioids: set[str]) -> dict:
    src = RAW / "cms_partd_provider_drug_2020.csv"
    out = STAGE / "cms_opioid_rows.csv"
    total_rows = 0
    all_claims_by_state = defaultdict(float)
    with open(src, newline="", encoding="utf-8", errors="replace") as f, open(out, "w", newline="") as g:
        r = csv.DictReader(f)
        w = csv.writer(g)
        w.writerow(["npi", "state", "prescriber_type", "brand_name", "generic_name",
                    "total_claims", "total_day_supply", "total_drug_cost", "total_beneficiaries"])
        for row in r:
            total_rows += 1
            st = row["Prscrbr_State_Abrvtn"]
            clms = float(row["Tot_Clms"] or 0)
            if st in STATES:
                all_claims_by_state[st] += clms
            if row["Gnrc_Name"].strip().upper() in opioids and st in STATES:
                w.writerow([row["Prscrbr_NPI"], st, row["Prscrbr_Type"], row["Brnd_Name"], row["Gnrc_Name"],
                            row["Tot_Clms"], row["Tot_Day_Suply"], row["Tot_Drug_Cst"], row["Tot_Benes"]])
            if total_rows % 5_000_000 == 0:
                print(f"  {total_rows:,} rows read", flush=True)
    pd.Series(all_claims_by_state, name="all_drug_claims").rename_axis("state").reset_index() \
        .to_csv(STAGE / "cms_all_claims_by_state.csv", index=False)
    print(f"CMS rows read: {total_rows:,}")
    return {"cms_rows_total": total_rows}


def prepare_cdc() -> dict:
    d = pd.read_csv(RAW / "cdc_vsrr_overdose.csv")
    d = d.rename(columns={"State": "state", "Year": "year", "Month": "month", "Period": "period",
                          "Indicator": "indicator", "Data Value": "data_value",
                          "Predicted Value": "predicted_value", "State Name": "state_name"})
    d["data_value"] = pd.to_numeric(d["data_value"].astype(str).str.replace(",", ""), errors="coerce")
    d[["state", "state_name", "year", "month", "period", "indicator", "data_value"]] \
        .to_csv(STAGE / "cdc_overdose.csv", index=False)
    return {"cdc_rows_total": len(d)}


SDOH_COLS = {
    "COUNTYFIPS": "county_fips", "STATEFIPS": "state_fips", "STATE": "state_name", "COUNTY": "county_name",
    "ACS_TOT_POP_WT": "population", "ACS_PCT_PERSON_INC_BELOW99": "poverty_pct",
    "ACS_PCT_UNEMPLOY": "unemployment_pct", "ACS_PCT_UNINSURED": "uninsured_pct",
    "ACS_GINI_INDEX": "gini_index", "ACS_MEDIAN_HH_INC": "median_hh_income",
}


def prepare_sdoh() -> dict:
    d = pd.read_excel(RAW / "ahrq_sdoh_county_2020.xlsx", sheet_name="Data", dtype={"COUNTYFIPS": str, "STATEFIPS": str})
    missing = [c for c in SDOH_COLS if c not in d.columns]
    if missing:
        cands = [c for c in d.columns if "POV" in c or "BELOW" in c][:30]
        raise SystemExit(f"SDOH columns missing: {missing}. Poverty-like columns: {cands}")
    d = d[list(SDOH_COLS)].rename(columns=SDOH_COLS)
    d.to_csv(STAGE / "sdoh_county.csv", index=False)
    return {"sdoh_counties": len(d)}


if __name__ == "__main__":
    stats = {}
    stats |= prepare_sdoh()
    stats |= prepare_cdc()
    stats |= prepare_cms(opioid_generics())
    (STAGE / "source_stats.json").write_text(json.dumps(stats, indent=2))
    print(stats)
