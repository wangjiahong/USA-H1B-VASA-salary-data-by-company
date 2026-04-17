"""Fetch H1B salary data from h1bdata.info and cache one CSV per query.

Reuses the exact parsing approach from the original notebook (pandas.read_html
with html5lib) but adds caching, retries, rate-limiting, and concurrency.

Usage:
    python scripts/fetch_h1b.py               # fetch everything defined in config.py
    python scripts/fetch_h1b.py --workers 2   # lower concurrency
    python scripts/fetch_h1b.py --refresh     # ignore cache and re-fetch
"""
from __future__ import annotations

import argparse
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (  # noqa: E402
    BASE_URL,
    COMPANIES,
    JOB_OVERRIDES,
    JOBS,
    SALARY_MAX,
    SALARY_MIN,
    USER_AGENT,
    YEARS,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
COMBINED_PARQUET = PROJECT_ROOT / "data" / "combined.parquet"
COMBINED_CSV = PROJECT_ROOT / "data" / "combined.csv"

RAW_DIR.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})

_slug_re = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    return _slug_re.sub("-", text.lower()).strip("-")


@dataclass(frozen=True)
class FetchTask:
    company_key: str
    company_label: str
    company_category: str
    job_key: str
    job_label: str
    search_term_company: str
    search_term_job: str
    year: str

    @property
    def cache_path(self) -> Path:
        parts = [
            slug(self.company_key),
            slug(self.search_term_company),
            slug(self.job_key),
            slug(self.search_term_job),
            self.year,
        ]
        return RAW_DIR / ("__".join(parts) + ".csv")

    @property
    def url(self) -> str:
        return (
            f"{BASE_URL}"
            f"?em={quote_plus(self.search_term_company)}"
            f"&job={quote_plus(self.search_term_job)}"
            f"&city=&year={self.year}"
        )


def build_tasks() -> list[FetchTask]:
    tasks: list[FetchTask] = []
    for company in COMPANIES:
        for job in JOBS:
            override = JOB_OVERRIDES.get((company.key, job.key))
            job_term = override if override else job.search_term
            for term in company.search_terms:
                for year in YEARS:
                    tasks.append(
                        FetchTask(
                            company_key=company.key,
                            company_label=company.label,
                            company_category=company.category,
                            job_key=job.key,
                            job_label=job.label,
                            search_term_company=term,
                            search_term_job=job_term,
                            year=year,
                        )
                    )
    return tasks


def _parse_html_table(html: str) -> pd.DataFrame:
    """Apply the same cleaning logic as the original notebook."""
    try:
        tables = pd.read_html(StringIO(html), flavor="html5lib")
    except ValueError:
        return pd.DataFrame()
    if not tables:
        return pd.DataFrame()
    df = tables[0]
    if "EMPLOYER" not in df.columns:
        return pd.DataFrame()
    df = df[~df.EMPLOYER.isnull()].reset_index(drop=True)
    df = df[~df.EMPLOYER.astype(str).str.contains("adsbygoogle", na=False)].reset_index(drop=True)
    if df.empty:
        return df
    # BASE SALARY sometimes arrives with commas as strings
    if df["BASE SALARY"].dtype == object:
        df["BASE SALARY"] = (
            df["BASE SALARY"].astype(str).str.replace(",", "", regex=False)
        )
    df["BASE SALARY"] = pd.to_numeric(df["BASE SALARY"], errors="coerce")
    df = df.dropna(subset=["BASE SALARY"]).reset_index(drop=True)
    df["BASE SALARY"] = df["BASE SALARY"].astype(int)
    df = df[(df["BASE SALARY"] >= SALARY_MIN) & (df["BASE SALARY"] <= SALARY_MAX)]
    return df.reset_index(drop=True)


def fetch_one(task: FetchTask, refresh: bool = False, max_retries: int = 3) -> tuple[FetchTask, int, str]:
    """Return (task, rows, status) where status is 'cached' | 'ok' | 'empty' | 'error: ...'"""
    if not refresh and task.cache_path.exists():
        try:
            df = pd.read_csv(task.cache_path)
            return task, len(df), "cached"
        except Exception:
            pass  # re-fetch on corrupt cache

    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(0.3 + random.random() * 0.3)
            resp = SESSION.get(task.url, timeout=25)
            resp.raise_for_status()
            df = _parse_html_table(resp.text)
            # Write even if empty so we don't retry forever
            df.to_csv(task.cache_path, index=False)
            return task, len(df), ("ok" if len(df) else "empty")
        except Exception as exc:
            last_err = exc
            time.sleep(1.5 * attempt)
    return task, 0, f"error: {last_err}"


def combine_cached(tasks: list[FetchTask]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for task in tasks:
        if not task.cache_path.exists():
            continue
        try:
            df = pd.read_csv(task.cache_path)
        except Exception:
            continue
        if df.empty:
            continue
        df = df.copy()
        df["company_key"] = task.company_key
        df["company_label"] = task.company_label
        df["company_category"] = task.company_category
        df["job_key"] = task.job_key
        df["job_label"] = task.job_label
        df["query_year"] = int(task.year)
        df["search_term_company"] = task.search_term_company
        df["search_term_job"] = task.search_term_job
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    # Deduplicate: the same record can show up when a company has multiple search_terms.
    dedup_cols = [
        "EMPLOYER",
        "JOB TITLE",
        "BASE SALARY",
        "LOCATION",
        "SUBMIT DATE",
        "START DATE",
        "company_key",
        "job_key",
        "query_year",
    ]
    existing = [c for c in dedup_cols if c in out.columns]
    out = out.drop_duplicates(subset=existing).reset_index(drop=True)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--refresh", action="store_true", help="ignore cache and refetch")
    parser.add_argument("--limit", type=int, default=None, help="debug: only run first N tasks")
    args = parser.parse_args()

    tasks = build_tasks()
    if args.limit:
        tasks = tasks[: args.limit]
    print(f"Planned {len(tasks)} fetch tasks. Cache dir: {RAW_DIR}")

    ok = cached = empty = errored = 0
    error_list: list[str] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(fetch_one, t, args.refresh) for t in tasks]
        for i, fut in enumerate(as_completed(futures), 1):
            task, rows, status = fut.result()
            tag = status.split(":")[0]
            if tag == "ok":
                ok += 1
            elif tag == "cached":
                cached += 1
            elif tag == "empty":
                empty += 1
            else:
                errored += 1
                error_list.append(f"{task.cache_path.name}: {status}")
            if i % 25 == 0 or i == len(tasks):
                print(
                    f"[{i:>4}/{len(tasks)}] ok={ok} cached={cached} "
                    f"empty={empty} err={errored}  last={task.cache_path.name} "
                    f"rows={rows} {status}"
                )

    print("\n=== Fetch summary ===")
    print(f"ok={ok} cached={cached} empty={empty} err={errored}")
    if error_list:
        print("First 10 errors:")
        for line in error_list[:10]:
            print(" -", line)

    print("\nCombining cached CSVs ...")
    combined = combine_cached(tasks)
    print(f"Combined rows: {len(combined):,}")
    if combined.empty:
        print("No rows. Aborting parquet write.")
        return
    combined.to_parquet(COMBINED_PARQUET, index=False)
    combined.to_csv(COMBINED_CSV, index=False)
    print(f"Wrote {COMBINED_PARQUET} ({COMBINED_PARQUET.stat().st_size/1e6:.1f} MB)")
    print(f"Wrote {COMBINED_CSV} ({COMBINED_CSV.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
