"""Statistical analysis, risk score, charts and Power BI exports.

Reads the tables built by sql/03_transform.sql from PostgreSQL (DATABASE_URL).
"""
import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import psycopg
import statsmodels.api as sm
from scipy import stats
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.inspection import permutation_importance
from statsmodels.stats.outliers_influence import variance_inflation_factor

ROOT = Path(__file__).resolve().parents[1]
RES, CH, PBI = ROOT / "results", ROOT / "results" / "charts", ROOT / "powerbi" / "data"
for p in (RES, CH, PBI):
    p.mkdir(parents=True, exist_ok=True)

# Theme (same palette as powerbi/opioid_theme.json)
NAVY, TEAL, CORAL, GOLD, SLATE, LIGHT = "#13294B", "#1B998B", "#F46036", "#E9C46A", "#6C757D", "#F7F9FB"
REGION_COLORS = {"South": CORAL, "West": TEAL, "Midwest": GOLD, "Northeast": NAVY}
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": "#C9D1D9", "axes.labelcolor": NAVY,
    "axes.titlecolor": NAVY, "axes.titleweight": "bold", "axes.titlesize": 12, "axes.titlelocation": "left",
    "xtick.color": SLATE, "ytick.color": SLATE, "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": "white", "axes.facecolor": "white", "axes.grid": True, "grid.color": "#EEF1F4",
})

SDOH = ["poverty_pct", "unemployment_pct", "uninsured_pct", "gini_index", "median_hh_income"]
LABEL = {"rx_rate_per_1k": "Prescribing rate", "poverty_pct": "Poverty %", "unemployment_pct": "Unemployment %",
         "uninsured_pct": "Uninsured %", "gini_index": "GINI index", "median_hh_income": "Median income"}


def q(sql: str) -> pd.DataFrame:
    with psycopg.connect(os.environ["DATABASE_URL"]) as con:
        cur = con.execute(sql)
        cols = [c.name for c in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def num(df):
    for c in df.columns:
        if df[c].dtype == object:
            try:
                df[c] = pd.to_numeric(df[c])
            except (ValueError, TypeError):
                pass
    return df


def save(fig, name):
    fig.tight_layout()
    fig.savefig(CH / name, dpi=180)
    plt.close(fig)


def minmax(s):
    return 100 * (s - s.min()) / (s.max() - s.min())


def main():
    master = num(q("SELECT * FROM opioid.state_master ORDER BY state_abbr"))
    drugs = num(q("SELECT * FROM opioid.drug_top"))
    spec = num(q("SELECT * FROM opioid.specialty_top"))
    trend = num(q("SELECT * FROM opioid.drug_trend_us"))
    county = num(q("SELECT * FROM opioid.stg_sdoh_county"))
    source_stats = json.loads((ROOT / "data" / "staging" / "source_stats.json").read_text())

    a = master.dropna(subset=["opioid_death_rate_per_100k", "rx_rate_per_1k"] + SDOH).copy()
    n = len(a)
    y = a["opioid_death_rate_per_100k"]

    # --- Spearman correlations with the death rate
    corr_rows = []
    for v in ["rx_rate_per_1k"] + SDOH:
        r, p = stats.spearmanr(a[v], y)
        corr_rows.append({"variable": v, "label": LABEL[v], "spearman_r": r, "p_value": p})
    corr = pd.DataFrame(corr_rows)

    # --- Model 1: death rate ~ prescribing rate
    m1 = sm.OLS(y, sm.add_constant(a[["rx_rate_per_1k"]])).fit()

    # --- Model 2: standardized predictors (betas comparable)
    X = a[["rx_rate_per_1k"] + SDOH]
    Xz = (X - X.mean()) / X.std(ddof=0)
    yz = (y - y.mean()) / y.std(ddof=0)
    m2 = sm.OLS(yz, sm.add_constant(Xz)).fit()
    vif = {c: variance_inflation_factor(sm.add_constant(Xz).values, i + 1) for i, c in enumerate(Xz.columns)}
    coef = pd.DataFrame({"variable": Xz.columns, "label": [LABEL[c] for c in Xz.columns],
                         "beta": m2.params[Xz.columns].values, "p_value": m2.pvalues[Xz.columns].values,
                         "vif": [vif[c] for c in Xz.columns]})

    # --- Gradient boosting permutation importance (non-linear check)
    gbr = GradientBoostingRegressor(random_state=42, n_estimators=200, max_depth=2, learning_rate=0.05).fit(X, y)
    pi = permutation_importance(gbr, X, y, n_repeats=50, random_state=42)
    coef["gb_importance"] = pi.importances_mean

    # --- Kruskal-Wallis: death rate across income tertiles
    groups = [g["opioid_death_rate_per_100k"].values for _, g in a.groupby("income_tertile")]
    kw = stats.kruskal(*groups)
    tert = a.groupby("income_tertile")["opioid_death_rate_per_100k"].median()

    # --- Risk score: 30% prescribing + 40% death rate + 30% SDOH vulnerability
    vuln = pd.concat([a[c].rank(pct=True) for c in ["poverty_pct", "unemployment_pct", "uninsured_pct", "gini_index"]]
                     + [(-a["median_hh_income"]).rank(pct=True)], axis=1).mean(axis=1)
    a["rx_score"] = minmax(a["rx_rate_per_1k"])
    a["death_score"] = minmax(y)
    a["sdoh_score"] = minmax(vuln)
    a["risk_score"] = 0.3 * a["rx_score"] + 0.4 * a["death_score"] + 0.3 * a["sdoh_score"]
    a["risk_rank"] = a["risk_score"].rank(ascending=False, method="min").astype(int)
    top10 = a.sort_values("risk_score", ascending=False).head(10)

    # --- Trend: change 2019 -> 2020 by drug type (US)
    tw = trend.pivot_table(index="year", columns="indicator", values="deaths")
    change = ((tw.loc[2020] / tw.loc[2019] - 1) * 100).round(1).to_dict() if {2019, 2020} <= set(tw.index) else {}

    # ================= Charts =================
    m_sorted = master.dropna(subset=["rx_rate_per_1k"]).sort_values("rx_rate_per_1k")
    fig, ax = plt.subplots(figsize=(8, 10))
    ax.barh(m_sorted["state_abbr"], m_sorted["rx_rate_per_1k"], color=m_sorted["region"].map(REGION_COLORS))
    ax.set_title("Medicare Part D opioid claims per 1,000 residents, 2020")
    ax.set_xlabel("Opioid claims per 1,000 residents")
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=c) for c in REGION_COLORS.values()],
              labels=REGION_COLORS.keys(), loc="lower right", frameon=False)
    ax.tick_params(axis="y", labelsize=7)
    save(fig, "01_prescribing_rate_by_state.png")

    fig, ax = plt.subplots(figsize=(8, 5.5))
    ax.scatter(a["rx_rate_per_1k"], y, s=a["population"] / 1.5e5 + 15, c=a["region"].map(REGION_COLORS),
               alpha=0.8, edgecolor="white", linewidth=0.6)
    for _, r in a.iterrows():
        ax.annotate(r["state_abbr"], (r["rx_rate_per_1k"], r["opioid_death_rate_per_100k"]), fontsize=7,
                    color=SLATE, xytext=(3, 3), textcoords="offset points")
    xs = np.linspace(a["rx_rate_per_1k"].min(), a["rx_rate_per_1k"].max(), 50)
    ax.plot(xs, m1.params["const"] + m1.params["rx_rate_per_1k"] * xs, color=NAVY, lw=1.5, ls="--")
    ax.set_title(f"Prescribing vs opioid death rate, 2020 (R² = {m1.rsquared:.3f}, p = {m1.pvalues['rx_rate_per_1k']:.2f})")
    ax.set_xlabel("Opioid claims per 1,000 residents")
    ax.set_ylabel("Opioid deaths per 100,000")
    save(fig, "02_prescribing_vs_deaths.png")

    c2 = coef.sort_values("beta")
    fig, ax = plt.subplots(figsize=(7.5, 4))
    cols = [CORAL if p < 0.05 else "#C9D1D9" for p in c2["p_value"]]
    ax.barh(c2["label"], c2["beta"], color=cols)
    for i, (b, p) in enumerate(zip(c2["beta"], c2["p_value"])):
        ax.text(b + (0.02 if b >= 0 else -0.02), i, f"β={b:.2f}, p={p:.3f}", va="center",
                ha="left" if b >= 0 else "right", fontsize=8, color=NAVY)
    ax.axvline(0, color=SLATE, lw=0.8)
    ax.set_title(f"Standardized drivers of opioid death rate (R² = {m2.rsquared:.3f}, n = {n})")
    ax.set_xlabel("Standardized coefficient (coral = p < 0.05)")
    save(fig, "03_regression_drivers.png")

    fig, ax = plt.subplots(figsize=(8, 4.5))
    t = top10.iloc[::-1]
    ax.barh(t["state_name"], 0.3 * t["rx_score"], color=TEAL, label="Prescribing (30%)")
    ax.barh(t["state_name"], 0.4 * t["death_score"], left=0.3 * t["rx_score"], color=CORAL, label="Death rate (40%)")
    ax.barh(t["state_name"], 0.3 * t["sdoh_score"], left=0.3 * t["rx_score"] + 0.4 * t["death_score"], color=GOLD,
            label="SDOH vulnerability (30%)")
    ax.set_title("Top 10 priority states: combined risk score (0 to 100)")
    ax.legend(frameon=False, loc="lower right", fontsize=8)
    save(fig, "04_top10_priority_states.png")

    fig, ax = plt.subplots(figsize=(8, 4.5))
    palette = [CORAL, TEAL, GOLD, NAVY, SLATE, "#8E7DBE"]
    for i, ind in enumerate([c for c in tw.columns if c != "Number of Drug Overdose Deaths"]):
        ax.plot(tw.index, tw[ind], marker="o", ms=3, lw=2, color=palette[i % len(palette)], label=ind.split(" (")[0])
    ax.axvspan(2019.5, 2020.5, color=CORAL, alpha=0.08)
    ax.set_title("U.S. overdose deaths by drug type (12 months ending December)")
    ax.set_ylabel("Deaths")
    ax.legend(frameon=False, fontsize=7)
    save(fig, "05_drug_type_trend.png")

    d15 = drugs.head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(d15["generic_name"].str.slice(0, 40), d15["claims"] / 1e6, color=TEAL)
    ax.set_title("Top 15 opioid drugs by Medicare Part D claims, 2020")
    ax.set_xlabel("Claims (millions)")
    save(fig, "06_top_drugs.png")

    s15 = spec.head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(s15["prescriber_type"], s15["claims"] / 1e6, color=NAVY)
    ax.set_title("Top 15 prescriber specialties by opioid claims, 2020")
    ax.set_xlabel("Claims (millions)")
    save(fig, "07_top_specialties.png")

    fig, axs = plt.subplots(2, 2, figsize=(9, 6))
    for ax, (v, col) in zip(axs.flat, [("poverty_pct", CORAL), ("unemployment_pct", TEAL),
                                         ("uninsured_pct", GOLD), ("gini_index", NAVY)]):
        vals = county[v].dropna()
        ax.hist(vals, bins=40, color=col, alpha=0.9)
        ax.axvline(vals.median(), color=SLATE, ls="--", lw=1)
        ax.set_title(f"{LABEL[v]} (skew {stats.skew(vals):.2f})", fontsize=10)
    fig.suptitle("SDOH distributions across U.S. counties, 2020", color=NAVY, fontweight="bold", x=0.02, ha="left")
    save(fig, "08_sdoh_distributions.png")

    cm = a[["rx_rate_per_1k"] + SDOH + ["opioid_death_rate_per_100k"]].corr(method="spearman")
    labels = [LABEL.get(c, "Death rate") for c in cm.columns]
    fig, ax = plt.subplots(figsize=(7, 6))
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("t", [TEAL, "white", CORAL])
    im = ax.imshow(cm, cmap=cmap, vmin=-1, vmax=1)
    ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
    ax.set_yticks(range(len(labels)), labels)
    ax.grid(False)
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(j, i, f"{cm.iloc[i, j]:.2f}", ha="center", va="center", fontsize=8, color=NAVY)
    fig.colorbar(im, fraction=0.04)
    ax.set_title(f"Spearman correlations ({n} states)")
    save(fig, "09_correlation_matrix.png")

    # ================= Exports for Power BI =================
    master.merge(a[["state_abbr", "rx_score", "death_score", "sdoh_score", "risk_score", "risk_rank"]],
                 on="state_abbr", how="left").to_csv(PBI / "fact_state_metrics.csv", index=False)
    master[["state_abbr", "state_name", "region"]].to_csv(PBI / "dim_state.csv", index=False)
    trend.to_csv(PBI / "fact_drug_trend.csv", index=False)
    drugs.to_csv(PBI / "fact_top_drugs.csv", index=False)
    spec.to_csv(PBI / "fact_specialties.csv", index=False)
    county.to_csv(PBI / "fact_county_sdoh.csv", index=False)
    coef.to_csv(PBI / "model_coefficients.csv", index=False)
    corr.to_csv(PBI / "correlations.csv", index=False)

    # ================= Summary =================
    sig = coef[coef["p_value"] < 0.05].sort_values("beta", key=abs, ascending=False)
    summary = {
        **source_stats,
        "states_total": int(len(master)),
        "states_analyzed": n,
        "states_missing_death_data": sorted(master.loc[master["opioid_deaths"].isna(), "state_abbr"].tolist()),
        "total_opioid_claims": float(master["opioid_claims"].sum()),
        "total_opioid_prescribers": int(spec["prescribers"].sum()),
        "opioid_deaths_analyzed_states": float(a["opioid_deaths"].sum()),
        "model1": {"r2": m1.rsquared, "p": float(m1.pvalues["rx_rate_per_1k"]), "slope": float(m1.params["rx_rate_per_1k"])},
        "model2": {"r2": m2.rsquared, "adj_r2": m2.rsquared_adj, "f_p": float(m2.f_pvalue),
                   "coefficients": coef.to_dict(orient="records")},
        "spearman": corr.to_dict(orient="records"),
        "kruskal_income_tertiles": {"H": kw.statistic, "p": kw.pvalue, "median_death_rate_by_tertile": tert.to_dict()},
        "top_predictor": sig.iloc[0]["label"] if len(sig) else None,
        "top10": top10[["risk_rank", "state_name", "risk_score", "opioid_death_rate_per_100k", "rx_rate_per_1k",
                        "sdoh_score"]].to_dict(orient="records"),
        "change_2019_2020_pct": change,
        "top_drugs": drugs.head(5)[["generic_name", "claims"]].to_dict(orient="records"),
        "top_specialties": spec.head(5)[["prescriber_type", "claims", "prescribers"]].to_dict(orient="records"),
    }
    (RES / "summary.json").write_text(json.dumps(summary, indent=2, default=float))

    lines = ["# Results (generated by src/analysis.py)", "",
             f"- CMS Provider x Drug rows read: {source_stats['cms_rows_total']:,}",
             f"- Total Medicare Part D opioid claims (51 jurisdictions): {summary['total_opioid_claims']/1e6:.1f} M",
             f"- States with CDC opioid death data for 2020: {n} of 51 (missing: {', '.join(summary['states_missing_death_data'])})",
             f"- Opioid deaths in analysed states (12 months to Dec 2020): {summary['opioid_deaths_analyzed_states']:,.0f}",
             f"- Model 1, death rate ~ prescribing rate: R² = {m1.rsquared:.3f}, p = {m1.pvalues['rx_rate_per_1k']:.3f}",
             f"- Model 2, + 5 SDOH variables (standardized): R² = {m2.rsquared:.3f} (adj. {m2.rsquared_adj:.3f}), F-test p = {m2.f_pvalue:.3f}",
             f"- Strongest significant predictor: {summary['top_predictor']}",
             f"- Kruskal-Wallis across income tertiles: H = {kw.statistic:.2f}, p = {kw.pvalue:.3f}", "",
             "## Spearman correlations with opioid death rate", "", corr.round(3).to_markdown(index=False), "",
             "## Model 2 coefficients", "", coef.round(3).to_markdown(index=False), "",
             "## Top 10 priority states", "", top10[["risk_rank", "state_name", "risk_score", "opioid_death_rate_per_100k",
                                                    "rx_rate_per_1k", "sdoh_score"]].round(1).to_markdown(index=False), "",
             "## Change in U.S. deaths 2019 to 2020 (%)", "",
             pd.Series(change, name="change_pct").to_markdown(), ""]
    (RES / "summary.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
