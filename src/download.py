"""Download the public source files into data/raw.

All sources are U.S. federal open data (public domain).
"""
import sys
import urllib.request
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"

SOURCES = {
    # CMS Medicare Part D Prescribers by Provider and Drug, data year 2020 (~25M rows, ~3.7 GB)
    "cms_partd_provider_drug_2020.csv":
        "https://data.cms.gov/sites/default/files/2024-05/75fecc51-c9e8-4904-b570-9da9dc101721/MUP_DPR_RY24_P04_V10_DY20_NPIBN.csv",
    # CMS Medicare Part D Prescribers by Geography and Drug, 2020 (used for the official opioid drug flag)
    "cms_partd_geo_drug_2020.csv":
        "https://data.cms.gov/sites/default/files/2022-07/ca71b7df-4d48-4c2d-aded-2ca22285739c/MUP_DPR_RY22_P04_V10_DY20_Geo.csv",
    # CDC VSRR Provisional Drug Overdose Death Counts (state x month x drug indicator)
    "cdc_vsrr_overdose.csv":
        "https://data.cdc.gov/api/views/xkb8-kh2a/rows.csv?accessType=DOWNLOAD",
    # AHRQ Social Determinants of Health / Community-Level Health database, county 2020
    "ahrq_sdoh_county_2020.xlsx":
        "https://www.ahrq.gov/sites/default/files/wysiwyg/sdoh/clh_2020_county_2_0.xlsx",
}


def download(name: str, url: str) -> None:
    target = RAW / name
    if target.exists() and target.stat().st_size > 0:
        print(f"skip (exists): {name}")
        return
    print(f"downloading {name} ...", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=600) as r, open(target, "wb") as f:
        while chunk := r.read(1 << 22):
            f.write(chunk)
    print(f"  {target.stat().st_size / 1e6:,.1f} MB")


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])
    for name, url in SOURCES.items():
        if not only or name in only:
            download(name, url)
