# Opioid Crisis Intelligence Dashboard

**Do U.S. states that prescribe more opioids have more opioid deaths, and which social factors matter more?**
A multi-source analysis of the 2020 Medicare Part D prescribing data (25.2M rows), CDC overdose deaths and AHRQ social determinants of health (SDOH), built so a state health department could decide where to send intervention resources.

By [Yajuvendra Dhadhal](https://www.linkedin.com/in/yajuvendra-dhadhal-2b7a93213/) · M.Sc. International Information Systems, FAU Erlangen-Nürnberg

**Stack:** PostgreSQL (schema, CTEs, NTILE window function, population-weighted aggregation) · Python (pandas, statsmodels, scipy, scikit-learn, matplotlib) · Power BI · GitHub Actions (the whole pipeline runs automatically from the raw public files)

## Key results (2020)

| | |
|---|---|
| Medicare Part D opioid claims | **56.9 M** (from 25,209,729 provider × drug rows) |
| States with CDC opioid death data | **42 of 51** (missing: AL, AR, FL, ID, LA, MN, ND, NE, PA) |
| Opioid deaths in those states | **54,781** (12 months ending Dec 2020) |
| Prescribing rate alone vs death rate | **R² = 0.006, p = 0.61** (no relationship) |
| Prescribing + 5 SDOH variables | **R² = 0.447** (adj. 0.352), F-test p = 0.001 |
| Highest-risk state | **West Virginia** (62.9 opioid deaths per 100,000) |

1. **Prescribing does not explain deaths at state level.** States that prescribe more opioids to Medicare patients do not have higher opioid death rates (Spearman r = 0.02, p = 0.91).
2. **Social factors explain far more.** Unemployment has a significant positive effect (β = 0.41, p = 0.045). The uninsured rate is the strongest predictor (β = −0.50, p = 0.002), but its direction is negative, which is counterintuitive. It most likely reflects geography rather than a protective effect: the states with the most uninsured people (Texas 17.3%, Oklahoma 14.4%, Georgia 13.0%) had low opioid death rates in 2020, a pattern often explained by illicit fentanyl reaching the South-West later than the East.
3. **Top 10 priority states** (score = 30% prescribing + 40% death rate + 30% SDOH vulnerability): West Virginia, Kentucky, Tennessee, South Carolina, Mississippi, North Carolina, District of Columbia, Ohio, New Mexico, Missouri.
4. **2020 changed the drugs behind the crisis.** From 2019 to 2020 U.S. deaths involving synthetic opioids (mainly illicit fentanyl) rose 55%, psychostimulants such as meth 48% and cocaine 22%, while heroin deaths fell 6% and prescription-type opioids rose 13%.

![Prescribing vs deaths](results/charts/02_prescribing_vs_deaths.png)

| Drivers of the death rate | Top 10 priority states |
|---|---|
| ![drivers](results/charts/03_regression_drivers.png) | ![top10](results/charts/04_top10_priority_states.png) |

| Deaths by drug type | Top prescriber specialties |
|---|---|
| ![trend](results/charts/05_drug_type_trend.png) | ![specialties](results/charts/07_top_specialties.png) |

Family Practice (13.0M claims), Internal Medicine (10.0M) and Nurse Practitioners (8.4M) write the most opioid prescriptions. Pain Management has only 2,183 prescribers but about 1,220 claims each, roughly six times the Family Practice average. All numbers come from [`results/summary.md`](results/summary.md).

## Power BI dashboard

![Power BI dashboard](docs/powerbi_dashboard.png)

[`powerbi/opioid_dashboard.pbix`](powerbi/opioid_dashboard.pbix): one page with 5 KPI cards, prescribing vs death rate (scatter), top 10 priority states (stacked risk score), regression drivers, overdose deaths by drug type and death rate by income third.

The data paths in the `.pbix` point to my local folder. To open it on another machine, change the source folder in **Transform data → Data source settings** to your copy of `powerbi/data/`.

Everything needed to rebuild it is in `powerbi/`:

- `data/`: star-schema tables exported by the pipeline (`dim_state`, `fact_state_metrics`, `fact_drug_trend`, `fact_top_drugs`, `fact_specialties`, `model_coefficients`, `correlations`)
- `model.tmdl`: the full semantic model (tables, relationship, 17 DAX measures) as a TMDL script. Paste it into Power BI Desktop's **TMDL view** and click Apply
- `measures.dax`: the same DAX measures as plain text
- `opioid_theme.json`: report theme (navy, teal, coral, gold)
- `BUILD_GUIDE.md`: layout and visual settings

## How it works

```
data.cms.gov ─┐                                  ┌─ state_sdoh (population-weighted)
data.cdc.gov ─┼─ download.py ─ prepare.py ─ PostgreSQL ─┼─ state_rx, state_deaths
ahrq.gov ─────┘   (raw files)  (25M rows →         └─ state_master (4-CTE merge, NTILE)
                               opioid rows)                       │
                                                         analysis.py: Spearman, OLS,
                                                         gradient boosting, risk score,
                                                         charts, Power BI CSVs
```

| Step | File |
|---|---|
| Download the 4 public files | [`src/download.py`](src/download.py) |
| Stream 25.2M CMS rows and keep opioid rows; prepare CDC and AHRQ | [`src/prepare.py`](src/prepare.py) |
| Schema, loading and transformations | [`sql/01_schema.sql`](sql/01_schema.sql), [`sql/02_load.sql`](sql/02_load.sql), [`sql/03_transform.sql`](sql/03_transform.sql) |
| Statistics, risk score, charts and exports | [`src/analysis.py`](src/analysis.py) |
| Automatic run | [`.github/workflows/pipeline.yml`](.github/workflows/pipeline.yml) |

### Data sources (all public, U.S. government)

| Dataset | Source | Used for |
|---|---|---|
| Medicare Part D Prescribers by Provider and Drug, 2020 | CMS | Opioid claims by state, drug and specialty |
| Medicare Part D Prescribers by Geography and Drug, 2020 | CMS | Official opioid drug flag |
| VSRR Provisional Drug Overdose Death Counts | CDC NCHS | Opioid deaths per state (12 months ending Dec 2020), national trend by drug |
| SDOH / Community-Level Health Database, county 2020 | AHRQ | Population, poverty, unemployment, uninsured rate, GINI index, median income |

### Run it yourself

```bash
pip install -r requirements.txt
python src/download.py        # about 3.8 GB
python src/prepare.py
export DATABASE_URL=postgresql://user:password@localhost:5432/opioid
psql "$DATABASE_URL" -f sql/01_schema.sql -f sql/02_load.sql -f sql/03_transform.sql
python src/analysis.py
```

Or run the **Run analysis pipeline** workflow on GitHub Actions, which starts its own PostgreSQL container.

## What went wrong and what I changed

- **The CMS opioid flag is not always consistent.** In the first run, Topiramate, an anti-seizure drug, appeared among the top opioid drugs, because 2 of its 11 rows in the CMS file are flagged as opioid. Now a drug only counts as an opioid if most of its rows are flagged. The same rule also removed Buprenorphine HCl, whose rows are mixed because it is mainly used to treat opioid addiction. Total claims went from 60.0M to 56.9M.
- **The numbers differ from my first version of this project (April 2026),** whose code I no longer have. That version reported R² = 0.043, 41 states, 58.8M claims and 11,680 deaths, and named unemployment the strongest predictor. This rebuild, which anyone can reproduce from the raw files, finds R² = 0.006, 42 states, 56.9M claims, 54,781 deaths, and the uninsured rate as the strongest predictor, with unemployment second. The overall conclusion is the same: prescribing alone does not explain deaths, and social factors do.
- **AHRQ blocked the download** without a browser user agent, and the SDOH file has moved to the new "Community-Level Health Database". Fixed in `download.py`.

## Limitations

- **Ecological data:** state-level patterns do not show individual causation.
- **Medicare covers mostly people over 65,** while most overdose deaths are among 25 to 54 year olds.
- **Illicit fentanyl** drives most deaths since about 2016, which weakens any prescribing-to-death link.
- **9 states lack opioid death data** for 2020 under the CDC indicator used, including Florida and Pennsylvania.
- **Small sample:** 42 states and 6 predictors (7 per predictor). Poverty and income are strongly correlated (VIF of about 7), so their separate effects are not reliable.
- **A single year:** 2020 was the first COVID-19 year.

## Recommendations for a state health department

1. **Prioritise economically distressed states** with high unemployment and high death rates, such as West Virginia, New Mexico and DC, and do not rely on prescribing rates alone to target help.
2. **Keep prescriber education,** but target it at the groups that write the most opioid prescriptions: Family Practice, Internal Medicine and Nurse Practitioners.
3. **Respond to illicit fentanyl and stimulants** with naloxone, fentanyl test strips and drug-checking services, since these drove the 2020 increase.
4. **Close the data gaps:** 9 states have no opioid-specific death data for 2020.
