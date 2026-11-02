# Power BI build guide

Builds the one-page **Opioid Crisis Intelligence** dashboard in Power BI Desktop from the CSV files in `powerbi/data/`. Time: about 60 to 90 minutes.

## 1. Load the data

1. **Home → Get data → Text/CSV** and load each file from `powerbi/data/`:
   `fact_state_metrics.csv`, `dim_state.csv`, `fact_drug_trend.csv`, `fact_top_drugs.csv`, `fact_specialties.csv`, `model_coefficients.csv`, `correlations.csv`
2. In **Power Query**, check the column types: numbers as *Decimal number*, `state_abbr` as *Text*, `year` as *Whole number*. Then **Close & Apply**.
3. **Model view:** create the relationship `dim_state[state_abbr]` 1 → * `fact_state_metrics[state_abbr]` (single direction).
4. Select `dim_state[state_name]` → **Column tools → Data category → State or Province** (needed for the map).

## 2. Theme and measures

1. **View → Themes → Browse for themes** → `powerbi/opioid_theme.json`.
2. **Home → Enter data** → create an empty table called `_Measures`.
3. Create each measure from `powerbi/measures.dax` in `_Measures` (**New measure**, paste one block at a time).
   Format: `Total Opioid Claims (M)` as decimal with 1 place and suffix "M"; `Change 2019 to 2020 %` as percentage.

## 3. Page layout (16:9, 1280 × 720)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Header (navy rectangle): title, subtitle, Region slicer on the right         │
├──────────┬──────────┬──────────┬──────────┬──────────────────────────────────┤
│ KPI 1    │ KPI 2    │ KPI 3    │ KPI 4    │ KPI 5                            │
├──────────┴──────────┴──────────┼──────────┴──────────────────────────────────┤
│ A. Prescribing vs death rate   │ B. Top 10 priority states (stacked bar)      │
│    (scatter)                   │                                              │
├────────────────────┬───────────┴──────────┬───────────────────────────────────┤
│ C. Regression      │ D. Overdose deaths   │ E. Risk map (filled map)          │
│    drivers         │    by drug type      │    + F. Poor vs rich states       │
└────────────────────┴──────────────────────┴───────────────────────────────────┘
```

**Header:** Insert → Shapes → Rectangle, fill `#13294B`, height 70. Text box in white: "Opioid Crisis Intelligence Dashboard", subtitle "Medicare Part D × CDC overdose deaths × AHRQ SDOH, 2020". Slicer `dim_state[region]` (Tile style), right side of the header.

**KPI cards** (Card visual, 5 in a row):

| Card | Field | Label |
|---|---|---|
| 1 | `Total Opioid Claims (M)` | Opioid claims (Medicare Part D) |
| 2 | `Opioid Deaths` | Opioid deaths, states with data |
| 3 | `States Analyzed Label` | States analyzed |
| 4 | `Highest Risk State` | Highest risk state (colour the value `#F46036`) |
| 5 | `Top Predictor` | Strongest predictor |

**A. Scatter chart:** X = `fact_state_metrics[rx_rate_per_1k]` (Don't summarize), Y = `opioid_death_rate_per_100k` (Don't summarize), Values/Details = `state_abbr`, Legend = `dim_state[region]`, Size = `population`. Analytics pane → **Trend line** on. Title: "Prescribing does not explain deaths".

**B. Stacked bar chart:** Y = `state_name`, X = `Risk Prescribing Part`, `Risk Death Part`, `Risk SDOH Part`. Filter pane: `risk_rank` is less than or equal to 10. Sort by the sum, descending. Colours: teal / coral / gold.

**C. Bar chart:** Y = `model_coefficients[label]`, X = `beta` (Sum). Conditional formatting on bar colour: rules on `p_value`, below 0.05 → `#F46036`, otherwise `#D5DCE3`. Tooltip: `p_value`, `vif`.

**D. Line chart:** X = `fact_drug_trend[year]` (Continuous), Y = `Deaths (Trend)`, Legend = `indicator`. Filter: exclude "Number of Drug Overdose Deaths". Add a constant line or shaded band at 2020 (Analytics pane → X-axis constant line = 2020).

**E. Filled map:** Location = `dim_state[state_name]`, Tooltips = `risk_score`, `opioid_death_rate_per_100k`. Fill colours → fx → **Field value** → `Risk Colour`.

**F. Clustered column chart:** X = `fact_state_metrics[income_tertile]` (rename to "Income third: 1 = poorest"), Y = `Opioid Death Rate per 100k`.

## 4. Finish

1. Turn on **View → Gridlines / Snap to grid**, align all visuals, 12 px spacing.
2. Check that the KPI cards change with the Region slicer. Cards 4 and 5 are deliberately fixed, since they use `ALL`.
3. **File → Save as** `powerbi/opioid_dashboard.pbix`.
4. **File → Export → Export to PDF** (save as `powerbi/opioid_dashboard.pdf`) and also take a PNG screenshot (`docs/dashboard.png`).
