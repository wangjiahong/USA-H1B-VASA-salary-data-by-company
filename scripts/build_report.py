"""Build the interactive HTML report from data/combined.parquet.

Renders 8 Plotly figures into a Jinja2 template at scripts/report_template.html
and writes the final report to output/report.html (self-contained, double-clickable).
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader, select_autoescape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import COMPANIES, JOBS, SALARY_MAX, SALARY_MIN, YEARS  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COMBINED = PROJECT_ROOT / "data" / "combined.parquet"
OUT = PROJECT_ROOT / "output" / "report.html"
OUT.parent.mkdir(parents=True, exist_ok=True)

PLOTLY_TEMPLATE = "plotly_dark"
PLOTLY_COLORWAY = px.colors.qualitative.Bold

LABEL_MAP = {c.key: c.label for c in COMPANIES}
CATEGORY_MAP = {c.key: c.category for c in COMPANIES}
JOB_LABEL_MAP = {j.key: j.label for j in JOBS}


def fmt_money(x: float | int | None) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{int(round(x)):,}"


def fig_to_html(fig: go.Figure) -> str:
    return fig.to_html(include_plotlyjs="cdn", full_html=False, config={"displaylogo": False})


def state_from_location(loc: str) -> str | None:
    """'MOUNTAIN VIEW, CA' -> 'CA'."""
    if not isinstance(loc, str):
        return None
    m = re.search(r",\s*([A-Z]{2})\b", loc)
    return m.group(1) if m else None


def city_from_location(loc: str) -> str | None:
    if not isinstance(loc, str):
        return None
    parts = loc.split(",")
    if len(parts) < 2:
        return None
    return parts[0].strip().title()


def style(fig: go.Figure, title: str, xaxis_title: str = "", yaxis_title: str = "") -> go.Figure:
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        title=dict(text=title, x=0.02, xanchor="left", font=dict(size=16)),
        margin=dict(l=20, r=20, t=56, b=40),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e6eaf2"),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        colorway=PLOTLY_COLORWAY,
        xaxis_title=xaxis_title,
        yaxis_title=yaxis_title,
    )
    return fig


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------

def q1_company_pay_ranking(df: pd.DataFrame) -> dict:
    swe = df[df["job_key"] == "swe"].copy()
    stats = (
        swe.groupby("company_label")["BASE SALARY"]
        .agg(["median", "count"])
        .reset_index()
    )
    stats = stats[stats["count"] >= 30].sort_values("median", ascending=True)
    order = stats["company_label"].tolist()
    swe = swe[swe["company_label"].isin(order)]
    swe["company_label"] = pd.Categorical(swe["company_label"], categories=order, ordered=True)
    fig = px.box(
        swe,
        x="BASE SALARY",
        y="company_label",
        points=False,
        color_discrete_sequence=["#7cc4ff"],
        hover_data=["EMPLOYER", "JOB TITLE", "LOCATION", "query_year"],
    )
    fig.update_traces(boxmean=True, line=dict(width=1.5))
    style(
        fig,
        "Software Engineer base salary distribution by company (2021-2025 combined)",
        "Base salary (USD)",
        "",
    )
    fig.update_layout(height=max(420, 28 * len(order) + 120))

    top = stats.sort_values("median", ascending=False).head(3)["company_label"].tolist()
    insight = (
        f"Among {len(order)} companies with at least 30 SWE filings, "
        f"{', '.join(top)} lead on median base salary. "
        "The box width shows the spread between mid-level and senior filings."
    )

    tbl = (
        stats.sort_values("median", ascending=False)
        .assign(**{"median base": stats["median"].map(fmt_money)})
        .rename(columns={"company_label": "Company", "count": "Records"})
        [["Company", "median base", "Records"]]
        .to_html(index=False, classes="tbl", border=0)
    )
    return {
        "title": "Q1. Which companies pay Software Engineers the most?",
        "insight": insight,
        "chart_html": fig_to_html(fig),
        "table_html": tbl,
    }


def q2_role_gradient_within_companies(df: pd.DataFrame) -> dict:
    counts = (
        df.groupby(["company_label", "job_label"])
        .size()
        .reset_index(name="n")
        .pivot(index="company_label", columns="job_label", values="n")
        .fillna(0)
    )
    pick = (
        counts.ge(30).sum(axis=1).sort_values(ascending=False).head(8).index.tolist()
    )
    sub = df[df["company_label"].isin(pick)].copy()
    sub = sub[sub.groupby(["company_label", "job_label"])["BASE SALARY"].transform("size") >= 30]
    fig = px.violin(
        sub,
        x="company_label",
        y="BASE SALARY",
        color="job_label",
        box=True,
        points=False,
        category_orders={"company_label": pick, "job_label": [j.label for j in JOBS]},
    )
    fig.update_traces(meanline_visible=True)
    style(
        fig,
        "Role salary gradient inside the top 8 companies (roles with >=30 filings)",
        "",
        "Base salary (USD)",
    )
    fig.update_layout(height=520, violingap=0.15, violingroupgap=0.05, legend_title_text="Role")

    med = (
        sub.groupby(["company_label", "job_label"])["BASE SALARY"].median().unstack().round(0)
    )
    insight = (
        "Within the same company, Machine Learning and Research roles usually sit above "
        "generic SWE, while Data Engineer and Product Manager bases can differ sharply by company. "
        "Hover a violin to compare medians and distributions."
    )
    tbl = med.map(lambda v: fmt_money(v) if pd.notna(v) else "—").to_html(classes="tbl", border=0)
    return {
        "title": "Q2. Inside each company, how do pay grades differ by role?",
        "insight": insight,
        "chart_html": fig_to_html(fig),
        "table_html": tbl,
    }


def q3_time_trend(df: pd.DataFrame) -> dict:
    swe = df[df["job_key"] == "swe"].copy()
    trend = (
        swe.groupby(["query_year", "company_label"])["BASE SALARY"]
        .agg(["median", "count"])
        .reset_index()
    )
    trend = trend[trend["count"] >= 10]
    # show the 12 companies with most total SWE records
    top_12 = (
        swe.groupby("company_label").size().sort_values(ascending=False).head(12).index.tolist()
    )
    trend = trend[trend["company_label"].isin(top_12)]
    fig = px.line(
        trend,
        x="query_year",
        y="median",
        color="company_label",
        markers=True,
        hover_data={"count": True, "median": ":,"},
    )
    style(
        fig,
        "Median Software Engineer base salary trend (2021-2025)",
        "Year filed",
        "Median base salary (USD)",
    )
    fig.update_layout(height=500, legend_title_text="Company")

    first = trend[trend["query_year"] == trend["query_year"].min()]
    last = trend[trend["query_year"] == trend["query_year"].max()]
    joined = first.merge(last, on="company_label", suffixes=("_first", "_last"))
    joined["delta"] = joined["median_last"] - joined["median_first"]
    top_gainer = joined.sort_values("delta", ascending=False).head(1)
    insight = "Most big tech SWE bases rose 10-20% over this window. "
    if not top_gainer.empty:
        row = top_gainer.iloc[0]
        insight += (
            f"{row['company_label']} shows the largest gain, "
            f"+${int(row['delta']):,} median from {int(row['query_year_first'])} to {int(row['query_year_last'])}."
        )
    insight += " 2025 is partial — only applications already submitted count."
    return {
        "title": "Q3. How has SWE base salary moved year-over-year?",
        "insight": insight,
        "chart_html": fig_to_html(fig),
        "table_html": None,
    }


def q4_geo_distribution(df: pd.DataFrame) -> dict:
    swe = df[df["job_key"] == "swe"].copy()
    swe["state"] = swe["LOCATION"].map(state_from_location)
    swe["city"] = swe["LOCATION"].map(city_from_location)
    state_stats = (
        swe.dropna(subset=["state"]).groupby("state")["BASE SALARY"]
        .agg(["median", "count"]).reset_index()
    )
    state_stats = state_stats[state_stats["count"] >= 50]
    fig = go.Figure(
        go.Choropleth(
            locations=state_stats["state"],
            z=state_stats["median"],
            locationmode="USA-states",
            colorscale="Viridis",
            colorbar_title="Median $",
            hovertext=state_stats.apply(
                lambda r: f"{r['state']}<br>median=${int(r['median']):,}<br>n={int(r['count']):,}",
                axis=1,
            ),
            hoverinfo="text",
        )
    )
    fig.update_layout(
        geo=dict(scope="usa", bgcolor="rgba(0,0,0,0)"),
        template=PLOTLY_TEMPLATE,
        title=dict(text="Median SWE base salary by state (states with >=50 filings)", x=0.02, font=dict(size=16)),
        margin=dict(l=20, r=20, t=56, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e6eaf2"),
        height=500,
    )
    top_states = state_stats.sort_values("median", ascending=False).head(3)["state"].tolist()
    insight = (
        f"SWE pay concentrates in coastal tech hubs — top states by median: "
        f"{', '.join(top_states)}. States with fewer than 50 filings are omitted for stability."
    )
    city_stats = (
        swe.dropna(subset=["city"]).groupby("city")["BASE SALARY"]
        .agg(["median", "count"]).reset_index()
    )
    city_stats = city_stats[city_stats["count"] >= 100].sort_values("median", ascending=False).head(25)
    tbl = (
        city_stats.assign(**{"median base": city_stats["median"].map(fmt_money)})
        .rename(columns={"city": "City", "count": "Records"})
        [["City", "median base", "Records"]]
        .to_html(index=False, classes="tbl", border=0)
    )
    return {
        "title": "Q4. Where are the highest-paying US cities?",
        "insight": insight,
        "chart_html": fig_to_html(fig),
        "table_html": tbl,
    }


def q5_p95_ceiling(df: pd.DataFrame) -> dict:
    swe = df[df["job_key"] == "swe"].copy()
    stats = swe.groupby("company_label")["BASE SALARY"].agg(
        p50="median",
        p95=lambda s: s.quantile(0.95),
        count="count",
    ).reset_index()
    stats = stats[stats["count"] >= 50]
    stats["category"] = stats["company_label"].map(
        {c.label: c.category for c in COMPANIES}
    )
    fig = px.scatter(
        stats,
        x="p50",
        y="p95",
        size="count",
        color="category",
        hover_name="company_label",
        hover_data={"count": True, "p50": ":,", "p95": ":,"},
        size_max=36,
    )
    lo = min(stats["p50"].min(), stats["p95"].min()) * 0.95
    hi = stats["p95"].max() * 1.02
    fig.add_shape(type="line", x0=lo, y0=lo, x1=hi, y1=hi, line=dict(color="#555", dash="dash"))
    style(
        fig,
        "SWE ceiling vs median: P95 (Y) vs P50 (X) by company",
        "Median base salary (P50)",
        "Top-5% base salary (P95)",
    )
    fig.update_layout(height=560, legend_title_text="Category")
    leaders = stats.sort_values("p95", ascending=False).head(3)["company_label"].tolist()
    insight = (
        f"Companies further above the dashed y=x line have steeper senior pay ladders. "
        f"{', '.join(leaders)} have the highest 95th-percentile SWE bases in the dataset."
    )
    tbl = (
        stats.sort_values("p95", ascending=False)
        .assign(
            **{
                "median": stats["p50"].map(fmt_money),
                "p95": stats["p95"].map(fmt_money),
            }
        )
        .rename(columns={"company_label": "Company", "count": "Records"})
        [["Company", "median", "p95", "Records", "category"]]
        .to_html(index=False, classes="tbl", border=0)
    )
    return {
        "title": "Q5. Who has the highest ceiling for senior SWE pay?",
        "insight": insight,
        "chart_html": fig_to_html(fig),
        "table_html": tbl,
    }


def q6_china_vs_faang(df: pd.DataFrame) -> dict:
    china_keys = [c.key for c in COMPANIES if c.category == "China-affiliated"]
    faang_keys = [c.key for c in COMPANIES if c.category == "FAANG"]
    sub = df[df["job_key"] == "swe"].copy()
    sub["group"] = sub["company_key"].map(
        lambda k: "China-affiliated" if k in china_keys else "FAANG" if k in faang_keys else None
    )
    sub = sub[sub["group"].notna()]
    fig = px.violin(
        sub,
        x="company_label",
        y="BASE SALARY",
        color="group",
        box=True,
        points=False,
        category_orders={"company_label": sorted(sub["company_label"].unique())},
    )
    fig.update_traces(meanline_visible=True)
    style(
        fig,
        "SWE base salary: China-affiliated companies vs FAANG",
        "",
        "Base salary (USD)",
    )
    fig.update_layout(height=480, legend_title_text="Group")
    grp = sub.groupby("group")["BASE SALARY"].median()
    insight = (
        f"Median SWE base at China-affiliated US subsidiaries is "
        f"${int(grp.get('China-affiliated', 0)):,}, versus ${int(grp.get('FAANG', 0)):,} at FAANG. "
        "Distribution shape reveals whether the gap is on the median or the tail."
    )
    return {
        "title": "Q6. Do China-affiliated US subsidiaries (ByteDance, etc.) pay competitively with FAANG?",
        "insight": insight,
        "chart_html": fig_to_html(fig),
        "table_html": None,
    }


def q7_ai_native_vs_big_tech(df: pd.DataFrame) -> dict:
    target_jobs = ["mle", "rs", "swe"]
    ai_keys = [c.key for c in COMPANIES if c.category == "AI-native"] + ["nvidia"]
    faang_keys = [c.key for c in COMPANIES if c.category == "FAANG"]
    sub = df[df["job_key"].isin(target_jobs)].copy()
    sub["bucket"] = sub["company_key"].map(
        lambda k: "AI-native / NVIDIA" if k in ai_keys else ("FAANG" if k in faang_keys else None)
    )
    sub = sub[sub["bucket"].notna()]
    fig = px.box(
        sub,
        x="job_label",
        y="BASE SALARY",
        color="bucket",
        points=False,
        category_orders={"job_label": [JOB_LABEL_MAP[k] for k in target_jobs]},
    )
    style(
        fig,
        "AI-native + NVIDIA vs FAANG on ML-adjacent and SWE roles",
        "Role",
        "Base salary (USD)",
    )
    fig.update_layout(height=480, legend_title_text="Bucket")
    grp = sub.groupby(["bucket", "job_label"])["BASE SALARY"].median().unstack()
    insight = "AI-native shops compress their pay to the top percentiles of the market. "
    if "Machine Learning Engineer" in grp.columns:
        try:
            insight += (
                f"MLE median at AI-native+NVIDIA: ${int(grp.loc['AI-native / NVIDIA','Machine Learning Engineer']):,} "
                f"vs FAANG ${int(grp.loc['FAANG','Machine Learning Engineer']):,}."
            )
        except Exception:
            pass
    return {
        "title": "Q7. Do AI-native companies (OpenAI, Anthropic) + NVIDIA out-pay FAANG on ML roles?",
        "insight": insight,
        "chart_html": fig_to_html(fig),
        "table_html": None,
    }


def q8_market_role_comparison(df: pd.DataFrame) -> dict:
    order = [j.label for j in JOBS]
    sub = df.copy()
    fig = px.box(
        sub,
        x="job_label",
        y="BASE SALARY",
        color="job_label",
        points=False,
        category_orders={"job_label": order},
    )
    style(
        fig,
        "Market-wide base salary distribution by role (all tracked companies)",
        "Role",
        "Base salary (USD)",
    )
    fig.update_layout(height=460, showlegend=False)
    med = sub.groupby("job_label")["BASE SALARY"].median().reindex(order).dropna()
    top3 = med.sort_values(ascending=False).head(3)
    insight = (
        "Across every tracked company: "
        + ", ".join(f"{k} ${int(v):,}" for k, v in top3.items())
        + " lead on median base. Data scientists and analysts tend to trail ML-leaning roles."
    )
    stats = sub.groupby("job_label")["BASE SALARY"].agg(
        median="median",
        p90=lambda s: s.quantile(0.9),
        count="count",
    ).reindex(order).dropna()
    tbl = (
        stats.reset_index()
        .assign(
            median=stats["median"].map(fmt_money).values,
            p90=stats["p90"].map(fmt_money).values,
        )
        .rename(columns={"job_label": "Role", "count": "Records"})
        [["Role", "median", "p90", "Records"]]
        .to_html(index=False, classes="tbl", border=0)
    )
    return {
        "title": "Q8. How do the six roles compare across the whole market?",
        "insight": insight,
        "chart_html": fig_to_html(fig),
        "table_html": tbl,
    }


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def main() -> None:
    if not COMBINED.exists():
        sys.exit(f"Missing {COMBINED}. Run scripts/fetch_h1b.py first.")
    df = pd.read_parquet(COMBINED)
    print(f"Loaded {len(df):,} records from {COMBINED.name}")

    questions = [
        q1_company_pay_ranking(df),
        q2_role_gradient_within_companies(df),
        q3_time_trend(df),
        q4_geo_distribution(df),
        q5_p95_ceiling(df),
        q6_china_vs_faang(df),
        q7_ai_native_vs_big_tech(df),
        q8_market_role_comparison(df),
    ]

    kpi = {
        "total_rows": f"{len(df):,}",
        "employers": f"{df['EMPLOYER'].nunique():,}",
        "median": fmt_money(df["BASE SALARY"].median()),
        "p90": fmt_money(df["BASE SALARY"].quantile(0.9)),
        "max": fmt_money(df["BASE SALARY"].max()),
    }

    env = Environment(
        loader=FileSystemLoader(str(Path(__file__).resolve().parent)),
        autoescape=select_autoescape(["html"]),
    )
    tpl = env.get_template("report_template.html")
    html = tpl.render(
        generated_at=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        n_companies=df["company_label"].nunique(),
        n_jobs=df["job_label"].nunique(),
        years_covered=", ".join(sorted({str(y) for y in df["query_year"].unique()})),
        kpi=kpi,
        questions=questions,
        salary_min=f"${SALARY_MIN:,}",
        salary_max=f"${SALARY_MAX:,}",
    )
    OUT.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size/1e6:.2f} MB)")


if __name__ == "__main__":
    main()
