# USA H1B Tech Salary Analysis

An analysis of **BASE SALARY** figures from US H1B visa LCA filings, aggregated from the public dataset at [h1bdata.info](https://h1bdata.info). Produces an interactive single-page HTML report answering 8 questions about tech compensation in the USA.

## What's inside

| Path | Purpose |
| --- | --- |
| `scripts/config.py` | 37 companies × 6 roles × 5 years config + alias mapping |
| `scripts/fetch_h1b.py` | Scrapes h1bdata.info into `data/raw/*.csv` with caching, retries, rate-limiting |
| `scripts/build_report.py` | Builds 8 interactive Plotly figures and renders `output/report.html` |
| `scripts/report_template.html` | Jinja2 dark-themed layout |
| `Explore_data.ipynb` | The original exploratory notebook (kept for reference) |
| `fetchdata.py` | The original one-shot fetch script |

## Questions answered in the report

1. Which companies pay Software Engineers the most?
2. Inside each company, how do pay grades differ by role?
3. How has SWE base salary moved year-over-year (2021-2025)?
4. Where are the highest-paying US cities and states?
5. Who has the highest ceiling for senior SWE pay (P95)?
6. Do China-affiliated US subsidiaries pay competitively with FAANG?
7. Do AI-native companies (OpenAI, Anthropic) + NVIDIA out-pay FAANG on ML roles?
8. How do the six roles compare across the whole market?

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Step 1: fetch ~1200 company-role-year combinations (~6 minutes first run, seconds after)
python scripts/fetch_h1b.py

# Step 2: build the interactive HTML report
python scripts/build_report.py

# Step 3: open it
open output/report.html
```

Re-running `fetch_h1b.py` uses cached CSVs in `data/raw/`. Use `--refresh` to ignore the cache, or `--limit N` for a quick smoke test.

## Scope

- **Companies (37):** FAANG, semiconductors (NVIDIA / Intel / AMD / Qualcomm / Tesla), China-affiliated (ByteDance/TikTok, Alibaba), fintech (Stripe, Block, PayPal, Robinhood, Coinbase), SaaS/enterprise (Salesforce, Adobe, Oracle, Snowflake, Databricks, ServiceNow, Workday, Palantir, Cloudflare), consumer (Uber, Airbnb, Lyft, DoorDash, LinkedIn, Pinterest, Snap, Reddit), AI-native (OpenAI, Anthropic).
- **Roles (6):** Software Engineer, Data Scientist, Data Engineer, Machine Learning Engineer, Product Manager, Research Scientist. Amazon uses "Software Development Engineer" and "Applied Scientist" — handled via aliases in `config.py`.
- **Years:** 2021, 2022, 2023, 2024, 2025 (2025 is partial).
- **Salary band kept:** `$50,000 – $1,200,000` base.

## Caveats

- H1B LCA shows **base salary only** — stock, bonuses, and sign-on are excluded and are often a large fraction of total tech comp.
- Records are de-duplicated across multiple search terms per company (e.g. Meta vs Facebook Inc).
- Some (company, role, year) combinations return zero rows; that's normal and simply means no H1B filings matched.
- 2025 data is still accruing; early-year quantiles can be noisy.
